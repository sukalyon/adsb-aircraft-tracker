from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.models.aircraft import AircraftTelemetry, RawAircraftMessage


@dataclass(slots=True, frozen=True)
class NormalizationBatch:
    telemetry: list[AircraftTelemetry]
    issues: list[str] = field(default_factory=list)


class TelemetryNormalizer:
    """Convert raw decoder messages into canonical telemetry records."""

    def normalize_many(self, messages: Iterable[RawAircraftMessage]) -> NormalizationBatch:
        telemetry: list[AircraftTelemetry] = []
        issues: list[str] = []

        for message in messages:
            normalized, message_issues = self.normalize_message(message)
            telemetry.append(normalized)
            issues.extend(message_issues)

        return NormalizationBatch(telemetry=telemetry, issues=issues)

    def normalize_message(
        self,
        message: RawAircraftMessage,
    ) -> tuple[AircraftTelemetry, list[str]]:
        issues: list[str] = []

        latitude = self._normalize_latitude(message.raw_latitude)
        longitude = self._normalize_longitude(message.raw_longitude)
        if latitude is None or longitude is None:
            if message.raw_latitude is not None or message.raw_longitude is not None:
                issues.append(f"{message.aircraft_id}: invalid or incomplete position")
            latitude = None
            longitude = None

        heading = self._normalize_heading(message.raw_heading_deg)
        if message.raw_heading_deg is not None and heading is None:
            issues.append(f"{message.aircraft_id}: invalid heading")

        speed = self._normalize_speed(message.raw_ground_speed_kt)
        if message.raw_ground_speed_kt is not None and speed is None:
            issues.append(f"{message.aircraft_id}: invalid ground speed")

        telemetry = AircraftTelemetry(
            aircraft_id=message.aircraft_id.lower(),
            captured_at=message.captured_at,
            source=message.source,
            callsign=self._normalize_callsign(message.raw_callsign),
            squawk=self._normalize_code(message.raw_squawk),
            category=self._normalize_code(message.raw_category),
            latitude=latitude,
            longitude=longitude,
            altitude_ft=message.raw_altitude_ft,
            ground_speed_kt=speed,
            heading_deg=heading,
            vertical_rate_fpm=message.raw_vertical_rate_fpm,
        )

        return telemetry, issues

    @staticmethod
    def _normalize_callsign(value: str | None) -> str | None:
        if value is None:
            return None
        callsign = value.strip().upper()
        return callsign or None

    @staticmethod
    def _normalize_code(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @staticmethod
    def _normalize_latitude(value: float | None) -> float | None:
        if value is None:
            return None
        if -90.0 <= value <= 90.0:
            return value
        return None

    @staticmethod
    def _normalize_longitude(value: float | None) -> float | None:
        if value is None:
            return None
        if -180.0 <= value <= 180.0:
            return value
        return None

    @staticmethod
    def _normalize_heading(value: float | None) -> float | None:
        if value is None:
            return None
        return value % 360.0

    @staticmethod
    def _normalize_speed(value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0:
            return None
        return value
