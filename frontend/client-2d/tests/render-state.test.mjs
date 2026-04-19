import assert from "node:assert/strict";
import test from "node:test";

import { createRenderPlan } from "../render-state.mjs";

test("render plan separates create, update, and remove operations", () => {
  const aircraft = new Map([
    [
      "4ca123",
      {
        aircraft_id: "4ca123",
        latitude: 41.0,
        longitude: 29.0,
        heading_deg: 90,
        trail: [[41.0, 29.0]],
      },
    ],
    [
      "a8b42f",
      {
        aircraft_id: "a8b42f",
        latitude: 40.9,
        longitude: 29.3,
        heading_deg: 240,
        trail: [[40.9, 29.3]],
      },
    ],
  ]);

  const renderState = new Map([
    ["4ca123", { marker: {}, trail: {} }],
    ["dead01", { marker: {}, trail: {} }],
  ]);

  const plan = createRenderPlan({
    aircraft,
    renderState,
    selectedAircraftId: "4ca123",
  });

  assert.equal(plan.create.length, 1);
  assert.equal(plan.create[0].aircraftId, "a8b42f");
  assert.equal(plan.update.length, 1);
  assert.equal(plan.update[0].aircraftId, "4ca123");
  assert.equal(plan.update[0].isSelected, true);
  assert.equal(plan.remove.length, 1);
  assert.deepEqual(plan.remove[0], {
    aircraftId: "dead01",
    reason: "missing_from_domain",
  });
});

test("render plan removes positionless aircraft from render cache", () => {
  const aircraft = new Map([
    [
      "4ca123",
      {
        aircraft_id: "4ca123",
        latitude: null,
        longitude: null,
        trail: [],
      },
    ],
  ]);

  const renderState = new Map([["4ca123", { marker: {}, trail: {} }]]);

  const plan = createRenderPlan({
    aircraft,
    renderState,
    selectedAircraftId: null,
  });

  assert.equal(plan.create.length, 0);
  assert.equal(plan.update.length, 0);
  assert.deepEqual(plan.remove, [{ aircraftId: "4ca123", reason: "no_position" }]);
});
