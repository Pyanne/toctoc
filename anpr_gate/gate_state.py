"""Gate state detector using yellow stripe detection.

When the gate is OPEN, the camera sees through to the road beyond which has
bright yellow warning stripes painted on the asphalt. When the gate is CLOSED,
the gate panels block the view and no yellow stripes are visible.

Detection method: look for yellow pixels in the lower portion of the image
using HSV color thresholding. If enough yellow is present → gate is open.
Otherwise → gate is closed.

This works for daytime (color camera). At night (IR/grayscale mode), yellow
detection is unreliable, so we fall back to checking overall brightness —
night images with the gate open tend to show more of the bright road surface.
"""
import os
from typing import Tuple

import cv2
import numpy as np


class GateStateDetector:
    """Detects gate state (open/closed) by looking for yellow warning stripes."""

    def __init__(self, ref_day_path: str = "", ref_night_path: str = "",
                 roi: Tuple[int, int, int, int] = (200, 200, 1400, 500),
                 threshold: float = 20.0,
                 yellow_threshold: float = 0.03):
        """
        Args:
            ref_day_path: unused (kept for API compatibility)
            ref_night_path: unused (kept for API compatibility)
            roi: unused (kept for API compatibility)
            threshold: unused (kept for API compatibility)
            yellow_threshold: minimum fraction of image that must be yellow
                              to consider the gate open (default 5%)
        """
        self._yellow_threshold = yellow_threshold

    def check(self, image_path: str) -> str:
        """Detect gate state from a snapshot image.
        Returns "closed", "open", or "unknown".
        """
        if not os.path.exists(image_path):
            return "unknown"

        try:
            img = cv2.imread(image_path)
            if img is None:
                return "unknown"

            # Check if image is color (daytime) or grayscale (nighttime IR)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            avg_saturation = hsv[:, :, 1].mean()

            if avg_saturation > 25:
                # Daytime: use yellow stripe detection
                return self._check_yellow(img)
            else:
                # Nighttime (IR/grayscale): use brightness-based detection
                return self._check_brightness(img)
        except Exception:
            return "unknown"

    def _check_yellow(self, img: np.ndarray) -> str:
        """Detect yellow warning stripes in a color image.

        The yellow stripes are bright yellow painted on dark asphalt.
        We convert to HSV and look for pixels in the yellow hue range
        with moderate-to-high saturation and value.
        """
        # Focus on the lower 2/3 of the image (where the road/stripes are)
        h, w = img.shape[:2]
        roi = img[h // 3:, :]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Yellow in HSV: hue ~15-45 (OpenCV hue range 0-180)
        # Using moderate thresholds to catch yellow paint on asphalt
        lower_yellow = np.array([15, 60, 100])
        upper_yellow = np.array([45, 255, 255])

        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

        # Clean up noise with morphological operations
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Calculate fraction of ROI that is yellow
        yellow_fraction = np.count_nonzero(mask) / mask.size

        return "open" if yellow_fraction > self._yellow_threshold else "closed"

    def _check_brightness(self, img: np.ndarray) -> str:
        """Nighttime fallback: check if the scene is brighter than typical.

        With gate open at night, the IR camera sees more of the road which
        tends to be brighter than the dark gate panels. This is a rough heuristic.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        # Check lower portion of image
        h = gray.shape[0]
        lower = gray[h // 2:, :]
        avg_brightness = lower.mean()
        # Threshold determined empirically — bright road > 80, dark gate < 60
        return "open" if avg_brightness > 70 else "closed"

    def diff_scores(self, image_path: str) -> dict:
        """Return diagnostic info."""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {}

            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            avg_sat = hsv[:, :, 1].mean()
            is_color = avg_sat > 25

            if is_color:
                h, w = img.shape[:2]
                roi = img[h // 3:, :]
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                lower = np.array([15, 60, 100])
                upper = np.array([45, 255, 255])
                mask = cv2.inRange(hsv_roi, lower, upper)
                kernel = np.ones((5, 5), np.uint8)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                yellow_frac = np.count_nonzero(mask) / mask.size
                return {
                    "method": "yellow_stripes",
                    "avg_saturation": round(avg_sat, 1),
                    "yellow_fraction": round(yellow_frac, 4),
                    "yellow_threshold": self._yellow_threshold,
                    "gate_state": "open" if yellow_frac > self._yellow_threshold else "closed",
                }
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
                lower = gray[gray.shape[0] // 2:, :]
                return {
                    "method": "brightness",
                    "avg_saturation": round(avg_sat, 1),
                    "avg_brightness": round(lower.mean(), 1),
                    "gate_state": "open" if lower.mean() > 70 else "closed",
                }
        except Exception:
            return {}
