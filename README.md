# ADS-B Aircraft Tracker

An end-to-end real-time aircraft tracking pipeline built around RTL-SDR, ADS-B decoder output, Python backend processing, and a live 2D operations screen.

The goal of this project is not to clone an existing flight tracking product. The goal is to build a clean, extensible system for:

- ingesting real decoder output
- normalizing live aircraft telemetry
- maintaining active aircraft state over time
- streaming updates to connected clients with low latency
- validating behavior in a clean 2D surface before taking the system into live SDR field use

## Current Status

The repository currently contains the backend foundation, the runnable validation POC, and the first pass of a more operational 2D screen:

- Phase 1: source contract, ingestion adapter, normalization pipeline, in-memory aircraft state store, debug tooling
- Phase 2: snapshot/delta stream contract, websocket hub, framework adapter boundary, change detection, and stream observability
- Phase 3: runnable 2D validation POC with a FastAPI bootstrap, live WebSocket mode, built-in sample mode, and a decoder file polling path
- Phase 4: initial 2D operations-screen redesign with a cleaner information hierarchy, traffic list, selected-flight panel, and improved aircraft symbology

What is not finished yet:

- deeper 2D operational features such as follow modes, richer filtering, and SDR-focused health visibility
- real-world field validation against a live `readsb` or `dump1090` feed
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
   Operate the live tracker through a refined 2D client that stays readable under real traffic.

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
  Thin FastAPI adapter layer for realtime, monitoring, and local client mounting

- `backend/app/runtime`
  Live pipeline coordinator and decoder file polling runtime for the validation POC

- `frontend/client-2d`
  Leaflet-based 2D operations client for snapshot/delta verification and live traffic monitoring

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

Install backend runtime dependencies with:

```bash
python3 -m pip install -r backend/requirements.txt
```

You can run the default 2D tracker with the built-in sample feed:

```bash
cd backend
python3 -m app.main
```

Then open:

```text
http://127.0.0.1:8000/
```

The root path serves the 2D tracker directly.

You can also run the 2D client standalone with:

```bash
cd frontend/client-2d
python3 -m http.server 8080
```

Then open `http://localhost:8080` and either:

- connect to a live websocket backend
- or run the built-in sample stream

To poll a real decoder file such as `readsb` or `dump1090` `aircraft.json`, start the backend in file mode:

```bash
cd backend
ADSB_SOURCE_MODE=readsb_file \
ADSB_SOURCE_NAME=dump1090 \
ADSB_DECODER_TYPE=dump1090 \
ADSB_READSB_SNAPSHOT_PATH=/absolute/path/to/aircraft.json \
python3 -m app.main
```

Optional runtime configuration:

- `ADSB_STALE_AFTER_SECONDS`
  Override stale track eviction timing. The default is `12`.

- `ADSB_POLL_INTERVAL_SECONDS`
  Override how often the backend polls the decoder file. The default is `1.0`.

- `ADSB_SAMPLE_INTERVAL_SECONDS`
  Override the built-in sample feed tick interval. The default is `1.2`.

## Roadmap

- Continue upgrading the 2D operations screen with filters, follow controls, and live SDR validation tooling
- Validate the full stack against a real `readsb` or `dump1090` source in the field
- Add recording, replay, and analytics
- Harden setup, packaging, and CI for repeatable local installs

## Tech Direction

- Decoder: `readsb`, `dump1090`, or a compatible ADS-B JSON source
- Backend: Python
- Realtime transport: WebSocket
- Frontend target: Leaflet-based 2D operations UI

## Why This Project Exists

This project is intentionally framed as a real-time geospatial data pipeline, not just a map UI. The main engineering value is in the signal-derived data flow:

decoder output -> normalization -> live state -> realtime distribution -> map rendering

That separation keeps the system easier to scale, test, and extend.
