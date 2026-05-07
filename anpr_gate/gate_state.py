"""Gate state detector using dual-reference pixel difference.

Determines if the gate is open or closed by comparing a live snapshot
against two references: closed (day) and closed (night).
Uses the minimum of the two diffs to handle lighting adaptation.
"""
import os
from typing import Tuple

import numpy as np
from PIL import Image


class GateStateDetector:
    """Detects gate state (open/closed/unknown) using image comparison."""

    def __init__(self, ref_day_path: str, ref_night_path: str,
                 roi: Tuple[int, int, int, int] = (200, 200, 1400, 500),
                 threshold: float = 20.0):
        self._roix1, self._roiy1, self._roix2, self._roiy2 = roi
        self._threshold = threshold
        self._ref_day = self._load_ref(ref_day_path)
        self._ref_night = self._load_ref(ref_night_path)

    def check(self, image_path: str) -> str:
        """Detect gate state from a snapshot image.
        Returns "closed", "open", or "unknown" on error.
        """
        try:
            if not os.path.exists(image_path):
                return "unknown"
            img = self._load_gray(image_path)
            roi = img[self._roiy1:self._roiy2, self._roix1:self._roix2]
            diff_day = float(np.abs(roi - self._ref_day).mean())
            diff_night = float(np.abs(roi - self._ref_night).mean())
            return "closed" if min(diff_day, diff_night) < self._threshold else "open"
        except Exception:
            return "unknown"

    def diff_scores(self, image_path: str) -> dict:
        """Return detailed diff scores for diagnostics."""
        try:
            img = self._load_gray(image_path)
            roi = img[self._roiy1:self._roiy2, self._roix1:self._roix2]
            dd = float(np.abs(roi - self._ref_day).mean())
            dn = float(np.abs(roi - self._ref_night).mean())
            return {"diff_day": round(dd, 1), "diff_night": round(dn, 1),
                    "min_diff": round(min(dd, dn), 1)}
        except Exception:
            return {}

    @staticmethod
    def _load_ref(path: str) -> np.ndarray:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Reference not found: {path}")
        arr = np.array(Image.open(path), dtype=np.float32)
        return arr if arr.ndim == 2 else arr.mean(axis=2)

    @staticmethod
    def _load_gray(path: str) -> np.ndarray:
        arr = np.array(Image.open(path), dtype=np.float32)
        return arr if arr.ndim == 2 else arr.mean(axis=2)
