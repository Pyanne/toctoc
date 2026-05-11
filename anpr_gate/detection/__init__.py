"""Detection module — lightweight imports only."""

from anpr_gate.detection.base import Bbox, DetectorError, PlateDetector
from anpr_gate.detection.mock_detector import MockDetector

# Concrete implementations imported lazily via container.py
__all__ = ["Bbox", "DetectorError", "PlateDetector", "MockDetector",
           "YOLODetector", "GateStateDetector"]