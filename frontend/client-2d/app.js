import {
  applyDeltaEventToDomainState,
  applySnapshotEventToDomainState,
  createClientDomainState,
  getSelectedAircraft,
  selectAircraftInDomainState,
} from "./state.mjs";
import { createRenderPlan } from "./render-state.mjs";

const DEFAULT_CENTER = [41.0082, 28.9784];
const DEFAULT_ZOOM = 5;
const DEFAULT_WS_URL = buildDefaultWebSocketUrl();
const DEFAULT_AIRCRAFT_API_URL = buildDefaultAircraftApiUrl();
const DEFAULT_SOURCE_API_URL = buildDefaultSourceApiUrl();
const MAX_LOG_ENTRIES = 14;
const SAMPLE_TICK_MS = 1200;
const LIVE_POLL_INTERVAL_MS = 1000;
const TRAIL_SPLINE_SAMPLES = 7;
const TRAIL_TWO_POINT_SAMPLES = 18;
const TRAIL_TAIL_OFFSET_PX = 14;
const PANEL_STACK_GAP = 12;
const PANEL_EDGE_GAP_WIDE = 16;
const PANEL_EDGE_GAP_COMPACT = 12;
const FLOATING_PANEL_MARGIN = 8;
const sessionStartedAt = Date.now();

const domainState = createClientDomainState({ trailMaxPoints: Number.POSITIVE_INFINITY });
const renderState = new Map();
let floatingPanelLayoutFrame = null;

const runtime = {
  websocket: null,
  sampleTimer: null,
  livePollTimer: null,
  sourceMode: "none",
  activeSourceId: null,
  activeSourceLabel: null,
  activeSourceKind: "none",
  selectedSourceId: "sample",
  selectedSourceLabel: "Sample",
  sourceOptions: buildFallbackSourceOptions(),
  sourceControlAvailable: false,
  transportMode: "none",
  connectionStatus: "idle",
  connectionLabel: "Stopped",
  mapStyle: "satellite",
  snapshots: 0,
  deltas: 0,
  upserts: 0,
  removals: 0,
  lastSequence: null,
  lastActivityAt: null,
  searchQuery: "",
};

const floatingPanels = {
  activeDrag: null,
  zIndexSeed: 20,
  selected: { moved: false },
  traffic: { moved: false },
  debug: { moved: false },
};

const elements = {
  stage: document.querySelector(".tactical-stage"),
  wsUrlInput: document.querySelector("#ws-url"),
  sourceSelect: document.querySelector("#source-select"),
  connectSourceButton: document.querySelector("#connect-source"),
  stopSourceButton: document.querySelector("#stop-source"),
  fitAircraftButton: document.querySelector("#fit-aircraft"),
  clearUiButton: document.querySelector("#clear-ui"),
  focusSelectedButton: document.querySelector("#focus-selected"),
  clearSelectionButton: document.querySelector("#clear-selection"),
  selectedDragHandle: document.querySelector("#selected-drag-handle"),
  trafficDragHandle: document.querySelector("#traffic-drag-handle"),
  debugDragHandle: document.querySelector("#debug-drag-handle"),
  aircraftSearchInput: document.querySelector("#aircraft-search"),
  liveIndicator: document.querySelector("#live-indicator"),
  selectedPanel: document.querySelector("#selected-panel"),
  trafficPanel: document.querySelector("#traffic-panel"),
  debugDrawer: document.querySelector("#debug-drawer"),
  selectedTitle: document.querySelector("#selected-title"),
  selectedSummary: document.querySelector("#selected-summary"),
  selectedAircraft: document.querySelector("#selected-aircraft"),
  trafficSummary: document.querySelector("#traffic-summary"),
  emptyTraffic: document.querySelector("#empty-traffic"),
  aircraftList: document.querySelector("#aircraft-list"),
  statConnected: document.querySelector("#stat-connected"),
  statAircraftCount: document.querySelector("#stat-aircraft-count"),
  statSnapshots: document.querySelector("#stat-snapshots"),
  statDeltas: document.querySelector("#stat-deltas"),
  statUpserts: document.querySelector("#stat-upserts"),
  statRemovals: document.querySelector("#stat-removals"),
  statSequence: document.querySelector("#stat-sequence"),
  statSelected: document.querySelector("#stat-selected"),
  eventLog: document.querySelector("#event-log"),
  footerTime: document.querySelector("#footer-time"),
  footerUptime: document.querySelector("#footer-uptime"),
  footerLink: document.querySelector("#footer-link"),
  footerSource: document.querySelector("#footer-source"),
  footerTransport: document.querySelector("#footer-transport"),
  footerActivity: document.querySelector("#footer-activity"),
  mapStyleSelect: document.querySelector("#map-style"),
};

const map = L.map("map", {
  attributionControl: false,
  preferCanvas: true,
  zoomControl: true,
}).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

L.control.attribution({
  position: "bottomleft",
  prefix: false,
}).addTo(map);

const mapLayers = createMapLayers();
let activeBaseLayer = null;

initializeUi();
setMapStyle(runtime.mapStyle);
updatePanels();
updateClockDisplay();

function initializeUi() {
  elements.wsUrlInput.value = DEFAULT_WS_URL;
  elements.mapStyleSelect.value = runtime.mapStyle;
  renderSourceOptions();

  elements.connectSourceButton.addEventListener("click", () => {
    void connectSelectedSource();
  });
  elements.stopSourceButton.addEventListener("click", () => {
    void stopCurrentSource();
  });
  elements.fitAircraftButton.addEventListener("click", fitAircraftBounds);
  elements.clearUiButton.addEventListener("click", clearUiState);
  elements.focusSelectedButton.addEventListener("click", focusSelectedAircraft);
  elements.clearSelectionButton.addEventListener("click", clearSelectedAircraft);
  elements.aircraftSearchInput.addEventListener("input", handleAircraftSearchInput);
  elements.mapStyleSelect.addEventListener("change", handleMapStyleChange);
  elements.sourceSelect.addEventListener("change", handleSourceSelectionChange);
  elements.wsUrlInput.addEventListener("change", () => {
    void handleWebSocketUrlChange();
  });
  elements.debugDrawer.addEventListener("toggle", queueFloatingPanelLayout);

  map.on("click", () => {
    if (domainState.selectedAircraftId) {
      clearSelectedAircraft();
    }
  });
  map.on("zoomend", reconcileMapRenderState);

  initializeFloatingPanels();
  window.addEventListener("resize", handleFloatingPanelResize);
  window.setInterval(updateClockDisplay, 1000);
  void refreshSourceControlState({ quiet: true });
}

function initializeFloatingPanels() {
  registerDraggablePanel("selected", elements.selectedPanel, elements.selectedDragHandle);
  registerDraggablePanel("traffic", elements.trafficPanel, elements.trafficDragHandle);
  registerDraggablePanel("debug", elements.debugDrawer, elements.debugDragHandle);
  queueFloatingPanelLayout();
}

function registerDraggablePanel(panelId, panelElement, handleElement) {
  handleElement.addEventListener("pointerdown", (event) => {
    startPanelDrag(event, panelId);
  });

  handleElement.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
  });

  panelElement.addEventListener("pointerdown", () => {
    bringPanelToFront(panelId);
  });
}

function startPanelDrag(event, panelId) {
  if (event.button !== 0) {
    return;
  }

  const panelElement = getFloatingPanelElement(panelId);
  if (!panelElement || panelElement.hidden) {
    return;
  }

  event.preventDefault();
  event.stopPropagation();

  const stageRect = elements.stage.getBoundingClientRect();
  const panelRect = panelElement.getBoundingClientRect();
  pinPanelToCurrentPosition(panelId, panelRect, stageRect);
  floatingPanels[panelId].moved = true;
  bringPanelToFront(panelId);

  panelElement.classList.add("is-dragging");
  floatingPanels.activeDrag = {
    panelId,
    pointerId: event.pointerId,
    offsetX: event.clientX - panelRect.left,
    offsetY: event.clientY - panelRect.top,
  };

  event.currentTarget.setPointerCapture?.(event.pointerId);
  window.addEventListener("pointermove", handlePanelDrag);
  window.addEventListener("pointerup", endPanelDrag);
  window.addEventListener("pointercancel", endPanelDrag);
}

