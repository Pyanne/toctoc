"""Mock relay for testing — tracks open/close calls without hardware."""

from __future__ import annotations

import threading
from typing import Any

from anpr_gate.relay.base import GateRelayBase


class MockRelay(GateRelayBase):
    """In-memory relay that records all open/close calls."""

    def __init__(self, auto_respond: bool = True):
        self.auto_respond = auto_respond
        self.open_count = 0
        self.close_count = 0
        self._call_log: list[tuple[str, float]] = []
        self._lock = threading.Lock()
        self._online = True

    def open(self) -> bool:
        with self._lock:
            self.open_count += 1
            self._call_log.append(("open", 0.0))
        return self.auto_respond

    def close(self) -> bool:
        with self._lock:
            self.close_count += 1
            self._call_log.append(("close", 0.0))
        return self.auto_respond

    def is_online(self) -> bool:
        return self._online

    def set_online(self, state: bool):
        self._online = state

    @property
    def calls(self) -> list[tuple[str, float]]:
        with self._lock:
            return list(self._call_log)

    def reset(self):
        with self._lock:
            self.open_count = 0
            self.close_count = 0
            self._call_log.clear()