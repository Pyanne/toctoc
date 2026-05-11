"""Gate state enum."""

from __future__ import annotations

from enum import Enum


class GateState(Enum):
    """Possible gate states as reported by the detector."""
    CLOSED = "closed"
    OPEN = "open"
    UNKNOWN = "unknown"