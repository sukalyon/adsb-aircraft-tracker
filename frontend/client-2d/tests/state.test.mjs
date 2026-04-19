import assert from "node:assert/strict";
import test from "node:test";

import {
  applyDeltaEventToDomainState,
  applySnapshotEventToDomainState,
  createClientDomainState,
  getSelectedAircraft,
  selectAircraftInDomainState,
} from "../state.mjs";

test("snapshot removes aircraft missing from the new snapshot", () => {
  const domainState = createClientDomainState();

  applySnapshotEventToDomainState(domainState, {
    aircraft: [
      {
        aircraft_id: "4ca123",
        latitude: 41.0,
        longitude: 29.0,
        updated_at: "2026-04-19T10:00:00Z",
      },
      {
        aircraft_id: "a8b42f",
        latitude: 40.9,
        longitude: 29.3,
        updated_at: "2026-04-19T10:00:00Z",
      },
    ],
  });

  const summary = applySnapshotEventToDomainState(domainState, {
    aircraft: [
      {
        aircraft_id: "4ca123",
        latitude: 41.1,
        longitude: 29.1,
        updated_at: "2026-04-19T10:00:05Z",
      },
    ],
  });

  assert.equal(domainState.aircraft.size, 1);
  assert.deepEqual(summary.removedAircraftIds, ["a8b42f"]);
});

test("delta upsert preserves previous values and bounds trail length", () => {
  const domainState = createClientDomainState({ trailMaxPoints: 2 });

  applyDeltaEventToDomainState(domainState, {
    changes: [
      {
        action: "upsert",
        aircraft: {
          aircraft_id: "4ca123",
          callsign: "THY7AB",
          latitude: 41.0,
          longitude: 29.0,
          altitude_ft: 30000,
          updated_at: "2026-04-19T10:00:00Z",
        },
      },
      {
        action: "upsert",
        aircraft: {
          aircraft_id: "4ca123",
          latitude: 41.1,
          longitude: 29.1,
          updated_at: "2026-04-19T10:00:05Z",
        },
      },
      {
        action: "upsert",
        aircraft: {
          aircraft_id: "4ca123",
          ground_speed_kt: 440.0,
          latitude: 41.2,
          longitude: 29.2,
          updated_at: "2026-04-19T10:00:10Z",
        },
      },
    ],
  });

  const aircraft = domainState.aircraft.get("4ca123");

  assert.ok(aircraft);
  assert.equal(aircraft.callsign, "THY7AB");
  assert.equal(aircraft.ground_speed_kt, 440.0);
  assert.equal(aircraft.trail.length, 2);
  assert.deepEqual(aircraft.trail[0], [41.1, 29.1]);
  assert.deepEqual(aircraft.trail[1], [41.2, 29.2]);
});

test("removing a selected aircraft clears the selection", () => {
  const domainState = createClientDomainState();

  applyDeltaEventToDomainState(domainState, {
    changes: [
      {
        action: "upsert",
        aircraft: {
          aircraft_id: "4ca123",
          latitude: 41.0,
          longitude: 29.0,
          updated_at: "2026-04-19T10:00:00Z",
        },
      },
    ],
  });

  selectAircraftInDomainState(domainState, "4ca123");
  applyDeltaEventToDomainState(domainState, {
    changes: [{ action: "remove", aircraft_id: "4ca123" }],
  });

  assert.equal(domainState.selectedAircraftId, null);
  assert.equal(getSelectedAircraft(domainState), null);
});
