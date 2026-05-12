"""Gate state detection using dual-reference pixel difference.

Improved version of the original gate_state.py:
- Uses OpenCV instead of PIL for speed
- Adds morphological noise reduction
- Tracks recent scores for adaptive thresholding
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from anpr_gate.detection.base import DetectorError, PlateDetector

logger = logging.getLogger(__name__)


class GateStateDetector(PlateDetector):
    """Detect gate open/closed state by comparing snapshots to reference images.

    Uses two references (day/night) and picks whichever gives the lower diff,
    handling lighting changes gracefully.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_UNKNOWN = "unknown"

    def __init__(
        self,
        ref_day: str,
        ref_night: str,
        roi: tuple[int, int, int, int] = (200, 200, 1400, 500),
        threshold: float = 35.0,
        morph_kernel: int = 5,
    ):
        self._roi = roi
        self._threshold = threshold
        self._morph_kernel = morph_kernel

        self._ref_gray_day = self._load_ref(ref_day)
        self._ref_gray_night = self._load_ref(ref_night)

        # Pre-extract ROI from references
        x1, y1, x2, y2 = roi
        self._ref_roi_day = self._ref_gray_day[y1:y2, x1:x2]
        self._ref_roi_night = self._ref_gray_night[y1:y2, x1:x2]

        # Morphological kernel for noise reduction
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (morph_kernel, morph_kernel))

        # Recent diff scores for adaptive tracking
        self._recent_scores: list[float] = []
        self._max_history = 20

    def detect(self, image: np.ndarray) -> list:
        """Returns list of Bbox-like dicts with gate state info (for API compat)."""
        state, info = self.classify(image)
        return [{"state": state, **info}]

    def classify(self, image: np.ndarray) -> tuple[str, dict]:
        """Classify gate state from an image. Returns (state, {diff_day, diff_night, min_diff})."""
        try:
            gray = self._to_gray(image)
            x1, y1, x2, y2 = self._roi
            roi = gray[y1:y2, x1:x2]

            # Denoise
            roi = cv2.morphologyEx(roi, cv2.MORPH_OPEN, self._kernel)

            dd = float(cv2.absdiff(roi, self._ref_roi_day).mean())
            dn = float(cv2.absdiff(roi, self._ref_roi_night).mean())
            min_diff = min(dd, dn)

            # Track recent scores for diagnostics
            self._recent_scores.append(min_diff)
            if len(self._recent_scores) > self._max_history:
                self._recent_scores.pop(0)

            state = self.STATE_CLOSED if min_diff < self._threshold else self.STATE_OPEN
            return state, {"diff_day": round(dd, 1), "diff_night": round(dn, 1), "min_diff": round(min_diff, 1)}
        except Exception as exc:
            logger.warning("Gate state detection failed: %s", exc)
            return self.STATE_UNKNOWN, {}

    def recent_avg_diff(self) -> float | None:
        """Return average of recent min-diff scores, or None if no data."""
        if not self._recent_scores:
            return None
        return round(sum(self._recent_scores) / len(self._recent_scores), 1)

    def is_confident(self) -> bool:
        """True if we have enough recent data and scores are consistent."""
        if len(self._recent_scores) < 3:
            return False
        avg = sum(self._recent_scores) / len(self._recent_scores)
        variance = sum((s - avg) ** 2 for s in self._recent_scores) / len(self._recent_scores)
        return variance < (self._threshold ** 2) * 0.1

    def update_threshold(self, new_value: float):
        """Dynamically adjust threshold."""
        self._threshold = new_value

    # --- Static helpers ---

    @staticmethod
    def _load_ref(path: str) -> np.ndarray:
        p = Path(path)
        if not p.exists():
            raise DetectorError(f"Reference image not found: {path}")
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise DetectorError(f"Failed to read reference image: {path}")
        return img.astype(np.float32)

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return image.astype(np.float32)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)