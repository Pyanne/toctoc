"""Configuration management with typed validation and YAML support only."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid or missing required fields."""


# ---------------------------------------------------------------------------
# Typed config sections
# ---------------------------------------------------------------------------

@dataclass
class CameraConfig:
    host: str = ""
    port: int = 554
    user: str = ""
    password: str = ""
    path: str = "/h264/ch1/main/av_stream"
    roi_x1: int = 0
    roi_y1: int = 0
    roi_x2: int = 1920
    roi_y2: int = 1080
    snapshot_fps: int = 1  # how many snapshots per second to attempt

    def roi(self) -> tuple[int, int, int, int]:
        return self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2

    @property
    def rtsp_url(self) -> str:
        cred = f"{self.user}:{self.password}@" if self.user else ""
        return f"rtsp://{cred}{self.host}:{self.port}{self.path}"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.host:
            errors.append("camera.host is required")
        return errors


@dataclass
class RelayConfig:
    host: str = "192.168.20.26"
    url_open: str = "/30000/07"
    url_close: str = "/30000/06"
    pulse_duration: float = 1.0
    ping_interval: int = 1800  # seconds between health checks

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.host:
            errors.append("relay.host is required")
        if self.pulse_duration <= 0:
            errors.append("relay.pulse_duration must be > 0")
        return errors


@dataclass
class GateCameraConfig:
    host: str = "192.168.20.22"
    port: int = 82
    user: str = "admin"
    password: str = ""
    snapshot_path: str = "/ISAPI/Streaming/channels/101/picture"

    @property
    def snapshot_url(self) -> str:
        return f"http://{self.host}:{self.port}{self.snapshot_path}"

    @property
    def auth(self) -> str:
        return f"{self.user}:{self.password}"

    def validate(self) -> list[str]:
        return []  # optional; gate detection degrades gracefully


@dataclass
class GateDetectorConfig:
    ref_day_path: str = ""
    ref_night_path: str = ""
    threshold: float = 35.0
    enabled: bool = False
    reopen_check_interval: int = 180  # auto-close timer (seconds)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.enabled:
            if not self.ref_day_path:
                errors.append("gate_detector.ref_day_path is required when enabled")
            if not self.ref_night_path:
                errors.append("gate_detector.ref_night_path is required when enabled")
        if self.threshold <= 0:
            errors.append("gate_detector.threshold must be > 0")
        return errors


@dataclass
class OCRConfig:
    enabled: bool = True
    confidence_threshold: float = 0.15
    languages: list[str] = field(default_factory=lambda: ["en"])
    use_gpu: bool = False
    preprocess_upscale: int = 3       # upscale factor before OCR
    preprocess_denoise_strength: int = 11  # bilateral filter param

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.confidence_threshold < 0 or self.confidence_threshold > 1:
            errors.append("ocr.confidence_threshold must be between 0 and 1")
        return errors


@dataclass
class PollingConfig:
    poll_interval: int = 2            # seconds between poll cycles
    cooldown_after_detection: int = 75  # seconds to wait after a detection

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.poll_interval < 1:
            errors.append("polling.poll_interval must be >= 1")
        if self.cooldown_after_detection < 0:
            errors.append("polling.cooldown_after_detection must be >= 0")
        return errors


@dataclass
class ArchiveConfig:
    enabled: bool = True
    directory: str = "plaques.d"
    max_age_days: int = 30            # auto-cleanup
    filename_fmt: str = "{ts} {plate}.jpg"  # {ts}, {plate}, {hash}

    def validate(self) -> list[str]:
        return []


