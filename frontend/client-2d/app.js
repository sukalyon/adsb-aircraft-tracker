import {
  applyDeltaEventToDomainState,
  applySnapshotEventToDomainState,
  createClientDomainState,
  getSelectedAircraft,
  selectAircraftInDomainState,
} from "./state.mjs";
import { createRenderPlan } from "./render-state.mjs";

const DEFAULT_CENTER = [41.0082, 28.9784];
const DEFAULT_ZOOM = 7;
const DEFAULT_WS_URL = buildDefaultWebSocketUrl();
const DEFAULT_AIRCRAFT_API_URL = buildDefaultAircraftApiUrl();
const MAX_LOG_ENTRIES = 14;
const SAMPLE_TICK_MS = 1200;
const LIVE_POLL_INTERVAL_MS = 1000;

const domainState = createClientDomainState({ trailMaxPoints: 16 });
const renderState = new Map();

const runtime = {
  websocket: null,
  sampleTimer: null,
  livePollTimer: null,
  sourceMode: "none",
  transportMode: "none",
  connectionStatus: "idle",
  snapshots: 0,
  deltas: 0,
  upserts: 0,
  removals: 0,
  lastSequence: null,
};

const elements = {
  wsUrlInput: document.querySelector("#ws-url"),
  connectLiveButton: document.querySelector("#connect-live"),
  startSampleButton: document.querySelector("#start-sample"),
  stopSourceButton: document.querySelector("#stop-source"),
  fitAircraftButton: document.querySelector("#fit-aircraft"),
  connectionStatus: document.querySelector("#connection-status"),
  sourceMode: document.querySelector("#source-mode"),
  statConnected: document.querySelector("#stat-connected"),
  statAircraftCount: document.querySelector("#stat-aircraft-count"),
  statSnapshots: document.querySelector("#stat-snapshots"),
  statDeltas: document.querySelector("#stat-deltas"),
  statUpserts: document.querySelector("#stat-upserts"),
  statRemovals: document.querySelector("#stat-removals"),
  statSequence: document.querySelector("#stat-sequence"),
  statSelected: document.querySelector("#stat-selected"),
  selectedAircraft: document.querySelector("#selected-aircraft"),
  eventLog: document.querySelector("#event-log"),
};

const map = L.map("map", {
  zoomControl: true,
  preferCanvas: true,
}).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(map);

initializeUi();
updateSidebar();

function initializeUi() {
  elements.wsUrlInput.value = DEFAULT_WS_URL;
  elements.connectLiveButton.addEventListener("click", connectLiveStream);
  elements.startSampleButton.addEventListener("click", startSampleStream);
  elements.stopSourceButton.addEventListener("click", stopCurrentSource);
  elements.fitAircraftButton.addEventListener("click", fitAircraftBounds);
}

