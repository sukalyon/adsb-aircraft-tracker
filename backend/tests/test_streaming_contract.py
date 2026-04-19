from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingestion.readsb import ReadsbFileIngestionAdapter
from app.models.aircraft import AircraftTelemetry, parse_timestamp
from app.services.normalization import TelemetryNormalizer
from app.state.store import AircraftStateStore
from app.streaming.contracts import (
    DeltaAction,
    STREAM_CONTRACT_VERSION,
    build_delta_event,
    build_snapshot_event,
    prepare_delta_changes,
)


class StreamingContractTests(unittest.TestCase):
    def test_snapshot_event_serializes_active_state(self) -> None:
        adapter = ReadsbFileIngestionAdapter(
            ROOT / "samples/fixtures/readsb/basic_snapshot.json"
        )
        raw_batch = adapter.ingest()
        normalized = TelemetryNormalizer().normalize_many(raw_batch.messages)
        store = AircraftStateStore()
        store.apply_many(normalized.telemetry)

        event = build_snapshot_event(
            store.snapshot(),
            sequence=1,
            sent_at=parse_timestamp("2026-04-14T10:00:00Z"),
        )
        payload = event.to_dict()

        self.assertEqual(payload["type"], "snapshot")
        self.assertEqual(payload["version"], STREAM_CONTRACT_VERSION)
        self.assertEqual(payload["sequence"], 1)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["aircraft"][0]["aircraft_id"], "4ca123")

    def test_delta_event_maps_create_update_and_remove_changes(self) -> None:
        store = AircraftStateStore(stale_after=timedelta(seconds=30))

        create_change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T10:00:00Z"),
                source="readsb",
                callsign="THY7AB",
                latitude=41.0,
                longitude=29.0,
                altitude_ft=30000,
                ground_speed_kt=430.0,
                heading_deg=90.0,
            )
        )
        update_change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T10:00:05Z"),
                source="readsb",
                ground_speed_kt=440.0,
                heading_deg=92.0,
            )
        )
        remove_change = store.remove_stale(
            reference_time=parse_timestamp("2026-04-14T10:00:36Z")
        )[0]

        event = build_delta_event(
            [create_change, update_change, remove_change],
            sequence=2,
            sent_at=parse_timestamp("2026-04-14T10:00:36Z"),
        )
        payload = event.to_dict()

        self.assertEqual(payload["type"], "delta")
        self.assertEqual(payload["version"], STREAM_CONTRACT_VERSION)
        self.assertEqual(payload["sequence"], 2)
        self.assertEqual(len(payload["changes"]), 3)
        self.assertEqual(payload["changes"][0]["action"], DeltaAction.UPSERT.value)
        self.assertEqual(payload["changes"][1]["aircraft"]["ground_speed_kt"], 440.0)
        self.assertEqual(payload["changes"][2]["action"], DeltaAction.REMOVE.value)
        self.assertEqual(payload["changes"][2]["reason"], "stale_timeout")

    def test_delta_event_drops_ignored_changes(self) -> None:
        store = AircraftStateStore()
        store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T10:00:00Z"),
                source="readsb",
                latitude=41.0,
                longitude=29.0,
            )
        )
        ignored_change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T09:59:59Z"),
                source="readsb",
                latitude=40.0,
                longitude=28.0,
            )
        )

        event = build_delta_event(
            [ignored_change],
            sequence=3,
            sent_at=parse_timestamp("2026-04-14T10:00:01Z"),
        )
        payload = event.to_dict()

        self.assertEqual(payload["changes"], [])

    def test_delta_preparation_suppresses_non_wire_updates(self) -> None:
        store = AircraftStateStore()
        store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T10:00:00Z"),
                source="readsb",
                callsign="THY7AB",
                latitude=41.0,
                longitude=29.0,
                altitude_ft=30000,
                ground_speed_kt=430.0,
                heading_deg=90.0,
                squawk="1000",
            )
        )
        non_wire_update = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-14T10:00:05Z"),
                source="readsb",
                squawk="2000",
            )
        )

        prepared = prepare_delta_changes([non_wire_update])

        self.assertEqual(prepared.delta_changes, [])
        self.assertEqual(prepared.seen_change_count, 1)
        self.assertEqual(prepared.publishable_change_count, 0)
        self.assertEqual(prepared.suppressed_change_count, 1)


if __name__ == "__main__":
    unittest.main()
