"""Framework adapters for HTTP and WebSocket endpoints."""

from .realtime import create_realtime_router

__all__ = ["create_realtime_router"]
