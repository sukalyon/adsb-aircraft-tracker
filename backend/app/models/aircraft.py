from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


def parse_timestamp(value: str) -> datetime:
    """Parse ISO-8601 timestamps and normalize them to UTC."""
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


class TrackStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    REMOVED = "removed"


@dataclass(slots=True, frozen=True)
class RawAircraftMessage:
    source: str
    decoder_type: str
    captured_at: datetime
    aircraft_id: str
    raw_callsign: str | None = None
    raw_squawk: str | None = None
    raw_category: str | None = None
    raw_latitude: float | None = None
    raw_longitude: float | None = None
    raw_altitude_ft: int | None = None
    raw_ground_speed_kt: float | None = None
    raw_heading_deg: float | None = None
    raw_vertical_rate_fpm: int | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_readsb_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        captured_at: datetime,
        source: str = "readsb",
    ) -> "RawAircraftMessage":
        aircraft_id = _clean_text(payload.get("hex"))
        if aircraft_id is None:
            raise ValueError("readsb payload must include a non-empty 'hex' field")

        return cls(
            source=source,
            decoder_type="readsb",
            captured_at=captured_at.astimezone(timezone.utc),
            aircraft_id=aircraft_id.lower(),
            raw_callsign=_clean_text(payload.get("flight")),
            raw_squawk=_clean_text(payload.get("squawk")),
            raw_category=_clean_text(payload.get("category")),
            raw_latitude=_coerce_float(payload.get("lat")),
            raw_longitude=_coerce_float(payload.get("lon")),
            raw_altitude_ft=_coerce_int(
                _first_present(payload.get("alt_baro"), payload.get("alt_geom"))
            ),
            raw_ground_speed_kt=_coerce_float(payload.get("gs")),
            raw_heading_deg=_coerce_float(payload.get("track")),
            raw_vertical_rate_fpm=_coerce_int(
                _first_present(payload.get("baro_rate"), payload.get("geom_rate"))
            ),
            raw_payload=dict(payload),
        )


@dataclass(slots=True, frozen=True)
class AircraftTelemetry:
    aircraft_id: str
    captured_at: datetime
    source: str
    callsign: str | None = None
    squawk: str | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_ft: int | None = None
    ground_speed_kt: float | None = None
    heading_deg: float | None = None
    vertical_rate_fpm: int | None = None

    @property
    def has_position(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(slots=True, frozen=True)
class TrailPoint:
    captured_at: datetime
    latitude: float
    longitude: float
    altitude_ft: int | None = None


@dataclass(slots=True)
class AircraftState:
    aircraft_id: str
    last_seen: datetime
    source: str
    status: TrackStatus = TrackStatus.ACTIVE
    callsign: str | None = None
    squawk: str | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_ft: int | None = None
    ground_speed_kt: float | None = None
    heading_deg: float | None = None
    vertical_rate_fpm: int | None = None
    trail: list[TrailPoint] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class AircraftUpdateDTO:
    aircraft_id: str
    updated_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    altitude_ft: int | None = None
    ground_speed_kt: float | None = None
    heading_deg: float | None = None
    callsign: str | None = None


@dataclass(slots=True, frozen=True)
class AircraftMetadata:
    aircraft_id: str
    registration: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    operator: str | None = None
    origin: str | None = None
    destination: str | None = None
    image_url: str | None = None
    country: str | None = None
