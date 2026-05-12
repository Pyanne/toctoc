"""Relay module — lightweight imports only."""

from anpr_gate.relay.base import GateRelayBase, RelayError
from anpr_gate.relay.mock_relay import MockRelay

# HTTPRelay imported lazily via container.py
__all__ = ["GateRelayBase", "RelayError", "MockRelay", "HTTPRelay"]