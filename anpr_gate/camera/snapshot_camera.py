"""HTTP snapshot camera for gate state monitoring (e.g. Hikvision ISAPI)."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from anpr_gate.camera.base import Camera, CameraError

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class SnapshotCamera(Camera):
    """Captures single frames from an HTTP snapshot endpoint.

    Supports HTTP digest auth (required for Hikvision ISAPI).
    Caches the last successful frame for up to ``cache_ttl`` seconds
    so repeated calls don't hammer the network.
    """

    def __init__(self, cfg: Any, cache_ttl: float = 1.0):
        self._url = cfg.snapshot_url
        self._auth = (cfg.user, cfg.password)
        self._cache_ttl = cache_ttl
        self._cached_frame: np.ndarray | None = None
        self._cached_at: float = 0.0

    def capture(self) -> np.ndarray:
        now = time.time()
        if self._cached_frame is not None and (now - self._cached_at) < self._cache_ttl:
            return self._cached_frame.copy()

        if not HAS_REQUESTS:
            raise CameraError("requests library not installed — cannot grab snapshot")

        try:
            resp = requests.get(
                self._url,
                auth=self._auth,
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise CameraError(f"Snapshot fetch failed: {exc}") from exc

        arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise CameraError("Failed to decode snapshot image")

        self._cached_frame = frame
        self._cached_at = now
        return frame

    def release(self):
        pass  # nothing to release