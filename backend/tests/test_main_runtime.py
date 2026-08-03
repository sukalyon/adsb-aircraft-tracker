from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.runtime.support import ensure_websocket_runtime_support


class MainRuntimeTests(unittest.TestCase):
    def test_websocket_runtime_check_accepts_websockets_dependency(self) -> None:
        with patch("app.runtime.support.importlib.util.find_spec") as find_spec:
            find_spec.side_effect = [object(), None]

            ensure_websocket_runtime_support()

    def test_websocket_runtime_check_accepts_wsproto_dependency(self) -> None:
        with patch("app.runtime.support.importlib.util.find_spec") as find_spec:
            find_spec.side_effect = [None, object()]

            ensure_websocket_runtime_support()

    def test_websocket_runtime_check_raises_without_supported_dependency(self) -> None:
        with patch("app.runtime.support.importlib.util.find_spec", return_value=None):
            with self.assertRaises(RuntimeError):
                ensure_websocket_runtime_support()


if __name__ == "__main__":
    unittest.main()
