"""Abstract plate detector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class Bbox:
    """Bounding box with optional confidence."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 0.0

    def to_xyxy(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2


class DetectorError(Exception):
    """Raised when detection fails."""


class PlateDetector(ABC):
    """Detect license plates in an image.

    Returns a list of Bbox objects. Implementations may be model-based
    (YOLO) or heuristic (pixel diff for gate state).
    """

    @abstractmethod
    def detect(self, image: np.ndarray) -> list[Bbox]:
        """Run detection on a BGR image. Returns list of bounding boxes."""
        ...

    def release(self) -> None:
        """Release model resources. Idempotent."""
        pass