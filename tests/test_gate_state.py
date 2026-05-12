"""Tests for gate state enum."""

from anpr_gate.gate.state import GateState


class TestGateState:
    def test_closed_value(self):
        assert GateState.CLOSED.value == "closed"

    def test_open_value(self):
        assert GateState.OPEN.value == "open"

    def test_unknown_value(self):
        assert GateState.UNKNOWN.value == "unknown"

    def test_all_states(self):
        states = {s.value for s in GateState}
        assert "closed" in states
        assert "open" in states
        assert "unknown" in states