"""Automatic Number Plate Recognition using Ultralytics YOLO and EasyOCR."""

import re
import subprocess

import cv2
import numpy as np
from ultralytics import YOLO


class ANPR:
    """Automatic Number Plate Recognition using Ultralytics YOLO and EasyOCR.

    This class handles license plate detection using a YOLO model and text extraction
    using EasyOCR. It supports both image and video streams for real-time inference.

    Attributes:
        model (YOLO): The YOLO model for license plate detection.
        reader (easyocr.Reader): Lazily initialized OCR reader instance.
    """

    def __init__(self, model_path: str = "anpr_best.pt"):
        """Initializes the ANPR system."""
        self.model = YOLO(model_path)
        self.reader = None

    def detect_plates(self, im0: np.ndarray):
        """Detects license plates in an image."""
        h, w = im0.shape[:2]
        scale_x, scale_y = w / 640, h / 640
        small = cv2.resize(im0, (640, 640))
        results = self.model.predict(small, imgsz=640, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy() if results and results[0].boxes is not None else []
        # Scale bounding boxes back to original resolution
        if len(boxes):
            boxes[:, [0, 2]] *= scale_x
            boxes[:, [1, 3]] *= scale_y
        return boxes

    def extract_text(self, im0: np.ndarray, bbox: np.ndarray):
        """Performs OCR on the cropped license plate region."""
        if self.reader is None:
            import warnings
            warnings.filterwarnings("ignore", message=".*pin_memory.*")
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False)
        x1, y1, x2, y2 = map(int, bbox)
        roi = im0[y1:y2, x1:x2]

        # Preprocessing: upscale → denoise → binarize
        h, w = roi.shape[:2]
        roi = cv2.resize(roi, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # OCR with confidence filtering
        results = self.reader.readtext(binary, detail=1, paragraph=False)
        if not results:
            return ""
        chars = []
        for bbox_pts, text, conf in results:
            if conf >= 0.3:
                chars.append(text)
        raw = " ".join(chars).strip()
        return self._correct_plate(raw) if raw else ""

    @staticmethod
    def _correct_plate(raw: str) -> str:
        """Post-process OCR output for French license plates.

        French plates use two formats:
          - New: AB-123-CD  (2 letters, 3 digits, 2 letters)
          - Old: 1234 AB 56 (4 digits, 2 letters, 2 digits)

        Letters I and O are never used, so we map them unambiguously.
        """
        # Map characters that are never valid French plate letters
        char_map = {
            "I": "1", "i": "1",
            "l": "1",  # lowercase L commonly misread as 1
            "O": "0", "o": "0",
        }
        corrected = []
        for ch in raw:
            corrected.append(char_map.get(ch, ch))
        result = "".join(corrected)
        # Strip everything except letters, digits, and hyphens, then uppercase
        result = re.sub(r"[^A-Za-z0-9-]", "", result)
        return result.upper()

    def infer_image(self, image_path: str):
        """Detects license plates in a single image and returns the extracted text(s)."""
        im0 = cv2.imread(image_path)
        if im0 is None:
            raise ValueError(f"Cannot read image: {image_path}")

        boxes = self.detect_plates(im0)
        plates = []
        for bbox in boxes:
            text = self.extract_text(im0, bbox)
            if text:
                plates.append(text)
        return plates


def grab_snapshot(rtsp_url: str, output_path: str = "/tmp/anpr_snapshot.jpg") -> bool:
    """Capture a single frame from RTSP stream using ffmpeg."""
    cmd = [
        "ffmpeg", "-rtsp_transport", "tcp", "-y",
        "-i", rtsp_url,
        "-vframes", "1", "-f", "mjpeg", output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def build_rtsp_url(host: str, port: int, user: str, password: str, path: str) -> str:
    """Build RTSP URL from camera configuration."""
    return f"rtsp://{user}:{password}@{host}:{port}{path}"
