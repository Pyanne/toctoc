"""Tests for the archive manager."""

import os
import tempfile
from pathlib import Path

from anpr_gate.archive.manager import ArchiveManager
from anpr_gate.config import ArchiveConfig


class TestArchiveManager:
    def test_save_creates_file(self, tmp_path):
        src = tmp_path / "source.jpg"
        src.write_bytes(b"fake image data for testing")

        cfg = ArchiveConfig(enabled=True, directory=str(tmp_path / "arch"))
        arch = ArchiveManager(cfg, base_dir=tmp_path)
        result = arch.save(str(src), "AB-123-CD")
        assert result is not None
        assert Path(result).exists()

    def test_disabled_returns_none(self, tmp_path):
        cfg = ArchiveConfig(enabled=False, directory=str(tmp_path / "arch"))
        arch = ArchiveManager(cfg, base_dir=tmp_path)
        assert arch.save("/tmp/nonexistent.jpg", "AB-123-CD") is None

    def test_filename_includes_plate(self, tmp_path):
        src = tmp_path / "source.jpg"
        src.write_bytes(b"test data")
        cfg = ArchiveConfig(enabled=True, directory=str(tmp_path / "arch"))
        arch = ArchiveManager(cfg, base_dir=tmp_path)
        result = arch.save(str(src), "AB-123-CD")
        assert "AB-123-CD" in result

    def test_cleanup_removes_old(self, tmp_path):
        arch_dir = tmp_path / "arch"
        arch_dir.mkdir()
        old_file = arch_dir / "old_file.jpg"
        old_file.write_bytes(b"old data")
        # Set mtime to 31 days ago
        old_time = old_file.stat().st_mtime - (31 * 86400)
        os.utime(old_file, (old_time, old_time))

        recent_file = arch_dir / "recent_file.jpg"
        recent_file.write_bytes(b"recent data")

        cfg = ArchiveConfig(enabled=True, directory=str(arch_dir), max_age_days=30)
        arch = ArchiveManager(cfg, base_dir=tmp_path)
        arch.cleanup()

        assert not old_file.exists()
        assert recent_file.exists()