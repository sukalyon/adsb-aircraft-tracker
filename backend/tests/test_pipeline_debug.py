from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.pipeline_debug import build_readsb_file_debug_report


class PipelineDebugReportTests(unittest.TestCase):
    def test_debug_report_summarizes_basic_snapshot(self) -> None:
        report = build_readsb_file_debug_report(
            ROOT / "samples/fixtures/readsb/basic_snapshot.json",
            trail_max_points=8,
            stale_after_seconds=60,
        )

        payload = report.to_dict()

        self.assertEqual(payload["source"], "readsb")
        self.assertEqual(payload["raw_record_count"], 2)
        self.assertEqual(payload["dropped_record_count"], 0)
        self.assertEqual(payload["normalization_issue_count"], 0)
        self.assertEqual(payload["active_count"], 2)
        self.assertEqual(payload["created_count"], 2)
        self.assertEqual(payload["ignored_count"], 0)
        self.assertEqual(len(payload["aircraft"]), 2)
        self.assertEqual(payload["aircraft"][0]["trail_points"], 1)


if __name__ == "__main__":
    unittest.main()
