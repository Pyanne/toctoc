"""Mock plate detector for testing."""

from __future__ import annotations

import numpy as np

from anpr_gate.detection.base import Bbox, PlateDetector


class MockDetector(PlateDetector):
    """Returns predefined detection results for testing.

    Usage:
        det = MockDetector([Bbox(10, 20, 200, 80, 0.95)])
    """

    def __init__(self, boxes: list[Bbox] | None = None):
        self._boxes = boxes or []
        self.call_count = 0

    def detect(self, image) -> list[Bbox]:
        self.call_count += 1
        return list(self._boxes)

    def set_boxes(self, boxes: list[Bbox]):
        self._boxes = boxes