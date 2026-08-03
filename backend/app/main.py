from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.api.monitoring import create_monitoring_router
from app.api.realtime import register_realtime_websocket
from app.ingestion.readsb import ReadsbFileIngestionAdapter
from app.runtime import (
    DecoderFileSourceRuntime,
    RealtimePipeline,
    ensure_websocket_runtime_support,
)
from app.services.normalization import TelemetryNormalizer
from app.services.sample_feed import run_sample_feed
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub


def create_app() -> Any:
    """Build the validation backend application."""
    try:
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import RedirectResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastAPI must be installed to create the validation backend app."
        ) from exc

    ensure_websocket_runtime_support()

    source_mode = os.getenv("ADSB_SOURCE_MODE", "sample").strip().lower()
    state_store = AircraftStateStore(
        stale_after=timedelta(seconds=_env_float("ADSB_STALE_AFTER_SECONDS", default=12.0))
    )
    websocket_hub = RealtimeWebSocketHub()
    pipeline = RealtimePipeline(
        state_store=state_store,
        websocket_hub=websocket_hub,
    )
    source_runtime = _create_source_runtime(source_mode=source_mode, pipeline=pipeline)

    @asynccontextmanager
    async def lifespan(app: Any):
        app.state.source_task = _create_source_task(
            source_mode=source_mode,
            pipeline=pipeline,
            source_runtime=source_runtime,
        )
        try:
            yield
        finally:
            task = app.state.source_task
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                finally:
                    app.state.source_task = None

    app = FastAPI(
        title="ADS-B Aircraft Tracker",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.state_store = state_store
    app.state.websocket_hub = websocket_hub
    app.state.pipeline = pipeline
    app.state.source_mode = source_mode
    app.state.source_runtime = source_runtime
    app.state.source_task = None

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
            source_runtime=source_runtime,
            source_mode=source_mode,
        )
    )

    client_2d_path = Path(__file__).resolve().parents[2] / "frontend" / "client-2d"
    if client_2d_path.exists():
        app.mount(
            "/client-2d",
            StaticFiles(directory=client_2d_path, html=True),
            name="client-2d",
        )

        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:
            return RedirectResponse(url="/client-2d/")

    return app


def _env_float(name: str, *, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _create_source_runtime(*, source_mode: str, pipeline: RealtimePipeline) -> DecoderFileSourceRuntime | None:
    if source_mode != "readsb_file":
        return None

    snapshot_path = os.getenv("ADSB_READSB_SNAPSHOT_PATH")
    if not snapshot_path:
        raise RuntimeError(
            "ADSB_READSB_SNAPSHOT_PATH must be set when ADSB_SOURCE_MODE=readsb_file."
        )

    source_name = os.getenv("ADSB_SOURCE_NAME", "readsb")
    decoder_type = os.getenv("ADSB_DECODER_TYPE", source_name)

    return DecoderFileSourceRuntime(
        pipeline=pipeline,
        ingestion_adapter=ReadsbFileIngestionAdapter(
            snapshot_path=Path(snapshot_path),
            source_name=source_name,
            decoder_type=decoder_type,
        ),
        normalizer=TelemetryNormalizer(),
        poll_interval_seconds=_env_float("ADSB_POLL_INTERVAL_SECONDS", default=1.0),
    )


def _create_source_task(
    *,
    source_mode: str,
    pipeline: RealtimePipeline,
    source_runtime: DecoderFileSourceRuntime | None,
) -> asyncio.Task[None] | None:
    if source_mode == "sample":
        return asyncio.create_task(
            run_sample_feed(
                pipeline,
                interval_seconds=_env_float("ADSB_SAMPLE_INTERVAL_SECONDS", default=1.2),
            )
        )

    if source_mode == "readsb_file":
        if source_runtime is None:
            raise RuntimeError("readsb_file source mode requires a configured source runtime.")
        return asyncio.create_task(source_runtime.run())

    raise RuntimeError(f"Unsupported ADS-B source mode: {source_mode}")


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
