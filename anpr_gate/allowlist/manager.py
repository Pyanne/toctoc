"""Allowlist manager — hot-reloadable set of authorized license plates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AllowlistManager:
    """Manages the set of authorized license plates.

    Supports normalization (uppercase, strip hyphens/spaces) for
    fuzzy matching, and hot-reload from config.
    """

    def __init__(self, plates: list[str] | None = None):
        self._plates: set[str] = set()
        if plates:
            self.update(plates)

    # --- Public API ---

    def is_allowed(self, plate: str) -> bool:
        """Check if a plate is in the allowlist (normalized comparison)."""
        normalized = self._normalize(plate)
        if not normalized:
            return False
        return normalized in self._plates

    def is_empty(self) -> bool:
        return len(self._plates) == 0

    def plates(self) -> list[str]:
        """Return sorted list of allowed plates."""
        return sorted(self._plates)

    def update(self, plates: list[str]):
        """Replace the allowlist with a new set of plates."""
        self._plates = {self._normalize(p) for p in plates if p.strip()}
        logger.info("Allowlist updated: %d plates", len(self._plates))

    def add(self, plate: str) -> bool:
        """Add a single plate. Returns True if new, False if already present."""
        norm = self._normalize(plate)
        if not norm:
            return False
        if norm in self._plates:
            return False
        self._plates.add(norm)
        return True

    def remove(self, plate: str) -> bool:
        """Remove a single plate. Returns True if removed, False if not found."""
        norm = self._normalize(plate)
        return self._plates.discard(norm) is None

    def reload_from_config(self, allowed_plates: list[str] | Any):
        """Hot-reload from config data (list of strings)."""
        self.update(allowed_plates if isinstance(allowed_plates, list) else [])

    # --- Helpers ---

    @staticmethod
    def _normalize(plate: str) -> str:
        """Normalize a plate string: uppercase, strip spaces/hyphens."""
        if not plate:
            return ""
        return plate.strip().upper().replace(" ", "-").replace("--", "-")

    def __len__(self) -> int:
        return len(self._plates)

    def __contains__(self, plate: str) -> bool:
        return self.is_allowed(plate)