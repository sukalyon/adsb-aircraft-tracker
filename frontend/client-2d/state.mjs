export function createClientDomainState({ trailMaxPoints } = {}) {
  return {
    aircraft: new Map(),
    selectedAircraftId: null,
    trailMaxPoints: trailMaxPoints ?? 16,
  };
}

export function applySnapshotEventToDomainState(domainState, event) {
  const seenAircraftIds = new Set();
  const upsertedAircraftIds = [];
  const removedAircraftIds = [];
  const aircraftEntries = Array.isArray(event.aircraft) ? event.aircraft : [];

  for (const aircraft of aircraftEntries) {
    if (!aircraft?.aircraft_id) {
      continue;
    }
    seenAircraftIds.add(aircraft.aircraft_id);
    upsertAircraftInDomainState(domainState, aircraft);
    upsertedAircraftIds.push(aircraft.aircraft_id);
  }

  for (const aircraftId of Array.from(domainState.aircraft.keys())) {
    if (seenAircraftIds.has(aircraftId)) {
      continue;
    }
    removeAircraftFromDomainState(domainState, aircraftId);
    removedAircraftIds.push(aircraftId);
  }

  return {
    upsertedAircraftIds,
    removedAircraftIds,
    aircraftCount: domainState.aircraft.size,
  };
}

export function applyDeltaEventToDomainState(domainState, event) {
  const upsertedAircraftIds = [];
  const removedAircraftIds = [];
  const changes = Array.isArray(event.changes) ? event.changes : [];

  for (const change of changes) {
    if (change?.action === "upsert" && change.aircraft?.aircraft_id) {
      upsertAircraftInDomainState(domainState, change.aircraft);
      upsertedAircraftIds.push(change.aircraft.aircraft_id);
      continue;
    }

    if (change?.action === "remove" && change.aircraft_id) {
      removeAircraftFromDomainState(domainState, change.aircraft_id);
      removedAircraftIds.push(change.aircraft_id);
    }
  }

  return {
    upsertedAircraftIds,
    removedAircraftIds,
    aircraftCount: domainState.aircraft.size,
  };
}

export function upsertAircraftInDomainState(domainState, aircraft) {
  const previous = domainState.aircraft.get(aircraft.aircraft_id);
  const next = {
    aircraft_id: aircraft.aircraft_id,
    callsign: aircraft.callsign ?? previous?.callsign ?? null,
    latitude: aircraft.latitude ?? previous?.latitude ?? null,
    longitude: aircraft.longitude ?? previous?.longitude ?? null,
    altitude_ft: aircraft.altitude_ft ?? previous?.altitude_ft ?? null,
    ground_speed_kt: aircraft.ground_speed_kt ?? previous?.ground_speed_kt ?? null,
    heading_deg: aircraft.heading_deg ?? previous?.heading_deg ?? null,
    updated_at: aircraft.updated_at ?? previous?.updated_at ?? null,
    trail: previous?.trail ? [...previous.trail] : [],
  };

  appendTrailPoint(next, domainState.trailMaxPoints);
  domainState.aircraft.set(next.aircraft_id, next);
  return next;
}

export function removeAircraftFromDomainState(domainState, aircraftId) {
  domainState.aircraft.delete(aircraftId);

  if (domainState.selectedAircraftId === aircraftId) {
    domainState.selectedAircraftId = null;
  }
}

export function selectAircraftInDomainState(domainState, aircraftId) {
  if (!aircraftId || !domainState.aircraft.has(aircraftId)) {
    domainState.selectedAircraftId = null;
    return null;
  }

  domainState.selectedAircraftId = aircraftId;
  return domainState.aircraft.get(aircraftId) ?? null;
}

export function getSelectedAircraft(domainState) {
  if (!domainState.selectedAircraftId) {
    return null;
  }
  return domainState.aircraft.get(domainState.selectedAircraftId) ?? null;
}

function appendTrailPoint(aircraft, trailMaxPoints) {
  if (aircraft.latitude == null || aircraft.longitude == null) {
    return;
  }

  const nextPoint = [aircraft.latitude, aircraft.longitude];
  const lastPoint = aircraft.trail.at(-1);
  if (lastPoint && lastPoint[0] === nextPoint[0] && lastPoint[1] === nextPoint[1]) {
    return;
  }

  aircraft.trail.push(nextPoint);
  if (aircraft.trail.length > trailMaxPoints) {
    aircraft.trail.splice(0, aircraft.trail.length - trailMaxPoints);
  }
}
