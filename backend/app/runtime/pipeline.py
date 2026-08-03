from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.models.aircraft import AircraftTelemetry
from app.state.store import AircraftStateStore, StateChangeType
from app.streaming.websocket import PublishDeltaResult, RealtimeWebSocketHub


@dataclass(slots=True, frozen=True)
class RealtimePipelineResult:
    telemetry_count: int
    state_change_count: int
    created_count: int
    updated_count: int
    removed_count: int
    ignored_count: int
    publish_result: PublishDeltaResult


@dataclass(slots=True, frozen=True)
class RealtimePipelineMetricsSnapshot:
    active_aircraft_count: int
    total_batches_processed: int
    total_telemetry_messages: int
    total_state_changes: int
    total_created_changes: int
    total_updated_changes: int
    total_removed_changes: int
    total_ignored_changes: int
    last_batch_processed_at: datetime | None


class RealtimePipeline:
    """Coordinate state updates and realtime publishing for validation flows."""

    def __init__(
        self,
        *,
        state_store: AircraftStateStore,
        websocket_hub: RealtimeWebSocketHub,
    ) -> None:
        self.state_store = state_store
        self.websocket_hub = websocket_hub
        self._total_batches_processed = 0
        self._total_telemetry_messages = 0
        self._total_state_changes = 0
        self._total_created_changes = 0
        self._total_updated_changes = 0
        self._total_removed_changes = 0
        self._total_ignored_changes = 0
        self._last_batch_processed_at: datetime | None = None

    async def process_telemetry_batch(
        self,
        telemetry_batch: Iterable[AircraftTelemetry],
    ) -> RealtimePipelineResult:
        telemetry = list(telemetry_batch)
        changes = self.state_store.apply_many(telemetry)
        publish_result = await self.websocket_hub.publish_delta(changes)
        result = self._build_result(
            telemetry_count=len(telemetry),
            changes=changes,
            publish_result=publish_result,
        )
        self._record_result(result)
        self._last_batch_processed_at = max(
            (entry.captured_at for entry in telemetry),
            default=self._last_batch_processed_at,
        )
        return result

    async def expire_stale_tracks(
        self,
        *,
        reference_time: datetime | None = None,
    ) -> RealtimePipelineResult:
        removed_changes = self.state_store.remove_stale(reference_time=reference_time)
        publish_result = await self.websocket_hub.publish_delta(removed_changes)
        result = self._build_result(
            telemetry_count=0,
            changes=removed_changes,
            publish_result=publish_result,
        )
        self._record_result(result)
        if reference_time is not None:
            self._last_batch_processed_at = reference_time
        return result

    def metrics_snapshot(self) -> RealtimePipelineMetricsSnapshot:
        return RealtimePipelineMetricsSnapshot(
            active_aircraft_count=self.state_store.active_count,
            total_batches_processed=self._total_batches_processed,
            total_telemetry_messages=self._total_telemetry_messages,
            total_state_changes=self._total_state_changes,
            total_created_changes=self._total_created_changes,
            total_updated_changes=self._total_updated_changes,
            total_removed_changes=self._total_removed_changes,
            total_ignored_changes=self._total_ignored_changes,
            last_batch_processed_at=self._last_batch_processed_at,
        )

    @staticmethod
    def _build_result(
        *,
        telemetry_count: int,
        changes,
        publish_result: PublishDeltaResult,
    ) -> RealtimePipelineResult:
        created_count = sum(1 for change in changes if change.change_type == StateChangeType.CREATED)
        updated_count = sum(1 for change in changes if change.change_type == StateChangeType.UPDATED)
        removed_count = sum(1 for change in changes if change.change_type == StateChangeType.REMOVED)
        ignored_count = sum(1 for change in changes if change.change_type == StateChangeType.IGNORED)

        return RealtimePipelineResult(
            telemetry_count=telemetry_count,
            state_change_count=len(changes),
            created_count=created_count,
            updated_count=updated_count,
            removed_count=removed_count,
            ignored_count=ignored_count,
            publish_result=publish_result,
        )

    def _record_result(self, result: RealtimePipelineResult) -> None:
        self._total_batches_processed += 1
        self._total_telemetry_messages += result.telemetry_count
        self._total_state_changes += result.state_change_count
        self._total_created_changes += result.created_count
        self._total_updated_changes += result.updated_count
        self._total_removed_changes += result.removed_count
        self._total_ignored_changes += result.ignored_count
