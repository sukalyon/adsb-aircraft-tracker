from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol
from uuid import uuid4

from app.models.aircraft import AircraftState
from app.state.store import StateChange

from .contracts import build_delta_event, build_snapshot_event


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


class RealtimeWebSocketHub:
    def __init__(self) -> None:
        self._sessions: dict[str, WebSocketClientSession] = {}

    @property
    def connected_count(self) -> int:
        return len(self._sessions)

    def session_ids(self) -> list[str]:
        return sorted(self._sessions)

    async def connect(
        self,
        socket: JsonWebSocketConnection,
        *,
        snapshot_states: Iterable[AircraftState],
    ) -> str:
        await socket.accept()
        session = WebSocketClientSession(client_id=uuid4().hex, socket=socket)
        self._sessions[session.client_id] = session

        snapshot_event = build_snapshot_event(
            snapshot_states,
            sequence=session.reserve_sequence(),
        )
        try:
            await socket.send_json(snapshot_event.to_dict())
        except Exception:
            await self._drop_session(session.client_id, close_code=1011)
            raise

        return session.client_id

    async def disconnect(self, client_id: str, *, close_code: int = 1000) -> bool:
        if client_id not in self._sessions:
            return False

        await self._drop_session(client_id, close_code=close_code)
        return True

    async def publish_delta(self, changes: Iterable[StateChange]) -> int:
        change_list = list(changes)
        delivered = 0
        disconnected_clients: list[str] = []

        for session in list(self._sessions.values()):
            delta_event = build_delta_event(
                change_list,
                sequence=session.reserve_sequence(),
            )
            if not delta_event.changes:
                session.next_sequence -= 1
                session.sent_event_count -= 1
                continue

            try:
                await session.socket.send_json(delta_event.to_dict())
            except Exception:
                disconnected_clients.append(session.client_id)
                continue

            delivered += 1

        for client_id in disconnected_clients:
            await self._drop_session(client_id, close_code=1011)

        return delivered

    async def _drop_session(self, client_id: str, *, close_code: int) -> None:
        session = self._sessions.pop(client_id, None)
        if session is None:
            return

        try:
            await session.socket.close(code=close_code)
        except Exception:
            return
