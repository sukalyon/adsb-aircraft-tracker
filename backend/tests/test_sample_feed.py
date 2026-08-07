from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.aircraft import parse_timestamp
from app.services.sample_feed import SampleTelemetryScenario


class SampleTelemetryScenarioTests(unittest.TestCase):
    def test_first_batch_contains_all_mock_aircraft(self) -> None:
        scenario = SampleTelemetryScenario()

        telemetry_batch = scenario.next_batch(parse_timestamp("2026-08-07T12:00:00Z"))

        self.assertEqual(len(telemetry_batch), 5)
        self.assertEqual(
            {telemetry.aircraft_id for telemetry in telemetry_batch},
            {"4ca123", "a8b42f", "71be10", "45aa71", "3c91ef"},
        )

    def test_timeout_aircraft_stops_emitting_after_configured_tick(self) -> None:
        scenario = SampleTelemetryScenario()

        for tick in range(1, 49):
            telemetry_batch = scenario.next_batch(
                parse_timestamp(f"2026-08-07T12:00:{tick:02d}Z")
            )

        self.assertNotIn("a8b42f", {telemetry.aircraft_id for telemetry in telemetry_batch})


if __name__ == "__main__":
    unittest.main()
