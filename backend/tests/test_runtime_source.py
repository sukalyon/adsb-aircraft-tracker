from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingestion.readsb import ReadsbFileIngestionAdapter
from app.runtime import DecoderFileSourceRuntime, RealtimePipeline
from app.services.normalization import TelemetryNormalizer
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


class DecoderFileSourceRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_once_updates_pipeline_and_metrics(self) -> None:
        runtime = self._build_runtime("samples/fixtures/readsb/basic_snapshot.json")

        processed = await runtime.process_once()
        metrics = runtime.metrics_snapshot()

        self.assertTrue(processed)
        self.assertEqual(runtime.pipeline.state_store.active_count, 2)
        self.assertEqual(metrics.total_batches_ingested, 1)
        self.assertEqual(metrics.total_raw_records, 2)
        self.assertEqual(metrics.total_normalized_telemetry, 2)
        self.assertEqual(metrics.total_ingestion_warnings, 0)
        self.assertEqual(metrics.total_normalization_issues, 0)

    async def test_process_once_skips_duplicate_snapshot_timestamp(self) -> None:
        runtime = self._build_runtime("samples/fixtures/readsb/basic_snapshot.json")

        first_processed = await runtime.process_once()
        second_processed = await runtime.process_once()
        metrics = runtime.metrics_snapshot()

        self.assertTrue(first_processed)
        self.assertFalse(second_processed)
        self.assertEqual(metrics.total_batches_ingested, 1)
        self.assertEqual(metrics.total_batches_skipped, 1)

    @staticmethod
    def _build_runtime(relative_path: str) -> DecoderFileSourceRuntime:
        return DecoderFileSourceRuntime(
            pipeline=RealtimePipeline(
                state_store=AircraftStateStore(),
                websocket_hub=RealtimeWebSocketHub(),
            ),
            ingestion_adapter=ReadsbFileIngestionAdapter(ROOT / relative_path),
            normalizer=TelemetryNormalizer(),
            poll_interval_seconds=0.01,
        )


if __name__ == "__main__":
    unittest.main()
