"""Dependency injection container — assembles the full application graph."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from anpr_gate.config import AppConfig, load

# Avoid importing concrete modules at package level (breaks headless installs)
# These are imported lazily inside factory methods.

logger = logging.getLogger(__name__)


class Container:
    """Central DI container. Call build(), then access components as properties.

    For testing, construct with overrides::

        c = Container(config=my_config, relay=MockRelay())
    """

    # Config is the single source of truth
    config: AppConfig

    # Concrete services (populated by build())
    _camera: Optional[Any] = None
    _gate_camera: Optional[Any] = None
    _detector: Optional[Any] = None
    _gate_detector: Optional[Any] = None
    _ocr: Optional[Any] = None
    _relay: Optional[Any] = None
    _gate_controller: Optional[Any] = None
    _allowlist: Optional[Any] = None
    _archiver: Optional[Any] = None
    _logger: Optional[logging.Logger] = None

    def __init__(
        self,
        config: AppConfig | None = None,
        config_path: str | Path | None = None,
        # Optional overrides for testing
        camera: Any | None = None,
        gate_camera: Any | None = None,
        detector: Any | None = None,
        gate_detector: Any | None = None,
        ocr: Any | None = None,
        relay: Any | None = None,
        gate_controller: Any | None = None,
        allowlist: Any | None = None,
        archiver: Any | None = None,
    ):
        if config is None and config_path is None:
            raise ValueError("Either config or config_path must be provided")

        self.config = config or load(config_path)

        # Allow test overrides — if None, will be built lazily on first access
        self._camera = camera
        self._gate_camera = gate_camera
        self._detector = detector
        self._gate_detector = gate_detector
        self._ocr = ocr
        self._relay = relay
        self._gate_controller = gate_controller
        self._allowlist = allowlist
        self._archiver = archiver

    # ------------------------------------------------------------------
    # Lazy builders — each checks for override first, then creates real impl
    # ------------------------------------------------------------------

    def get_camera(self) -> Any:
        if self._camera is None:
            from anpr_gate.camera.rtsp_camera import RTSPCamera
            self._camera = RTSPCamera(self.config.camera)
        return self._camera

    def get_gate_camera(self) -> Any:
        if self._gate_camera is None:
            from anpr_gate.camera.snapshot_camera import SnapshotCamera
            self._gate_camera = SnapshotCamera(self.config.gate_camera)
        return self._gate_camera

    def get_detector(self) -> Any:
        if self._detector is None:
            from anpr_gate.detection.yolo_detector import YOLODetector
            model_path = Path(__file__).parent / "anpr_best.pt"
            if not model_path.exists():
                model_path = Path.home() / "anpr_best.pt"
            self._detector = YOLODetector(str(model_path), self.config.camera.roi())
        return self._detector

    def get_gate_detector(self) -> Any | None:
        if not self.config.gate_detector.enabled:
            return None
        if self._gate_detector is None:
            from anpr_gate.detection.pixel_diff_detector import PixelDiffDetector
            self._gate_detector = PixelDiffDetector(
                ref_day=self.config.gate_detector.ref_day_path,
                ref_night=self.config.gate_detector.ref_night_path,
                roi=self.config.camera.roi(),
                threshold=self.config.gate_detector.threshold,
            )
        return self._gate_detector

    def get_ocr(self) -> Any:
        if self._ocr is None:
            from anpr_gate.ocr.easyocr_engine import EasyOCREngine
            self._ocr = EasyOCREngine(self.config.ocr)
        return self._ocr

    def get_relay(self) -> Any:
        if self._relay is None:
            from anpr_gate.relay.http_relay import HTTPRelay
            self._relay = HTTPRelay(self.config.relay)
        return self._relay

    def get_gate_controller(self, relay: Any | None = None) -> Any:
        if self._gate_controller is None:
            from anpr_gate.gate.controller import GateController
            r = relay or self.get_relay()
            self._gate_controller = GateController(
                relay=r,
                travel_time=self.config.relay.pulse_duration,
                auto_close_delay=self.config.gate_detector.reopen_check_interval,
            )
        return self._gate_controller

    def get_allowlist(self) -> Any:
        if self._allowlist is None:
            from anpr_gate.allowlist.manager import AllowlistManager
            self._allowlist = AllowlistManager(self.config.get_allowed_plates())
        return self._allowlist

    def get_archiver(self) -> Any:
        if self._archiver is None:
            from anpr_gate.archive.manager import ArchiveManager
            self._archiver = ArchiveManager(self.config.archive)
        return self._archiver

    def get_logger(self) -> logging.Logger:
        if self._logger is None:
            self._logger = _setup_logging(self.config.debug)
        return self._logger

    def teardown(self):
        """Release resources (cameras, etc.)."""
        if self._camera:
            try:
                self._camera.release()
            except Exception:
                pass


def _setup_logging(debug: bool = False) -> logging.Logger:
    """Configure structured JSON file logging + readable console output."""
    import json
    from datetime import datetime, timezone
    import logging

    root = logging.getLogger("anpr_gate")
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Prevent duplicate handlers on reload
    if root.handlers:
        return root

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if record.exc_info and record.exc_info[0] is not None:
                entry["exc"] = self.formatException(record.exc_info)
            return json.dumps(entry, ensure_ascii=False)

    # File handler — JSON lines
    log_dir = Path(__file__).parent.parent
    log_file = log_dir / "logs" / "anpr.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(JSONFormatter())
        fh.setLevel(logging.DEBUG)
        root.addHandler(fh)
    except Exception as e:
        # Non-fatal — logging shouldn't crash the app
        pass

    # Console handler — human-readable
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if debug else logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
        datefmt="%H:%M:%S"
    )
    ch.setFormatter(console_fmt)
    root.addHandler(ch)

    return root