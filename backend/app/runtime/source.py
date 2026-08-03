from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from app.ingestion.readsb import DecoderIngestionAdapter
from app.runtime.pipeline import RealtimePipeline
from app.services.normalization import TelemetryNormalizer


@dataclass(slots=True, frozen=True)
class DecoderFileSourceMetricsSnapshot:
    source_mode: str
    is_running: bool
    poll_interval_seconds: float
    total_batches_ingested: int
    total_batches_skipped: int
    total_raw_records: int
    total_dropped_records: int
    total_normalized_telemetry: int
    total_ingestion_warnings: int
    total_normalization_issues: int
    last_batch_captured_at: datetime | None
    last_error: str | None


class DecoderFileSourceRuntime:
    """Poll a decoder JSON file and feed normalized telemetry into the live pipeline."""

    def __init__(
        self,
        *,
        pipeline: RealtimePipeline,
        ingestion_adapter: DecoderIngestionAdapter,
        normalizer: TelemetryNormalizer,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.pipeline = pipeline
        self.ingestion_adapter = ingestion_adapter
        self.normalizer = normalizer
        self.poll_interval_seconds = poll_interval_seconds
        self._is_running = False
        self._last_batch_captured_at: datetime | None = None
        self._last_error: str | None = None
        self._total_batches_ingested = 0
        self._total_batches_skipped = 0
        self._total_raw_records = 0
        self._total_dropped_records = 0
        self._total_normalized_telemetry = 0
        self._total_ingestion_warnings = 0
        self._total_normalization_issues = 0

    def metrics_snapshot(self) -> DecoderFileSourceMetricsSnapshot:
        return DecoderFileSourceMetricsSnapshot(
            source_mode="readsb_file",
            is_running=self._is_running,
            poll_interval_seconds=self.poll_interval_seconds,
            total_batches_ingested=self._total_batches_ingested,
            total_batches_skipped=self._total_batches_skipped,
            total_raw_records=self._total_raw_records,
            total_dropped_records=self._total_dropped_records,
            total_normalized_telemetry=self._total_normalized_telemetry,
            total_ingestion_warnings=self._total_ingestion_warnings,
            total_normalization_issues=self._total_normalization_issues,
            last_batch_captured_at=self._last_batch_captured_at,
            last_error=self._last_error,
        )

    async def run(self) -> None:
        self._is_running = True
        try:
            while True:
                try:
                    await self.process_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._last_error = str(exc)
                await asyncio.sleep(self.poll_interval_seconds)
        finally:
            self._is_running = False

    async def process_once(self) -> bool:
        batch = self.ingestion_adapter.ingest()
        self._total_raw_records += batch.raw_record_count
        self._total_dropped_records += batch.dropped_record_count
        self._total_ingestion_warnings += len(batch.warnings)

        if self._last_batch_captured_at is not None and batch.captured_at <= self._last_batch_captured_at:
            self._total_batches_skipped += 1
            return False

        normalized = self.normalizer.normalize_many(batch.messages)
        self._total_normalization_issues += len(normalized.issues)
        self._total_normalized_telemetry += len(normalized.telemetry)

        await self.pipeline.process_telemetry_batch(normalized.telemetry)
        await self.pipeline.expire_stale_tracks(reference_time=batch.captured_at)

        self._total_batches_ingested += 1
        self._last_batch_captured_at = batch.captured_at
        self._last_error = None
        return True
