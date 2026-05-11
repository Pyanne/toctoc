"""Abstract camera interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class CameraError(Exception):
    """Raised when camera capture fails after retries."""


class Camera(ABC):
    """Capture frames from a video source.

    Implementations should handle reconnection and return BGR numpy arrays
    (same format as OpenCV imread).
    """

    @abstractmethod
    def capture(self) -> np.ndarray:
        """Capture a single frame. Returns BGR uint8 numpy array.

        Raises CameraError on failure.
        """
        ...

    def release(self) -> None:
        """Release resources. Idempotent."""
        pass