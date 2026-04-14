"""Gate relay control module."""
import subprocess
import time
from urllib.parse import urljoin


class GateRelay:
    """Controls the gate opener relay via HTTP requests."""

    def __init__(self, host: str, url_open: str, url_close: str, pulse_duration: float = 1.0):
        """Initialize the relay controller.

        Args:
            host: Relay server IP/hostname
            url_open: URL path to activate relay
            url_close: URL path to deactivate relay
            pulse_duration: Duration of the relay pulse in seconds
        """
        self.host = host
        self.url_open_path = url_open
        self.url_close_path = url_close
        self.pulse_duration = pulse_duration
        self._url_open = f"http://{host}{url_open}"
        self._url_close = f"http://{host}{url_close}"

    def open(self) -> bool:
        """Trigger the gate to open.

        Returns:
            True if gate opened successfully, False otherwise
        """
        try:
            # Activate relay (close contacts)
            subprocess.run(
                ["curl", "-s", self._url_open],
                capture_output=True,
                timeout=5
            )

            # Wait for pulse duration
            time.sleep(self.pulse_duration)

            # Deactivate relay (open contacts)
            subprocess.run(
                ["curl", "-s", self._url_close],
                capture_output=True,
                timeout=5
            )

            return True
        except Exception:
            return False

    def is_online(self) -> bool:
        """Check if the relay server is reachable.

        Returns:
            True if relay is reachable, False otherwise
        """
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", self.host],
                capture_output=True,
                timeout=3
            )
            return result.returncode == 0
        except Exception:
            return False
