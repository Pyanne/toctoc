"""Mock camera for testing — returns synthetic frames."""

from __future__ import annotations

import numpy as np

from anpr_gate.camera.base import Camera, CameraError


class MockCamera(Camera):
    """Returns a synthetic frame with an optional plate overlay.

    Useful for unit tests that need deterministic images.
    """

    def __init__(self, plate_text: str = "", width: int = 640, height: int = 480):
        self._plate = plate_text
        self._width = width
        self._height = height
        self._call_count = 0

    def capture(self) -> np.ndarray:
        self._call_count += 1
        # Solid dark frame
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:, :] = [30, 30, 30]  # dark gray

        # Draw a fake plate rectangle if text provided
        if self._plate:
            import cv2
            x, y, w, h = self._width // 4, self._height // 3, self._width // 2, 60
            cv2.rectangle(frame, (x, y), (x + w, y + h), (200, 200, 200), 2)
            cv2.putText(frame, self._plate, (x + 10, y + 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        return frame

    def release(self):
        pass

    def set_plate(self, text: str):
        self._plate = text