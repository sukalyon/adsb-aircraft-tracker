from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingestion.readsb import IngestionError, ReadsbFileIngestionAdapter
from app.models.aircraft import AircraftTelemetry, RawAircraftMessage, parse_timestamp
from app.services.normalization import TelemetryNormalizer


def load_json(relative_path: str) -> dict | list:
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class AircraftModelFixtureTests(unittest.TestCase):
    def test_basic_readsb_fixture_builds_raw_messages(self) -> None:
        snapshot = load_json("samples/fixtures/readsb/basic_snapshot.json")
        captured_at = parse_timestamp(snapshot["captured_at"])

        messages = [
            RawAircraftMessage.from_readsb_payload(
                aircraft,
                captured_at=captured_at,
                source=snapshot["source"],
            )
            for aircraft in snapshot["aircraft"]
        ]

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].aircraft_id, "4ca123")
        self.assertEqual(messages[0].raw_callsign, "THY7AB")
        self.assertEqual(messages[0].raw_altitude_ft, 32000)
        self.assertEqual(messages[1].raw_vertical_rate_fpm, -512)

    def test_edge_case_fixture_identifies_invalid_records(self) -> None:
        snapshot = load_json("samples/fixtures/readsb/edge_cases_snapshot.json")
        captured_at = parse_timestamp(snapshot["captured_at"])

        valid_messages = []
        invalid_records = 0

        for aircraft in snapshot["aircraft"]:
            try:
                valid_messages.append(
                    RawAircraftMessage.from_readsb_payload(
                        aircraft,
                        captured_at=captured_at,
                        source=snapshot["source"],
                    )
                )
            except ValueError:
                invalid_records += 1

        self.assertEqual(len(valid_messages), 2)
        self.assertEqual(invalid_records, 1)
        self.assertEqual(valid_messages[0].aircraft_id, "4ca123")
        self.assertIsNone(valid_messages[0].raw_latitude)
        self.assertEqual(valid_messages[1].raw_altitude_ft, 10400)

    def test_expected_normalized_fixture_matches_model_contract(self) -> None:
        entries = load_json("samples/fixtures/expected/normalized_telemetry_from_basic.json")

        telemetry = [
            AircraftTelemetry(
                aircraft_id=entry["aircraft_id"],
                captured_at=parse_timestamp(entry["captured_at"]),
                source=entry["source"],
                callsign=entry.get("callsign"),
                squawk=entry.get("squawk"),
                category=entry.get("category"),
                latitude=entry.get("latitude"),
                longitude=entry.get("longitude"),
                altitude_ft=entry.get("altitude_ft"),
                ground_speed_kt=entry.get("ground_speed_kt"),
                heading_deg=entry.get("heading_deg"),
                vertical_rate_fpm=entry.get("vertical_rate_fpm"),
            )
            for entry in entries
        ]

        self.assertTrue(telemetry[0].has_position)
        self.assertEqual(telemetry[0].aircraft_id, "4ca123")
        self.assertEqual(telemetry[1].callsign, "PGT2YZ")

    def test_readsb_file_adapter_ingests_basic_snapshot(self) -> None:
        adapter = ReadsbFileIngestionAdapter(
            ROOT / "samples/fixtures/readsb/basic_snapshot.json"
        )

        batch = adapter.ingest()

        self.assertEqual(batch.source, "readsb")
        self.assertEqual(batch.raw_record_count, 2)
        self.assertEqual(batch.dropped_record_count, 0)
        self.assertEqual(len(batch.messages), 2)
        self.assertEqual(batch.messages[0].aircraft_id, "4ca123")

    def test_readsb_file_adapter_counts_dropped_records(self) -> None:
        adapter = ReadsbFileIngestionAdapter(
            ROOT / "samples/fixtures/readsb/edge_cases_snapshot.json"
        )

        batch = adapter.ingest()

        self.assertEqual(batch.raw_record_count, 3)
        self.assertEqual(batch.dropped_record_count, 1)
        self.assertEqual(len(batch.messages), 2)
        self.assertEqual(len(batch.warnings), 1)

    def test_readsb_file_adapter_rejects_invalid_snapshot_shape(self) -> None:
        invalid_path = ROOT / "samples/fixtures/readsb/invalid_snapshot.json"
        invalid_path.write_text('{"source": "readsb", "aircraft": {}}', encoding="utf-8")

        self.addCleanup(invalid_path.unlink)

        adapter = ReadsbFileIngestionAdapter(invalid_path)

        with self.assertRaises(IngestionError):
            adapter.ingest()

    def test_normalizer_matches_expected_fixture_for_basic_snapshot(self) -> None:
        adapter = ReadsbFileIngestionAdapter(
            ROOT / "samples/fixtures/readsb/basic_snapshot.json"
        )
        expected = load_json("samples/fixtures/expected/normalized_telemetry_from_basic.json")

        batch = adapter.ingest()
        normalized = TelemetryNormalizer().normalize_many(batch.messages)

        self.assertEqual(normalized.issues, [])
        self.assertEqual(
            [self._telemetry_to_dict(entry) for entry in normalized.telemetry],
            expected,
        )

    def test_normalizer_sanitizes_invalid_values(self) -> None:
        message = RawAircraftMessage(
            source="readsb",
            decoder_type="readsb",
            captured_at=parse_timestamp("2026-04-13T09:10:00Z"),
            aircraft_id="abc123",
            raw_callsign=" thy123 ",
            raw_squawk=" 4453 ",
            raw_category=" a3 ",
            raw_latitude=91.0,
            raw_longitude=28.9,
            raw_altitude_ft=28000,
            raw_ground_speed_kt=-5.0,
            raw_heading_deg=721.2,
            raw_vertical_rate_fpm=128,
        )

        telemetry, issues = TelemetryNormalizer().normalize_message(message)

        self.assertEqual(telemetry.callsign, "THY123")
        self.assertEqual(telemetry.squawk, "4453")
        self.assertEqual(telemetry.category, "A3")
        self.assertIsNone(telemetry.latitude)
        self.assertIsNone(telemetry.longitude)
        self.assertIsNone(telemetry.ground_speed_kt)
        self.assertAlmostEqual(telemetry.heading_deg or 0.0, 1.2)
        self.assertEqual(len(issues), 2)

    @staticmethod
    def _telemetry_to_dict(entry: AircraftTelemetry) -> dict[str, object | None]:
        return {
            "aircraft_id": entry.aircraft_id,
            "captured_at": entry.captured_at.isoformat().replace("+00:00", "Z"),
            "source": entry.source,
            "callsign": entry.callsign,
            "squawk": entry.squawk,
            "category": entry.category,
            "latitude": entry.latitude,
            "longitude": entry.longitude,
            "altitude_ft": entry.altitude_ft,
            "ground_speed_kt": entry.ground_speed_kt,
            "heading_deg": entry.heading_deg,
            "vertical_rate_fpm": entry.vertical_rate_fpm,
        }


if __name__ == "__main__":
    unittest.main()
