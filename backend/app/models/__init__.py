"""Canonical data models used across ingestion, normalization, and state layers."""

from .aircraft import (
    AircraftMetadata,
    AircraftState,
    AircraftTelemetry,
    AircraftUpdateDTO,
    RawAircraftMessage,
    TrackStatus,
    TrailPoint,
    parse_timestamp,
)

__all__ = [
    "AircraftMetadata",
    "AircraftState",
    "AircraftTelemetry",
    "AircraftUpdateDTO",
    "RawAircraftMessage",
    "TrackStatus",
    "TrailPoint",
    "parse_timestamp",
]
