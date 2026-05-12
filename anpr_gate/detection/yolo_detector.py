"""YOLOv8-based license plate detector."""

from __future__ import annotations

import numpy as np

from anpr_gate.detection.base import Bbox, DetectorError, PlateDetector


class YOLODetector(PlateDetector):
    """Detect license plates using a YOLOv8 model (Ultralytics).

    The model file (anpr_best.pt) is loaded once and reused.
    Detection is scoped to the configured ROI to reduce false positives.
    """

    def __init__(self, model_path: str, roi: tuple[int, int, int, int] = (0, 0, 1920, 1080),
                 confidence: float = 0.25, iou: float = 0.45):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise DetectorError("ultralytics not installed — run: pip install ultralytics")

        self._model = YOLO(model_path)
        self._roi = roi
        self._conf = confidence
        self._iou = iou
        # Warm up with a dummy inference so first real call isn't slow
        try:
            import cv2
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self._model.predict(dummy, imgsz=640, verbose=False)
        except Exception:
            pass  # non-fatal — model will warm up on first real call

    def detect(self, image: np.ndarray) -> list[Bbox]:
        try:
            roi = self._crop_to_roi(image)
        except Exception as exc:
            raise DetectorError(f"Detection failed: {exc}") from exc

        results = self._model.predict(roi, imgsz=640, conf=self._conf,
                                       iou=self._iou, verbose=False)
        boxes: list[Bbox] = []
        if not results or results[0].boxes is None:
            return boxes

        xyxy = results[0].boxes.xyxy.cpu().numpy()
        confs = results[0].boxes.conf.cpu().numpy()
        rx, ry = self._roi_scales(image, roi)

        for i, (x1, y1, x2, y2) in enumerate(xyxy):
            boxes.append(Bbox(
                x1=int(x1 * rx),
                y1=int(y1 * ry),
                x2=int(x2 * rx),
                y2=int(y2 * ry),
                confidence=float(confs[i]),
            ))
        return boxes

    # --- Helpers ---

    def _crop_to_roi(self, image: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = self._roi
        h, w = image.shape[:2]
        cx1 = max(0, min(x1, w))
        cy1 = max(0, min(y1, h))
        cx2 = max(cx1 + 1, min(x2, w))
        cy2 = max(cy1 + 1, min(y2, h))
        return image[cy1:cy2, cx1:cx2]

    def _roi_scales(self, full: np.ndarray, roi: np.ndarray) -> tuple[float, float]:
        fh, fw = full.shape[:2]
        rh, rw = roi.shape[:2]
        return fw / rw if rw else 1.0, fh / rh if rh else 1.0

    def release(self):
        pass  # YOLO model stays in memory for speed; no explicit release needed