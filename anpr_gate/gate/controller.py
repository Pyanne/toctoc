"""Gate state enum and controller with safety interlocks.

The gate controller implements a state machine:
  CLOSED → OPENING → OPEN → CLOSING → CLOSED

Safety features:
- Debounce: minimum time between relay pulses
- Never auto-close if gate was opened by remote
- Configurable auto-close timeout
- Open/close event callbacks
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class GateState(enum.Enum):
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    UNKNOWN = "unknown"


class GateController:
    """Manages gate state with safety interlocks.

    The gate is opened by pulsing the relay briefly. The actual gate motor
    (e.g. Avidsen TEHA 410) takes ~16s to complete the full travel.

    Auto-close: if the gate stays open longer than ``auto_close_delay`` seconds
    (as detected by the gate state detector), the controller will pulse the relay
    to close it. This prevents the gate from being left open indefinitely.

    Safety: the gate is never closed if the detector reports it is already open
    by other means (remote control, manual override).
    """

    DEBOUNCE_SECONDS = 2.0  # minimum time between relay activations

    def __init__(
        self,
        relay: Any,
        travel_time: float = 16.0,
        auto_close_delay: float = 180.0,
    ):
        self._relay = relay
        self._travel_time = travel_time
        self._auto_close_delay = auto_close_delay

        self._state = GateState.CLOSED
        self._state_changed_at = time.monotonic()
        self._last_relay_pulse = 0.0
        self._opened_by_us = False  # track if we opened it (vs remote)
        self._on_state_change: list[Callable] = []

    def open(self) -> bool:
        """Open the gate by pulsing the relay."""
        if not self._can_transition(GateState.OPENING):
            return False

        self._set_state(GateState.OPENING)
        try:
            self._relay.open()
        except Exception as exc:
            logger.error("Relay open failed: %s", exc)
            self._set_state(GateState.CLOSED)  # rollback
            return False

        self._opened_by_us = True
        self._last_relay_pulse = time.monotonic()
        self._set_state(GateState.OPEN)
        return True

    def close(self) -> bool:
        """Close the gate by pulsing the relay."""
        if not self._can_transition(GateState.CLOSING):
            return False

        self._set_state(GateState.CLOSING)
        try:
            self._relay.open()  # relay toggle: same pulse opens or closes
        except Exception as exc:
            logger.error("Relay close failed: %s", exc)
            self._set_state(GateState.OPEN)
            return False

        self._last_relay_pulse = time.monotonic()
        self._set_state(GateState.CLOSED)
        return True

    def auto_close_if_needed(self, gate_detector_state: str) -> bool:
        """Attempt auto-close if gate has been open too long.

        Args:
            gate_detector_state: Current state from gate state detector
                ("open", "closed", or "unknown")

        Returns:
            True if auto-close was triggered, False otherwise.
        """
        # Only auto-close if WE opened it (not remote)
        if not self._opened_by_us:
            return False

        # Respect debounce
        if time.monotonic() - self._last_relay_pulse < self.DEBOUNCE_SECONDS:
            return False

        # Gate detector confirms it's still open
        if gate_detector_state != "open":
            return False

        # Enough time has passed
        if time.monotonic() - self._state_changed_at < self._auto_close_delay:
            return False

        logger.info("Auto-closing gate (open for %.0fs)",
                     time.monotonic() - self._state_changed_at)
        return self.close()

    def on_state_change(self, callback: Callable[[GateState], None]):
        """Register a callback for state changes."""
        self._on_state_change.append(callback)

    def set_state_from_detector(self, detector_state: str):
        """Update our state estimate from the gate state detector.

        This is called when the detection loop gets a fresh gate state reading.
        """
        if detector_state == "open":
            self._set_state(GateState.OPEN)
            self._opened_by_us = False  # could have been remote
        elif detector_state == "closed":
            if self._state in (GateState.OPEN, GateState.OPENING, GateState.CLOSING):
                self._set_state(GateState.CLOSED)
                self._opened_by_us = False
        # "unknown" — don't change state, just log

    def stop_auto_close(self):
        """Cancel any pending auto-close (called when user manually opens)."""
        self._opened_by_us = False

    @property
    def state(self) -> GateState:
        return self._state

    @property
    def opened_by_us(self) -> bool:
        return self._opened_by_us

    # --- Internal ---

    def _can_transition(self, target: GateState) -> bool:
        now = time.monotonic()
        # Debounce
        if now - self._last_relay_pulse < self.DEBOUNCE_SECONDS:
            logger.debug("Debounced: last pulse was %.1fs ago",
                         now - self._last_relay_pulse)
            return False

        # State transitions
        valid: dict[GateState, set[GateState]] = {
            GateState.OPENING: {GateState.CLOSED},
            GateState.CLOSING: {GateState.OPEN},
        }
        if target in valid and self._state not in valid[target]:
            logger.debug("Invalid transition: %s → %s", self._state.value, target.value)
            return False

        return True

    def _set_state(self, new_state: GateState):
        old = self._state
        self._state = new_state
        self._state_changed_at = time.monotonic()
        logger.info("Gate state: %s → %s", old.value, new_state.value)
        for cb in self._on_state_change:
            try:
                cb(new_state)
            except Exception:
                pass