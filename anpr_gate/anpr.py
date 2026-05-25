"""Automatic Number Plate Recognition using Ultralytics YOLO and EasyOCR."""

import os
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
        """Performs OCR on the cropped license plate region.

        Multi-pass pipeline (earlier passes are faster; slower passes as fallbacks):
          1. 5x LANCZOS4 upscale → grayscale → CLAHE-2.0 (day/even lighting)
          2. Gamma brighten (0.8) → CLAHE-4.0 (dark/night scenes)
          3. Adaptive threshold on brightened image (very dark scenes)
          4. Red-channel boost → CLAHE (yellow plate enhancement for night)
          5. Lowered confidence threshold pass (catches weak detections)

        If all passes fail but allowed_plates is provided, fuzzy-match raw EasyOCR
        output against the allowlist (dictionary fallback).
        """
        if self.reader is None:
            import warnings
            warnings.filterwarnings("ignore", message=".*pin_memory.*")
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False)
        x1, y1, x2, y2 = map(int, bbox)
        roi = im0[y1:y2, x1:x2]
        if roi.size == 0:
            return ""

        h, w = roi.shape[:2]
        roi_up = cv2.resize(roi, (w * 5, h * 5), interpolation=cv2.INTER_LANCZOS4)

        # Build preprocessing variants
        gray = cv2.cvtColor(roi_up, cv2.COLOR_BGR2GRAY)
        # Dark-night: aggressive gamma (lower = brighter)
        gamma_table_dark = np.array([((i / 255.0) ** 0.3) * 255 for i in range(256)], dtype="uint8")
        gray_dark = cv2.LUT(gray, gamma_table_dark)
        # Moderate night: moderate gamma
        gamma_table_night = np.array([((i / 255.0) ** 0.5) * 255 for i in range(256)], dtype="uint8")
        gray_night = cv2.LUT(gray, gamma_table_night)
        # Warm: red-channel boost (yellow plate chars on red background)
        b_ch, g_ch, r_ch = cv2.split(roi_up)
        r_boosted = cv2.convertScaleAbs(r_ch, alpha=1.5, beta=0)
        gray_warm = cv2.cvtColor(cv2.merge([b_ch, g_ch, r_boosted]), cv2.COLOR_BGR2GRAY)

        def clahe(mat, clip=2.0, tiles=(4, 4)):
            c = cv2.createCLAHE(clip, tiles)
            return c.apply(mat)

        # Fast passes first (no binarization)
        passes = [
            ("day",        lambda: clahe(gray, 2.0)),
            ("dark-night", lambda: clahe(gray_dark, 8.0, (2, 2))),
            ("night",      lambda: clahe(gray_night, 4.0)),
            ("dark-warm",  lambda: clahe(cv2.LUT(gray_warm, gamma_table_dark), 8.0, (2, 2))),
            ("warm",       lambda: clahe(gray_warm, 3.0)),
        ]
        for name, prep in passes:
            raw = self._ocr_plate_image(prep(), min_conf=0.10)
            if raw:
                corrected = self._correct_plate(raw, allowed_plates)
                if corrected:
                    # Check if this result matches allowlist (possibly after stripping trailing chars)
                    import re
                    result_key = re.sub(r"[^A-Za-z0-9]", "", corrected.upper())
                    allowed_normalized = {re.sub(r"[^A-Za-z0-9]", "", p.upper()): p for p in (allowed_plates or [])}
                    if result_key in allowed_normalized:
                        return allowed_normalized[result_key]
                    for tail_len in (2, 1):
                        if len(result_key) - tail_len >= 5:
                            stripped = result_key[:-tail_len]
                            if stripped in allowed_normalized:
                                return allowed_normalized[stripped]
                    # Not matched — keep trying other passes
                    return corrected

        # Slow passes with binarization
        _, bin_day    = cv2.threshold(gray,        0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, bin_dark   = cv2.threshold(gray_dark,   0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, bin_night  = cv2.threshold(gray_night,   0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bin_warm = cv2.adaptiveThreshold(gray_warm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY, 15, 2)
        bin_passes = [
            ("bin_day",    bin_day),
            ("bin_dark",   bin_dark),
            ("bin_night",  bin_night),
            ("bin_warm",   bin_warm),
        ]
        for name, prep in bin_passes:
            raw = self._ocr_plate_image(prep, min_conf=0.10)
            if raw:
                corrected = self._correct_plate(raw, allowed_plates)
                if corrected:
                    return corrected

        # Night-mode: try multiple gamma values + CLAHE on the dark frame,
        # then on bright frame, collecting all readable fragments
        # Ensure reader is initialized before any OCR calls
        if self.reader is None:
            import warnings
            warnings.filterwarnings("ignore", message=".*pin_memory.*")
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False)

        night_candidates = []
        for g in [0.20, 0.25, 0.30, 0.35, 0.40]:
            gt = np.array([((i / 255.0) ** g) * 255 for i in range(256)], dtype="uint8")
            for clip in [6.0, 8.0, 10.0]:
                c = cv2.createCLAHE(clip, (2, 2))
                brightened = cv2.LUT(gray, gt)
                prep = c.apply(brightened)
                raw = self._ocr_plate_image(prep, min_conf=0.05)
                if raw:
                    corrected = self._correct_plate(raw, allowed_plates)
                    if corrected:
                        # Only return immediately if it looks like a complete valid plate
                        # (no trailing garbage that would be stripped anyway)
                        # Re-check: does it match allowlist after our normalization?
                        import re
                        result_key = re.sub(r"[^A-Za-z0-9]", "", corrected.upper())
                        allowed_normalized = {re.sub(r"[^A-Za-z0-9]", "", p.upper()): p for p in (allowed_plates or [])}
                        # Accept if exact match, or if stripping 1-2 trailing chars gives a match
                        if result_key in allowed_normalized:
                            return allowed_normalized[result_key]
                        for tail_len in (2, 1):
                            if len(result_key) - tail_len >= 5:
                                stripped = result_key[:-tail_len]
                                if stripped in allowed_normalized:
                                    return allowed_normalized[stripped]
                    night_candidates.append(raw)

        # If no pass produced a valid format, try Levenshtein fuzzy-match
        # on all fragments collected across passes
        if night_candidates:
            best = self._fuzzy_fallback(gray, night_candidates, allowed_plates)
            if best:
                return best

        # Dictionary fallback: match raw EasyOCR output directly against allowlist
        return self._dictionary_fallback(gray, allowed_plates)

    def _ocr_plate_image(self, processed: np.ndarray, min_conf: float = 0.10) -> str:
        """Run EasyOCR on a preprocessed plate image and return joined text."""
        results = self.reader.readtext(processed, detail=1, paragraph=False)
        if not results:
            return ""
        parts = []
        for _, text, conf in results:
            if conf >= min_conf:
                parts.append(text)
        return "".join(parts).strip()

    def _dictionary_fallback(self, gray: np.ndarray, allowed_plates: set = None) -> str:
        """Last-resort: run OCR at very low threshold and fuzzy-match against allowlist.

        Uses Levenshtein distance up to 2 to handle systematic OCR confusions in dark
        conditions (5↔6, Z↔2, M↔H, 0↔D). Only considers candidates of roughly the
        same length as the shortest allowed plate (within ±2 chars).
        """
        if not allowed_plates:
            return ""
        import re
        # Normalize allowlist
        allowed_normalized = {}
        min_len = 999
        for plate in allowed_plates:
            pk = re.sub(r"[^A-Za-z0-9]", "", plate.upper())
            allowed_normalized[pk] = plate
            min_len = min(min_len, len(pk))

        # Apply CLAHE preprocessing before OCR — same as main pipeline
        # This dramatically improves character recognition on small/contrast-poor crops
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Also try dark-night variant (aggressive gamma + high-clip CLAHE)
        gamma_table_dark = np.array([((i / 255.0) ** 0.3) * 255 for i in range(256)], dtype="uint8")
        dark = cv2.LUT(gray, gamma_table_dark)
        clahe_dark = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(2, 2))
        dark_enhanced = clahe_dark.apply(dark)

        # Run OCR on both preprocessed versions
        seen = set()
        candidates = []
        for prep in [enhanced, dark_enhanced]:
            results = self.reader.readtext(prep, detail=1, paragraph=False)
            for _, text, _ in results:
                cleaned = re.sub(r"[^A-Za-z0-9]", "", text.upper())
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    candidates.append(cleaned)

        # Try concatenating pairs/triples of fragments that together form a valid length
        # French plates are 7-9 chars (new: AB-123-CD, old: 1234-AB-56)
        if len(candidates) > 1:
            for i in range(len(candidates)):
                for j in range(i + 1, len(candidates)):
                    concat = candidates[i] + candidates[j]
                    if 7 <= len(concat) <= 9:
                        candidates.append(concat)

        best_match = None
        best_dist = 99
        for raw_key in candidates:
            # Only try matches of roughly right length
            if not (min_len - 2 <= len(raw_key) <= min_len + 2):
                continue
            for plate_key, plate in allowed_normalized.items():
                if abs(len(raw_key) - len(plate_key)) > 2:
                    continue
                # Levenshtein distance
                d = self._levenshtein(raw_key, plate_key)
                if d <= 2 and d < best_dist:
                    best_dist = d
                    best_match = plate
        return best_match or ""

    def _fuzzy_fallback(self, gray: np.ndarray, candidates: list, allowed_plates: set) -> str:
        """Try Levenshtein fuzzy-match of raw candidate strings against allowlist.

        Candidates are unformatted OCR fragments collected from multiple passes.
        This catches plates that OCR can read character-by-character but can't
        assemble into the correct order/form.
        """
        if not candidates or not allowed_plates:
            return ""
        import re
        allowed_normalized = {}
        for plate in allowed_plates:
            pk = re.sub(r"[^A-Za-z0-9]", "", plate.upper())
            allowed_normalized[pk] = plate

        best_match = None
        best_dist = 99
        for raw in candidates:
            cleaned = re.sub(r"[^A-Za-z0-9]", "", raw.upper())
            for plate_key, plate in allowed_normalized.items():
                d = self._levenshtein(cleaned, plate_key)
                if d <= 2 and d < best_dist:
                    best_dist = d
                    best_match = plate
        return best_match or ""

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Simple Levenshtein distance ( insertion + deletion + substitution = 1 each)."""
        # Row-wise DP; only keep prev and current rows to save memory
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                cost = 0 if ca == cb else 1
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost))
            prev = curr
        return prev[-1]

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
            "U": "V",  # U never appears; likely misread V
            "u": "V",
        }
        corrected = []
        for ch in raw:
            corrected.append(char_map.get(ch, ch))
        result = "".join(corrected)
        # Strip everything except letters, digits, and hyphens, then uppercase
        result = re.sub(r"[^A-Za-z0-9-]", "", result)
        result = result.upper()

        # Remove characters never found in French plates (only I, O, U are excluded)
        result = re.sub(r"[IOio]", "", result)

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


def grab_gate_snapshot(snapshot_url: str, auth: str,
                       snap_path: str) -> bool:
    """Grab a single frame from the gate camera via HTTP digest auth.

    The gate camera lives at ``http://192.168.20.22:82`` and exposes
    Hikvision ISAPI ``/Streaming/channels/101/picture``.
    """
    import shutil
    cmd = [
        "curl", "-s", "--connect-timeout", "5",
        "-u", auth, "--digest",
        snapshot_url,
        "-o", snap_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        return result.returncode == 0 and os.path.getsize(snap_path) > 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def build_rtsp_url(host: str, port: int, user: str, password: str, path: str) -> str:
    """Build RTSP URL from camera configuration."""
    return f"rtsp://{user}:{password}@{host}:{port}{path}"
