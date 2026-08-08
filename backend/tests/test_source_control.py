from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.runtime.source_control import build_source_definitions_from_env


class SourceControlConfigTests(unittest.TestCase):
    def test_default_configuration_keeps_sample_available_and_live_sources_disabled(self) -> None:
        definitions, initial_source_id = build_source_definitions_from_env({})

        self.assertEqual(initial_source_id, "sample")
        self.assertTrue(definitions["sample"].availability()[0])
        self.assertFalse(definitions["readsb"].availability()[0])
        self.assertFalse(definitions["dump1090"].availability()[0])

    def test_legacy_dump1090_configuration_maps_to_dump1090_source(self) -> None:
        definitions, initial_source_id = build_source_definitions_from_env(
            {
                "ADSB_SOURCE_MODE": "readsb_file",
                "ADSB_SOURCE_NAME": "dump1090",
                "ADSB_DECODER_TYPE": "dump1090",
                "ADSB_READSB_SNAPSHOT_PATH": str(
                    ROOT / "samples" / "fixtures" / "readsb" / "basic_snapshot.json"
                ),
            }
        )

        self.assertEqual(initial_source_id, "dump1090")
        self.assertTrue(definitions["dump1090"].availability()[0])

    def test_explicit_dump1090_url_configuration_enables_live_source(self) -> None:
        definitions, initial_source_id = build_source_definitions_from_env(
            {
                "ADSB_SOURCE_MODE": "dump1090_file",
                "ADSB_DUMP1090_SNAPSHOT_URL": str(
                    (ROOT / "samples" / "fixtures" / "readsb" / "decoder_aircraft_snapshot.json").as_uri()
                ),
            }
        )

        self.assertEqual(initial_source_id, "dump1090")
        self.assertTrue(definitions["dump1090"].availability()[0])


if __name__ == "__main__":
    unittest.main()
