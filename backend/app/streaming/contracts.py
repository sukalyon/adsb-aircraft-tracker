from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

from app.models.aircraft import AircraftState, AircraftUpdateDTO
from app.state.store import StateChange, StateChangeType

STREAM_CONTRACT_VERSION = 1
DELTA_PUBLISH_FIELDS = frozenset(
    {
        "callsign",
        "latitude",
        "longitude",
        "altitude_ft",
        "ground_speed_kt",
        "heading_deg",
    }
)


def _serialize_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_update(dto: AircraftUpdateDTO) -> dict[str, Any]:
    return {
        "aircraft_id": dto.aircraft_id,
        "updated_at": _serialize_timestamp(dto.updated_at),
        "latitude": dto.latitude,
        "longitude": dto.longitude,
        "altitude_ft": dto.altitude_ft,
        "ground_speed_kt": dto.ground_speed_kt,
        "heading_deg": dto.heading_deg,
        "callsign": dto.callsign,
    }


class StreamEventType(StrEnum):
    SNAPSHOT = "snapshot"
    DELTA = "delta"


class DeltaAction(StrEnum):
    UPSERT = "upsert"
    REMOVE = "remove"


@dataclass(slots=True, frozen=True)
class DeltaAircraftEvent:
    action: DeltaAction
    aircraft_id: str
    aircraft: AircraftUpdateDTO | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "action": self.action.value,
            "aircraft_id": self.aircraft_id,
        }
        if self.aircraft is not None:
            payload["aircraft"] = _serialize_update(self.aircraft)
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(slots=True, frozen=True)
class SnapshotStreamEvent:
    sequence: int
    sent_at: datetime
    aircraft: list[AircraftUpdateDTO]
    version: int = STREAM_CONTRACT_VERSION
    event_type: StreamEventType = StreamEventType.SNAPSHOT

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.event_type.value,
            "version": self.version,
            "sequence": self.sequence,
            "sent_at": _serialize_timestamp(self.sent_at),
            "total": len(self.aircraft),
            "aircraft": [_serialize_update(entry) for entry in self.aircraft],
        }


@dataclass(slots=True, frozen=True)
class DeltaStreamEvent:
    sequence: int
    sent_at: datetime
    changes: list[DeltaAircraftEvent]
    version: int = STREAM_CONTRACT_VERSION
    event_type: StreamEventType = StreamEventType.DELTA

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.event_type.value,
            "version": self.version,
            "sequence": self.sequence,
            "sent_at": _serialize_timestamp(self.sent_at),
            "changes": [change.to_dict() for change in self.changes],
        }


@dataclass(slots=True, frozen=True)
class DeltaPreparationResult:
    delta_changes: list[DeltaAircraftEvent]
    seen_change_count: int
    publishable_change_count: int
    suppressed_change_count: int
    ignored_change_count: int


def state_to_update_dto(state: AircraftState) -> AircraftUpdateDTO:
    return AircraftUpdateDTO(
        aircraft_id=state.aircraft_id,
        updated_at=state.last_seen,
        latitude=state.latitude,
        longitude=state.longitude,
        altitude_ft=state.altitude_ft,
        ground_speed_kt=state.ground_speed_kt,
        heading_deg=state.heading_deg,
        callsign=state.callsign,
    )


def build_snapshot_event(
    states: Iterable[AircraftState],
    *,
    sequence: int,
    sent_at: datetime | None = None,
) -> SnapshotStreamEvent:
    if sent_at is None:
        sent_at = datetime.now(timezone.utc)

    snapshot_payload = [state_to_update_dto(state) for state in states]
    return SnapshotStreamEvent(
        sequence=sequence,
        sent_at=sent_at,
        aircraft=snapshot_payload,
    )


def build_delta_event(
    changes: Iterable[StateChange],
    *,
    sequence: int,
    sent_at: datetime | None = None,
) -> DeltaStreamEvent:
    if sent_at is None:
        sent_at = datetime.now(timezone.utc)
    preparation = prepare_delta_changes(changes)

    return DeltaStreamEvent(
        sequence=sequence,
        sent_at=sent_at,
        changes=preparation.delta_changes,
    )


def prepare_delta_changes(changes: Iterable[StateChange]) -> DeltaPreparationResult:
    delta_changes: list[DeltaAircraftEvent] = []
    seen_change_count = 0
    publishable_change_count = 0
    suppressed_change_count = 0
    ignored_change_count = 0

    for change in changes:
        seen_change_count += 1

        if change.change_type == StateChangeType.IGNORED:
            ignored_change_count += 1
            suppressed_change_count += 1
            continue

        if change.change_type == StateChangeType.REMOVED:
            publishable_change_count += 1
            delta_changes.append(
                DeltaAircraftEvent(
                    action=DeltaAction.REMOVE,
                    aircraft_id=change.aircraft_id,
                    reason=change.reason,
                )
            )
            continue

        if change.change_type == StateChangeType.CREATED:
            if change.state is None:
                raise ValueError("created changes must include state")
            publishable_change_count += 1
            delta_changes.append(
                DeltaAircraftEvent(
                    action=DeltaAction.UPSERT,
                    aircraft_id=change.aircraft_id,
                    aircraft=state_to_update_dto(change.state),
                )
            )
            continue

        if change.change_type == StateChangeType.UPDATED:
            if change.state is None:
                raise ValueError("updated changes must include state")
            if not set(change.changed_fields).intersection(DELTA_PUBLISH_FIELDS):
                suppressed_change_count += 1
                continue
            publishable_change_count += 1
            delta_changes.append(
                DeltaAircraftEvent(
                    action=DeltaAction.UPSERT,
                    aircraft_id=change.aircraft_id,
                    aircraft=state_to_update_dto(change.state),
                )
            )
            continue

        raise ValueError(f"unsupported state change type: {change.change_type}")

    return DeltaPreparationResult(
        delta_changes=delta_changes,
        seen_change_count=seen_change_count,
        publishable_change_count=publishable_change_count,
        suppressed_change_count=suppressed_change_count,
        ignored_change_count=ignored_change_count,
    )
