"""Tests for the relay module."""

from __future__ import annotations

import pytest

from anpr_gate.relay.mock_relay import MockRelay
from anpr_gate.relay.http_relay import HTTPRelay
from anpr_gate.relay.base import RelayError


class TestMockRelay:
    def test_initial_state(self):
        r = MockRelay()
        assert r.open_count == 0
        assert r.close_count == 0
        assert r.calls == []

    def test_open_increments(self):
        r = MockRelay()
        r.open()
        assert r.open_count == 1

    def test_close_increments(self):
        r = MockRelay()
        r.close()
        assert r.close_count == 1

    def test_reset(self):
        r = MockRelay()
        r.open()
        r.close()
        r.reset()
        assert r.open_count == 0
        assert r.close_count == 0
        assert r.calls == []

    def test_offline_returns_false(self):
        r = MockRelay(auto_respond=False)
        r.set_online(False)
        assert not r.is_online()


class TestHTTPRelay:
    def test_requires_requests(self):
        try:
            import requests
            has_requests = True
        except ImportError:
            has_requests = False

        if not has_requests:
            r = HTTPRelay(type("Cfg", (), {"host": "x"})())  # type: ignore
            with pytest.raises(RelayError, match="requests"):
                r.open()

    def test_config_attrs(self):
        cfg = type("Cfg", (), {
            "host": "192.168.20.26",
            "url_open": "/30000/07",
            "url_close": "/30000/06",
            "pulse_duration": 1.0,
            "ping_interval": 1800,
        })()
        r = HTTPRelay(cfg)
        assert r._host == "192.168.20.26"