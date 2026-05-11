"""Abstract relay interface for gate control."""

from __future__ import annotations

from abc import ABC, abstractmethod


class RelayError(Exception):
    """Raised when relay operation fails."""


class GateRelayBase(ABC):
    """Interface for controlling a gate opening relay.

    Implementations should handle the open/close pulse sequence
    required by the specific relay hardware.
    """

    @abstractmethod
    def open(self) -> bool:
        """Trigger the gate to open. Returns True on success."""
        ...

    @abstractmethod
    def close(self) -> bool:
        """Trigger the gate to close. Returns True on success."""
        ...

    @abstractmethod
    def is_online(self) -> bool:
        """Check if the relay is reachable."""
        ...