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
from app.state.store import AircraftStateStore, StateChangeType


class AircraftStateStoreTests(unittest.TestCase):
    def test_pipeline_creates_active_states_from_basic_fixture(self) -> None:
        adapter = ReadsbFileIngestionAdapter(
            ROOT / "samples/fixtures/readsb/basic_snapshot.json"
        )
        raw_batch = adapter.ingest()
        normalized = TelemetryNormalizer().normalize_many(raw_batch.messages)
        store = AircraftStateStore(trail_max_points=4)

        changes = store.apply_many(normalized.telemetry)
        snapshot = store.snapshot()

        self.assertEqual(len(changes), 2)
        self.assertTrue(all(change.change_type == StateChangeType.CREATED for change in changes))
        self.assertEqual(store.active_count, 2)
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(len(snapshot[0].trail), 1)

    def test_partial_updates_preserve_previous_position(self) -> None:
        store = AircraftStateStore(trail_max_points=4)

        first = AircraftTelemetry(
            aircraft_id="4ca123",
            captured_at=parse_timestamp("2026-04-13T09:00:00Z"),
            source="readsb",
            callsign="THY7AB",
            latitude=41.0,
            longitude=29.0,
            altitude_ft=30000,
            ground_speed_kt=430.0,
            heading_deg=90.0,
            vertical_rate_fpm=0,
        )
        second = AircraftTelemetry(
            aircraft_id="4ca123",
            captured_at=parse_timestamp("2026-04-13T09:00:05Z"),
            source="readsb",
            ground_speed_kt=440.0,
            heading_deg=92.0,
        )

        store.apply(first)
        change = store.apply(second)
        state = change.state

        self.assertIsNotNone(state)
        self.assertEqual(change.change_type, StateChangeType.UPDATED)
        self.assertEqual(change.changed_fields, ("ground_speed_kt", "heading_deg"))
        self.assertEqual(state.latitude, 41.0)
        self.assertEqual(state.longitude, 29.0)
        self.assertEqual(state.ground_speed_kt, 440.0)
        self.assertEqual(len(state.trail), 1)

    def test_same_live_values_produce_empty_changed_fields(self) -> None:
        store = AircraftStateStore(trail_max_points=4)

        store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:00Z"),
                source="readsb",
                callsign="THY7AB",
                latitude=41.0,
                longitude=29.0,
                altitude_ft=30000,
                ground_speed_kt=430.0,
                heading_deg=90.0,
            )
        )
        change = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:05Z"),
                source="readsb",
                callsign="THY7AB",
                latitude=41.0,
                longitude=29.0,
                altitude_ft=30000,
                ground_speed_kt=430.0,
                heading_deg=90.0,
            )
        )

        self.assertEqual(change.change_type, StateChangeType.UPDATED)
        self.assertEqual(change.changed_fields, ())

    def test_trail_is_bounded_and_out_of_order_updates_are_ignored(self) -> None:
        store = AircraftStateStore(trail_max_points=2)

        updates = [
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:00Z"),
                source="readsb",
                latitude=41.0,
                longitude=29.0,
            ),
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:05Z"),
                source="readsb",
                latitude=41.1,
                longitude=29.1,
            ),
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:10Z"),
                source="readsb",
                latitude=41.2,
                longitude=29.2,
            ),
        ]

        for telemetry in updates:
            store.apply(telemetry)

        ignored = store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:03Z"),
                source="readsb",
                latitude=40.5,
                longitude=28.5,
            )
        )

        state = store.get("4ca123")

        self.assertIsNotNone(state)
        self.assertEqual(ignored.change_type, StateChangeType.IGNORED)
        self.assertEqual(ignored.changed_fields, ())
        self.assertEqual(len(state.trail), 2)
        self.assertEqual(state.trail[0].latitude, 41.1)
        self.assertEqual(state.trail[1].latitude, 41.2)

    def test_remove_stale_tracks(self) -> None:
        store = AircraftStateStore(stale_after=timedelta(seconds=30))

        store.apply(
            AircraftTelemetry(
                aircraft_id="4ca123",
                captured_at=parse_timestamp("2026-04-13T09:00:00Z"),
                source="readsb",
                latitude=41.0,
                longitude=29.0,
            )
        )

        removed = store.remove_stale(
            reference_time=parse_timestamp("2026-04-13T09:00:31Z")
        )

        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].change_type, StateChangeType.REMOVED)
        self.assertEqual(removed[0].changed_fields, ("status",))
        self.assertEqual(store.active_count, 0)


if __name__ == "__main__":
    unittest.main()
