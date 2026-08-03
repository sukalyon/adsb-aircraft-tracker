from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.models.aircraft import RawAircraftMessage, parse_timestamp


class IngestionError(ValueError):
    """Raised when a decoder snapshot cannot be parsed into the canonical shape."""


@dataclass(slots=True, frozen=True)
class IngestionBatch:
    source: str
    captured_at: datetime
    messages: list[RawAircraftMessage]
    raw_record_count: int
    dropped_record_count: int = 0
    warnings: list[str] = field(default_factory=list)


class DecoderIngestionAdapter(Protocol):
    def ingest(self) -> IngestionBatch:
        """Read a decoder source and return canonical raw aircraft messages."""


@dataclass(slots=True)
class ReadsbFileIngestionAdapter:
    snapshot_path: Path
    source_name: str = "readsb"
    decoder_type: str = "readsb"

    def ingest(self) -> IngestionBatch:
        snapshot = self._load_snapshot()
        captured_at = self._resolve_captured_at(snapshot)
        source = str(snapshot.get("source") or self.source_name)
        aircraft_entries = snapshot["aircraft"]

        messages: list[RawAircraftMessage] = []
        warnings: list[str] = []

        for aircraft in aircraft_entries:
            try:
                messages.append(
                    RawAircraftMessage.from_readsb_payload(
                        aircraft,
                        captured_at=captured_at,
                        source=source,
                        decoder_type=self.decoder_type,
                    )
                )
            except ValueError as exc:
                warnings.append(str(exc))

        return IngestionBatch(
            source=source,
            captured_at=captured_at,
            messages=messages,
            raw_record_count=len(aircraft_entries),
            dropped_record_count=len(aircraft_entries) - len(messages),
            warnings=warnings,
        )

    def _load_snapshot(self) -> dict[str, Any]:
        with self.snapshot_path.open("r", encoding="utf-8") as handle:
            snapshot = json.load(handle)

        if not isinstance(snapshot, dict):
            raise IngestionError("readsb snapshot must be a JSON object")

        if "captured_at" not in snapshot:
            if "now" not in snapshot:
                raise IngestionError("readsb snapshot must include 'captured_at' or 'now'")

        aircraft_entries = snapshot.get("aircraft")
        if not isinstance(aircraft_entries, list):
            raise IngestionError("readsb snapshot must include an 'aircraft' list")

        return snapshot

    @staticmethod
    def _resolve_captured_at(snapshot: dict[str, Any]) -> datetime:
        captured_at = snapshot.get("captured_at")
        if isinstance(captured_at, str):
            return parse_timestamp(captured_at)

        now_value = snapshot.get("now")
        if isinstance(now_value, (int, float)):
            return datetime.fromtimestamp(float(now_value), tz=timezone.utc)
        if isinstance(now_value, str):
            try:
                return datetime.fromtimestamp(float(now_value), tz=timezone.utc)
            except ValueError:
                return parse_timestamp(now_value)

        raise IngestionError("readsb snapshot must include a valid 'captured_at' or 'now'")
