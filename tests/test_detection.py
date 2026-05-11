"""Tests for the detection modules."""

import numpy as np
from anpr_gate.detection.base import Bbox
from anpr_gate.detection.mock_detector import MockDetector


class TestBbox:
    def test_to_xyxy(self):
        b = Bbox(10, 20, 100, 200, 0.9)
        assert b.to_xyxy() == (10, 20, 100, 200)

    def test_zero_confidence(self):
        b = Bbox(0, 0, 50, 50)
        assert b.confidence == 0.0


class TestMockDetector:
    def test_empty_by_default(self):
        d = MockDetector()
        assert d.detect(np.zeros((480, 640, 3), dtype=np.uint8)) == []

    def test_returns_predefined(self):
        boxes = [Bbox(10, 20, 100, 200, 0.95)]
        d = MockDetector(boxes)
        result = d.detect(np.zeros((480, 640, 3), dtype=np.uint8))
        assert len(result) == 1
        assert result[0].x1 == 10