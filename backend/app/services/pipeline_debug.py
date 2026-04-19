from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.ingestion.readsb import ReadsbFileIngestionAdapter
from app.state.store import AircraftStateStore, StateChangeType

from .normalization import TelemetryNormalizer


@dataclass(slots=True, frozen=True)
class PipelineDebugReport:
    source: str
    captured_at: datetime
    raw_record_count: int
    dropped_record_count: int
    normalization_issue_count: int
    active_count: int
    created_count: int
    updated_count: int
    ignored_count: int
    ingestion_warnings: list[str]
    normalization_issues: list[str]
    aircraft: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "captured_at": self.captured_at.isoformat().replace("+00:00", "Z"),
            "raw_record_count": self.raw_record_count,
            "dropped_record_count": self.dropped_record_count,
            "normalization_issue_count": self.normalization_issue_count,
            "active_count": self.active_count,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "ignored_count": self.ignored_count,
            "ingestion_warnings": self.ingestion_warnings,
            "normalization_issues": self.normalization_issues,
            "aircraft": self.aircraft,
        }


def build_readsb_file_debug_report(
    snapshot_path: Path,
    *,
    trail_max_points: int = 32,
    stale_after_seconds: int = 60,
) -> PipelineDebugReport:
    ingestion_batch = ReadsbFileIngestionAdapter(snapshot_path).ingest()
    normalization_batch = TelemetryNormalizer().normalize_many(ingestion_batch.messages)

    store = AircraftStateStore(
        trail_max_points=trail_max_points,
        stale_after=timedelta(seconds=stale_after_seconds),
    )
    changes = store.apply_many(normalization_batch.telemetry)

    created_count = sum(1 for change in changes if change.change_type == StateChangeType.CREATED)
    updated_count = sum(1 for change in changes if change.change_type == StateChangeType.UPDATED)
    ignored_count = sum(1 for change in changes if change.change_type == StateChangeType.IGNORED)

    aircraft = []
    for state in store.snapshot():
        aircraft.append(
            {
                "aircraft_id": state.aircraft_id,
                "callsign": state.callsign,
                "status": state.status.value,
                "latitude": state.latitude,
                "longitude": state.longitude,
                "altitude_ft": state.altitude_ft,
                "ground_speed_kt": state.ground_speed_kt,
                "heading_deg": state.heading_deg,
                "trail_points": len(state.trail),
                "last_seen": state.last_seen.isoformat().replace("+00:00", "Z"),
            }
        )

    return PipelineDebugReport(
        source=ingestion_batch.source,
        captured_at=ingestion_batch.captured_at,
        raw_record_count=ingestion_batch.raw_record_count,
        dropped_record_count=ingestion_batch.dropped_record_count,
        normalization_issue_count=len(normalization_batch.issues),
        active_count=store.active_count,
        created_count=created_count,
        updated_count=updated_count,
        ignored_count=ignored_count,
        ingestion_warnings=ingestion_batch.warnings,
        normalization_issues=normalization_batch.issues,
        aircraft=aircraft,
    )
