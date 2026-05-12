"""Shared test fixtures."""

import pytest
import numpy as np

from anpr_gate.config import AppConfig, CameraConfig, RelayConfig
from anpr_gate.relay.mock_relay import MockRelay
from anpr_gate.camera.mock_camera import MockCamera
from anpr_gate.detection.mock_detector import MockDetector
from anpr_gate.detection.base import Bbox
from anpr_gate.ocr.mock_ocr import MockOCR
from anpr_gate.gate.controller import GateController
from anpr_gate.allowlist.manager import AllowlistManager


@pytest.fixture
def sample_config():
    return AppConfig(
        camera=CameraConfig(host="127.0.0.1"),
        relay=RelayConfig(host="127.0.0.1"),
    )


@pytest.fixture
def mock_relay():
    return MockRelay(auto_respond=True)


@pytest.fixture
def mock_camera():
    return MockCamera(width=640, height=480)


@pytest.fixture
def mock_camera_with_plate():
    cam = MockCamera(plate_text="AB-123-CD", width=640, height=480)
    return cam


@pytest.fixture
def mock_detector():
    return MockDetector([Bbox(100, 150, 400, 250, 0.95)])


@pytest.fixture
def mock_ocr():
    return MockOCR(result="AB-123-CD")


@pytest.fixture
def gate_controller(mock_relay):
    return GateController(
        relay=mock_relay,
        travel_time=1.0,
        auto_close_delay=2.0,
    )


@pytest.fixture
def sample_image():
    """A simple 640x480 BGR test image."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def allowlist():
    return AllowlistManager(["AB-123-CD", "XY-999-ZZ"])