function buildDefaultWebSocketUrl() {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/aircraft`;
  }

  return "ws://localhost:8000/ws/aircraft";
}

function buildDefaultAircraftApiUrl() {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return `${window.location.origin}/api/aircraft`;
  }

  return "http://127.0.0.1:8000/api/aircraft";
}

function connectLiveStream() {
  stopCurrentSource();
  clearVisualizationState();

  const url = elements.wsUrlInput.value.trim() || DEFAULT_WS_URL;
  const socket = new WebSocket(url);
  runtime.websocket = socket;
  runtime.sourceMode = "live";
  runtime.transportMode = "websocket";
  setConnectionStatus("idle", "Connecting");
  pushLog(`Connecting to ${url}`);

  socket.addEventListener("open", () => {
    if (runtime.websocket !== socket) {
      return;
    }
    setConnectionStatus("live", "Connected");
    pushLog("WebSocket connected");
    updateSidebar();
  });

  socket.addEventListener("message", (event) => {
    try {
      handleStreamMessage(JSON.parse(event.data));
    } catch (error) {
      setConnectionStatus("error", "Bad payload");
      pushLog(`Payload error: ${error instanceof Error ? error.message : String(error)}`);
    }
  });

  socket.addEventListener("close", () => {
    if (runtime.websocket === socket) {
      runtime.websocket = null;
      if (runtime.sourceMode === "live" && runtime.transportMode === "websocket") {
        startLivePollingFallback();
        return;
      }
      runtime.sourceMode = "none";
      runtime.transportMode = "none";
      setConnectionStatus("idle", "Disconnected");
      pushLog("WebSocket disconnected");
      updateSidebar();
    }
  });

  socket.addEventListener("error", () => {
    if (runtime.websocket === socket && runtime.sourceMode === "live") {
      pushLog("WebSocket connection error");
    }
  });
}

function startSampleStream() {
  stopCurrentSource();
  clearVisualizationState();

  runtime.sourceMode = "sample";
  runtime.transportMode = "sample";
  setConnectionStatus("sample", "Sample feed");
  pushLog("Sample stream started");

  const sampleAircraft = [
    {
      aircraft_id: "4ca123",
      callsign: "THY7AB",
      latitude: 41.2758,
      longitude: 28.7519,
      altitude_ft: 32000,
      ground_speed_kt: 438.5,
      heading_deg: 92,
    },
    {
      aircraft_id: "a8b42f",
      callsign: "PGT2YZ",
      latitude: 40.9634,
      longitude: 29.3092,
      altitude_ft: 11825,
      ground_speed_kt: 214.8,
      heading_deg: 242,
    },
    {
      aircraft_id: "71be10",
      callsign: "UAE5KL",
      latitude: 41.802,
      longitude: 27.712,
      altitude_ft: 36500,
      ground_speed_kt: 456.1,
      heading_deg: 118,
    },
  ];

  runtime.lastSequence = 1;
  applySnapshotEvent({
    type: "snapshot",
    sequence: 1,
    sent_at: new Date().toISOString(),
    aircraft: sampleAircraft.map((aircraft) => ({
      ...aircraft,
      updated_at: new Date().toISOString(),
    })),
  });

  let tick = 0;
  runtime.sampleTimer = window.setInterval(() => {
    tick += 1;
    const changes = sampleAircraft.map((aircraft, index) => {
      const directionBias = index === 1 ? -1 : 1;
      aircraft.latitude += 0.012 * directionBias;
      aircraft.longitude += 0.024;
      aircraft.altitude_ft += index === 1 ? -160 : 110;
      aircraft.ground_speed_kt += index === 1 ? 0.4 : 0.7;
      aircraft.heading_deg = (aircraft.heading_deg + 4 + index) % 360;

      return {
        action: "upsert",
        aircraft_id: aircraft.aircraft_id,
        aircraft: {
          ...aircraft,
          updated_at: new Date().toISOString(),
        },
      };
    });

    if (tick === 8) {
      changes.push({
        action: "remove",
        aircraft_id: "a8b42f",
        reason: "sample_timeout",
      });
      sampleAircraft.splice(
        sampleAircraft.findIndex((aircraft) => aircraft.aircraft_id === "a8b42f"),
        1,
      );
    }

    const sequence = Number(runtime.lastSequence || 1) + 1;
    applyDeltaEvent({
      type: "delta",
      sequence,
      sent_at: new Date().toISOString(),
      changes,
    });
  }, SAMPLE_TICK_MS);

  updateSidebar();
}

function stopCurrentSource() {
  if (runtime.websocket) {
    runtime.websocket.close();
    runtime.websocket = null;
  }

  if (runtime.sampleTimer !== null) {
    window.clearInterval(runtime.sampleTimer);
    runtime.sampleTimer = null;
  }

  if (runtime.livePollTimer !== null) {
    window.clearInterval(runtime.livePollTimer);
    runtime.livePollTimer = null;
  }

  if (runtime.sourceMode !== "none") {
    runtime.sourceMode = "none";
    runtime.transportMode = "none";
    setConnectionStatus("idle", "Stopped");
    updateSidebar();
  }
}

function startLivePollingFallback() {
  if (runtime.sourceMode !== "live") {
    return;
  }

  if (runtime.livePollTimer !== null) {
    return;
  }

  runtime.transportMode = "polling";
  setConnectionStatus("live", "Polling live");
  pushLog(`WebSocket unavailable, falling back to ${DEFAULT_AIRCRAFT_API_URL}`);

  void pollLiveAircraftSnapshot();
  runtime.livePollTimer = window.setInterval(() => {
    void pollLiveAircraftSnapshot();
  }, LIVE_POLL_INTERVAL_MS);
}

async function pollLiveAircraftSnapshot() {
  try {
    const response = await fetch(DEFAULT_AIRCRAFT_API_URL, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    applySnapshotEvent({
      type: "snapshot",
      sequence: Number(runtime.lastSequence || 0) + 1,
      sent_at: new Date().toISOString(),
      aircraft: payload.aircraft.map((aircraft) => ({
        aircraft_id: aircraft.aircraft_id,
        callsign: aircraft.callsign,
        latitude: aircraft.latitude,
        longitude: aircraft.longitude,
        altitude_ft: aircraft.altitude_ft,
        ground_speed_kt: aircraft.ground_speed_kt,
        heading_deg: aircraft.heading_deg,
        updated_at: aircraft.last_seen,
      })),
    });
  } catch (error) {
    setConnectionStatus("error", "Polling error");
    pushLog(`Live polling error: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function clearVisualizationState() {
  for (const aircraftId of Array.from(renderState.keys())) {
    removeAircraftRender(aircraftId);
  }

  domainState.aircraft.clear();
  domainState.selectedAircraftId = null;
  runtime.snapshots = 0;
  runtime.deltas = 0;
  runtime.upserts = 0;
  runtime.removals = 0;
  runtime.lastSequence = null;
  elements.eventLog.innerHTML = "";
  updateSidebar();
}

function handleStreamMessage(message) {
  if (message.type === "snapshot") {
    applySnapshotEvent(message);
    return;
  }

  if (message.type === "delta") {
    applyDeltaEvent(message);
    return;
  }

  pushLog(`Ignored unknown message type: ${message.type ?? "missing"}`);
}

function applySnapshotEvent(event) {
  runtime.snapshots += 1;
  runtime.lastSequence = event.sequence ?? runtime.lastSequence;
  setConnectionStatus(runtime.sourceMode === "sample" ? "sample" : "live", "Streaming");

  const summary = applySnapshotEventToDomainState(domainState, event);
  runtime.upserts += summary.upsertedAircraftIds.length;
  runtime.removals += summary.removedAircraftIds.length;
  reconcileMapRenderState();

  pushLog(`Snapshot received with ${summary.upsertedAircraftIds.length} aircraft`);
  updateSidebar();
}

function applyDeltaEvent(event) {
  runtime.deltas += 1;
  runtime.lastSequence = event.sequence ?? runtime.lastSequence;

  const summary = applyDeltaEventToDomainState(domainState, event);
  runtime.upserts += summary.upsertedAircraftIds.length;
  runtime.removals += summary.removedAircraftIds.length;
  reconcileMapRenderState();

  pushLog(`Delta received with ${summary.upsertedAircraftIds.length + summary.removedAircraftIds.length} changes`);
  updateSidebar();
}

function reconcileMapRenderState() {
  const plan = createRenderPlan({
    aircraft: domainState.aircraft,
    renderState,
    selectedAircraftId: domainState.selectedAircraftId,
  });

  for (const removal of plan.remove) {
    removeAircraftRender(removal.aircraftId);
  }

  for (const creation of plan.create) {
    createAircraftRender(creation.aircraft);
  }

  for (const update of plan.update) {
    updateAircraftRender(update.aircraft, update.isSelected);
  }

  for (const creation of plan.create) {
    updateAircraftRender(creation.aircraft, creation.isSelected);
  }
}

function createAircraftRender(aircraft) {
  const position = [aircraft.latitude, aircraft.longitude];
  const marker = L.marker(position, {
    icon: buildAircraftIcon(aircraft.heading_deg, false),
    keyboard: false,
  }).addTo(map);

  marker.on("click", () => {
    selectAircraftInDomainState(domainState, aircraft.aircraft_id);
    reconcileMapRenderState();
    updateSidebar();
  });

  const trail = L.polyline(aircraft.trail, {
    color: "#0d8f72",
    weight: 3,
    opacity: 0.7,
  }).addTo(map);

  renderState.set(aircraft.aircraft_id, { marker, trail });
}

function updateAircraftRender(aircraft, isSelected) {
  const renderEntry = renderState.get(aircraft.aircraft_id);
  if (!renderEntry || aircraft.latitude == null || aircraft.longitude == null) {
    return;
  }

  const position = [aircraft.latitude, aircraft.longitude];
  renderEntry.marker.setLatLng(position);
  renderEntry.marker.setIcon(buildAircraftIcon(aircraft.heading_deg, isSelected));
  renderEntry.marker.bindTooltip(aircraft.callsign || aircraft.aircraft_id, {
    direction: "top",
    offset: [0, -12],
    opacity: 0.88,
  });
  renderEntry.trail.setLatLngs(aircraft.trail);
  renderEntry.trail.setStyle({
    color: isSelected ? "#bb5a2a" : "#0d8f72",
    weight: isSelected ? 4 : 3,
  });
}

function removeAircraftRender(aircraftId) {
  const renderEntry = renderState.get(aircraftId);
  if (!renderEntry) {
    return;
  }

  renderEntry.marker.remove();
  renderEntry.trail.remove();
  renderState.delete(aircraftId);
}

function buildAircraftIcon(headingDeg, isSelected) {
  const rotation = Number.isFinite(headingDeg) ? headingDeg : 0;
  const className = isSelected ? "aircraft-icon selected" : "aircraft-icon";

  return L.divIcon({
    className: "leaflet-aircraft-marker",
    html: `<div class="${className}" style="transform: rotate(${rotation}deg)"></div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

function updateSidebar() {
  elements.statConnected.textContent = runtime.connectionStatus === "live" ? "yes" : "no";
  elements.statAircraftCount.textContent = String(domainState.aircraft.size);
  elements.statSnapshots.textContent = String(runtime.snapshots);
  elements.statDeltas.textContent = String(runtime.deltas);
  elements.statUpserts.textContent = String(runtime.upserts);
  elements.statRemovals.textContent = String(runtime.removals);
  elements.statSequence.textContent = runtime.lastSequence == null ? "-" : String(runtime.lastSequence);
  elements.statSelected.textContent = domainState.selectedAircraftId ?? "none";
  elements.sourceMode.textContent = runtime.sourceMode;
  updateSelectedAircraftPanel();
}

function updateSelectedAircraftPanel() {
  const selected = getSelectedAircraft(domainState);

  if (!selected) {
    elements.selectedAircraft.innerHTML = `
      <div>
        <dt>State</dt>
        <dd>No aircraft selected.</dd>
      </div>
    `;
    return;
  }

  elements.selectedAircraft.innerHTML = `
    ${detailRow("Aircraft ID", selected.aircraft_id)}
    ${detailRow("Callsign", selected.callsign ?? "-")}
    ${detailRow("Latitude", formatNumber(selected.latitude, 4))}
    ${detailRow("Longitude", formatNumber(selected.longitude, 4))}
    ${detailRow("Altitude", formatInteger(selected.altitude_ft, " ft"))}
    ${detailRow("Ground Speed", formatNumber(selected.ground_speed_kt, 1, " kt"))}
    ${detailRow("Heading", formatNumber(selected.heading_deg, 1, " deg"))}
    ${detailRow("Trail Points", String(selected.trail.length))}
    ${detailRow("Updated At", selected.updated_at ?? "-")}
  `;
}

function detailRow(label, value) {
  return `
    <div>
      <dt>${label}</dt>
      <dd>${value}</dd>
    </div>
  `;
}

function pushLog(message) {
  const item = document.createElement("li");
  item.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  elements.eventLog.prepend(item);

  while (elements.eventLog.children.length > MAX_LOG_ENTRIES) {
    elements.eventLog.removeChild(elements.eventLog.lastChild);
  }
}

function fitAircraftBounds() {
  const bounds = [];
  for (const aircraft of domainState.aircraft.values()) {
    if (aircraft.latitude != null && aircraft.longitude != null) {
      bounds.push([aircraft.latitude, aircraft.longitude]);
    }
  }

  if (bounds.length === 0) {
    map.flyTo(DEFAULT_CENTER, DEFAULT_ZOOM, { duration: 0.7 });
    return;
  }

  map.fitBounds(bounds, { padding: [48, 48], maxZoom: 9 });
}

function setConnectionStatus(kind, label) {
  runtime.connectionStatus = kind;
  elements.connectionStatus.textContent = label;
  elements.connectionStatus.className = `status-pill status-${kind}`;
  updateSidebar();
}

function formatNumber(value, digits, suffix = "") {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatInteger(value, suffix = "") {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return `${Math.round(Number(value))}${suffix}`;
}