function handlePanelDrag(event) {
  const activeDrag = floatingPanels.activeDrag;
  if (!activeDrag || event.pointerId !== activeDrag.pointerId) {
    return;
  }

  const panelElement = getFloatingPanelElement(activeDrag.panelId);
  if (!panelElement) {
    return;
  }

  const stageRect = elements.stage.getBoundingClientRect();
  const panelWidth = panelElement.offsetWidth;
  const panelHeight = panelElement.offsetHeight;
  const maxLeft = Math.max(FLOATING_PANEL_MARGIN, stageRect.width - panelWidth - FLOATING_PANEL_MARGIN);
  const maxTop = Math.max(FLOATING_PANEL_MARGIN, stageRect.height - panelHeight - FLOATING_PANEL_MARGIN);
  const left = clamp(
    event.clientX - stageRect.left - activeDrag.offsetX,
    FLOATING_PANEL_MARGIN,
    maxLeft,
  );
  const top = clamp(
    event.clientY - stageRect.top - activeDrag.offsetY,
    FLOATING_PANEL_MARGIN,
    maxTop,
  );
  const resolvedPosition = resolveFloatingPanelCollision(activeDrag.panelId, { left, top }, stageRect);

  panelElement.style.left = `${Math.round(resolvedPosition.left)}px`;
  panelElement.style.top = `${Math.round(resolvedPosition.top)}px`;
  panelElement.style.right = "auto";
  panelElement.style.bottom = "auto";

  if (activeDrag.panelId === "selected" && !floatingPanels.traffic.moved) {
    queueFloatingPanelLayout();
  }
}

function endPanelDrag(event) {
  const activeDrag = floatingPanels.activeDrag;
  if (!activeDrag || event.pointerId !== activeDrag.pointerId) {
    return;
  }

  const panelElement = getFloatingPanelElement(activeDrag.panelId);
  if (panelElement) {
    panelElement.classList.remove("is-dragging");
  }

  floatingPanels.activeDrag = null;
  window.removeEventListener("pointermove", handlePanelDrag);
  window.removeEventListener("pointerup", endPanelDrag);
  window.removeEventListener("pointercancel", endPanelDrag);
}

function handleFloatingPanelResize() {
  queueFloatingPanelLayout();
}

function queueFloatingPanelLayout() {
  if (floatingPanelLayoutFrame !== null) {
    return;
  }

  floatingPanelLayoutFrame = window.requestAnimationFrame(() => {
    floatingPanelLayoutFrame = null;
    syncFloatingPanelLayout();
  });
}

function syncFloatingPanelLayout() {
  const stageRect = elements.stage.getBoundingClientRect();
  if (stageRect.width <= 0 || stageRect.height <= 0) {
    return;
  }

  const horizontalGap = getFloatingHorizontalGap();
  const topGap = getFloatingTopGap();
  const trafficBottomGap = getTrafficBottomGap();
  const rightPanelWidth = getRightPanelWidth(stageRect.width);

  if (!floatingPanels.selected.moved) {
    positionFloatingPanel(elements.selectedPanel, {
      left: stageRect.width - rightPanelWidth - horizontalGap,
      top: topGap,
      width: rightPanelWidth,
    });
  }

  if (!floatingPanels.traffic.moved) {
    const trafficLeft = stageRect.width - rightPanelWidth - horizontalGap;
    let trafficTop = topGap;

    if (!elements.selectedPanel.hidden) {
      const selectedRect = elements.selectedPanel.getBoundingClientRect();
      if (shouldStackTrafficBelowSelected(selectedRect, stageRect, trafficLeft, rightPanelWidth)) {
        const selectedTop = selectedRect.top - stageRect.top;
        trafficTop = selectedTop + selectedRect.height + PANEL_STACK_GAP;
      }
    }

    positionFloatingPanel(elements.trafficPanel, {
      left: trafficLeft,
      top: Math.min(trafficTop, Math.max(topGap, stageRect.height - 220)),
      bottom: trafficBottomGap,
      width: rightPanelWidth,
    });
  }

  if (!floatingPanels.debug.moved) {
    positionFloatingPanel(elements.debugDrawer, {
      left: horizontalGap,
      bottom: getDebugBottomGap(),
      width: getDebugPanelWidth(stageRect.width),
    });
  }

  clampMovedFloatingPanels();

  elements.selectedPanel.style.zIndex = "9";
  elements.trafficPanel.style.zIndex = "8";
  elements.debugDrawer.style.zIndex = "7";
}

function positionFloatingPanel(panelElement, { left, top = null, bottom = null, width }) {
  panelElement.style.width = `${Math.round(width)}px`;
  panelElement.style.left = `${Math.round(left)}px`;
  panelElement.style.right = "auto";
  panelElement.style.top = top == null ? "auto" : `${Math.round(top)}px`;
  panelElement.style.bottom = bottom == null ? "auto" : `${Math.round(bottom)}px`;
  panelElement.style.height = "";
}

function clampMovedFloatingPanels() {
  const stageRect = elements.stage.getBoundingClientRect();

  for (const panelId of ["selected", "traffic", "debug"]) {
    const panelState = floatingPanels[panelId];
    if (!panelState.moved) {
      continue;
    }

    const panelElement = getFloatingPanelElement(panelId);
    if (!panelElement || panelElement.hidden) {
      continue;
    }

    const panelRect = panelElement.getBoundingClientRect();
    const panelWidth = panelRect.width;
    const panelHeight = panelRect.height;
    const left = parseFloat(panelElement.style.left);
    const top = parseFloat(panelElement.style.top);
    const maxLeft = Math.max(FLOATING_PANEL_MARGIN, stageRect.width - panelWidth - FLOATING_PANEL_MARGIN);
    const maxTop = Math.max(FLOATING_PANEL_MARGIN, stageRect.height - panelHeight - FLOATING_PANEL_MARGIN);
    let nextLeft = Number.isFinite(left) ? clamp(left, FLOATING_PANEL_MARGIN, maxLeft) : FLOATING_PANEL_MARGIN;
    let nextTop = Number.isFinite(top) ? clamp(top, FLOATING_PANEL_MARGIN, maxTop) : FLOATING_PANEL_MARGIN;

    ({ left: nextLeft, top: nextTop } = resolveFloatingPanelCollision(
      panelId,
      { left: nextLeft, top: nextTop },
      stageRect,
    ));

    panelElement.style.left = `${Math.round(nextLeft)}px`;
    panelElement.style.top = `${Math.round(nextTop)}px`;
  }
}

function pinPanelToCurrentPosition(panelId, panelRect, stageRect) {
  const panelElement = getFloatingPanelElement(panelId);
  if (!panelElement) {
    return;
  }

  panelElement.style.left = `${Math.round(panelRect.left - stageRect.left)}px`;
  panelElement.style.top = `${Math.round(panelRect.top - stageRect.top)}px`;
  panelElement.style.right = "auto";
  panelElement.style.bottom = "auto";
  panelElement.style.width = `${Math.round(panelRect.width)}px`;
  panelElement.style.height = panelId === "traffic" ? `${Math.round(panelRect.height)}px` : "";
}

function bringPanelToFront(panelId) {
  const panelElement = getFloatingPanelElement(panelId);
  if (!panelElement || panelElement.hidden) {
    return;
  }

  panelElement.style.zIndex = String(floatingPanels.zIndexSeed);
  floatingPanels.zIndexSeed += 1;
}

function getFloatingPanelElement(panelId) {
  if (panelId === "selected") {
    return elements.selectedPanel;
  }
  if (panelId === "traffic") {
    return elements.trafficPanel;
  }
  if (panelId === "debug") {
    return elements.debugDrawer;
  }
  return null;
}

function resolveFloatingPanelCollision(panelId, proposedPosition, stageRect) {
  const panelElement = getFloatingPanelElement(panelId);
  if (!panelElement) {
    return proposedPosition;
  }

  const panelWidth = panelElement.offsetWidth;
  const panelHeight = panelElement.offsetHeight;
  const otherRects = getOtherFloatingPanelRects(panelId, stageRect);
  const basePosition = {
    left: clampFloatingPanelLeft(proposedPosition.left, stageRect.width, panelWidth),
    top: clampFloatingPanelTop(proposedPosition.top, stageRect.height, panelHeight),
  };

  let resolvedPosition = basePosition;

  for (let attempt = 0; attempt < otherRects.length * 4; attempt += 1) {
    const currentRect = {
      left: resolvedPosition.left,
      top: resolvedPosition.top,
      width: panelWidth,
      height: panelHeight,
    };
    const overlapRect = otherRects.find((otherRect) =>
      rectanglesOverlap(currentRect, otherRect, PANEL_STACK_GAP),
    );

    if (!overlapRect) {
      return resolvedPosition;
    }

    const candidatePositions = buildCollisionCandidates(
      currentRect,
      overlapRect,
      stageRect,
      panelWidth,
      panelHeight,
    );
    const bestCandidate = pickBestCollisionCandidate(
      panelId,
      candidatePositions,
      basePosition,
      otherRects,
      panelWidth,
      panelHeight,
    );

    if (!bestCandidate) {
      return resolvedPosition;
    }

    resolvedPosition = bestCandidate;
  }

  return resolvedPosition;
}

