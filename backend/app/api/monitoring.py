from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.runtime import RealtimePipeline
from app.runtime.source_control import SourceController, SourceSelectionError
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


def create_monitoring_router(
    *,
    state_store: AircraftStateStore,
    websocket_hub: RealtimeWebSocketHub,
    pipeline: RealtimePipeline,
    source_controller: SourceController,
) -> Any:
    """Create lightweight HTTP endpoints for validation and observability."""
    try:
        from fastapi import APIRouter, HTTPException
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI must be installed to create the monitoring router."
        ) from exc

    router = APIRouter()

    @router.get("/api/health")
    async def healthcheck() -> dict[str, Any]:
        pipeline_metrics = pipeline.metrics_snapshot()
        hub_metrics = websocket_hub.metrics_snapshot()
        return {
            "status": "ok",
            "generated_at": _serialize_timestamp(datetime.now(timezone.utc)),
            "active_aircraft": state_store.active_count,
            "connected_clients": websocket_hub.connected_count,
            "pipeline": {
                "total_batches_processed": pipeline_metrics.total_batches_processed,
                "total_telemetry_messages": pipeline_metrics.total_telemetry_messages,
                "total_state_changes": pipeline_metrics.total_state_changes,
                "total_created_changes": pipeline_metrics.total_created_changes,
                "total_updated_changes": pipeline_metrics.total_updated_changes,
                "total_removed_changes": pipeline_metrics.total_removed_changes,
                "total_ignored_changes": pipeline_metrics.total_ignored_changes,
                "last_batch_processed_at": _serialize_timestamp(
                    pipeline_metrics.last_batch_processed_at
                ),
            },
            "stream": {
                "total_connections_accepted": hub_metrics.total_connections_accepted,
                "total_disconnects": hub_metrics.total_disconnects,
                "total_snapshot_messages_sent": hub_metrics.total_snapshot_messages_sent,
                "total_delta_publish_calls": hub_metrics.total_delta_publish_calls,
                "total_delta_messages_sent": hub_metrics.total_delta_messages_sent,
                "total_delta_change_entries_sent": hub_metrics.total_delta_change_entries_sent,
                "total_client_send_failures": hub_metrics.total_client_send_failures,
                "total_seen_state_changes": hub_metrics.total_seen_state_changes,
                "total_publishable_state_changes": hub_metrics.total_publishable_state_changes,
                "total_suppressed_state_changes": hub_metrics.total_suppressed_state_changes,
                "total_ignored_state_changes": hub_metrics.total_ignored_state_changes,
                "last_snapshot_sent_at": _serialize_timestamp(hub_metrics.last_snapshot_sent_at),
                "last_delta_sent_at": _serialize_timestamp(hub_metrics.last_delta_sent_at),
            },
            "source": source_controller.monitoring_payload(),
        }

    @router.get("/api/aircraft")
    async def active_aircraft() -> dict[str, Any]:
        return {
            "count": state_store.active_count,
            "aircraft": [
                {
                    "aircraft_id": state.aircraft_id,
                    "callsign": state.callsign,
                    "latitude": state.latitude,
                    "longitude": state.longitude,
                    "altitude_ft": state.altitude_ft,
                    "ground_speed_kt": state.ground_speed_kt,
                    "heading_deg": state.heading_deg,
                    "last_seen": _serialize_timestamp(state.last_seen),
                    "trail_points": len(state.trail),
                }
                for state in state_store.snapshot()
            ],
        }

    @router.get("/api/source")
    async def source_status() -> dict[str, Any]:
        return source_controller.monitoring_payload()

    @router.post("/api/source/select")
    async def select_source(payload: dict[str, Any]) -> dict[str, Any]:
        source_id = str(payload.get("source") or "").strip().lower()
        if not source_id:
            raise HTTPException(status_code=400, detail="source is required")

        try:
            snapshot = await source_controller.select_source(source_id)
        except SourceSelectionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return snapshot.to_dict()

    @router.post("/api/source/stop")
    async def stop_source() -> dict[str, Any]:
        snapshot = await source_controller.stop_source()
        return snapshot.to_dict()

    return router


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
