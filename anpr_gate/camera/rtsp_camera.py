"""RTSP camera using OpenCV with automatic reconnection."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from anpr_gate.camera.base import Camera, CameraError


class RTSPCamera(Camera):
    """OpenCV-backed RTSP camera with reconnect logic.

    Reconnects with exponential backoff on failure.
    """

    MAX_BACKOFF = 60  # seconds

    def __init__(self, cfg: Any):
        self._url = cfg.rtsp_url
        self._cap: cv2.VideoCapture | None = None
        self._backoff = 1

    def capture(self) -> np.ndarray:
        self._ensure_open()
        ret, frame = self._cap.read()  # type: ignore[union-attr]
        if not ret:
            self._release()
            raise CameraError("RTSP stream returned empty frame")
        self._backoff = 1
        return frame

    def _ensure_open(self):
        if self._cap is not None and self._cap.isOpened():
            return
        while True:
            self._release()
            self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if self._cap.isOpened():
                self._backoff = 1
                return
            # Exponential backoff
            wait = min(self._backoff, self.MAX_BACKOFF)
            time.sleep(wait)
            self._backoff = min(self._backoff * 2, self.MAX_BACKOFF * 2)

    def _release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def release(self):
        self._release()