"""Archive manager — saves detection snapshots with metadata."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from anpr_gate.config import ArchiveConfig

logger = logging.getLogger(__name__)


class ArchiveManager:
    """Manages archival of detection snapshots.

    Files are named using a configurable format string with placeholders:
      {ts}     — timestamp (e.g. "11-05-26 14h30")
      {plate}  — OCR result
      {hash}   — short content hash for deduplication

    Supports automatic cleanup of old files.
    """

    def __init__(self, cfg: ArchiveConfig, base_dir: str | Path | None = None):
        self._cfg = cfg
        self._base = Path(base_dir) if base_dir else Path.cwd()
        self._archive_dir = self._base / cfg.directory
        self._enabled = cfg.enabled

    def save(self, source_path: str, plate: str) -> str | None:
        """Archive a detection snapshot.

        Args:
            source_path: Path to the source image
            plate: OCR result for the filename

        Returns:
            Path to the archived file, or None if archiving is disabled.
        """
        if not self._enabled:
            return None

        try:
            self._archive_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            ts = datetime.now().strftime("%d-%m-%y %Hh%M")
            content_hash = self._file_hash(source_path)[:6]

            # Sanitize plate for filename
            safe_plate = self._sanitize_filename(plate) or "UNKNOWN"

            filename = self._cfg.filename_fmt.format(
                ts=ts, plate=safe_plate, hash=content_hash
            )
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                filename += ".jpg"

            dest = self._archive_dir / filename

            # Copy the file
            shutil.copy2(source_path, dest)
            logger.info("Archived snapshot: %s", dest.name)
            return str(dest)

        except Exception as exc:
            logger.warning("Archive failed: %s", exc)
            return None

    def cleanup(self):
        """Remove archives older than max_age_days."""
        if not self._enabled or not self._archive_dir.exists():
            return

        max_age = self._cfg.max_age_days
        if max_age <= 0:
            return

        cutoff = datetime.now().timestamp() - (max_age * 86400)
        removed = 0

        for f in self._archive_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1

        if removed:
            logger.info("Cleaned up %d old archive files", removed)

    # --- Helpers ---

    @staticmethod
    def _file_hash(path: str) -> str:
        """Short MD5 hash of file contents."""
        import hashlib
        h = hashlib.md5(usedforsecurity=False)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _sanitize_filename(text: str) -> str:
        """Remove characters invalid in filenames."""
        import re
        return re.sub(r'[<>:"/\\|?*]', '', text)[:30]

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value