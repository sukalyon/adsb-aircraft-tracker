from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.aircraft import AircraftTelemetry
from app.runtime import RealtimePipeline


@dataclass(slots=True)
class _SampleAircraft:
    aircraft_id: str
    callsign: str
    latitude: float
    longitude: float
    altitude_ft: int
    ground_speed_kt: float
    heading_deg: float


class SampleTelemetryScenario:
    """Produce deterministic moving telemetry for the 2D operations client."""

    def __init__(self) -> None:
        self._tick = 0
        self._aircraft = [
            _SampleAircraft(
                aircraft_id="4ca123",
                callsign="THY7AB",
                latitude=41.2758,
                longitude=28.7519,
                altitude_ft=32000,
                ground_speed_kt=438.5,
                heading_deg=92.0,
            ),
            _SampleAircraft(
                aircraft_id="a8b42f",
                callsign="PGT2YZ",
                latitude=40.9634,
                longitude=29.3092,
                altitude_ft=11825,
                ground_speed_kt=214.8,
                heading_deg=242.0,
            ),
            _SampleAircraft(
                aircraft_id="71be10",
                callsign="UAE5KL",
                latitude=41.8020,
                longitude=27.7120,
                altitude_ft=36500,
                ground_speed_kt=456.1,
                heading_deg=118.0,
            ),
        ]

    def next_batch(self, captured_at: datetime) -> list[AircraftTelemetry]:
        self._tick += 1
        telemetry_batch: list[AircraftTelemetry] = []

        for index, aircraft in enumerate(list(self._aircraft)):
            if aircraft.aircraft_id == "a8b42f" and self._tick >= 9:
                # Stop emitting this aircraft so stale cleanup can validate removals.
                continue

            previous_latitude = aircraft.latitude
            previous_longitude = aircraft.longitude
            direction_bias = -1 if aircraft.aircraft_id == "a8b42f" else 1
            phase = self._tick * 0.42 + index * 0.85
            aircraft.latitude += 0.009 * direction_bias + math.sin(phase) * 0.0028
            aircraft.longitude += 0.018 + math.cos(phase * 0.88) * 0.0046
            aircraft.altitude_ft += -160 if aircraft.aircraft_id == "a8b42f" else 110
            aircraft.ground_speed_kt += 0.4 if aircraft.aircraft_id == "a8b42f" else 0.7
            aircraft.heading_deg = _calculate_bearing(
                previous_latitude,
                previous_longitude,
                aircraft.latitude,
                aircraft.longitude,
            )

            telemetry_batch.append(
                AircraftTelemetry(
                    aircraft_id=aircraft.aircraft_id,
                    captured_at=captured_at,
                    source="sample",
                    callsign=aircraft.callsign,
                    latitude=round(aircraft.latitude, 4),
                    longitude=round(aircraft.longitude, 4),
                    altitude_ft=aircraft.altitude_ft,
                    ground_speed_kt=round(aircraft.ground_speed_kt, 1),
                    heading_deg=round(aircraft.heading_deg, 1),
                )
            )

        return telemetry_batch


async def run_sample_feed(
    pipeline: RealtimePipeline,
    *,
    interval_seconds: float = 1.2,
) -> None:
    """Continuously publish sample telemetry into the live websocket pipeline."""

    scenario = SampleTelemetryScenario()

    try:
        while True:
            now = datetime.now(timezone.utc)
            telemetry_batch = scenario.next_batch(now)
            await pipeline.process_telemetry_batch(telemetry_batch)
            await pipeline.expire_stale_tracks(reference_time=now)
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        raise


def _calculate_bearing(
    from_latitude: float,
    from_longitude: float,
    to_latitude: float,
    to_longitude: float,
) -> float:
    delta_longitude = to_longitude - from_longitude
    delta_latitude = to_latitude - from_latitude
    if delta_longitude == 0.0 and delta_latitude == 0.0:
        return 0.0

    return (math.degrees(math.atan2(delta_longitude, delta_latitude)) + 360.0) % 360.0
