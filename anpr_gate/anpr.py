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

    def extract_text(self, im0: np.ndarray, bbox: np.ndarray, allowed_plates: set = None):
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
            if conf >= 0.15:   # lowered from 0.3 to catch borderline reads
                chars.append(text)
        raw = " ".join(chars).strip()
        return self._correct_plate(raw, allowed_plates) if raw else ""

    @staticmethod
    def _correct_plate(raw: str, allowed_plates: set = None) -> str:
        """Post-process OCR output for French license plates.

        French plates use two formats:
          - New: AB-123-CD  (2 letters, 3 digits, 2 letters)
          - Old: 1234 AB 56 (4 digits, 2 letters, 2 digits)

        Letters I and O are never used, so we map them unambiguously.
        J, U, W, Z never appear in standard French plates and are stripped.
        Common suffix/prefix garbage from OCR boundary artifacts is removed.
        End-character substitutions handle common OCR confusions at plate boundary.
        Dictionary fallback catches 1-character errors against the allowed list.
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
        result = result.upper()

        # Remove characters never found in French plates (per ANPR standard)
        result = re.sub(r"[JUWZj]", "", result)

        # Strip leading/trailing boundary digits — OCR often adds phantom 1s at plate edges
        # Safe because new-format plates always have LETTERS at positions 1,2,4,5,7
        # and old-format always starts with 4 digits. A digit next to a letter = boundary noise.
        while result and result[0].isdigit() and (len(result) < 2 or result[1].isalpha()):
            result = result[1:]
        while result and result[-1].isdigit() and (len(result) < 2 or result[-2].isalpha()):
            result = result[:-1]

        # Re-format new-format French plates: 2 letters, 3 digits, 2 letters
        new_pat = re.compile(r"^([A-Z]{2})[- ]*(\d{3})[- ]*([A-Z]{2})$")
        m = new_pat.match(result)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # Re-format old-format French plates: 4 digits, 2 letters, 2 digits
        old_pat = re.compile(r"^(\d{4})[- ]*([A-Z]{2})[- ]*(\d{2})$")
        m = old_pat.match(result)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"

        # Try end-character substitutions: common OCR confusions at plate boundary
        # H<->7, P<->F, P<->H — only swap if it creates a valid format
        end_subs = [('7','H'), ('H','7'), ('F','P'), ('P','F'), ('H','P'), ('P','H')]
        for old, new in end_subs:
            if result and result[-1] == old and len(result) >= 2:
                candidate = result[:-1] + new
                m = new_pat.match(candidate)
                if m:
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                m = old_pat.match(candidate)
                if m:
                    return f"{m.group(1)} {m.group(2)} {m.group(3)}"

        # Dictionary fallback: if result is close to an allowed plate, use it
        if allowed_plates:
            result_key = re.sub(r"[- ]", "", result)

            # Normalize allowed plates once
            allowed_normalized = {}
            for plate in allowed_plates:
                pk = re.sub(r"[- ]", "", plate)
                allowed_normalized[pk] = plate

            # 1. Try stripping trailing digit pairs (handles garbled suffix: CF938PH301 -> CF938PH)
            for tail_len in (2, 1):
                if len(result_key) - tail_len >= 5:
                    stripped = result_key[:-tail_len]
                    if stripped in allowed_normalized:
                        return allowed_normalized[stripped]

            # 2. Exact match
            if result_key in allowed_normalized:
                return allowed_normalized[result_key]

            # 3. One-character error correction (substitution, insertion, deletion)
            best = None
            best_diffs = 999
            for plate_key, plate in allowed_normalized.items():
                if len(result_key) == len(plate_key):
                    diffs = sum(1 for a, b in zip(result_key, plate_key) if a != b)
                    if diffs == 1 and diffs < best_diffs:
                        best = plate
                        best_diffs = diffs
                elif abs(len(result_key) - len(plate_key)) == 1:
                    # One extra or missing char — check prefix match
                    shorter, longer = (result_key, plate_key) if len(result_key) < len(plate_key) else (plate_key, result_key)
                    for i in range(len(longer)):
                        candidate = longer[:i] + longer[i+1:]
                        if candidate == shorter:
                            return plate
            if best:
                return best

        return result

    def infer_image(self, image_path: str, allowed_plates: set = None):
        """Detects license plates in a single image and returns the extracted text(s)."""
        im0 = cv2.imread(image_path)
        if im0 is None:
            raise ValueError(f"Cannot read image: {image_path}")

        boxes = self.detect_plates(im0)
        plates = []
        for bbox in boxes:
            text = self.extract_text(im0, bbox, allowed_plates)
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
