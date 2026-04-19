# Realtime Change Detection and Observability

## Goal

Reduce unnecessary realtime traffic and expose enough internal counters to understand what the stream layer is doing.

This phase focuses on two questions:

1. Did the incoming state change actually affect the client payload?
2. What happened when we tried to publish it?

## Change Detection Strategy

Change detection is split across two layers.

### State Layer

`AircraftStateStore` now emits `StateChange.changed_fields`.

That means every state transition carries a compact description of what actually changed in the in-memory aircraft state, for example:

- `("latitude", "longitude", "heading_deg")`
- `("ground_speed_kt",)`
- `()`

An empty tuple means the update advanced internal timing but did not materially change tracked aircraft values.

### Streaming Layer

The websocket contract does not care about every domain field.

The current hot-path delta payload only includes:

- `callsign`
- `latitude`
- `longitude`
- `altitude_ft`
- `ground_speed_kt`
- `heading_deg`

Because of that, the streaming layer suppresses updates that only changed non-wire fields such as:

- `squawk`
- `category`
- `vertical_rate_fpm`

Those fields may still matter later, but they do not currently justify a delta publish.

## Preparation Step

`prepare_delta_changes(...)` converts raw `StateChange` entries into two outputs:

- a filtered list of delta payload changes
- counters describing what happened in the batch

Tracked counts:

- `seen_change_count`
- `publishable_change_count`
- `suppressed_change_count`
- `ignored_change_count`

## WebSocket Hub Metrics

`RealtimeWebSocketHub.metrics_snapshot()` exposes cumulative counters for the transport layer.

Tracked metrics:

- connected clients
- accepted connections
- disconnects
- snapshot messages sent
- delta publish calls
- delta messages sent
- delta change entries sent
- client send failures
- seen state changes
- publishable state changes
- suppressed state changes
- ignored state changes
- last snapshot timestamp
- last delta timestamp

## Why This Matters

- The backend now avoids sending deltas for changes that do not affect the current client contract.
- We can inspect whether the system is quiet because traffic is low or because updates are being suppressed.
- We can tell whether publish problems come from transport failures or from there being nothing meaningful to send.

## Current Limitation

The suppression rule is based on the current websocket DTO, not on a future richer client contract.

If the realtime payload later includes more fields, the publish field set should be updated accordingly.
