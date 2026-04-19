# Realtime Event Contract

## Goal

Define the payload shape that clients will receive from the realtime backend.

This contract is intentionally separate from the in-memory domain state.
The backend keeps richer state internally, while the stream sends only the fields needed on the hot path.

## Design Rules

- New clients receive a `snapshot` event first.
- Connected clients then receive `delta` events only.
- Contract versioning starts at `1`.
- Event ordering is tracked with a monotonically increasing `sequence`.
- `ignored` state changes never leave the backend.
- `created` and `updated` state changes are both serialized as `upsert`.
- `removed` state changes are serialized as `remove`.

## Event Types

### Snapshot Event

Purpose:

- Bring a newly connected client to the current active aircraft state.

Shape:

```json
{
  "type": "snapshot",
  "version": 1,
  "sequence": 1,
  "sent_at": "2026-04-14T10:00:00Z",
  "total": 2,
  "aircraft": [
    {
      "aircraft_id": "4ca123",
      "updated_at": "2026-04-14T09:59:58Z",
      "latitude": 41.2758,
      "longitude": 28.7519,
      "altitude_ft": 32000,
      "ground_speed_kt": 438.5,
      "heading_deg": 92.4,
      "callsign": "THY7AB"
    }
  ]
}
```

### Delta Event

Purpose:

- Send only changed or removed aircraft after the initial snapshot.

Shape:

```json
{
  "type": "delta",
  "version": 1,
  "sequence": 2,
  "sent_at": "2026-04-14T10:00:05Z",
  "changes": [
    {
      "action": "upsert",
      "aircraft_id": "4ca123",
      "aircraft": {
        "aircraft_id": "4ca123",
        "updated_at": "2026-04-14T10:00:05Z",
        "latitude": 41.2762,
        "longitude": 28.7601,
        "altitude_ft": 32100,
        "ground_speed_kt": 441.0,
        "heading_deg": 94.0,
        "callsign": "THY7AB"
      }
    },
    {
      "action": "remove",
      "aircraft_id": "a8b42f",
      "reason": "stale_timeout"
    }
  ]
}
```

## Payload Mapping

### Snapshot Payload

Source:

- `AircraftStateStore.snapshot()`

Mapped with:

- `state_to_update_dto()`
- `build_snapshot_event()`

### Delta Payload

Source:

- `StateChange` values returned by the state store

Mapping:

- `created` -> `upsert`
- `updated` -> `upsert`
- `removed` -> `remove`
- `ignored` -> dropped

Mapped with:

- `build_delta_event()`

## Why This Separation Matters

- The in-memory state can stay rich and backend-oriented.
- The wire payload stays compact and frontend-oriented.
- 2D and 3D clients can share the same stream contract.
- Contract changes can be versioned without reshaping the internal store.

## Phase 2 Task 1 Delivery

Task complete when:

- the event contract is written down
- snapshot payload generation is implemented
- delta payload generation is implemented
- serialization is test-covered
