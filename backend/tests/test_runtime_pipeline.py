from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.aircraft import AircraftTelemetry, parse_timestamp
from app.runtime import RealtimePipeline
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)

    async def close(self, code: int = 1000) -> None:
        return None


class RealtimePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_processing_batch_updates_state_and_websocket_metrics(self) -> None:
        store = AircraftStateStore()
        hub = RealtimeWebSocketHub()
        pipeline = RealtimePipeline(state_store=store, websocket_hub=hub)
        socket = FakeWebSocket()

        await hub.connect(socket, snapshot_states=store.snapshot())
        result = await pipeline.process_telemetry_batch(
            [
                AircraftTelemetry(
                    aircraft_id="4ca123",
                    captured_at=parse_timestamp("2026-04-19T12:00:00Z"),
                    source="sample",
                    callsign="THY7AB",
                    latitude=41.0,
                    longitude=29.0,
                    altitude_ft=30000,
                    ground_speed_kt=430.0,
                    heading_deg=90.0,
                )
            ]
        )

        metrics = pipeline.metrics_snapshot()

        self.assertEqual(result.telemetry_count, 1)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.publish_result.delivered_client_count, 1)
        self.assertEqual(store.active_count, 1)
        self.assertEqual(metrics.total_batches_processed, 1)
        self.assertEqual(metrics.total_telemetry_messages, 1)
        self.assertEqual(metrics.total_created_changes, 1)
        self.assertEqual(len(socket.messages), 2)

    async def test_stale_cleanup_publishes_remove_change(self) -> None:
        store = AircraftStateStore(stale_after=timedelta(seconds=30))
        hub = RealtimeWebSocketHub()
        pipeline = RealtimePipeline(state_store=store, websocket_hub=hub)
        socket = FakeWebSocket()

        await hub.connect(socket, snapshot_states=store.snapshot())
        await pipeline.process_telemetry_batch(
            [
                AircraftTelemetry(
                    aircraft_id="4ca123",
                    captured_at=parse_timestamp("2026-04-19T12:00:00Z"),
                    source="sample",
                    latitude=41.0,
                    longitude=29.0,
                )
            ]
        )

        result = await pipeline.expire_stale_tracks(
            reference_time=parse_timestamp("2026-04-19T12:00:31Z")
        )

        self.assertEqual(result.removed_count, 1)
        self.assertEqual(result.publish_result.emitted_change_count, 1)
        self.assertEqual(result.publish_result.delivered_client_count, 1)
        self.assertEqual(store.active_count, 0)


if __name__ == "__main__":
    unittest.main()
