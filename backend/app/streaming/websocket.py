from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol
from uuid import uuid4

from app.models.aircraft import AircraftState
from app.state.store import StateChange

from .contracts import DeltaStreamEvent, build_snapshot_event, prepare_delta_changes


class JsonWebSocketConnection(Protocol):
    async def accept(self) -> None:
        """Accept the websocket connection."""

    async def send_json(self, payload: dict[str, Any]) -> None:
        """Send a JSON-serializable payload to the client."""

    async def close(self, code: int = 1000) -> None:
        """Close the websocket connection."""


@dataclass(slots=True)
class WebSocketClientSession:
    client_id: str
    socket: JsonWebSocketConnection
    next_sequence: int = 1
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_event_count: int = 0

    def reserve_sequence(self) -> int:
        sequence = self.next_sequence
        self.next_sequence += 1
        self.sent_event_count += 1
        return sequence


@dataclass(slots=True, frozen=True)
class PublishDeltaResult:
    attempted_client_count: int
    delivered_client_count: int
    dropped_client_count: int
    emitted_change_count: int
    seen_change_count: int
    publishable_change_count: int
    suppressed_change_count: int
    ignored_change_count: int


@dataclass(slots=True, frozen=True)
class WebSocketHubMetricsSnapshot:
    connected_client_count: int
    total_connections_accepted: int
    total_disconnects: int
    total_snapshot_messages_sent: int
    total_delta_publish_calls: int
    total_delta_messages_sent: int
    total_delta_change_entries_sent: int
    total_client_send_failures: int
    total_seen_state_changes: int
    total_publishable_state_changes: int
    total_suppressed_state_changes: int
    total_ignored_state_changes: int
    last_snapshot_sent_at: datetime | None
    last_delta_sent_at: datetime | None


class RealtimeWebSocketHub:
    def __init__(self) -> None:
        self._sessions: dict[str, WebSocketClientSession] = {}
        self._total_connections_accepted = 0
        self._total_disconnects = 0
        self._total_snapshot_messages_sent = 0
        self._total_delta_publish_calls = 0
        self._total_delta_messages_sent = 0
        self._total_delta_change_entries_sent = 0
        self._total_client_send_failures = 0
        self._total_seen_state_changes = 0
        self._total_publishable_state_changes = 0
        self._total_suppressed_state_changes = 0
        self._total_ignored_state_changes = 0
        self._last_snapshot_sent_at: datetime | None = None
        self._last_delta_sent_at: datetime | None = None

    @property
    def connected_count(self) -> int:
        return len(self._sessions)

    def session_ids(self) -> list[str]:
        return sorted(self._sessions)

    def metrics_snapshot(self) -> WebSocketHubMetricsSnapshot:
        return WebSocketHubMetricsSnapshot(
            connected_client_count=self.connected_count,
            total_connections_accepted=self._total_connections_accepted,
            total_disconnects=self._total_disconnects,
            total_snapshot_messages_sent=self._total_snapshot_messages_sent,
            total_delta_publish_calls=self._total_delta_publish_calls,
            total_delta_messages_sent=self._total_delta_messages_sent,
            total_delta_change_entries_sent=self._total_delta_change_entries_sent,
            total_client_send_failures=self._total_client_send_failures,
            total_seen_state_changes=self._total_seen_state_changes,
            total_publishable_state_changes=self._total_publishable_state_changes,
            total_suppressed_state_changes=self._total_suppressed_state_changes,
            total_ignored_state_changes=self._total_ignored_state_changes,
            last_snapshot_sent_at=self._last_snapshot_sent_at,
            last_delta_sent_at=self._last_delta_sent_at,
        )

    async def connect(
        self,
        socket: JsonWebSocketConnection,
        *,
        snapshot_states: Iterable[AircraftState],
    ) -> str:
        await socket.accept()
        session = WebSocketClientSession(client_id=uuid4().hex, socket=socket)
        self._sessions[session.client_id] = session
        self._total_connections_accepted += 1

        snapshot_event = build_snapshot_event(
            snapshot_states,
            sequence=session.reserve_sequence(),
        )
        try:
            await socket.send_json(snapshot_event.to_dict())
        except Exception:
            self._total_client_send_failures += 1
            await self._drop_session(session.client_id, close_code=1011)
            raise

        self._total_snapshot_messages_sent += 1
        self._last_snapshot_sent_at = snapshot_event.sent_at

        return session.client_id

    async def disconnect(self, client_id: str, *, close_code: int = 1000) -> bool:
        if client_id not in self._sessions:
            return False

        await self._drop_session(client_id, close_code=close_code)
        return True

    async def publish_delta(self, changes: Iterable[StateChange]) -> PublishDeltaResult:
        change_list = list(changes)
        prepared = prepare_delta_changes(change_list)
        self._total_delta_publish_calls += 1
        self._total_seen_state_changes += prepared.seen_change_count
        self._total_publishable_state_changes += prepared.publishable_change_count
        self._total_suppressed_state_changes += prepared.suppressed_change_count
        self._total_ignored_state_changes += prepared.ignored_change_count

        if not prepared.delta_changes:
            return PublishDeltaResult(
                attempted_client_count=self.connected_count,
                delivered_client_count=0,
                dropped_client_count=0,
                emitted_change_count=0,
                seen_change_count=prepared.seen_change_count,
                publishable_change_count=prepared.publishable_change_count,
                suppressed_change_count=prepared.suppressed_change_count,
                ignored_change_count=prepared.ignored_change_count,
            )

        delivered = 0
        disconnected_clients: list[str] = []
        sent_at = datetime.now(timezone.utc)

        for session in list(self._sessions.values()):
            delta_event = DeltaStreamEvent(
                sequence=session.reserve_sequence(),
                sent_at=sent_at,
                changes=prepared.delta_changes,
            )
            try:
                await session.socket.send_json(delta_event.to_dict())
            except Exception:
                self._total_client_send_failures += 1
                disconnected_clients.append(session.client_id)
                continue

            delivered += 1

        for client_id in disconnected_clients:
            await self._drop_session(client_id, close_code=1011)

        if delivered > 0:
            self._total_delta_messages_sent += delivered
            self._total_delta_change_entries_sent += delivered * len(prepared.delta_changes)
            self._last_delta_sent_at = sent_at

        return PublishDeltaResult(
            attempted_client_count=self.connected_count + len(disconnected_clients),
            delivered_client_count=delivered,
            dropped_client_count=len(disconnected_clients),
            emitted_change_count=len(prepared.delta_changes),
            seen_change_count=prepared.seen_change_count,
            publishable_change_count=prepared.publishable_change_count,
            suppressed_change_count=prepared.suppressed_change_count,
            ignored_change_count=prepared.ignored_change_count,
        )

    async def _drop_session(self, client_id: str, *, close_code: int) -> None:
        session = self._sessions.pop(client_id, None)
        if session is None:
            return

        self._total_disconnects += 1

        try:
            await session.socket.close(code=close_code)
        except Exception:
            return
