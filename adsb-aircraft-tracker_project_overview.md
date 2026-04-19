# Real-Time Aircraft Tracking and 3D Mapping System

## Project Overview

This project is an end-to-end **real-time aircraft tracking and geospatial visualization system** built on top of **RTL-SDR**, **ADS-B decoding**, **Python-based backend processing**, and **2D/3D map rendering**.

The goal is not to reinvent an already-solved flight tracking product, but to build a technically solid system that develops real capability in these areas:

- ingesting real-world RF-derived data,
- processing and normalizing live telemetry,
- managing real-time state efficiently,
- streaming updates with low latency,
- rendering aircraft on a 2D/3D map in a stable and performant way,
- and designing an extensible architecture suitable for open-source sharing.

In other words, the real value of the project is **not the map itself**, but the **pipeline from live signal-derived data to operational visualization**.

---

## Core Objective

Build a system that can:

1. receive real aircraft data through an RTL-SDR setup,
2. decode ADS-B / Mode-S messages via a decoder such as `readsb` or `dump1090-fa`,
3. parse and normalize telemetry into a clean internal data model,
4. maintain live aircraft state over time,
5. push updates to clients in real time,
6. render aircraft positions, movement, heading, altitude, and trails on a 2D/3D map,
7. and later support replay, analytics, and more advanced air-picture features.

---

## Strategic Positioning

This project should be positioned as a **real-time geospatial data pipeline project**, not as a simple "map app".

A weak framing would be:

> "I built a flight tracking interface."

A stronger and more accurate framing is:

> "I built a real-time ADS-B aircraft tracking pipeline using RTL-SDR, Python, WebSockets, and CesiumJS, including telemetry normalization, live state management, and 2D/3D geospatial visualization."

That positioning is more credible, more technical, and more valuable in a GitHub portfolio.

---

## Why This Project Matters

This project directly supports growth in the exact areas that matter:

- real-time data processing,
- geospatial visualization,
- live system architecture,
- frontend/backend separation,
- map performance,
- and operational rendering of moving targets.

It also bridges existing experience in map and display systems with a missing capability:

> handling **real live decoded data** and visualizing it continuously and correctly.

That is the actual skill gap this project closes.

---

## Design Principles

The architecture should follow these principles:

### 1. Separate domain state from render state
A flight track is not the same thing as a map marker.

- **Domain state** answers: what is the aircraft doing?
- **Render state** answers: what objects currently represent it on the map?

These must not be mixed.

### 2. Use identity-centered state management
Each aircraft should be tracked via a stable identity such as:

- ICAO hex / aircraft ID

All updates should reconcile against that identity.

### 3. Keep the hot path small
Live telemetry should remain lightweight.
Heavy details such as enriched metadata should not travel in the real-time stream unless necessary.

### 4. Build the pipeline first, polish later
The technically difficult and valuable part is:

- ingestion,
- normalization,
- state aggregation,
- live streaming,
- reconciliation,
- and performance.

Do not waste early effort on cosmetic UI or visual polish.

### 5. Make the project extensible
The first version should be simple, but the architecture should allow:

- replay,
- historical analysis,
- multi-layer filtering,
- 3D aircraft models,
- dashboards,
- and advanced visualization behaviors.

---

## High-Level System Architecture

The system should be organized into five major layers.

### 1. Data Acquisition Layer
Responsible for receiving real aircraft signal-derived data.

**Inputs:**
- RTL-SDR dongle
- appropriate ADS-B antenna
- decoder software such as `readsb` or `dump1090-fa`

**Responsibility:**
- receive ADS-B / Mode-S signals,
- decode them into structured records,
- expose usable output for downstream processing.

This project does **not** need to implement its own radio decoder. That would be a different project. The correct scope here is to consume decoded output and build the real-time pipeline on top of it.

### 2. Ingestion and Parsing Layer
Responsible for reading decoder output and converting it into a normalized internal representation.

**Responsibility:**
- read JSON/network output from decoder,
- parse aircraft telemetry fields,
- validate and normalize fields,
- map raw values into a stable schema.

### 3. Live State Aggregation Layer
Responsible for maintaining the current known state of all active aircraft.

**Responsibility:**
- merge repeated updates for the same aircraft,
- retain latest known telemetry,
- handle missing/partial updates,
- remove stale tracks,
- maintain bounded trail history,
- provide consistent live aircraft state to downstream consumers.

### 4. Realtime Distribution Layer
Responsible for pushing state updates to clients.

**Responsibility:**
- provide snapshot state for newly connected clients,
- provide incremental updates for changed aircraft,
- avoid unnecessary full-state retransmission,
- support low-latency frontend synchronization.

### 5. Visualization Layer
Responsible for 2D and 3D operational display.

**Responsibility:**
- display aircraft positions on map,
- rotate symbols/models by heading,
- render altitude and metadata,
- draw trails,
- allow aircraft selection,
- present details and analytics,
- support advanced 3D behavior over time.

---

