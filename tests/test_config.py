"""Tests for configuration loading and validation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from anpr_gate.config import (
    AppConfig, CameraConfig, RelayConfig, GateCameraConfig,
    GateDetectorConfig, OCRConfig, PollingConfig, ArchiveConfig,
    load_yaml, load_ini, write_yaml, create_default, ConfigError,
)


class TestCameraConfig:
    def test_defaults(self):
        c = CameraConfig(host="192.168.1.1")
        assert c.host == "192.168.1.1"
        assert c.port == 554
        assert c.roi() == (0, 0, 1920, 1080)

    def test_rtsp_url_no_auth(self):
        c = CameraConfig(host="10.0.0.1")
        assert c.rtsp_url == "rtsp://10.0.0.1:554/h264/ch1/main/av_stream"

    def test_rtsp_url_with_auth(self):
        c = CameraConfig(host="10.0.0.1", user="admin", password="pass")
        assert "admin:pass@" in c.rtsp_url

    def test_custom_port(self):
        c = CameraConfig(host="x", port=8554)
        assert "8554" in c.rtsp_url

    def test_validation_passes(self):
        c = CameraConfig(host="192.168.1.1")
        assert c.validate() == []

    def test_validation_fails_empty_host(self):
        c = CameraConfig(host="")
        assert len(c.validate()) > 0


class TestRelayConfig:
    def test_defaults(self):
        r = RelayConfig()
        assert r.host == "192.168.20.26"
        assert r.url_open == "/30000/07"
        assert r.url_close == "/30000/06"
        assert r.pulse_duration == 1.0

    def test_validation_negative_duration(self):
        r = RelayConfig(pulse_duration=-1.0)
        assert len(r.validate()) > 0


class TestGateDetectorConfig:
    def test_validation_without_refs(self):
        g = GateDetectorConfig(enabled=True)
        errors = g.validate()
        assert any("ref_day" in e for e in errors)
        assert any("ref_night" in e for e in errors)

    def test_validation_with_refs(self):
        g = GateDetectorConfig(
            enabled=True, ref_day_path="/tmp/d.jpg", ref_night_path="/tmp/n.jpg"
        )
        assert "ref_day" not in str(g.validate())

    def test_disabled_skips_validation(self):
        g = GateDetectorConfig(enabled=False)
        assert g.validate() == []


class TestOCRConfig:
    def test_confidence_range_valid(self):
        o = OCRConfig(confidence_threshold=0.5)
        assert o.validate() == []

    def test_confidence_range_invalid_low(self):
        o = OCRConfig(confidence_threshold=-0.1)
        assert len(o.validate()) > 0

    def test_confidence_range_invalid_high(self):
        o = OCRConfig(confidence_threshold=1.5)
        assert len(o.validate()) > 0


class TestPollingConfig:
    def test_invalid_interval(self):
        p = PollingConfig(poll_interval=0)
        assert len(p.validate()) > 0

    def test_valid(self):
        p = PollingConfig(poll_interval=5, cooldown_after_detection=60)
        assert p.validate() == []


class TestAppConfig:
    def test_default_validation_passes(self):
        cfg = AppConfig(camera=CameraConfig(host="127.0.0.1"))
        assert cfg.validate() == []

    def test_is_allowed(self):
        cfg = AppConfig(allowed_plates=["AB-123-CD", "XY-999-ZZ"])
        assert cfg.is_allowed("AB-123-CD") is True
        assert cfg.is_allowed("ab-123-cd") is True  # normalized
        assert cfg.is_allowed("ZZ-000-AA") is False

    def test_get_allowed_plates_sorted(self):
        cfg = AppConfig(allowed_plates=["ZZ-1", "AA-2"])
        assert cfg.get_allowed_plates() == ["AA-2", "ZZ-1"]


class TestLoadYAML:
    def test_roundtrip(self, tmp_path):
        original = AppConfig(
            camera=CameraConfig(host="192.168.10.1", port=554),
            relay=RelayConfig(host="192.168.20.26", pulse_duration=1.0),
        )
        path = tmp_path / "test.yaml"
        write_yaml(original, path)
        loaded = load_yaml(path)
        assert loaded.camera.host == "192.168.10.1"
        assert loaded.relay.host == "192.168.20.26"

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError):
            load_yaml(tmp_path / "nonexistent.yaml")


class TestLoadINI:
    def test_load_portier_conf(self, tmp_path):
        ini = tmp_path / "portier.conf"
        ini.write_text("""
[camera]
host = 192.168.10.1
port = 554

[relay]
host = 192.168.20.26
url_open = /30000/07
url_close = /30000/06

[plates]
cf938ph = 1
ab-123-cd = 1
""")
        cfg = load_ini(ini)
        assert cfg.camera.host == "192.168.10.1"
        assert cfg.relay.host == "192.168.20.26"
        assert "CF938PH" in cfg.get_allowed_plates()


class TestExportConfig:
    def test_create_default(self, tmp_path):
        path = tmp_path / "default.yaml"
        create_default(path)
        assert path.exists()
        cfg = load_yaml(path)
        assert cfg.camera is not None
        assert cfg.relay is not None