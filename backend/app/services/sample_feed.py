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
    drift_latitude: float
    drift_longitude: float
    wave_latitude: float
    wave_longitude: float
    wave_phase: float
    wave_frequency: float
    wave_longitude_frequency: float
    altitude_step: int
    speed_step: float
    remove_after_tick: int | None = None


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
                drift_latitude=0.009,
                drift_longitude=0.018,
                wave_latitude=0.0028,
                wave_longitude=0.0046,
                wave_phase=0.0,
                wave_frequency=0.42,
                wave_longitude_frequency=0.88,
                altitude_step=110,
                speed_step=0.7,
            ),
            _SampleAircraft(
                aircraft_id="a8b42f",
                callsign="PGT2YZ",
                latitude=40.9634,
                longitude=29.3092,
                altitude_ft=11825,
                ground_speed_kt=214.8,
                heading_deg=242.0,
                drift_latitude=-0.009,
                drift_longitude=0.018,
                wave_latitude=0.0028,
                wave_longitude=0.0046,
                wave_phase=0.85,
                wave_frequency=0.42,
                wave_longitude_frequency=0.88,
                altitude_step=-160,
                speed_step=0.4,
                remove_after_tick=48,
            ),
            _SampleAircraft(
                aircraft_id="71be10",
                callsign="UAE5KL",
                latitude=41.8020,
                longitude=27.7120,
                altitude_ft=36500,
                ground_speed_kt=456.1,
                heading_deg=118.0,
                drift_latitude=0.009,
                drift_longitude=0.018,
                wave_latitude=0.0028,
                wave_longitude=0.0046,
                wave_phase=1.7,
                wave_frequency=0.42,
                wave_longitude_frequency=0.88,
                altitude_step=110,
                speed_step=0.7,
            ),
            _SampleAircraft(
                aircraft_id="45aa71",
                callsign="SOF2IZ",
                latitude=42.6977,
                longitude=23.3219,
                altitude_ft=28600,
                ground_speed_kt=404.2,
                heading_deg=146.0,
                drift_latitude=-0.0135,
                drift_longitude=0.0152,
                wave_latitude=0.0032,
                wave_longitude=0.0038,
                wave_phase=2.4,
                wave_frequency=0.36,
                wave_longitude_frequency=0.82,
                altitude_step=90,
                speed_step=0.5,
            ),
            _SampleAircraft(
                aircraft_id="3c91ef",
                callsign="ESK4EU",
                latitude=39.7767,
                longitude=30.5206,
                altitude_ft=34750,
                ground_speed_kt=428.6,
                heading_deg=307.0,
                drift_latitude=0.0084,
                drift_longitude=-0.0186,
                wave_latitude=0.0024,
                wave_longitude=0.0044,
                wave_phase=3.15,
                wave_frequency=0.33,
                wave_longitude_frequency=0.94,
                altitude_step=70,
                speed_step=0.6,
            ),
        ]

    def next_batch(self, captured_at: datetime) -> list[AircraftTelemetry]:
        self._tick += 1
        telemetry_batch: list[AircraftTelemetry] = []

        for aircraft in list(self._aircraft):
            if aircraft.remove_after_tick is not None and self._tick >= aircraft.remove_after_tick:
                # Stop emitting this aircraft so stale cleanup can validate removals.
                continue

            previous_latitude = aircraft.latitude
            previous_longitude = aircraft.longitude
            phase = self._tick * aircraft.wave_frequency + aircraft.wave_phase
            aircraft.latitude += aircraft.drift_latitude + math.sin(phase) * aircraft.wave_latitude
            aircraft.longitude += (
                aircraft.drift_longitude
                + math.cos(phase * aircraft.wave_longitude_frequency) * aircraft.wave_longitude
            )
            aircraft.altitude_ft += aircraft.altitude_step
            aircraft.ground_speed_kt += aircraft.speed_step
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
