from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.api.monitoring import create_monitoring_router
from app.api.realtime import register_realtime_websocket
from app.runtime import (
    RealtimePipeline,
    SourceController,
    build_source_definitions_from_env,
    ensure_websocket_runtime_support,
)
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


def create_app() -> Any:
    """Build the validation backend application."""
    try:
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI must be installed to create the validation backend app."
        ) from exc

    ensure_websocket_runtime_support()

    state_store = AircraftStateStore(
        stale_after=timedelta(seconds=_env_float("ADSB_STALE_AFTER_SECONDS", default=12.0))
    )
    websocket_hub = RealtimeWebSocketHub()
    pipeline = RealtimePipeline(
        state_store=state_store,
        websocket_hub=websocket_hub,
    )
    source_definitions, initial_source_id = build_source_definitions_from_env()
    source_controller = SourceController(
        pipeline=pipeline,
        state_store=state_store,
        websocket_hub=websocket_hub,
        source_definitions=source_definitions,
        initial_source_id=initial_source_id,
        poll_interval_seconds=_env_float("ADSB_POLL_INTERVAL_SECONDS", default=1.0),
        sample_interval_seconds=_env_float("ADSB_SAMPLE_INTERVAL_SECONDS", default=1.2),
    )

    @asynccontextmanager
    async def lifespan(app: Any):
        await source_controller.start_initial_source()
        try:
            yield
        finally:
            await source_controller.shutdown()

    app = FastAPI(
        title="ADS-B Aircraft Tracker",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.state_store = state_store
    app.state.websocket_hub = websocket_hub
    app.state.pipeline = pipeline
    app.state.source_controller = source_controller

    register_realtime_websocket(
        app,
        hub=websocket_hub,
        state_store=state_store,
    )
    app.include_router(
        create_monitoring_router(
            state_store=state_store,
            websocket_hub=websocket_hub,
            pipeline=pipeline,
            source_controller=source_controller,
        )
    )

    client_2d_path = Path(__file__).resolve().parents[2] / "frontend" / "client-2d"
    if client_2d_path.exists():
        app.mount(
            "/",
            StaticFiles(directory=client_2d_path, html=True),
            name="client-root",
        )

    return app


def _env_float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


app = create_app()


def main() -> int:
    """Run the local validation backend with uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "uvicorn must be installed to run the validation backend."
        ) from exc

    uvicorn.run(
        "app.main:app",
        host=os.getenv("ADSB_HOST", "127.0.0.1"),
        port=int(os.getenv("ADSB_PORT", "8000")),
        reload=os.getenv("ADSB_RELOAD", "0") == "1",
        ws=os.getenv("ADSB_WS_BACKEND", "wsproto"),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