## Recommended Technology Direction

The most rational architecture is:

### Backend
- **Python**
- FastAPI or equivalent lightweight async web framework
- WebSocket-based streaming

### Frontend
- **CesiumJS** for 3D primary visualization
- optional lightweight 2D validation client for early-stage verification
- TypeScript/JavaScript for browser-side rendering

### Decoder
- `readsb` or `dump1090-fa`

### Packaging / Distribution
- Docker / Docker Compose

### Why this stack
Because it keeps responsibilities clear:

- Python handles parsing, normalization, aggregation, and streaming.
- CesiumJS handles the 3D geospatial rendering problem properly.
- Decoder tools solve the already-solved RF decoding layer.

Trying to force the entire stack into a single language would not be elegant engineering. It would be comfort-driven design.

---

## What to Learn from the Reference Project

The examined reference project appears to use a sound but simple structural pattern. Its strongest ideas should be retained.

### Strong patterns observed

#### 1. Live aircraft state and map render state are separate
This is correct and should be preserved.

Example conceptually:

- `activeFlights` → domain/live data
- `aircraftStateMap` → marker/polyline/render references

#### 2. Aircraft are keyed by a stable identity
Each aircraft is reconciled by a unique identifier such as ICAO hex.

This prevents duplicate entities and allows incremental updates.

#### 3. Trail data is bounded
The reference project appears to keep a limited set of recent coordinates for each aircraft, rather than infinite history.

This is the right approach for live rendering.

#### 4. Detailed metadata is loaded separately
Heavy or infrequently needed fields are not forced into the hot path.

This is important and should be kept.

---

## Data Model Philosophy

The project should not be built around one giant aircraft object used everywhere.
That is sloppy design.

Instead, it should use different models for different responsibilities.

### A. Raw Input Model
Represents the decoder output before full normalization.

```text
RawAircraftMessage
- source
- timestamp
- aircraft_id
- raw_lat
- raw_lon
- raw_altitude
- raw_speed
- raw_heading
- raw_callsign
- raw_vertical_rate
- raw_payload
```

### B. Normalized Telemetry Model
Represents cleaned and normalized aircraft telemetry.

```text
AircraftTelemetry
- aircraft_id
- timestamp
- latitude
- longitude
- altitude_ft
- ground_speed_kt
- heading_deg
- vertical_rate_fpm
- callsign
- squawk
- category
- source
```

### C. Live Aggregated Aircraft State
Represents the current known state of an aircraft in the system.

```text
AircraftState
- aircraft_id
- callsign
- latitude
- longitude
- altitude_ft
- ground_speed_kt
- heading_deg
- vertical_rate_fpm
- last_seen
- status
- trail
```

### D. Realtime Client Payload
Represents the minimal stream sent to clients.

```text
AircraftUpdateDTO
- aircraft_id
- latitude
- longitude
- altitude_ft
- ground_speed_kt
- heading_deg
- callsign
- updated_at
```

This should stay compact.

### E. Render State Model
Represents browser/map-side object references only.

```text
AircraftRenderState
- aircraft_id
- marker_ref
- label_ref
- trail_ref
- trail_points
- last_rendered_at
```

This is not domain data. It is rendering infrastructure.

### F. Metadata / Enrichment Model
Represents optional additional details.

```text
AircraftMetadata
- aircraft_id
- registration
- manufacturer
- model
- operator
- origin
- destination
- image_url
- country
```

This should be fetched lazily or cached separately.

---

## Realtime State Management Strategy

The central backend structure should conceptually behave like this:

```text
Map<aircraft_id, AircraftState>
```

When a new telemetry message arrives:

1. identify the aircraft,
2. check if state already exists,
3. merge new fields into the existing state,
4. update `last_seen`,
5. append valid trail point,
6. emit snapshot or delta update as needed.

This is the core operating model.

### Stale Track Removal
Aircraft not updated after a configured timeout should be removed from active state.

This avoids ghost tracks and reflects real operating conditions.

### Trail Management
Trail history should be bounded.
For example:

- keep the last N points,
- or keep only the last X minutes.

Do not keep unbounded trail state in memory for live rendering.

---

## Frontend Reconciliation Model

The frontend should not blindly recreate all markers for every update.
That would be amateur-level performance design.

Instead, it should reconcile updates against a render-state map.

Conceptually:

```text
Map<aircraft_id, AircraftRenderState>
```

Update loop:

1. receive snapshot or delta update,
2. for each aircraft:
   - create visual object if absent,
   - otherwise update existing object,
3. trim trail if needed,
4. remove aircraft no longer active,
5. update selected aircraft panel if applicable.

This pattern is stable, scalable, and maintainable.

---

## Snapshot + Delta Model

The realtime layer should support two modes:

### Snapshot
When a client first connects:
- send current active aircraft set

### Delta
After that:
- send only changed/new/removed aircraft

This is significantly cleaner than brute-force repeated full-state transmission.

It also gives a more professional architecture and better room for scale.

