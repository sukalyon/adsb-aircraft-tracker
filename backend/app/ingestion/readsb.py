from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
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

    def ingest(self) -> IngestionBatch:
        snapshot = self._load_snapshot()
        captured_at = parse_timestamp(snapshot["captured_at"])
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
            raise IngestionError("readsb snapshot must include 'captured_at'")

        aircraft_entries = snapshot.get("aircraft")
        if not isinstance(aircraft_entries, list):
            raise IngestionError("readsb snapshot must include an 'aircraft' list")

        return snapshot
