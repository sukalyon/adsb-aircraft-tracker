from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from app.ingestion.readsb import ReadsbFileIngestionAdapter, ReadsbUrlIngestionAdapter
from app.services.normalization import TelemetryNormalizer
from app.services.sample_feed import run_sample_feed
from app.state.store import AircraftStateStore
from app.streaming.websocket import RealtimeWebSocketHub

from .pipeline import RealtimePipeline
from .source import DecoderFileSourceRuntime


@dataclass(slots=True, frozen=True)
class SourceDefinition:
    source_id: str
    label: str
    source_mode: str
    source_name: str
    decoder_type: str | None = None
    snapshot_path: Path | None = None
    snapshot_url: str | None = None

    @property
    def kind(self) -> str:
        return "sample" if self.source_id == "sample" else "live"

    def availability(self) -> tuple[bool, str | None]:
        if self.kind == "sample":
            return True, None

        if self.snapshot_path is not None and self.snapshot_path.exists():
            return True, None

        if self.snapshot_url is not None:
            if not _snapshot_url_is_available(self.snapshot_url):
                return False, "Snapshot endpoint unavailable"
            return True, None

        if self.snapshot_path is not None:
            return False, "Snapshot file not found"

        return False, "Not configured"


@dataclass(slots=True, frozen=True)
class SourceOptionSnapshot:
    source_id: str
    label: str
    kind: str
    available: bool
    active: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "id": self.source_id,
            "label": self.label,
            "kind": self.kind,
            "available": self.available,
            "active": self.active,
            "reason": self.reason,
        }


@dataclass(slots=True, frozen=True)
class SourceControllerSnapshot:
    active_source_id: str | None
    active_source_label: str | None
    active_source_kind: str
    is_running: bool
    options: tuple[SourceOptionSnapshot, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "active_source_id": self.active_source_id,
            "active_source_label": self.active_source_label,
            "active_source_kind": self.active_source_kind,
            "is_running": self.is_running,
            "sources": [option.to_dict() for option in self.options],
        }


class SourceSelectionError(ValueError):
    """Raised when a requested source cannot be activated."""


class SourceController:
    def __init__(
        self,
        *,
        pipeline: RealtimePipeline,
        state_store: AircraftStateStore,
        websocket_hub: RealtimeWebSocketHub,
        source_definitions: Mapping[str, SourceDefinition],
        initial_source_id: str = "sample",
        poll_interval_seconds: float = 1.0,
        sample_interval_seconds: float = 1.2,
    ) -> None:
        self.pipeline = pipeline
        self.state_store = state_store
        self.websocket_hub = websocket_hub
        self._source_definitions = dict(source_definitions)
        self._initial_source_id = initial_source_id
        self._poll_interval_seconds = poll_interval_seconds
        self._sample_interval_seconds = sample_interval_seconds
        self._active_source_id: str | None = None
        self._source_runtime: DecoderFileSourceRuntime | None = None
        self._source_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def active_source_id(self) -> str | None:
        return self._active_source_id

    @property
    def source_runtime(self) -> DecoderFileSourceRuntime | None:
        return self._source_runtime

    async def start_initial_source(self) -> SourceControllerSnapshot:
        initial_source_id = self._initial_source_id
        if initial_source_id == "none":
            return self.snapshot()

        return await self.select_source(initial_source_id)

    async def shutdown(self) -> None:
        async with self._lock:
            await self._stop_locked(clear_state=False)

    async def select_source(self, source_id: str) -> SourceControllerSnapshot:
        async with self._lock:
            definition = self._source_definitions.get(source_id)
            if definition is None:
                raise SourceSelectionError(f"Unknown source: {source_id}")

            available, reason = definition.availability()
            if not available:
                raise SourceSelectionError(reason or f"Source unavailable: {source_id}")

            if self._active_source_id == source_id and self._source_task is not None and not self._source_task.done():
                return self.snapshot()

            await self._stop_locked(clear_state=True)
            self._start_locked(definition)
            return self.snapshot()

    async def stop_source(self) -> SourceControllerSnapshot:
        async with self._lock:
            await self._stop_locked(clear_state=True)
            return self.snapshot()

    def snapshot(self) -> SourceControllerSnapshot:
        active_source_id = self._active_source_id
        active_definition = self._source_definitions.get(active_source_id) if active_source_id else None
        options = []

        for definition in self._source_definitions.values():
            available, reason = definition.availability()
            options.append(
                SourceOptionSnapshot(
                    source_id=definition.source_id,
                    label=definition.label,
                    kind=definition.kind,
                    available=available,
                    active=definition.source_id == active_source_id,
                    reason=reason,
                )
            )

        is_running = self._source_task is not None and not self._source_task.done()
        return SourceControllerSnapshot(
            active_source_id=active_source_id,
            active_source_label=active_definition.label if active_definition is not None else None,
            active_source_kind=active_definition.kind if active_definition is not None else "none",
            is_running=is_running,
            options=tuple(options),
        )

    def monitoring_payload(self) -> dict[str, object]:
        snapshot = self.snapshot()
        payload = snapshot.to_dict()
        payload["mode"] = snapshot.active_source_id or "none"

        if self._source_runtime is None:
            return payload

        metrics = self._source_runtime.metrics_snapshot()
        payload.update(
            {
                "poll_interval_seconds": metrics.poll_interval_seconds,
                "total_batches_ingested": metrics.total_batches_ingested,
                "total_batches_skipped": metrics.total_batches_skipped,
                "total_raw_records": metrics.total_raw_records,
                "total_dropped_records": metrics.total_dropped_records,
                "total_normalized_telemetry": metrics.total_normalized_telemetry,
                "total_ingestion_warnings": metrics.total_ingestion_warnings,
                "total_normalization_issues": metrics.total_normalization_issues,
                "last_batch_captured_at": _serialize_timestamp(metrics.last_batch_captured_at),
                "last_error": metrics.last_error,
            }
        )
        return payload

    def _start_locked(self, definition: SourceDefinition) -> None:
        self._active_source_id = definition.source_id

        if definition.kind == "sample":
            self._source_runtime = None
            self._source_task = asyncio.create_task(
                run_sample_feed(
                    self.pipeline,
                    interval_seconds=self._sample_interval_seconds,
                )
            )
            return

        runtime = DecoderFileSourceRuntime(
            pipeline=self.pipeline,
            ingestion_adapter=_build_ingestion_adapter(definition),
            normalizer=TelemetryNormalizer(),
            poll_interval_seconds=self._poll_interval_seconds,
        )
        self._source_runtime = runtime
        self._source_task = asyncio.create_task(runtime.run())

    async def _stop_locked(self, *, clear_state: bool) -> None:
        task = self._source_task
        self._source_task = None

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._source_runtime = None
        self._active_source_id = None

        if clear_state:
            removed_changes = self.state_store.clear(reason="source_reset")
            if removed_changes:
                await self.websocket_hub.publish_delta(removed_changes)


