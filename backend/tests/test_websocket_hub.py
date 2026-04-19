from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.aircraft import AircraftTelemetry, parse_timestamp
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


class FakeWebSocket:
    def __init__(self, *, fail_after_messages: int | None = None) -> None:
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None
        self.messages: list[dict] = []
        self.fail_after_messages = fail_after_messages

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail_after_messages is not None and len(self.messages) >= self.fail_after_messages:
            raise RuntimeError("simulated websocket failure")
        self.messages.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = True
        self.close_code = code


class RealtimeWebSocketHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_sends_snapshot_to_new_client(self) -> None:
        store = AircraftStateStore()
        store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T11:00:00Z"),
                source="readsb",
                callsign="THY7AB",
                latitude=41.0,
                longitude=29.0,
                altitude_ft=30000,
                ground_speed_kt=430.0,
                heading_deg=90.0,
            )
        )

        hub = RealtimeWebSocketHub()
        socket = FakeWebSocket()

        client_id = await hub.connect(socket, snapshot_states=store.snapshot())

        self.assertTrue(socket.accepted)
        self.assertEqual(hub.connected_count, 1)
        self.assertIn(client_id, hub.session_ids())
        self.assertEqual(socket.messages[0]["type"], "snapshot")
        self.assertEqual(socket.messages[0]["sequence"], 1)
        self.assertEqual(socket.messages[0]["total"], 1)

    async def test_publish_delta_sends_upserts_after_snapshot(self) -> None:
        store = AircraftStateStore()
        hub = RealtimeWebSocketHub()
        socket = FakeWebSocket()

        await hub.connect(socket, snapshot_states=store.snapshot())
        change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T11:00:00Z"),
                source="readsb",
                callsign="THY7AB",
                latitude=41.0,
                longitude=29.0,
                altitude_ft=30000,
                ground_speed_kt=430.0,
                heading_deg=90.0,
            )
        )

        delivered = await hub.publish_delta([change])

        self.assertEqual(delivered, 1)
        self.assertEqual(len(socket.messages), 2)
        self.assertEqual(socket.messages[1]["type"], "delta")
        self.assertEqual(socket.messages[1]["sequence"], 2)
        self.assertEqual(socket.messages[1]["changes"][0]["action"], "upsert")

    async def test_each_client_has_its_own_sequence_progression(self) -> None:
        store = AircraftStateStore()
        hub = RealtimeWebSocketHub()
        first_socket = FakeWebSocket()
        second_socket = FakeWebSocket()

        await hub.connect(first_socket, snapshot_states=store.snapshot())
        first_change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T11:00:00Z"),
                source="readsb",
                latitude=41.0,
                longitude=29.0,
            )
        )
        await hub.publish_delta([first_change])
        await hub.connect(second_socket, snapshot_states=store.snapshot())

        second_change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T11:00:05Z"),
                source="readsb",
                ground_speed_kt=440.0,
            )
        )
        await hub.publish_delta([second_change])

        self.assertEqual(first_socket.messages[0]["sequence"], 1)
        self.assertEqual(first_socket.messages[1]["sequence"], 2)
        self.assertEqual(first_socket.messages[2]["sequence"], 3)
        self.assertEqual(second_socket.messages[0]["sequence"], 1)
        self.assertEqual(second_socket.messages[1]["sequence"], 2)

    async def test_ignored_changes_do_not_emit_messages(self) -> None:
        store = AircraftStateStore()
        hub = RealtimeWebSocketHub()
        socket = FakeWebSocket()

        await hub.connect(socket, snapshot_states=store.snapshot())
        store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T11:00:00Z"),
                source="readsb",
                latitude=41.0,
                longitude=29.0,
            )
        )
        ignored = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T10:59:59Z"),
                source="readsb",
                latitude=40.0,
                longitude=28.0,
            )
        )

        delivered = await hub.publish_delta([ignored])

        self.assertEqual(delivered, 0)
        self.assertEqual(len(socket.messages), 1)

    async def test_failed_client_is_removed_on_publish_error(self) -> None:
        store = AircraftStateStore()
        hub = RealtimeWebSocketHub()
        healthy_socket = FakeWebSocket()
        broken_socket = FakeWebSocket(fail_after_messages=1)

        await hub.connect(healthy_socket, snapshot_states=store.snapshot())
        await hub.connect(broken_socket, snapshot_states=store.snapshot())

        change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T11:00:00Z"),
                source="readsb",
                latitude=41.0,
                longitude=29.0,
            )
        )

        delivered = await hub.publish_delta([change])

        self.assertEqual(delivered, 1)
        self.assertEqual(hub.connected_count, 1)
        self.assertTrue(broken_socket.closed)
        self.assertEqual(broken_socket.close_code, 1011)
        self.assertFalse(healthy_socket.closed)


if __name__ == "__main__":
    unittest.main()