function shouldStackTrafficBelowSelected(selectedRect, stageRect, trafficLeft, rightPanelWidth) {
  const selectedLeft = selectedRect.left - stageRect.left;
  const selectedRight = selectedLeft + selectedRect.width;
  const selectedCenter = selectedLeft + selectedRect.width / 2;
  const trafficRight = trafficLeft + rightPanelWidth;
  const overlapsTrafficRail =
    selectedRight > trafficLeft - PANEL_STACK_GAP &&
    selectedLeft < trafficRight + PANEL_STACK_GAP;
  const anchoredOnRightSide =
    !floatingPanels.selected.moved || selectedCenter >= stageRect.width * 0.56;

  return overlapsTrafficRail || anchoredOnRightSide;
}

function getOtherFloatingPanelRects(panelId, stageRect) {
  const panelIds = ["selected", "traffic", "debug"];
  const rects = [];

  for (const otherPanelId of panelIds) {
    if (otherPanelId === panelId) {
      continue;
    }

    const otherPanel = getFloatingPanelElement(otherPanelId);
    if (!otherPanel || otherPanel.hidden) {
      continue;
    }

    const otherRect = otherPanel.getBoundingClientRect();
    rects.push({
      left: otherRect.left - stageRect.left,
      top: otherRect.top - stageRect.top,
      width: otherRect.width,
      height: otherRect.height,
    });
  }

  return rects;
}

function buildCollisionCandidates(currentRect, overlapRect, stageRect, panelWidth, panelHeight) {
  const leftOfOverlap = overlapRect.left - panelWidth - PANEL_STACK_GAP;
  const rightOfOverlap = overlapRect.left + overlapRect.width + PANEL_STACK_GAP;
  const aboveOverlap = overlapRect.top - panelHeight - PANEL_STACK_GAP;
  const belowOverlap = overlapRect.top + overlapRect.height + PANEL_STACK_GAP;
  const candidates = [
    { left: currentRect.left, top: aboveOverlap },
    { left: currentRect.left, top: belowOverlap },
    { left: leftOfOverlap, top: currentRect.top },
    { left: rightOfOverlap, top: currentRect.top },
    { left: leftOfOverlap, top: aboveOverlap },
    { left: rightOfOverlap, top: aboveOverlap },
    { left: leftOfOverlap, top: belowOverlap },
    { left: rightOfOverlap, top: belowOverlap },
  ];

  return candidates.map((candidate) => ({
    left: clampFloatingPanelLeft(candidate.left, stageRect.width, panelWidth),
    top: clampFloatingPanelTop(candidate.top, stageRect.height, panelHeight),
  }));
}

function pickBestCollisionCandidate(
  panelId,
  candidatePositions,
  basePosition,
  otherRects,
  panelWidth,
  panelHeight,
) {
  let bestCandidate = null;
  let bestScore = Number.POSITIVE_INFINITY;
  const preferVerticalStack = panelId === "selected" || panelId === "traffic";

  for (const candidatePosition of candidatePositions) {
    const candidateRect = {
      left: candidatePosition.left,
      top: candidatePosition.top,
      width: panelWidth,
      height: panelHeight,
    };
    const overlapCount = otherRects.reduce((count, otherRect) => {
      return count + (rectanglesOverlap(candidateRect, otherRect, PANEL_STACK_GAP) ? 1 : 0);
    }, 0);
    const deltaLeft = Math.abs(candidatePosition.left - basePosition.left);
    const deltaTop = Math.abs(candidatePosition.top - basePosition.top);
    const horizontalBiasPenalty =
      preferVerticalStack && deltaLeft > deltaTop ? Math.max(80, deltaLeft - deltaTop) : 0;
    const distanceScore = deltaLeft + deltaTop;
    const totalScore = overlapCount * 100000 + horizontalBiasPenalty + distanceScore;

    if (totalScore < bestScore) {
      bestScore = totalScore;
      bestCandidate = candidatePosition;
    }
  }

  return bestCandidate;
}

function rectanglesOverlap(firstRect, secondRect, gap = 0) {
  return (
    firstRect.left < secondRect.left + secondRect.width + gap &&
    firstRect.left + firstRect.width + gap > secondRect.left &&
    firstRect.top < secondRect.top + secondRect.height + gap &&
    firstRect.top + firstRect.height + gap > secondRect.top
  );
}

function clampFloatingPanelLeft(left, stageWidth, panelWidth) {
  const maxLeft = Math.max(FLOATING_PANEL_MARGIN, stageWidth - panelWidth - FLOATING_PANEL_MARGIN);
  return clamp(left, FLOATING_PANEL_MARGIN, maxLeft);
}

function clampFloatingPanelTop(top, stageHeight, panelHeight) {
  const maxTop = Math.max(FLOATING_PANEL_MARGIN, stageHeight - panelHeight - FLOATING_PANEL_MARGIN);
  return clamp(top, FLOATING_PANEL_MARGIN, maxTop);
}

function getFloatingHorizontalGap() {
  return window.innerWidth >= 1080 ? PANEL_EDGE_GAP_WIDE : PANEL_EDGE_GAP_COMPACT;
}

function getFloatingTopGap() {
  return window.innerWidth >= 1080 ? PANEL_EDGE_GAP_WIDE : PANEL_EDGE_GAP_COMPACT;
}

function getTrafficBottomGap() {
  return window.innerWidth >= 1080 ? PANEL_EDGE_GAP_WIDE : PANEL_EDGE_GAP_COMPACT;
}

function getDebugBottomGap() {
  return window.innerWidth >= 1080 ? 12 : 10;
}

function getRightPanelWidth(stageWidth) {
  const edgeGap = getFloatingHorizontalGap();
  const maxWidth = window.innerWidth >= 1080 ? 408 : 360;
  return Math.min(maxWidth, Math.max(220, stageWidth - edgeGap * 2));
}

function getDebugPanelWidth(stageWidth) {
  const edgeGap = getFloatingHorizontalGap();
  const maxWidth = window.innerWidth >= 1080 ? 440 : 320;
  return Math.min(maxWidth, Math.max(220, stageWidth - edgeGap * 2));
}

function createMapLayers() {
  const darkAttribution =
    '&copy; <a href="https://stadiamaps.com/" target="_blank" rel="noreferrer">Stadia Maps</a>, ' +
    '&copy; <a href="https://openmaptiles.org/" target="_blank" rel="noreferrer">OpenMapTiles</a>, ' +
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>';

  return {
    dark: L.tileLayer(
      "https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png",
      {
        attribution: darkAttribution,
        maxZoom: 20,
      },
    ),
    satellite: createSatelliteLayer(),
  };
}

function createSatelliteLayer() {
  if (!L.esri?.basemapLayer) {
    return null;
  }

  return L.layerGroup([
    L.esri.basemapLayer("Imagery"),
    L.esri.basemapLayer("ImageryLabels"),
  ]);
}

function handleMapStyleChange(event) {
  setMapStyle(event.currentTarget.value);
}

function setMapStyle(style) {
  let nextStyle = style;
  let nextLayer = mapLayers[nextStyle];

  if (!nextLayer) {
    nextStyle = "dark";
    nextLayer = mapLayers.dark;
    pushLog("Satellite basemap unavailable, using dark Leaflet tiles.");
  }

  if (activeBaseLayer && map.hasLayer(activeBaseLayer)) {
    map.removeLayer(activeBaseLayer);
  }

  activeBaseLayer = nextLayer;
  activeBaseLayer.addTo(map);
  runtime.mapStyle = nextStyle;
  elements.mapStyleSelect.value = nextStyle;
  document.body.dataset.mapStyle = nextStyle;
  updatePanels();
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

function buildDefaultSourceApiUrl() {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return `${window.location.origin}/api/source`;
  }

  return "http://127.0.0.1:8000/api/source";
}