---

## Visualization Strategy

The correct implementation order is:

### Phase 1: 2D validation view
Purpose:
- verify live data correctness,
- verify state updates,
- confirm heading, trail, and identity behavior,
- isolate data problems from 3D rendering issues.

### Phase 2: Cesium 3D operational view
Purpose:
- create the main product experience,
- represent aircraft in 3D,
- support richer spatial interaction,
- build the stronger portfolio artifact.

### Why not start directly with 3D?
Because when something breaks in a live system, there are already too many possible fault sources:

- bad telemetry,
- wrong heading,
- stale state,
- incorrect model orientation,
- altitude interpretation,
- terrain interactions,
- render performance issues.

A simple 2D validation client removes ambiguity.

---

## Suggested Feature Roadmap

### Milestone 1 — Live Ingestion MVP
Goal:
Establish a functioning signal-to-state pipeline.

Scope:
- RTL-SDR setup
- decoder integration
- Python ingestion
- telemetry parsing
- live aircraft state table
- terminal or debug viewer

Outcome:
A working system that receives and maintains live aircraft data.

### Milestone 2 — Realtime Client Delivery
Goal:
Expose live aircraft state to clients.

Scope:
- WebSocket endpoint
- snapshot support
- delta support
- stale cleanup
- compact update payloads

Outcome:
A reusable realtime backend for visualization.

### Milestone 3 — 2D Visualization
Goal:
Validate state visually.

Scope:
- simple map view
- aircraft markers
- heading-based icon rotation
- basic popup/details
- live movement
- trail rendering

Outcome:
A reliable correctness layer.

### Milestone 4 — Cesium 3D Visualization
Goal:
Build the main operational interface.

Scope:
- Cesium globe integration
- billboard or glTF aircraft representation
- heading/orientation handling
- altitude visualization
- trail display
- selection/focus controls

Outcome:
A strong portfolio-grade geospatial UI.

### Milestone 5 — Analytics and Operational Features
Goal:
Move beyond a simple tracker.

Scope:
- aircraft count dashboard
- altitude statistics
- speed summaries
- filters by class/type/source
- layer toggles
- coverage indicators

Outcome:
A more operationally meaningful system.

### Milestone 6 — Replay and Historical Mode
Goal:
Make the system substantially more valuable.

Scope:
- recording incoming telemetry
- playback engine
- timeline-based review
- basic persistence layer

Outcome:
A significantly stronger project than a live-only demo.

---

## Priority Order

This is the correct build order:

1. get live decoder data,
2. parse and normalize it,
3. aggregate active aircraft state,
4. stream it to clients,
5. validate in 2D,
6. build Cesium 3D experience,
7. add analytics,
8. add replay.

Any other order is likely to waste time.

---

## Common Failure Modes to Avoid

### 1. Starting from visual polish
This is procrastination disguised as productivity.

### 2. Mixing domain objects with map objects
This creates technical debt immediately.

### 3. Recreating markers every update
This kills performance and reflects weak state design.

### 4. Sending full aircraft state repeatedly
This is a brute-force architecture and should be avoided.

### 5. Storing infinite trail history in live memory
This is careless and will become a problem.

### 6. Trying to solve RF decoding from scratch
That is not this project.

### 7. Overbuilding too early
Do not build a giant system before proving the core live pipeline.

---

## Repository Structure Suggestion

```text
aircraft-tracking-system/
  README.md
  docs/
    architecture.md
    data-model.md
    roadmap.md
  backend/
    app/
      ingestion/
      parsing/
      normalization/
      state/
      streaming/
      api/
      models/
      services/
    tests/
  frontend/
    client-2d/
    client-3d-cesium/
  docker/
  samples/
  scripts/
```

This keeps the project readable and professionally organized.

---

## Documentation Expectations

The GitHub repository should eventually include:

- project objective,
- architecture diagram,
- data flow explanation,
- setup instructions,
- decoder integration notes,
- screenshots / GIFs,
- supported features,
- known limitations,
- roadmap,
- and sample data where possible.

A weak README makes even a good project look small.
A strong README makes the engineering visible.

---

## Final Architectural Summary

This project should be built as a **real-time aircraft telemetry pipeline** with clear separation between:

- raw input,
- normalized telemetry,
- live domain state,
- client stream payload,
- render cache,
- and optional metadata enrichment.

The best parts of the reference project to retain are:

- identity-based aircraft tracking,
- separation of live state and render state,
- bounded trail management,
- and lazy loading of details.

The improvements to make are:

- cleaner backend data modeling,
- explicit snapshot + delta streaming,
- stronger separation of hot-path and cold-path data,
- 2D validation before full 3D commitment,
- and a roadmap that includes replay and analytics.

If executed correctly, this will not just be a map demo.
It will be a technically credible system that demonstrates:

- realtime data ingestion,
- telemetry normalization,
- live state architecture,
- geospatial rendering,
- and practical systems engineering.

That is the level this project should target.
