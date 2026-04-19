from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Iterable

from app.models.aircraft import AircraftState, AircraftTelemetry, TrackStatus, TrailPoint


class StateChangeType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"
    IGNORED = "ignored"


@dataclass(slots=True, frozen=True)
class StateChange:
    change_type: StateChangeType
    aircraft_id: str
    state: AircraftState | None = None
    reason: str | None = None
    changed_fields: tuple[str, ...] = ()


class AircraftStateStore:
    def __init__(
        self,
        *,
        trail_max_points: int = 32,
        stale_after: timedelta = timedelta(seconds=60),
    ) -> None:
        self._states: dict[str, AircraftState] = {}
        self.trail_max_points = trail_max_points
        self.stale_after = stale_after

    @property
    def active_count(self) -> int:
        return len(self._states)

    def get(self, aircraft_id: str) -> AircraftState | None:
        return self._states.get(aircraft_id)

    def snapshot(self) -> list[AircraftState]:
        return [self._states[key] for key in sorted(self._states)]

    def apply(self, telemetry: AircraftTelemetry) -> StateChange:
        existing = self._states.get(telemetry.aircraft_id)
        if existing is not None and telemetry.captured_at < existing.last_seen:
            return StateChange(
                change_type=StateChangeType.IGNORED,
                aircraft_id=telemetry.aircraft_id,
                state=existing,
                reason="out_of_order",
            )

        if existing is None:
            before_fields: dict[str, object | None] | None = None
            state = AircraftState(
                aircraft_id=telemetry.aircraft_id,
                last_seen=telemetry.captured_at,
                source=telemetry.source,
            )
            change_type = StateChangeType.CREATED
        else:
            before_fields = self._capture_state_fields(existing)
            state = existing
            change_type = StateChangeType.UPDATED

        self._merge_into_state(state, telemetry)
        self._states[telemetry.aircraft_id] = state
        changed_fields = self._diff_state_fields(before_fields, self._capture_state_fields(state))

        return StateChange(
            change_type=change_type,
            aircraft_id=telemetry.aircraft_id,
            state=state,
            changed_fields=changed_fields,
        )

    def apply_many(self, telemetry_batch: Iterable[AircraftTelemetry]) -> list[StateChange]:
        return [self.apply(telemetry) for telemetry in telemetry_batch]

    def remove_stale(self, *, reference_time: datetime | None = None) -> list[StateChange]:
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        cutoff = reference_time - self.stale_after
        removed: list[StateChange] = []

        for aircraft_id, state in list(self._states.items()):
            if state.last_seen < cutoff:
                state.status = TrackStatus.REMOVED
                removed.append(
                    StateChange(
                        change_type=StateChangeType.REMOVED,
                        aircraft_id=aircraft_id,
                        state=state,
                        reason="stale_timeout",
                        changed_fields=("status",),
                    )
                )
                del self._states[aircraft_id]

        return removed

    def _merge_into_state(self, state: AircraftState, telemetry: AircraftTelemetry) -> None:
        state.last_seen = telemetry.captured_at
        state.source = telemetry.source
        state.status = TrackStatus.ACTIVE

        if telemetry.callsign is not None:
            state.callsign = telemetry.callsign
        if telemetry.squawk is not None:
            state.squawk = telemetry.squawk
        if telemetry.category is not None:
            state.category = telemetry.category
        if telemetry.altitude_ft is not None:
            state.altitude_ft = telemetry.altitude_ft
        if telemetry.ground_speed_kt is not None:
            state.ground_speed_kt = telemetry.ground_speed_kt
        if telemetry.heading_deg is not None:
            state.heading_deg = telemetry.heading_deg
        if telemetry.vertical_rate_fpm is not None:
            state.vertical_rate_fpm = telemetry.vertical_rate_fpm

        if telemetry.has_position:
            state.latitude = telemetry.latitude
            state.longitude = telemetry.longitude
            self._append_trail_point(state, telemetry)

    def _append_trail_point(self, state: AircraftState, telemetry: AircraftTelemetry) -> None:
        latitude = telemetry.latitude
        longitude = telemetry.longitude
        if latitude is None or longitude is None:
            return

        next_point = TrailPoint(
            captured_at=telemetry.captured_at,
            latitude=latitude,
            longitude=longitude,
            altitude_ft=telemetry.altitude_ft,
        )

        if state.trail:
            last_point = state.trail[-1]
            if (
                last_point.latitude == next_point.latitude
                and last_point.longitude == next_point.longitude
                and last_point.altitude_ft == next_point.altitude_ft
            ):
                return

        state.trail.append(next_point)
        if len(state.trail) > self.trail_max_points:
            del state.trail[: len(state.trail) - self.trail_max_points]

    @staticmethod
    def _capture_state_fields(state: AircraftState) -> dict[str, object | None]:
        return {
            "callsign": state.callsign,
            "squawk": state.squawk,
            "category": state.category,
            "latitude": state.latitude,
            "longitude": state.longitude,
            "altitude_ft": state.altitude_ft,
            "ground_speed_kt": state.ground_speed_kt,
            "heading_deg": state.heading_deg,
            "vertical_rate_fpm": state.vertical_rate_fpm,
            "status": state.status,
        }

    @staticmethod
    def _diff_state_fields(
        before: dict[str, object | None] | None,
        after: dict[str, object | None],
    ) -> tuple[str, ...]:
        if before is None:
            return tuple(name for name, value in after.items() if value is not None)

        return tuple(name for name, value in after.items() if before.get(name) != value)