function buildHttpUrlFromWebSocketUrl(webSocketUrl, pathname) {
  try {
    const nextUrl = new URL(webSocketUrl);
    if (nextUrl.protocol !== "ws:" && nextUrl.protocol !== "wss:") {
      return null;
    }

    nextUrl.protocol = nextUrl.protocol === "wss:" ? "https:" : "http:";
    nextUrl.pathname = pathname;
    nextUrl.search = "";
    nextUrl.hash = "";
    return nextUrl.toString();
  } catch {
    return null;
  }
}

function getConfiguredWebSocketUrl() {
  return elements.wsUrlInput.value.trim() || DEFAULT_WS_URL;
}

function getConfiguredAircraftApiUrl() {
  return buildHttpUrlFromWebSocketUrl(getConfiguredWebSocketUrl(), "/api/aircraft") || DEFAULT_AIRCRAFT_API_URL;
}

function getConfiguredSourceApiUrl() {
  return buildHttpUrlFromWebSocketUrl(getConfiguredWebSocketUrl(), "/api/source") || DEFAULT_SOURCE_API_URL;
}

function buildFallbackSourceOptions(reason = "Live source unavailable", activeSourceId = null) {
  return [
    {
      id: "sample",
      label: "Sample",
      kind: "sample",
      available: true,
      active: activeSourceId === "sample",
      reason: null,
    },
    {
      id: "readsb",
      label: "RTL-SDR / readsb",
      kind: "live",
      available: false,
      active: activeSourceId === "readsb",
      reason,
    },
    {
      id: "dump1090",
      label: "RTL-SDR / dump1090",
      kind: "live",
      available: false,
      active: activeSourceId === "dump1090",
      reason,
    },
  ];
}

function getSourceOption(sourceId) {
  return runtime.sourceOptions.find((option) => option.id === sourceId) ?? null;
}

function syncSourceModeFromActiveSource() {
  if (runtime.activeSourceKind === "live" || runtime.activeSourceKind === "sample") {
    runtime.sourceMode = runtime.activeSourceKind;
    return;
  }

  runtime.sourceMode = "none";
}

function renderSourceOptions(preferredSourceId = runtime.selectedSourceId) {
  elements.sourceSelect.innerHTML = "";

  for (const option of runtime.sourceOptions) {
    const optionElement = document.createElement("option");
    optionElement.value = option.id;
    optionElement.textContent = option.available ? option.label : `${option.label} (Unavailable)`;
    optionElement.disabled = !option.available && !option.active;
    elements.sourceSelect.appendChild(optionElement);
  }

  syncSelectedSource(preferredSourceId);
}

function syncSelectedSource(preferredSourceId = runtime.selectedSourceId) {
  const selectableSourceIds = runtime.sourceOptions
    .filter((option) => option.available || option.active)
    .map((option) => option.id);
  let nextSourceId = preferredSourceId;

  if (!selectableSourceIds.includes(nextSourceId)) {
    nextSourceId = runtime.activeSourceId;
  }
  if (!selectableSourceIds.includes(nextSourceId)) {
    nextSourceId = runtime.sourceOptions.find((option) => option.available)?.id ?? runtime.sourceOptions[0]?.id;
  }

  if (!nextSourceId) {
    return;
  }

  const nextOption = getSourceOption(nextSourceId);
  runtime.selectedSourceId = nextSourceId;
  runtime.selectedSourceLabel = nextOption?.label ?? "Sample";
  elements.sourceSelect.value = nextSourceId;
  elements.sourceSelect.title = nextOption?.reason ?? nextOption?.label ?? "";
}

function handleSourceSelectionChange(event) {
  syncSelectedSource(event.currentTarget.value);
  updatePanels();
}

async function handleWebSocketUrlChange() {
  const value = elements.wsUrlInput.value.trim();
  if (!value) {
    elements.wsUrlInput.value = DEFAULT_WS_URL;
  }

  await refreshSourceControlState({ preserveSelection: true, quiet: true });
}

