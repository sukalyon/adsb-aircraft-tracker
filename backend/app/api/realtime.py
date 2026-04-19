from __future__ import annotations

from typing import Any

from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


def create_realtime_router(
    *,
    hub: RealtimeWebSocketHub,
    state_store: AircraftStateStore,
) -> Any:
    """Create the websocket router that exposes the realtime aircraft stream."""
    try:
        from fastapi import APIRouter, WebSocket, WebSocketDisconnect
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI must be installed to create the realtime websocket router."
        ) from exc

    router = APIRouter()

    @router.websocket("/ws/aircraft")
    async def aircraft_stream(websocket: WebSocket) -> None:
        client_id = await hub.connect(
            websocket,
            snapshot_states=state_store.snapshot(),
        )
        try:
            while True:
                await websocket.receive()
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(client_id)

    return router