def build_source_definitions_from_env(
    environment: Mapping[str, str] | None = None,
) -> tuple[dict[str, SourceDefinition], str]:
    env = dict(os.environ if environment is None else environment)
    use_local_autodiscovery = environment is None
    source_mode = env.get("ADSB_SOURCE_MODE", "sample").strip().lower()
    legacy_snapshot_path = _read_path_env(env, "ADSB_READSB_SNAPSHOT_PATH")
    readsb_snapshot_path = _read_path_env(env, "ADSB_READSB_SNAPSHOT_PATH")
    dump1090_snapshot_path = _read_path_env(env, "ADSB_DUMP1090_SNAPSHOT_PATH")
    readsb_snapshot_url = _read_text_env(env, "ADSB_READSB_SNAPSHOT_URL")
    dump1090_snapshot_url = _read_text_env(env, "ADSB_DUMP1090_SNAPSHOT_URL")
    legacy_source_name = env.get("ADSB_SOURCE_NAME", "readsb").strip().lower()
    legacy_decoder_type = env.get("ADSB_DECODER_TYPE", legacy_source_name).strip().lower()

    if use_local_autodiscovery and dump1090_snapshot_path is None and dump1090_snapshot_url is None:
        dump1090_snapshot_url = "http://127.0.0.1:8080/data/aircraft.json"

    if source_mode == "readsb_file" and legacy_snapshot_path is not None:
        if "dump1090" in {legacy_source_name, legacy_decoder_type}:
            if dump1090_snapshot_path is None:
                dump1090_snapshot_path = legacy_snapshot_path
            if "ADSB_DUMP1090_SNAPSHOT_PATH" not in env:
                readsb_snapshot_path = None
        elif readsb_snapshot_path is None:
            readsb_snapshot_path = legacy_snapshot_path

    definitions = {
        "sample": SourceDefinition(
            source_id="sample",
            label="Sample",
            source_mode="sample",
            source_name="sample",
        ),
        "readsb": SourceDefinition(
            source_id="readsb",
            label="RTL-SDR / readsb",
            source_mode="readsb_file",
            source_name="readsb",
            decoder_type="readsb",
            snapshot_path=readsb_snapshot_path,
            snapshot_url=readsb_snapshot_url,
        ),
        "dump1090": SourceDefinition(
            source_id="dump1090",
            label="RTL-SDR / dump1090",
            source_mode="dump1090_file",
            source_name="dump1090",
            decoder_type="dump1090",
            snapshot_path=dump1090_snapshot_path,
            snapshot_url=dump1090_snapshot_url,
        ),
    }

    if source_mode == "readsb_file":
        initial_source_id = "dump1090" if "dump1090" in {legacy_source_name, legacy_decoder_type} else "readsb"
    elif source_mode == "dump1090_file":
        initial_source_id = "dump1090"
    elif source_mode == "none":
        initial_source_id = "none"
    else:
        initial_source_id = "sample"

    if initial_source_id != "none":
        definition = definitions[initial_source_id]
        available, reason = definition.availability()
        if not available:
            raise RuntimeError(reason or f"Configured source is unavailable: {initial_source_id}")

    return definitions, initial_source_id


def _read_path_env(environment: Mapping[str, str], key: str) -> Path | None:
    raw_value = environment.get(key)
    if not raw_value:
        return None

    return Path(raw_value).expanduser()


def _read_text_env(environment: Mapping[str, str], key: str) -> str | None:
    raw_value = environment.get(key)
    if raw_value is None:
        return None

    value = raw_value.strip()
    return value or None


def _snapshot_url_is_available(snapshot_url: str) -> bool:
    try:
        with urlopen(snapshot_url, timeout=0.5) as response:
            response.read(1)
        return True
    except Exception:
        return False


def _build_ingestion_adapter(definition: SourceDefinition) -> ReadsbFileIngestionAdapter | ReadsbUrlIngestionAdapter:
    if definition.snapshot_path is not None:
        return ReadsbFileIngestionAdapter(
            snapshot_path=definition.snapshot_path,
            source_name=definition.source_name,
            decoder_type=definition.decoder_type or definition.source_name,
        )

    if definition.snapshot_url is not None:
        return ReadsbUrlIngestionAdapter(
            snapshot_url=definition.snapshot_url,
            source_name=definition.source_name,
            decoder_type=definition.decoder_type or definition.source_name,
        )

    raise SourceSelectionError(f"No snapshot source configured for {definition.source_id}")


def _serialize_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
