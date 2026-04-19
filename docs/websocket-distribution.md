# WebSocket Distribution Service

## Goal

Attach the snapshot/delta wire contract to real client connections.

This layer is responsible for connection lifecycle and message fan-out.
It is not responsible for telemetry parsing or state aggregation.

## Python Concepts Used Here

- `Protocol`: describes the websocket methods we expect without binding to a specific framework
- `dataclass`: keeps per-client session state simple and explicit
- async methods: allow one hub to manage many websocket clients

## Main Types

### `JsonWebSocketConnection`

This is a protocol, not a concrete websocket implementation.
It says the transport object must support:

- `accept()`
- `send_json(...)`
- `close(...)`

That lets us test the hub with fake sockets and plug in FastAPI later without rewriting the distribution logic.

### `WebSocketClientSession`

Represents one connected client.

It stores:

- `client_id`
- the underlying socket
- the next sequence number for that client
- simple connection counters

### `RealtimeWebSocketHub`

This is the connection manager.

Responsibilities:

- accept a new client
- send the initial snapshot
- publish delta events to all connected clients
- drop broken connections

## Sequence Strategy

Sequence is tracked per client connection.

Why:

- every client starts with `snapshot` sequence `1`
- clients do not see gaps caused by other clients connecting
- ordering is easier to reason about on the frontend

## Delivery Rules

- `connect(...)` accepts the socket and immediately sends a snapshot
- `publish_delta(...)` broadcasts delta events to all connected clients
- empty deltas are not sent
- publish failures cause that client session to be dropped

## Framework Boundary

The current hub is framework-agnostic.
In the next step, we can attach it to a FastAPI websocket endpoint without changing the hub internals.
