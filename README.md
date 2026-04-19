# ADS-B Aircraft Tracker

An end-to-end real-time aircraft tracking pipeline built around RTL-SDR, ADS-B decoder output, Python backend processing, and live 2D/3D geospatial visualization.

The goal of this project is not to clone an existing flight tracking product. The goal is to build a clean, extensible system for:

- ingesting real decoder output
- normalizing live aircraft telemetry
- maintaining active aircraft state over time
- streaming updates to connected clients with low latency
- validating behavior in 2D first, then expanding into a 3D Cesium-based view

## Current Status

The repository currently contains the backend foundation and the first validation client for the first three phases:

- Phase 1: source contract, ingestion adapter, normalization pipeline, in-memory aircraft state store, debug tooling
- Phase 2: snapshot/delta stream contract, websocket hub, framework adapter boundary, change detection, and stream observability
- Phase 3: static 2D validation client scaffold with live WebSocket mode and built-in sample mode

What is not finished yet:

- a runnable FastAPI application bootstrap
- decoder polling against a live `readsb` endpoint or file source
- deeper 2D validation features such as filters and performance controls
- 3D Cesium client
- analytics, replay, and packaging

## Architecture

The project is built around a clear separation of responsibilities:

1. Ingestion
   Read decoder output such as `readsb` JSON snapshots and convert it into a canonical raw message model.

2. Normalization
   Clean and validate telemetry fields before they enter the live state pipeline.

3. State Aggregation
   Merge updates by `aircraft_id`, keep bounded trails, and remove stale tracks.

4. Realtime Distribution
   Send a full snapshot to new clients and delta-only updates to connected clients.

5. Visualization
   Validate behavior in a simple 2D client first, then build the operational 3D view.

## Implemented Modules

- `backend/app/models`
  Canonical data structures for raw messages, normalized telemetry, aircraft state, and client update DTOs

- `backend/app/ingestion`
  File-based `readsb` ingestion adapter for sample snapshot input

- `backend/app/services`
  Normalization rules and pipeline debug helpers

- `backend/app/state`
  Identity-based in-memory aircraft state store with bounded trail logic

- `backend/app/streaming`
  Snapshot/delta event contract and websocket connection hub

- `backend/app/api`
  Thin framework adapter layer for a future FastAPI websocket endpoint

- `frontend/client-2d`
  Leaflet-based validation client for snapshot/delta stream verification

## Repository Layout

```text
backend/
  app/
    api/
    ingestion/
    models/
    services/
    state/
    streaming/
  tests/
docs/
samples/
scripts/
```

## Development Notes

The current implementation uses sample `readsb` snapshots stored in `samples/fixtures/` to validate the backend pipeline before wiring in live decoder output.

You can run the existing test suite with:

```bash
python3 -m unittest discover -s backend/tests -v
```

You can inspect the Phase 1 pipeline with:

```bash
python3 scripts/debug_state_view.py --snapshot samples/fixtures/readsb/basic_snapshot.json
```

You can run the 2D validation client with:

```bash
cd frontend/client-2d
python3 -m http.server 8080
```

Then open `http://localhost:8080` and either:

- connect to a live websocket backend
- or run the built-in sample stream

## Roadmap

- Connect the websocket hub to a runnable backend application
- Expand the 2D validation client with filters and performance checks
- Build the Cesium 3D client
- Add recording, replay, and analytics

## Tech Direction

- Decoder: `readsb` or compatible ADS-B JSON source
- Backend: Python
- Realtime transport: WebSocket
- 3D frontend target: CesiumJS

## Why This Project Exists

This project is intentionally framed as a real-time geospatial data pipeline, not just a map UI. The main engineering value is in the signal-derived data flow:

decoder output -> normalization -> live state -> realtime distribution -> map rendering

That separation keeps the system easier to scale, test, and extend.
