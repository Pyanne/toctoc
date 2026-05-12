"""HTTP relay for gate control using the requests library.

Replaces the old subprocess-based curl approach with proper HTTP client
handling, timeouts, and connection error recovery.
"""

from __future__ import annotations

import logging
from typing import Any

from anpr_gate.relay.base import GateRelayBase, RelayError

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class HTTPRelay(GateRelayBase):
    """Controls the gate opener relay via HTTP requests.

    Sends a brief pulse (open then close) to trigger the relay.
    The relay hardware handles the actual gate motor activation.
    """

    def __init__(self, cfg: Any):
        self._host = cfg.host
        self._url_open = cfg.url_open
        self._url_close = cfg.url_close
        self._pulse = cfg.pulse_duration
        self._ping_interval = getattr(cfg, "ping_interval", 1800)
        self._timeout = 5.0
        self._last_online_check = 0.0
        self._online = False

    def open(self) -> bool:
        """Pulse the relay to open the gate.

        Activates the relay, waits for the configured pulse duration,
        then deactivates it.
        """
        if not HAS_REQUESTS:
            raise RelayError("requests library not installed")

        try:
            # Activate relay
            resp = requests.get(
                f"http://{self._host}{self._url_open}",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            logger.debug("Relay open signal sent (status=%d)", resp.status_code)
        except Exception as exc:
            raise RelayError(f"Failed to activate relay: {exc}") from exc

        # Wait for the mechanical pulse to complete
        import time
        time.sleep(self._pulse)

        try:
            # Deactivate relay
            resp = requests.get(
                f"http://{self._host}{self._url_close}",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            logger.debug("Relay close signal sent (status=%d)", resp.status_code)
        except Exception as exc:
            # Non-fatal: the relay pulse already fired
            logger.warning("Relay deactivation failed: %s", exc)

        return True

    def close(self) -> bool:
        """Explicitly close the relay (stop motor if active)."""
        if not HAS_REQUESTS:
            raise RelayError("requests library not installed")

        try:
            resp = requests.get(
                f"http://{self._host}{self._url_close}",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            raise RelayError(f"Failed to close relay: {exc}") from exc

    def is_online(self) -> bool:
        """Check if the relay server is reachable."""
        if not HAS_REQUESTS:
            return False

        try:
            resp = requests.get(
                f"http://{self._host}/",
                timeout=3,
            )
            online = resp.status_code < 500
        except Exception:
            online = False

        self._online = online
        self._last_online_check = _monotime()
        return online

    @property
    def last_online_check(self) -> float:
        return self._last_online_check

    @property
    def online(self) -> bool:
        return self._online


def _monotime() -> float:
    import time
    return time.monotonic()