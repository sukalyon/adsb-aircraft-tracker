"""Framework adapters for HTTP and WebSocket endpoints."""

from .realtime import register_realtime_websocket

__all__ = ["register_realtime_websocket"]