async function refreshSourceControlState({ preserveSelection = true, quiet = false } = {}) {
  try {
    const payload = await requestJson(getConfiguredSourceApiUrl());
    applySourceControllerPayload(payload, { preserveSelection });
  } catch (error) {
    runtime.sourceControlAvailable = false;
    runtime.sourceOptions = buildFallbackSourceOptions(
      "Live decoder unavailable",
      runtime.activeSourceId,
    );
    renderSourceOptions(preserveSelection ? runtime.selectedSourceId : runtime.activeSourceId);
    updatePanels();

    if (!quiet) {
      pushLog(`Source control unavailable: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

function applySourceControllerPayload(payload, { preserveSelection = true } = {}) {
  const activeSourceId =
    typeof payload?.active_source_id === "string" && payload.active_source_id.length > 0
      ? payload.active_source_id
      : null;
  const activeSourceLabel =
    typeof payload?.active_source_label === "string" && payload.active_source_label.length > 0
      ? payload.active_source_label
      : null;
  const activeSourceKind =
    payload?.active_source_kind === "live" || payload?.active_source_kind === "sample"
      ? payload.active_source_kind
      : "none";
  const sourceOptions = Array.isArray(payload?.sources)
    ? payload.sources.map((option) => ({
        id: String(option.id ?? ""),
        label: String(option.label ?? option.id ?? "").trim(),
        kind: option.kind === "sample" ? "sample" : "live",
        available: Boolean(option.available),
        active: String(option.id ?? "") === activeSourceId,
        reason:
          typeof option.reason === "string" && option.reason.length > 0 ? option.reason : null,
      }))
    : buildFallbackSourceOptions("Live decoder unavailable", activeSourceId);

  runtime.sourceControlAvailable = true;
  runtime.activeSourceId = activeSourceId;
  runtime.activeSourceLabel = activeSourceLabel;
  runtime.activeSourceKind = activeSourceKind;
  runtime.sourceOptions = sourceOptions;
  syncSourceModeFromActiveSource();

  if (!isTransportActive() && runtime.activeSourceId == null) {
    runtime.connectionStatus = "idle";
    runtime.connectionLabel = "Stopped";
  }

  renderSourceOptions(preserveSelection ? runtime.selectedSourceId : runtime.activeSourceId);
  updatePanels();
}

async function requestJson(url, init) {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail =
      typeof payload?.detail === "string" && payload.detail.length > 0
        ? payload.detail
        : `HTTP ${response.status}`;
    throw new Error(detail);
  }

  return payload;
}

function isTransportActive() {
  return (
    runtime.websocket !== null ||
    runtime.sampleTimer !== null ||
    runtime.livePollTimer !== null ||
    runtime.transportMode !== "none"
  );
}

async function connectSelectedSource() {
  const preferredSourceId = elements.sourceSelect.value || runtime.selectedSourceId || "sample";
  await refreshSourceControlState({ preserveSelection: true, quiet: true });
  syncSelectedSource(preferredSourceId);

  const selectedSource = getSourceOption(runtime.selectedSourceId);
  if (!selectedSource) {
    setConnectionStatus("error", "No source");
    pushLog("No source is available to connect.");
    return;
  }

  if (!selectedSource.available && !selectedSource.active) {
    setConnectionStatus("error", "Unavailable");
    pushLog(`${selectedSource.label} is unavailable${selectedSource.reason ? `: ${selectedSource.reason}` : "."}`);
    return;
  }

  if (!runtime.sourceControlAvailable) {
    if (selectedSource.id === "sample") {
      startSampleStream();
      return;
    }

    setConnectionStatus("error", "Unavailable");
    pushLog(`${selectedSource.label} cannot start without backend source control.`);
    return;
  }

  resetLocalTransport();
  clearVisualizationState();

  try {
    const payload = await requestJson(`${getConfiguredSourceApiUrl()}/select`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ source: selectedSource.id }),
    });
    applySourceControllerPayload(payload, { preserveSelection: true });
  } catch (error) {
    setConnectionStatus("error", "Source error");
    pushLog(`Source selection failed: ${error instanceof Error ? error.message : String(error)}`);
    return;
  }

  connectToWebSocket(getConfiguredWebSocketUrl());
}

function connectToWebSocket(url) {
  let socket;

  try {
    socket = new WebSocket(url);
  } catch (error) {
    setConnectionStatus("error", "Bad URL");
    pushLog(`WebSocket URL error: ${error instanceof Error ? error.message : String(error)}`);
    maybeStartLocalSampleFallback("WebSocket could not be created");
    return;
  }

  runtime.websocket = socket;
  runtime.transportMode = "websocket";
  setConnectionStatus("idle", "Connecting");
  pushLog(`Connecting to ${runtime.selectedSourceLabel} via ${url}`);

  socket.addEventListener("open", () => {
    if (runtime.websocket !== socket) {
      return;
    }

    const nextStatus = runtime.sourceMode === "sample" ? "sample" : "live";
    setConnectionStatus(nextStatus, "Connected");
    pushLog("WebSocket connected");
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
    if (runtime.websocket !== socket) {
      return;
    }

    runtime.websocket = null;
    if (runtime.sourceMode === "live" && runtime.transportMode === "websocket") {
      startLivePollingFallback();
      return;
    }

    if (runtime.sourceMode === "sample" && runtime.transportMode === "websocket") {
      maybeStartLocalSampleFallback("WebSocket disconnected");
      return;
    }

    runtime.transportMode = "none";
    setConnectionStatus("idle", "Disconnected");
    pushLog("WebSocket disconnected");
  });

  socket.addEventListener("error", () => {
    if (runtime.websocket === socket) {
      pushLog("WebSocket connection error");
    }
  });
}

function maybeStartLocalSampleFallback(reason) {
  if (runtime.sourceMode !== "sample") {
    return;
  }

  pushLog(`${reason}, falling back to local sample.`);
  startSampleStream();
}

function startSampleStream() {
  resetLocalTransport();
  clearVisualizationState();

  runtime.activeSourceId = "sample";
  runtime.activeSourceLabel = "Sample";
  runtime.activeSourceKind = "sample";
  runtime.sourceOptions = buildFallbackSourceOptions("Live decoder unavailable", "sample");
  syncSourceModeFromActiveSource();
  runtime.transportMode = "sample";
  renderSourceOptions("sample");
  setConnectionStatus("sample", "Sample active");
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
      drift_latitude: 0.009,
      drift_longitude: 0.018,
      wave_latitude: 0.0028,
      wave_longitude: 0.0046,
      wave_phase: 0.0,
      wave_frequency: 0.42,
      wave_longitude_frequency: 0.88,
      altitude_step: 110,
      speed_step: 0.7,
    },
    {
      aircraft_id: "a8b42f",
      callsign: "PGT2YZ",
      latitude: 40.9634,
      longitude: 29.3092,
      altitude_ft: 11825,
      ground_speed_kt: 214.8,
      heading_deg: 242,
      drift_latitude: -0.009,
      drift_longitude: 0.018,
      wave_latitude: 0.0028,
      wave_longitude: 0.0046,
      wave_phase: 0.85,
      wave_frequency: 0.42,
      wave_longitude_frequency: 0.88,
      altitude_step: -160,
      speed_step: 0.4,
      remove_after_tick: 48,
    },
    {
      aircraft_id: "71be10",
      callsign: "UAE5KL",
      latitude: 41.802,
      longitude: 27.712,
      altitude_ft: 36500,
      ground_speed_kt: 456.1,
      heading_deg: 118,
      drift_latitude: 0.009,
      drift_longitude: 0.018,
      wave_latitude: 0.0028,
      wave_longitude: 0.0046,
      wave_phase: 1.7,
      wave_frequency: 0.42,
      wave_longitude_frequency: 0.88,
      altitude_step: 110,
      speed_step: 0.7,
    },
    {
      aircraft_id: "45aa71",
      callsign: "SOF2IZ",
      latitude: 42.6977,
      longitude: 23.3219,
      altitude_ft: 28600,
      ground_speed_kt: 404.2,
      heading_deg: 146,
      drift_latitude: -0.0135,
      drift_longitude: 0.0152,
      wave_latitude: 0.0032,
      wave_longitude: 0.0038,
      wave_phase: 2.4,
      wave_frequency: 0.36,
      wave_longitude_frequency: 0.82,
      altitude_step: 90,
      speed_step: 0.5,
    },
    {
      aircraft_id: "3c91ef",
      callsign: "ESK4EU",
      latitude: 39.7767,
      longitude: 30.5206,
      altitude_ft: 34750,
      ground_speed_kt: 428.6,
      heading_deg: 307,
      drift_latitude: 0.0084,
      drift_longitude: -0.0186,
      wave_latitude: 0.0024,
      wave_longitude: 0.0044,
      wave_phase: 3.15,
      wave_frequency: 0.33,
      wave_longitude_frequency: 0.94,
      altitude_step: 70,
      speed_step: 0.6,
    },
  ];

  const buildSampleWireAircraft = (aircraft) => ({
    aircraft_id: aircraft.aircraft_id,
    callsign: aircraft.callsign,
    latitude: Number(aircraft.latitude.toFixed(4)),
    longitude: Number(aircraft.longitude.toFixed(4)),
    altitude_ft: Math.round(aircraft.altitude_ft),
    ground_speed_kt: Number(aircraft.ground_speed_kt.toFixed(1)),
    heading_deg: Number(aircraft.heading_deg.toFixed(1)),
    updated_at: new Date().toISOString(),
  });

  runtime.lastSequence = 1;
  applySnapshotEvent({
    type: "snapshot",
    sequence: 1,
    sent_at: new Date().toISOString(),
    aircraft: sampleAircraft.map(buildSampleWireAircraft),
  });

  let tick = 0;
  runtime.sampleTimer = window.setInterval(() => {
    tick += 1;
    const changes = sampleAircraft.map((aircraft) => {
      const previousLatitude = aircraft.latitude;
      const previousLongitude = aircraft.longitude;
      const phase = tick * aircraft.wave_frequency + aircraft.wave_phase;

      aircraft.latitude +=
        aircraft.drift_latitude + Math.sin(phase) * aircraft.wave_latitude;
      aircraft.longitude +=
        aircraft.drift_longitude +
        Math.cos(phase * aircraft.wave_longitude_frequency) * aircraft.wave_longitude;
      aircraft.altitude_ft += aircraft.altitude_step;
      aircraft.ground_speed_kt += aircraft.speed_step;
      aircraft.heading_deg = calculateBearingBetweenCoordinates(
        previousLatitude,
        previousLongitude,
        aircraft.latitude,
        aircraft.longitude,
      );

      return {
        action: "upsert",
        aircraft_id: aircraft.aircraft_id,
        aircraft: buildSampleWireAircraft(aircraft),
      };
    });

    const removableAircraft = sampleAircraft.find(
      (aircraft) => aircraft.remove_after_tick != null && tick === aircraft.remove_after_tick,
    );

    if (removableAircraft) {
      changes.push({
        action: "remove",
        aircraft_id: removableAircraft.aircraft_id,
        reason: "sample_timeout",
      });
      sampleAircraft.splice(
        sampleAircraft.findIndex((aircraft) => aircraft.aircraft_id === removableAircraft.aircraft_id),
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
}

function resetLocalTransport() {
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
}

async function stopCurrentSource() {
  if (runtime.sourceControlAvailable && runtime.activeSourceId != null) {
    try {
      const payload = await requestJson(`${getConfiguredSourceApiUrl()}/stop`, {
        method: "POST",
      });
      applySourceControllerPayload(payload, { preserveSelection: true });
    } catch (error) {
      setConnectionStatus("error", "Stop failed");
      pushLog(`Unable to stop source: ${error instanceof Error ? error.message : String(error)}`);
      return;
    }
  } else {
    runtime.activeSourceId = null;
    runtime.activeSourceLabel = null;
    runtime.activeSourceKind = "none";
    runtime.sourceOptions = buildFallbackSourceOptions("Live decoder unavailable");
    syncSourceModeFromActiveSource();
    renderSourceOptions(runtime.selectedSourceId);
  }

  resetLocalTransport();
  clearVisualizationState();
  runtime.transportMode = "none";
  syncSourceModeFromActiveSource();
  setConnectionStatus("idle", "Stopped");
  updatePanels();
}

function startLivePollingFallback() {
  if (runtime.sourceMode !== "live" || runtime.livePollTimer !== null) {
    return;
  }

  runtime.transportMode = "polling";
  setConnectionStatus("live", "Polling");
  pushLog(`WebSocket unavailable, falling back to ${getConfiguredAircraftApiUrl()}`);

  void pollLiveAircraftSnapshot();
  runtime.livePollTimer = window.setInterval(() => {
    void pollLiveAircraftSnapshot();
  }, LIVE_POLL_INTERVAL_MS);
}

async function pollLiveAircraftSnapshot() {
  try {
    const response = await fetch(getConfiguredAircraftApiUrl(), {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    if (runtime.sourceMode !== "live" || runtime.transportMode !== "polling") {
      return;
    }

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
  runtime.lastActivityAt = null;
  elements.eventLog.innerHTML = "";
  updatePanels();
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
  runtime.lastActivityAt = event.sent_at ?? new Date().toISOString();

  const statusLabel = runtime.sourceMode === "sample" ? "Sample active" : "Streaming";
  setConnectionStatus(runtime.sourceMode === "sample" ? "sample" : "live", statusLabel);

  const summary = applySnapshotEventToDomainState(domainState, event);
  runtime.upserts += summary.upsertedAircraftIds.length;
  runtime.removals += summary.removedAircraftIds.length;
  reconcileMapRenderState();

  pushLog(`Snapshot received with ${summary.upsertedAircraftIds.length} aircraft`);
  updatePanels();
}

function applyDeltaEvent(event) {
  runtime.deltas += 1;
  runtime.lastSequence = event.sequence ?? runtime.lastSequence;
  runtime.lastActivityAt = event.sent_at ?? new Date().toISOString();

  const summary = applyDeltaEventToDomainState(domainState, event);
  runtime.upserts += summary.upsertedAircraftIds.length;
  runtime.removals += summary.removedAircraftIds.length;
  reconcileMapRenderState();

  pushLog(
    `Delta received with ${summary.upsertedAircraftIds.length + summary.removedAircraftIds.length} changes`,
  );
  updatePanels();
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
  const trail = L.polyline(buildRenderableTrailLatLngs(aircraft), {
    color: "#47c8ef",
    weight: 1.7,
    opacity: 0.72,
    dashArray: "7 5",
    lineCap: "round",
    lineJoin: "round",
  }).addTo(map);

  const marker = L.marker(position, {
    icon: buildAircraftIcon(aircraft, false),
    keyboard: false,
  }).addTo(map);

  marker.on("click", (event) => {
    if (event?.originalEvent) {
      L.DomEvent.stopPropagation(event.originalEvent);
    }

    selectAircraftInDomainState(domainState, aircraft.aircraft_id);
    reconcileMapRenderState();
    updatePanels();
  });

  renderState.set(aircraft.aircraft_id, { marker, trail });
}

function updateAircraftRender(aircraft, isSelected) {
  const renderEntry = renderState.get(aircraft.aircraft_id);
  if (!renderEntry || aircraft.latitude == null || aircraft.longitude == null) {
    return;
  }

  const position = [aircraft.latitude, aircraft.longitude];
  renderEntry.marker.setLatLng(position);
  renderEntry.marker.setIcon(buildAircraftIcon(aircraft, isSelected));
  renderEntry.marker.setZIndexOffset(isSelected ? 1200 : 0);
  renderEntry.trail.setLatLngs(buildRenderableTrailLatLngs(aircraft));
  renderEntry.trail.setStyle({
    color: isSelected ? "#87c96b" : "#47c8ef",
    weight: isSelected ? 2.3 : 1.7,
    opacity: isSelected ? 0.94 : 0.72,
    dashArray: isSelected ? null : "7 5",
  });
  syncAircraftTooltip(renderEntry.marker, aircraft, isSelected);
}

function buildRenderableTrailLatLngs(aircraft) {
  const trailPoints = normalizeTrailPoints(aircraft.trail);
  if (trailPoints.length < 2) {
    return [];
  }

  const projectedPoints = trailPoints.map(([latitude, longitude]) =>
    map.latLngToLayerPoint([latitude, longitude]),
  );

  // Keep the historical start fixed, but end the visible path behind the aircraft body.
  projectedPoints[projectedPoints.length - 1] = buildTailAnchorPoint(aircraft, trailPoints);

  const smoothedPoints =
    projectedPoints.length === 2
      ? buildTwoPointBezier(projectedPoints[0], projectedPoints[1], aircraft, trailPoints)
      : buildCatmullRomSpline(projectedPoints, TRAIL_SPLINE_SAMPLES);
  return smoothedPoints.map((point) => map.layerPointToLatLng(point));
}

function normalizeTrailPoints(rawTrail) {
  if (!Array.isArray(rawTrail)) {
    return [];
  }

  const normalized = [];
  for (const point of rawTrail) {
    if (!Array.isArray(point) || point.length < 2) {
      continue;
    }

    const latitude = Number(point[0]);
    const longitude = Number(point[1]);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      continue;
    }

    const lastPoint = normalized.at(-1);
    if (lastPoint && lastPoint[0] === latitude && lastPoint[1] === longitude) {
      continue;
    }

    normalized.push([latitude, longitude]);
  }

  return normalized;
}

function buildTailAnchorPoint(aircraft, trailPoints) {
  const currentPoint = map.latLngToLayerPoint([aircraft.latitude, aircraft.longitude]);
  const heading = getAircraftVisualHeading(aircraft, trailPoints);
  const headingRadians = (heading * Math.PI) / 180;

  return L.point(
    currentPoint.x - Math.sin(headingRadians) * TRAIL_TAIL_OFFSET_PX,
    currentPoint.y + Math.cos(headingRadians) * TRAIL_TAIL_OFFSET_PX,
  );
}

function buildTwoPointBezier(startPoint, endPoint, aircraft, trailPoints) {
  const heading = getAircraftVisualHeading(aircraft, trailPoints);
  const chordBearing = calculateScreenBearing(startPoint, endPoint);
  const angleDelta = smallestAngleDelta(chordBearing, heading);
  const distance = startPoint.distanceTo(endPoint);
  const midpoint = L.point((startPoint.x + endPoint.x) / 2, (startPoint.y + endPoint.y) / 2);

  const controlDirection = chordBearing + 90 * (angleDelta === 0 ? 1 : Math.sign(angleDelta));
  const curvatureFactor = Math.max(Math.min(Math.abs(angleDelta) / 50, 1), 0.22);
  const controlDistance = Math.max(10, Math.min(distance * 0.16 * curvatureFactor, 34));
  const controlRadians = (controlDirection * Math.PI) / 180;
  const controlPoint = L.point(
    midpoint.x + Math.sin(controlRadians) * controlDistance,
    midpoint.y - Math.cos(controlRadians) * controlDistance,
  );

  return sampleQuadraticBezier(startPoint, controlPoint, endPoint, TRAIL_TWO_POINT_SAMPLES);
}

function getAircraftVisualHeading(aircraft, trailPoints = normalizeTrailPoints(aircraft.trail)) {
  const trailBearing = calculateTrailBearing(trailPoints);
  if (Number.isFinite(trailBearing)) {
    return trailBearing;
  }

  if (Number.isFinite(aircraft.heading_deg)) {
    return normalizeHeading(aircraft.heading_deg);
  }

  return 0;
}

function calculateTrailBearing(trailPoints) {
  if (!Array.isArray(trailPoints) || trailPoints.length < 2) {
    return Number.NaN;
  }

  for (let index = trailPoints.length - 1; index > 0; index -= 1) {
    const [startLatitude, startLongitude] = trailPoints[index - 1];
    const [endLatitude, endLongitude] = trailPoints[index];
    const bearing = calculateBearingBetweenCoordinates(
      startLatitude,
      startLongitude,
      endLatitude,
      endLongitude,
    );
    if (Number.isFinite(bearing)) {
      return bearing;
    }
  }

  return Number.NaN;
}

function buildCatmullRomSpline(points, samplesPerSegment) {
  if (points.length < 3) {
    return points;
  }

  const smoothed = [points[0]];

  for (let index = 0; index < points.length - 1; index += 1) {
    const point0 = points[Math.max(0, index - 1)];
    const point1 = points[index];
    const point2 = points[index + 1];
    const point3 = points[Math.min(points.length - 1, index + 2)];

    for (let step = 1; step <= samplesPerSegment; step += 1) {
      const t = step / samplesPerSegment;
      const t2 = t * t;
      const t3 = t2 * t;

      smoothed.push(
        L.point(
          0.5 *
            ((2 * point1.x) +
              (-point0.x + point2.x) * t +
              (2 * point0.x - 5 * point1.x + 4 * point2.x - point3.x) * t2 +
              (-point0.x + 3 * point1.x - 3 * point2.x + point3.x) * t3),
          0.5 *
            ((2 * point1.y) +
              (-point0.y + point2.y) * t +
              (2 * point0.y - 5 * point1.y + 4 * point2.y - point3.y) * t2 +
              (-point0.y + 3 * point1.y - 3 * point2.y + point3.y) * t3),
        ),
      );
    }
  }

  return smoothed;
}

function sampleQuadraticBezier(startPoint, controlPoint, endPoint, sampleCount) {
  const sampledPoints = [startPoint];

  for (let step = 1; step <= sampleCount; step += 1) {
    const t = step / sampleCount;
    const inverse = 1 - t;
    sampledPoints.push(
      L.point(
        inverse * inverse * startPoint.x +
          2 * inverse * t * controlPoint.x +
          t * t * endPoint.x,
        inverse * inverse * startPoint.y +
          2 * inverse * t * controlPoint.y +
          t * t * endPoint.y,
      ),
    );
  }

  return sampledPoints;
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

function buildAircraftIcon(aircraft, isSelected) {
  const rotation = getAircraftVisualHeading(aircraft);
  const className = isSelected ? "aircraft-shell selected" : "aircraft-shell";

  return L.divIcon({
    className: "leaflet-aircraft-marker",
    html: `<div class="${className}" style="transform: rotate(${rotation}deg)"></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

function syncAircraftTooltip(marker, aircraft, isSelected) {
  if (!shouldShowAircraftLabel(aircraft, isSelected)) {
    if (marker.getTooltip()) {
      marker.unbindTooltip();
    }
    return;
  }

  const content = isSelected
    ? buildSelectedTooltipHtml(aircraft)
    : `<span class="tooltip-call">${escapeHtml(aircraft.callsign || aircraft.aircraft_id.toUpperCase())}</span>`;

  marker.bindTooltip(content, {
    className: isSelected ? "aircraft-label selected" : "aircraft-label",
    direction: "top",
    offset: [0, -20],
    permanent: true,
    opacity: 0.98,
  });
  marker.openTooltip();
}

function shouldShowAircraftLabel(aircraft, isSelected) {
  if (isSelected) {
    return true;
  }

  if (runtime.searchQuery && isAircraftSearchMatch(aircraft)) {
    return true;
  }

  return map.getZoom() >= 7 && domainState.aircraft.size <= 8;
}

function buildSelectedTooltipHtml(aircraft) {
  return `
    <span class="tooltip-call">${escapeHtml(aircraft.callsign || aircraft.aircraft_id.toUpperCase())}</span>
    <span class="tooltip-meta">${escapeHtml(aircraft.aircraft_id.toUpperCase())}</span>
    <span class="tooltip-secondary">${escapeHtml(formatInteger(aircraft.altitude_ft, " ft"))} · ${escapeHtml(formatNumber(aircraft.ground_speed_kt, 0, " kt"))}</span>
    <span class="tooltip-secondary">${escapeHtml(formatAgeCompact(aircraft.updated_at))}</span>
  `;
}

function updatePanels() {
  const selected = getSelectedAircraft(domainState);
  const displayedAircraft = getDisplayedAircraft();

  updateLiveIndicator();
  updateSelectedAircraftPanel(selected);
  updateTrafficList(displayedAircraft, selected?.aircraft_id ?? null);
  updateDebugStats(selected);
  updateFooter();
  updateControlState(selected);
  queueFloatingPanelLayout();
  updateClockDisplay();
}

function updateLiveIndicator() {
  elements.liveIndicator.className = "live-indicator";

  if (runtime.connectionStatus === "error") {
    elements.liveIndicator.classList.add("is-error");
    elements.liveIndicator.textContent = "Error";
    return;
  }

  if (runtime.sourceMode === "live") {
    elements.liveIndicator.classList.add("is-live");
    elements.liveIndicator.textContent = "Live";
    return;
  }

  if (runtime.sourceMode === "sample") {
    elements.liveIndicator.classList.add("is-sample");
    elements.liveIndicator.textContent = "Sample";
    return;
  }

  elements.liveIndicator.textContent = "Idle";
}

function updateSelectedAircraftPanel(selected) {
  if (!selected) {
    elements.selectedPanel.hidden = true;
    elements.selectedTitle.textContent = "Flight Detail";
    elements.selectedSummary.innerHTML = "";
    elements.selectedAircraft.innerHTML = "";
    return;
  }

  elements.selectedPanel.hidden = false;
  elements.selectedTitle.textContent = selected.callsign || selected.aircraft_id.toUpperCase();
  elements.selectedSummary.innerHTML = `
    <div class="selected-summary-top">
      <div>
        <p class="selected-summary-title">${escapeHtml(selected.callsign || "Unknown Flight")}</p>
        <p class="selected-summary-subtitle">${escapeHtml(selected.aircraft_id.toUpperCase())}</p>
      </div>
      <span class="mode-pill">${escapeHtml(formatAgeCompact(selected.updated_at))}</span>
    </div>
  `;
  elements.selectedAircraft.innerHTML = `
    ${detailRow("Altitude", formatInteger(selected.altitude_ft, " ft"))}
    ${detailRow("Speed", formatNumber(selected.ground_speed_kt, 0, " kt"))}
    ${detailRow("Heading", formatNumber(selected.heading_deg, 0, " deg"))}
    ${detailRow("Position", formatCoordinatePair(selected.latitude, selected.longitude))}
    ${detailRow("Updated", formatRelativeAge(selected.updated_at) ?? "-")}
    ${detailRow("Trail Points", String(selected.trail.length))}
  `;
}

function updateTrafficList(displayedAircraft, selectedAircraftId) {
  elements.aircraftList.innerHTML = "";
  elements.trafficSummary.textContent = buildTrafficSummary(
    displayedAircraft.length,
    domainState.aircraft.size,
  );

  if (displayedAircraft.length === 0) {
    elements.emptyTraffic.textContent = runtime.searchQuery
      ? `No aircraft match "${runtime.searchQuery}".`
      : "No traffic loaded yet. Connect to a source to begin.";
    elements.emptyTraffic.hidden = false;
    return;
  }

  elements.emptyTraffic.hidden = true;

  for (const aircraft of displayedAircraft) {
    const row = document.createElement("li");
    const button = document.createElement("button");
    const isSelected = aircraft.aircraft_id === selectedAircraftId;

    button.type = "button";
    button.className = isSelected ? "aircraft-row-button is-selected" : "aircraft-row-button";
    button.innerHTML = `
      <div class="aircraft-row">
        <span class="row-symbol">${buildRowSymbol(isSelected)}</span>
        <span class="callsign">${escapeHtml(aircraft.callsign || "--------")}</span>
        <span>${escapeHtml(aircraft.aircraft_id.toUpperCase())}</span>
        <span>${escapeHtml(formatNumber(aircraft.heading_deg, 0))}</span>
        <span>${escapeHtml(formatInteger(aircraft.altitude_ft, " ft"))}</span>
        <span>${escapeHtml(formatNumber(aircraft.ground_speed_kt, 0, " kt"))}</span>
        <span>${escapeHtml(formatAgeCompact(aircraft.updated_at))}</span>
      </div>
    `;
    button.addEventListener("click", () => {
      selectAircraftInDomainState(domainState, aircraft.aircraft_id);
      reconcileMapRenderState();
      updatePanels();
      focusSelectedAircraft();
    });

    row.appendChild(button);
    elements.aircraftList.appendChild(row);
  }
}

function updateDebugStats(selected) {
  elements.statConnected.textContent = isTransportActive() ? "yes" : "no";
  elements.statAircraftCount.textContent = String(domainState.aircraft.size);
  elements.statSnapshots.textContent = String(runtime.snapshots);
  elements.statDeltas.textContent = String(runtime.deltas);
  elements.statUpserts.textContent = String(runtime.upserts);
  elements.statRemovals.textContent = String(runtime.removals);
  elements.statSequence.textContent =
    runtime.lastSequence == null ? "-" : String(runtime.lastSequence);
  elements.statSelected.textContent = selected?.aircraft_id ?? "none";
}

function updateFooter() {
  elements.footerLink.textContent = runtime.connectionLabel;
  elements.footerSource.textContent = describeFooterSource();
  elements.footerTransport.textContent = describeTransport();
  elements.footerActivity.textContent = formatRelativeAge(getLatestAircraftUpdateAt()) ?? "No data";
}

function updateControlState(selected) {
  const selectedSource = getSourceOption(runtime.selectedSourceId);
  const sourceUnavailable = selectedSource == null || (!selectedSource.available && !selectedSource.active);

  elements.connectSourceButton.disabled = sourceUnavailable || isTransportActive();
  elements.stopSourceButton.disabled = runtime.activeSourceId == null && !isTransportActive();
  elements.fitAircraftButton.disabled = domainState.aircraft.size === 0;
  elements.clearUiButton.disabled = !selected && runtime.searchQuery.length === 0;
  elements.focusSelectedButton.disabled = !selected;
  elements.clearSelectionButton.disabled = !selected;
}

function updateClockDisplay() {
  const now = new Date();
  elements.footerTime.textContent = now.toISOString().slice(11, 19);
  elements.footerUptime.textContent = formatDuration(Date.now() - sessionStartedAt);
  elements.footerActivity.textContent = formatRelativeAge(getLatestAircraftUpdateAt()) ?? "No data";
}

function clearUiState() {
  runtime.searchQuery = "";
  elements.aircraftSearchInput.value = "";
  selectAircraftInDomainState(domainState, null);
  reconcileMapRenderState();
  updatePanels();
}

function clearSelectedAircraft() {
  if (!domainState.selectedAircraftId) {
    return;
  }

  selectAircraftInDomainState(domainState, null);
  reconcileMapRenderState();
  updatePanels();
}

function focusSelectedAircraft() {
  const selected = getSelectedAircraft(domainState);
  if (!selected || selected.latitude == null || selected.longitude == null) {
    fitAircraftBounds();
    return;
  }

  const offsetPx = getSelectionOffsetPx();
  if (offsetPx > 0) {
    map.once("moveend", () => {
      map.panBy([-offsetPx, 0], {
        animate: true,
        duration: 0.35,
      });
    });
  }

  map.flyTo([selected.latitude, selected.longitude], Math.max(map.getZoom(), 7), {
    duration: 0.7,
  });
}

function handleAircraftSearchInput(event) {
  runtime.searchQuery = event.currentTarget.value.trim().toLowerCase();
  reconcileMapRenderState();
  updatePanels();
}

function getDisplayedAircraft() {
  const aircraft = Array.from(domainState.aircraft.values()).sort(compareAircraftForDisplay);
  if (!runtime.searchQuery) {
    return aircraft;
  }
  return aircraft.filter(isAircraftSearchMatch);
}

function compareAircraftForDisplay(left, right) {
  const leftSelected = left.aircraft_id === domainState.selectedAircraftId ? 1 : 0;
  const rightSelected = right.aircraft_id === domainState.selectedAircraftId ? 1 : 0;
  if (leftSelected !== rightSelected) {
    return rightSelected - leftSelected;
  }

  const updatedDelta = parseTimestampMs(right.updated_at) - parseTimestampMs(left.updated_at);
  if (updatedDelta !== 0) {
    return updatedDelta;
  }

  return (left.callsign || left.aircraft_id).localeCompare(right.callsign || right.aircraft_id);
}

function isAircraftSearchMatch(aircraft) {
  const haystack = `${aircraft.callsign ?? ""} ${aircraft.aircraft_id}`.toLowerCase();
  return haystack.includes(runtime.searchQuery);
}

function buildTrafficSummary(visibleCount, totalCount) {
  if (runtime.searchQuery) {
    return `${visibleCount} / ${totalCount}`;
  }

  return `${visibleCount} aircraft`;
}

function buildRowSymbol(isSelected) {
  const color = isSelected ? "#87c96b" : "#7ecbff";
  return `
    <svg viewBox="0 0 64 64" aria-hidden="true" style="fill:${color}">
      <path d="M35.8 4.5 40 21.3 58 30v4.8l-18.1-2.5-4.1 8.7 6.5 11.8v4.1L32 52.3l-10.3 4.6v-4.1L28.2 41l-4.1-8.7L6 34.8V30l18-8.7 4.2-16.8Z"></path>
      <path d="M30 24.7h4v21.4h-4z"></path>
    </svg>
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

  map.fitBounds(bounds, {
    paddingTopLeft: [36, 36],
    paddingBottomRight: [getRightRailPaddingPx(), 70],
    maxZoom: 8,
  });
}

function getRightRailPaddingPx() {
  if (floatingPanels.traffic.moved) {
    return 40;
  }

  if (window.innerWidth >= 1100) {
    return 430;
  }
  if (window.innerWidth >= 860) {
    return 360;
  }
  return 40;
}

function getSelectionOffsetPx() {
  if (floatingPanels.selected.moved) {
    return 0;
  }

  if (window.innerWidth >= 1100) {
    return 160;
  }
  return 0;
}

function getLatestAircraftUpdateAt() {
  let latest = runtime.lastActivityAt;
  let latestMs = parseTimestampMs(latest);

  for (const aircraft of domainState.aircraft.values()) {
    const aircraftMs = parseTimestampMs(aircraft.updated_at);
    if (aircraftMs > latestMs) {
      latest = aircraft.updated_at;
      latestMs = aircraftMs;
    }
  }

  return latest;
}

function setConnectionStatus(kind, label) {
  runtime.connectionStatus = kind;
  runtime.connectionLabel = label;
  updatePanels();
}

function describeFooterSource() {
  return runtime.activeSourceLabel ?? "None";
}

function describeTransport() {
  if (runtime.transportMode === "polling") {
    return "HTTP polling";
  }
  if (runtime.transportMode === "websocket") {
    return "WebSocket";
  }
  if (runtime.transportMode === "sample") {
    return "Local sample";
  }
  return "None";
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
  return `${Math.round(Number(value)).toLocaleString()}${suffix}`;
}

function formatRelativeAge(value) {
  const timestampMs = parseTimestampMs(value);
  if (!Number.isFinite(timestampMs)) {
    return null;
  }

  const diffSeconds = Math.max(0, Math.round((Date.now() - timestampMs) / 1000));
  if (diffSeconds < 5) {
    return "just now";
  }
  if (diffSeconds < 60) {
    return `${diffSeconds}s ago`;
  }

  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }

  return `${Math.round(diffHours / 24)}d ago`;
}

function formatAgeCompact(value) {
  const timestampMs = parseTimestampMs(value);
  if (!Number.isFinite(timestampMs)) {
    return "-";
  }

  const diffSeconds = Math.max(0, Math.round((Date.now() - timestampMs) / 1000));
  if (diffSeconds < 60) {
    return `${diffSeconds}s`;
  }

  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h`;
  }

  return `${Math.round(diffHours / 24)}d`;
}

function formatCoordinatePair(latitude, longitude) {
  if (latitude == null || longitude == null) {
    return "-";
  }
  return `${formatCoordinate(latitude, "lat")} ${formatCoordinate(longitude, "lon")}`;
}

function formatCoordinate(value, axis) {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }

  const absValue = Math.abs(Number(value)).toFixed(4);
  if (axis === "lat") {
    return `${absValue}° ${Number(value) >= 0 ? "N" : "S"}`;
  }

  return `${absValue}° ${Number(value) >= 0 ? "E" : "W"}`;
}

function formatDuration(durationMs) {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const hours = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

function parseTimestampMs(value) {
  if (typeof value !== "string" || value.length === 0) {
    return Number.NEGATIVE_INFINITY;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
}

function calculateBearingBetweenCoordinates(fromLatitude, fromLongitude, toLatitude, toLongitude) {
  const deltaLongitude = toLongitude - fromLongitude;
  const deltaLatitude = toLatitude - fromLatitude;

  if (deltaLongitude === 0 && deltaLatitude === 0) {
    return Number.NaN;
  }

  return normalizeHeading((Math.atan2(deltaLongitude, deltaLatitude) * 180) / Math.PI);
}

function calculateScreenBearing(fromPoint, toPoint) {
  return normalizeHeading((Math.atan2(toPoint.x - fromPoint.x, fromPoint.y - toPoint.y) * 180) / Math.PI);
}

function smallestAngleDelta(fromHeading, toHeading) {
  const normalizedDelta = ((toHeading - fromHeading + 540) % 360) - 180;
  return normalizedDelta;
}

function normalizeHeading(value) {
  return ((value % 360) + 360) % 360;
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function detailRow(label, value) {
  return `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value)}</dd>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