@dataclass
class AppConfig:
    """Top-level application configuration."""
    camera: CameraConfig = field(default_factory=CameraConfig)
    relay: RelayConfig = field(default_factory=RelayConfig)
    gate_camera: GateCameraConfig = field(default_factory=GateCameraConfig)
    gate_detector: GateDetectorConfig = field(default_factory=GateDetectorConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    allowed_plates: list[str] = field(default_factory=list)
    debug: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []
        errors += self.camera.validate()
        errors += self.relay.validate()
        errors += self.gate_camera.validate()
        errors += self.gate_detector.validate()
        errors += self.ocr.validate()
        errors += self.polling.validate()
        errors += self.archive.validate()
        return errors

    def get_allowed_plates(self) -> list[str]:
        """Return sorted, normalized allowed plates."""
        return sorted(set(p.strip().upper().replace(" ", "-") for p in self.allowed_plates if p.strip()))

    def is_allowed(self, plate: str) -> bool:
        """Check if a plate is in the allowlist (normalized comparison)."""
        normalized = plate.strip().upper().replace(" ", "-")
        return normalized in self.get_allowed_plates()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

DEFAULT_YAML = """\
# ANPR Gate Control Configuration
# --------------------------------

camera:
  host: "192.168.1.100"
  port: 554
  user: ""
  password: ""
  path: "/h264/ch1/main/av_stream"
  roi_x1: 0
  roi_y1: 0
  roi_x2: 1920
  roi_y2: 1080
  snapshot_fps: 1

relay:
  host: "192.168.20.26"
  url_open: "/30000/07"
  url_close: "/30000/06"
  pulse_duration: 1.0
  ping_interval: 1800

gate_camera:
  host: "192.168.20.22"
  port: 82
  user: "admin"
  password: ""
  snapshot_path: "/ISAPI/Streaming/channels/101/picture"

gate_detector:
  ref_day_path: "anpr_gate/refs/ref_close_day.jpg"
  ref_night_path: "anpr_gate/refs/ref_close_night.jpg"
  threshold: 35.0
  enabled: true
  reopen_check_interval: 180

ocr:
  enabled: true
  confidence_threshold: 0.15
  languages: ["en"]
  use_gpu: false
  preprocess_upscale: 3
  preprocess_denoise_strength: 11

polling:
  poll_interval: 2
  cooldown_after_detection: 75

archive:
  enabled: true
  directory: "plaques.d"
  max_age_days: 30

allowed_plates:
  # - CF938PH
  # - AB123CD
"""


def load_yaml(path: str | Path) -> AppConfig:
    """Load and validate config from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    cfg = _dict_to_config(raw)
    errors = cfg.validate()
    if errors:
        raise ConfigError(f"Invalid configuration:\n  " + "\n  ".join(errors))
    return cfg


def _dict_to_config(d: dict[str, Any]) -> AppConfig:
    """Recursively build typed config from a dict."""

    def _pop(section: str, cls: type, defaults: dict | None = None) -> Any:
        section_data = d.pop(section, {}) or {}
        if defaults:
            merged = {**defaults, **section_data}
        else:
            merged = section_data
        # Convert list fields
        fields = {f.name: f.type for f in cls.__dataclass_fields__.values()}
        for fname, ftype in fields.items():
            if ftype is list and fname in merged and isinstance(merged[fname], str):
                merged[fname] = [x.strip() for x in merged[fname].split(",") if x.strip()]
        return cls(**merged)

    return AppConfig(
        camera=_pop("camera", CameraConfig),
        relay=_pop("relay", RelayConfig),
        gate_camera=_pop("gate_camera", GateCameraConfig),
        gate_detector=_pop("gate_detector", GateDetectorConfig),
        ocr=_pop("ocr", OCRConfig),
        polling=_pop("polling", PollingConfig),
        archive=_pop("archive", ArchiveConfig),
        allowed_plates=d.pop("allowed_plates", []),
        debug=d.pop("debug", False),
    )


def load(path: str | Path) -> AppConfig:
    """Load and validate config from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    ext = path.suffix.lower()
    if ext not in (".yaml", ".yml"):
        raise ConfigError(
            f"Unsupported config format '{ext or '(no extension)'}'. "
            "Only YAML is supported. Use portier.yaml."
        )

    return load_yaml(path)

def write_yaml(cfg: AppConfig, path: str | Path):
    """Write config as YAML."""
    data = {
        "camera": {
            "host": cfg.camera.host,
            "port": cfg.camera.port,
            "user": cfg.camera.user,
            "password": cfg.camera.password,
            "path": cfg.camera.path,
            "roi_x1": cfg.camera.roi_x1,
            "roi_y1": cfg.camera.roi_y1,
            "roi_x2": cfg.camera.roi_x2,
            "roi_y2": cfg.camera.roi_y2,
            "snapshot_fps": cfg.camera.snapshot_fps,
        },
        "relay": {
            "host": cfg.relay.host,
            "url_open": cfg.relay.url_open,
            "url_close": cfg.relay.url_close,
            "pulse_duration": cfg.relay.pulse_duration,
            "ping_interval": cfg.relay.ping_interval,
        },
        "gate_camera": {
            "host": cfg.gate_camera.host,
            "port": cfg.gate_camera.port,
            "user": cfg.gate_camera.user,
            "password": cfg.gate_camera.password,
            "snapshot_path": cfg.gate_camera.snapshot_path,
        },
        "gate_detector": {
            "ref_day_path": cfg.gate_detector.ref_day_path,
            "ref_night_path": cfg.gate_detector.ref_night_path,
            "threshold": cfg.gate_detector.threshold,
            "enabled": cfg.gate_detector.enabled,
            "reopen_check_interval": cfg.gate_detector.reopen_check_interval,
        },
        "ocr": {
            "enabled": cfg.ocr.enabled,
            "confidence_threshold": cfg.ocr.confidence_threshold,
            "languages": cfg.ocr.languages,
            "use_gpu": cfg.ocr.use_gpu,
            "preprocess_upscale": cfg.ocr.preprocess_upscale,
            "preprocess_denoise_strength": cfg.ocr.preprocess_denoise_strength,
        },
        "polling": {
            "poll_interval": cfg.polling.poll_interval,
            "cooldown_after_detection": cfg.polling.cooldown_after_detection,
        },
        "archive": {
            "enabled": cfg.archive.enabled,
            "directory": cfg.archive.directory,
            "max_age_days": cfg.archive.max_age_days,
        },
        "allowed_plates": cfg.get_allowed_plates(),
        "debug": cfg.debug,
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def create_default(path: str | Path, camera_host: str = "192.168.1.100"):
    """Write a default YAML config file."""
    cfg = AppConfig(camera=CameraConfig(host=camera_host))
    write_yaml(cfg, path)