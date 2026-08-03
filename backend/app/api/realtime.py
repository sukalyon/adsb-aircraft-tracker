from __future__ import annotations

from typing import Any

from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


def register_realtime_websocket(
    app: Any,
    *,
    hub: RealtimeWebSocketHub,
    state_store: AircraftStateStore,
) -> None:
    """Register the realtime websocket endpoint directly on the FastAPI app."""
    try:
        from fastapi import WebSocket, WebSocketDisconnect
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI must be installed to register the realtime websocket route."
        ) from exc

    @app.websocket("/ws/aircraft")
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
