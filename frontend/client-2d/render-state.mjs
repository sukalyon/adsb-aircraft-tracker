export function createRenderPlan({ aircraft, renderState, selectedAircraftId }) {
  const create = [];
  const update = [];
  const remove = [];
  const seenRenderIds = new Set();

  for (const [aircraftId, currentAircraft] of aircraft.entries()) {
    const isSelected = selectedAircraftId === aircraftId;
    const hasPosition =
      currentAircraft.latitude != null && currentAircraft.longitude != null;
    const existingRenderEntry = renderState.get(aircraftId);

    if (!hasPosition) {
      if (existingRenderEntry) {
        remove.push({ aircraftId, reason: "no_position" });
      }
      continue;
    }

    const entry = {
      aircraftId,
      aircraft: currentAircraft,
      isSelected,
    };

    if (existingRenderEntry) {
      update.push(entry);
      seenRenderIds.add(aircraftId);
      continue;
    }

    create.push(entry);
  }

  for (const aircraftId of renderState.keys()) {
    if (seenRenderIds.has(aircraftId)) {
      continue;
    }
    if (aircraft.has(aircraftId)) {
      continue;
    }
    remove.push({ aircraftId, reason: "missing_from_domain" });
  }

  return { create, update, remove };
}
