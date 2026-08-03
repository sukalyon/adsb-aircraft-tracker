from __future__ import annotations

import importlib.util


def ensure_websocket_runtime_support() -> None:
    """Fail fast when the ASGI server lacks websocket protocol support."""
    if importlib.util.find_spec("websockets") is not None:
        return
    if importlib.util.find_spec("wsproto") is not None:
        return
    raise RuntimeError(
        "WebSocket runtime support is missing. Install 'websockets' or 'wsproto' "
        "before starting the validation backend."
    )
