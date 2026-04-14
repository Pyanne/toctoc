"""Configuration file management for ANPR Gate Control."""
import configparser
import os
from typing import Dict, List, Tuple


class ConfigManager:
    """Manages reading and writing the portier.conf file."""

    DEFAULT_CONFIG = """[general]
quiet_mode = False
archive_enabled = True

[camera]
host = 192.168.20.21
port = 554
user = ced
password = Gougou00
path = /h264/ch1/main/av_stream

[camera.roi]
x1 = 1170
y1 = 450
x2 = 1640
y2 = 750

[paths]
snap_path = /tmp/picture.jpg
cropped_path = /tmp/cropped.jpg
archive_dir = plaques.d

[relay]
host = 192.168.20.26
url_open = /30000/07
url_close = /30000/06
pulse_duration = 1

[polling]
poll_interval = 2
cooldown_after_detection = 75
relay_ping_interval = 1800
"""

    def __init__(self, config_path: str = "portier.conf"):
        """Initialize the config manager.

        Args:
            config_path: Path to the configuration file
        """
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._load_or_create()

    def _load_or_create(self):
        """Load existing config or create default one."""
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
        else:
            self._create_default()

    def _create_default(self):
        """Create default configuration file."""
        self.config.read_string(self.DEFAULT_CONFIG)
        self.save()

    def save(self):
        """Save configuration to file."""
        with open(self.config_path, 'w') as f:
            self.config.write(f)

    def get(self, section: str, key: str, fallback=None):
        """Get a configuration value."""
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        """Get an integer configuration value."""
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def getfloat(self, section: str, key: str, fallback: float = 0.0) -> float:
        """Get a float configuration value."""
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        """Get a boolean configuration value."""
        try:
            return self.config.getboolean(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback

    def set(self, section: str, key: str, value):
        """Set a configuration value."""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))

    def get_allowed_plates(self) -> List[str]:
        """Get list of allowed license plates."""
        plates = []
        if self.config.has_section('plates'):
            for key, _ in self.config.items('plates'):
                if key != '__name__':
                    plates.append(key.strip().upper())
        return sorted(plates)

    def set_allowed_plates(self, plates: List[str]):
        """Set allowed license plates."""
        # Remove existing plates section if it exists
        if self.config.has_section('plates'):
            self.config.remove_section('plates')
        self.config.add_section('plates')
        for plate in plates:
            self.config.set('plates', plate.upper(), '1')

    def add_plate(self, plate: str):
        """Add a plate to the allowed list."""
        plate = plate.strip().upper()
        if not self.config.has_section('plates'):
            self.config.add_section('plates')
        self.config.set('plates', plate, '1')

    def remove_plate(self, plate: str):
        """Remove a plate from the allowed list."""
        plate = plate.strip().upper()
        if self.config.has_section('plates'):
            try:
                self.config.remove_option('plates', plate)
            except configparser.NoOptionError:
                pass

    def get_roi(self) -> Tuple[int, int, int, int]:
        """Get Region of Interest coordinates as (x1, y1, x2, y2)."""
        return (
            self.getint('camera.roi', 'x1'),
            self.getint('camera.roi', 'y1'),
            self.getint('camera.roi', 'x2'),
            self.getint('camera.roi', 'y2')
        )

    def set_roi(self, x1: int, y1: int, x2: int, y2: int):
        """Set Region of Interest coordinates."""
        if not self.config.has_section('camera.roi'):
            self.config.add_section('camera.roi')
        self.config.set('camera.roi', 'x1', str(x1))
        self.config.set('camera.roi', 'y1', str(y1))
        self.config.set('camera.roi', 'x2', str(x2))
        self.config.set('camera.roi', 'y2', str(y2))

    def get_rtsp_url(self) -> str:
        """Build and return the RTSP URL."""
        user = self.get('camera', 'user', '')
        password = self.get('camera', 'password', '')
        host = self.get('camera', 'host', 'localhost')
        port = self.getint('camera', 'port', 554)
        path = self.get('camera', 'path', '/')
        return f"rtsp://{user}:{password}@{host}:{port}{path}"

    def get_all_camera_config(self) -> Dict:
        """Get all camera configuration as a dict."""
        return {
            'host': self.get('camera', 'host', 'localhost'),
            'port': self.getint('camera', 'port', 554),
            'user': self.get('camera', 'user', ''),
            'password': self.get('camera', 'password', ''),
            'path': self.get('camera', 'path', '/'),
        }

    def get_all_relay_config(self) -> Dict:
        """Get all relay configuration as a dict."""
        return {
            'host': self.get('relay', 'host', 'localhost'),
            'url_open': self.get('relay', 'url_open', ''),
            'url_close': self.get('relay', 'url_close', ''),
            'pulse_duration': self.getfloat('relay', 'pulse_duration', 1.0),
        }

    def get_all_polling_config(self) -> Dict:
        """Get all polling configuration as a dict."""
        return {
            'poll_interval': self.getint('polling', 'poll_interval', 2),
            'cooldown_after_detection': self.getint('polling', 'cooldown_after_detection', 75),
            'relay_ping_interval': self.getint('polling', 'relay_ping_interval', 1800),
        }
