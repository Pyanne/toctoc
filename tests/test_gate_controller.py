"""Tests for the gate controller state machine."""

from __future__ import annotations

import time
import pytest

from anpr_gate.gate.controller import GateController, GateState
from anpr_gate.gate.state import GateState as DetectorState


class TestGateController:
    def test_initial_state(self, mock_relay):
        gc = GateController(mock_relay, travel_time=1.0, auto_close_delay=2.0)
        assert gc.state == GateState.CLOSED
        assert not gc.opened_by_us

    def test_open_transitions(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.01)
        assert gc.open() is True
        assert mock_relay.open_count == 1

    def test_close_transitions(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.01)
        # Manipulate internal time so debounce doesn't block
        gc._last_relay_pulse = 0.0
        assert gc.open() is True
        gc._last_relay_pulse = 0.0  # reset for debounce
        assert gc.close() is True

    def test_debounce_blocks_rapid_opens(self, mock_relay):
        gc = GateController(mock_relay, travel_time=10, auto_close_delay=100)
        gc.open()
        # Immediately trying to close should be debounced
        assert not gc.close()
        assert mock_relay.open_count == 1

    def test_detector_sets_open(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.01)
        gc.set_state_from_detector("open")
        assert gc.state == GateState.OPEN

    def test_detector_sets_closed(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.01)
        gc.set_state_from_detector("open")
        gc.set_state_from_detector("closed")
        assert gc.state == GateState.CLOSED

    def test_stop_auto_cancel(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.01)
        gc.open()
        gc.stop_auto_close()
        assert not gc.opened_by_us

    def test_invalid_transition_returns_false(self, mock_relay):
        gc = GateController(mock_relay, travel_time=10, auto_close_delay=100)
        # Can't close when already closed
        assert not gc.close()


class TestGateSafety:
    """Test the critical safety feature: never close a gate opened by remote."""

    def test_remote_open_not_auto_closed(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.01)
        # Detector says gate is open (remote opened it)
        gc.set_state_from_detector("open")
        # Our flag says we didn't open it
        assert not gc.opened_by_us
        # Auto-close should refuse
        assert not gc.auto_close_if_needed("open")

    def test_our_open_can_be_auto_closed(self, mock_relay):
        gc = GateController(mock_relay, travel_time=0.01, auto_close_delay=0.0)
        gc._last_relay_pulse = 0.0
        gc.open()
        gc._last_relay_pulse = 0.0  # reset debounce so close() isn't blocked
        assert gc.opened_by_us
        # Fast-forward the timer by manipulating internal state
        gc._state_changed_at = time.monotonic() - 100
        # Detector confirms open
        result = gc.auto_close_if_needed("open")
        assert result is True
        assert mock_relay.open_count > 0