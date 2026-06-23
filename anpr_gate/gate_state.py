"""Gate state detector using OCR on a marked region.

A fridge magnet with French text is attached to the gate. When the gate is
closed, the magnet is visible in the camera's field of view at a known ROI.
When the gate is open, the magnet moves out of view.

Detection method:
1. Crop the gate camera snapshot to the magnet ROI
2. Run EasyOCR on the ROI
3. If text with confidence > 0.3 is found → gate is CLOSED (magnet visible)
4. If no text found → gate is OPEN (magnet not visible)

ROI: upper-left (488, 730), lower-right (840, 1184)
"""
import os
import subprocess
import tempfile
from typing import Tuple

import cv2
import numpy as np


class GateStateDetector:
    """Detects gate state by reading text from a magnet on the gate."""

    def __init__(self, ref_day_path: str = "", ref_night_path: str = "",
                 roi: Tuple[int, int, int, int] = (488, 730, 840, 1184),
                 threshold: float = 0.3,
                 gate_cam_url: str = "",
                 gate_cam_auth: str = ""):
        """
        Args:
            roi: (x1, y1, x2, y2) region where the magnet text appears
            threshold: minimum OCR confidence to consider text as detected
            gate_cam_url: RTSP URL for the gate camera
            gate_cam_auth: "user:password" for the camera
        """
        self._roi = roi
        self._threshold = threshold
        self._gate_cam_url = gate_cam_url
        self._gate_cam_auth = gate_cam_auth
        self._reader = None

    def _ensure_reader(self):
        """Lazily initialize EasyOCR reader."""
        if self._reader is None:
            import warnings
            warnings.filterwarnings("ignore", message=".*pin_memory.*")
            import easyocr
            self._reader = easyocr.Reader(["en", "fr"], gpu=False)

    def grab_snapshot(self, output_path: str) -> bool:
        """Grab a snapshot from the gate camera via RTSP."""
        if not self._gate_cam_url:
            return False
        cmd = [
            "ffmpeg", "-nostats", "-loglevel", "0",
            "-rtsp_transport", "tcp", "-y",
            "-i", self._gate_cam_url,
            "-vframes", "1", "-f", "mjpeg", output_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception:
            return False

    def check(self, image_path: str = None) -> str:
        """Detect gate state.

        If image_path is provided, use it directly.
        Otherwise grab a fresh snapshot from the gate camera.

        Returns "closed" (magnet visible), "open" (magnet not visible),
        or "unknown" (error).
        """
        try:
            if image_path is None or not os.path.exists(image_path):
                if not self._gate_cam_url:
                    return "unknown"
                tmp = tempfile.mktemp(suffix=".jpg")
                if not self.grab_snapshot(tmp):
                    return "unknown"
                image_path = tmp

            img = cv2.imread(image_path)
            if img is None:
                return "unknown"

            # Crop to ROI
            x1, y1, x2, y2 = self._roi
            roi_img = img[y1:y2, x1:x2]
            if roi_img.size == 0:
                return "unknown"

            # Run OCR
            self._ensure_reader()
            results = self._reader.readtext(roi_img, detail=1, paragraph=False)

            # Check if any text exceeds confidence threshold
            for _bbox, text, conf in results:
                if conf >= self._threshold and len(text.strip()) > 2:
                    return "closed"  # Magnet text visible → gate is closed

            return "open"  # No text found → magnet not visible → gate is open
        except Exception:
            return "unknown"

    def diff_scores(self, image_path: str = None) -> dict:
        """Return diagnostic info."""
        try:
            if image_path is None or not os.path.exists(image_path):
                if not self._gate_cam_url:
                    return {"error": "no camera configured"}
                tmp = tempfile.mktemp(suffix=".jpg")
                if not self.grab_snapshot(tmp):
                    return {"error": "snapshot failed"}
                image_path = tmp

            img = cv2.imread(image_path)
            if img is None:
                return {"error": "cannot read image"}

            x1, y1, x2, y2 = self._roi
            roi_img = img[y1:y2, x1:x2]

            self._ensure_reader()
            results = self._reader.readtext(roi_img, detail=1, paragraph=False)

            texts = [{"text": t, "conf": round(c, 2)} for _b, t, c in results if c >= 0.1]
            max_conf = max((c for _b, t, c in results), default=0)

            return {
                "method": "ocr_magnet",
                "roi": self._roi,
                "texts": texts,
                "max_confidence": round(max_conf, 2),
                "threshold": self._threshold,
                "gate_state": "closed" if max_conf >= self._threshold else "open",
            }
        except Exception as e:
            return {"error": str(e)}
