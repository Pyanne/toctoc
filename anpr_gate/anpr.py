"""Automatic Number Plate Recognition using Ultralytics YOLO and EasyOCR."""

import os
import re
import subprocess

import cv2
import numpy as np
import requests
from ultralytics import YOLO


class ANPR:
    """Automatic Number Plate Recognition using Ultralytics YOLO and EasyOCR.

    This class handles license plate detection using a YOLO model and text extraction
    using EasyOCR. It supports both image and video streams for real-time inference.

    Attributes:
        model (YOLO): The YOLO model for license plate detection.
        reader (easyocr.Reader): Lazily initialized OCR reader instance.
    """

    def __init__(self, model_path: str = "anpr_best.pt", upscale: int = 3):
        """Initialises the ANPR system.

        Args:
            model_path: Path to the YOLO .pt weights file.
            upscale: ROI upscaling factor (3 = good balance of accuracy/speed).
        """
        self.model = YOLO(model_path)
        self.reader = None
        self.upscale = upscale

        # Pre-compute gamma tables once (used in extract_text + night sweep)
        self._gamma_dark = np.array(
            [((i / 255.0) ** 0.3) * 255 for i in range(256)], dtype="uint8"
        )
        self._gamma_night = np.array(
            [((i / 255.0) ** 0.5) * 255 for i in range(256)], dtype="uint8"
        )
        # Night-sweep gamma tables
        self._night_gammas = [
            (g, np.array([((i / 255.0) ** g) * 255 for i in range(256)], dtype="uint8"))
            for g in [0.20, 0.30, 0.40]
        ]

    def detect_plates(self, im0: np.ndarray):
        """Detects license plates in an image.

        YOLO auto-letterboxes (maintains aspect ratio, pads to square).  No
        manual resize -- that would squash non-square frames and lose small plates.
        """
        results = self.model.predict(im0, imgsz=640, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy() if results and results[0].boxes is not None else []
        return boxes

    def extract_text(self, im0: np.ndarray, bbox: np.ndarray, allowed_plates: set = None):
        """Performs OCR on the cropped license plate region.

        Optimised single-pass pipeline -- each preprocessing variant is run exactly
        once. Early-exits on the first match against an allowlist.

        Pipeline passes:
          1. Grayscale + CLAHE-2.0 (day/evening) + upscale
          2. Gamma-0.3 brighten + CLAHE-8.0 (dark/night)
          3. Gamma-0.5 brighten + CLAHE-4.0 (moderate night)
          4. Red-channel boost + gamma-0.3 + CLAHE-8.0 (yellow plate at night)
          5. Red-channel boost + CLAHE-3.0 (warm lighting)
          6-9. OTSU / adaptive binarisation variants
          10. Low-confidence threshold catch-all

        If all passes fail but allowed_plates is provided, fuzzy-match against
        the allowlist (dictionary fallback).
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
        roi_up = cv2.resize(roi, (w * self.upscale, h * self.upscale),
                            interpolation=cv2.INTER_LANCZOS4)

        # Build all preprocessing variants once
        gray = cv2.cvtColor(roi_up, cv2.COLOR_BGR2GRAY)
        gray_dark = cv2.LUT(gray, self._gamma_dark)
        gray_night = cv2.LUT(gray, self._gamma_night)
        b_ch, g_ch, r_ch = cv2.split(roi_up)
        r_boosted = cv2.convertScaleAbs(r_ch, alpha=1.5, beta=0)
        gray_warm = cv2.cvtColor(cv2.merge([b_ch, g_ch, r_boosted]), cv2.COLOR_BGR2GRAY)

        def clahe(mat, clip=2.0, tiles=(4, 4)):
            c = cv2.createCLAHE(clip, tiles)
            return c.apply(mat)

        # Collect preprocessed images with their labels (single pass -- no duplicates)
        fast_passes = [
            ("day",        clahe(gray, 2.0)),
            ("dark-night", clahe(gray_dark, 8.0, (2, 2))),
            ("night",      clahe(gray_night, 4.0)),
            ("dark-warm",  clahe(cv2.LUT(gray_warm, self._gamma_dark), 8.0, (2, 2))),
            ("warm",       clahe(gray_warm, 3.0)),
        ]

        # Binarised variants
        _, bin_day   = cv2.threshold(gray,       0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, bin_dark  = cv2.threshold(gray_dark,   0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, bin_night = cv2.threshold(gray_night,  0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bin_warm = cv2.adaptiveThreshold(
            gray_warm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 2
        )
        bin_passes = [
            ("bin_day",   bin_day),
            ("bin_dark",  bin_dark),
            ("bin_night", bin_night),
            ("bin_warm",  bin_warm),
        ]

        # Normalise allowlist once
        if allowed_plates:
            allowed_normalized = {
                re.sub(r"[^A-Za-z0-9]", "", p.upper()): p for p in allowed_plates
            }
        else:
            allowed_normalized = {}

        # --- Run fast passes with early exit ---
        all_candidates = []
        for _name, prep_img in fast_passes:
            raw = self._ocr_plate_image(prep_img, min_conf=0.10)
            if raw:
                all_candidates.append(raw)
                if allowed_normalized:
                    corrected = self._correct_plate_cand(raw, allowed_normalized)
                    if corrected:
                        return corrected

        # --- Run binarised passes with early exit ---
        for _name, prep_img in bin_passes:
            raw = self._ocr_plate_image(prep_img, min_conf=0.10)
            if raw:
                all_candidates.append(raw)
                if allowed_normalized:
                    corrected = self._correct_plate_cand(raw, allowed_normalized)
                    if corrected:
                        return corrected

        # No fast/bin pass matched -- try remaining candidates via fuzzy matching
        if allowed_normalized:
            best = self._fuzzy_match(all_candidates, allowed_normalized)
            if best:
                return best

        # --- Night-mode gamma sweep (reduced: 3 gammas * 2 clips = 6 calls) ---
        night_candidates = list(all_candidates)
        for _gamma_val, gt in self._night_gammas:
            for clip in [6.0, 10.0]:
                c = cv2.createCLAHE(clip, (2, 2))
                brightened = c.apply(cv2.LUT(gray, gt))
                raw = self._ocr_plate_image(brightened, min_conf=0.05)
                if raw:
                    night_candidates.append(raw)
                    if allowed_normalized:
                        corrected = self._correct_plate_cand(raw, allowed_normalized)
                        if corrected:
                            return corrected

        # Final fuzzy attempt on all collected candidates
        if allowed_normalized:
            best = self._fuzzy_match(night_candidates, allowed_normalized)
            if best:
                return best

        # Last resort: dictionary fallback with very low threshold
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

    def _correct_plate_cand(self, raw: str, allowed_normalized: dict) -> str:
        """Try to correct a raw OCR string against an allowlist.

        Returns the corrected plate string on match, empty string otherwise.
        This is a lightweight version of _correct_plate that reuses a pre-built
        normalised allowlist dict.
        """
        corrected = self._correct_plate(raw, set(allowed_normalized.values()))
        if corrected:
            result_key = re.sub(r"[^A-Za-z0-9]", "", corrected.upper())
            if result_key in allowed_normalized:
                return allowed_normalized[result_key]
        return ""

    def _fuzzy_match(self, candidates: list, allowed_normalized: dict) -> str:
        """Fuzzy-match candidate strings against a pre-normalised allowlist.

        Uses Levenshtein distance <= 3, with length filtering to avoid
        unnecessary computation.
        """
        if not candidates or not allowed_normalized:
            return ""
        allowed_keys = list(allowed_normalized.keys())
        min_allowed_len = min(len(k) for k in allowed_keys) if allowed_keys else 5

        best_match = None
        best_dist = 99
        for raw in candidates:
            cleaned = re.sub(r"[^A-Za-z0-9]", "", raw.upper())
            if abs(len(cleaned) - min_allowed_len) > 4:
                continue
            for plate_key in allowed_keys:
                if abs(len(cleaned) - len(plate_key)) > 4:
                    continue
                d = self._levenshtein(cleaned, plate_key)
                if d <= 3 and d < best_dist:
                    best_dist = d
                    best_match = allowed_normalized[plate_key]
                    if d == 0:
                        return best_match  # can't beat exact
        return best_match or ""

    def _dictionary_fallback(self, gray: np.ndarray, allowed_plates: set = None) -> str:
        """Last-resort: run OCR at very low threshold and fuzzy-match against allowlist.

        Uses Levenshtein distance up to 2 to handle systematic OCR confusions in dark
        conditions (5<->6, Z<->2, M<->H, 0<->D). Only considers candidates of roughly the
        same length as the shortest allowed plate (within +-2 chars).
        """
        if not allowed_plates:
            return ""
        # Normalise allowlist
        allowed_normalized = {}
        min_len = 999
        for plate in allowed_plates:
            pk = re.sub(r"[^A-Za-z0-9]", "", plate.upper())
            allowed_normalized[pk] = plate
            min_len = min(min_len, len(pk))

        # Apply CLAHE preprocessing before OCR -- same as main pipeline
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Also try dark-night variant (aggressive gamma + high-clip CLAHE)
        dark = cv2.LUT(gray, self._gamma_dark)
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

        # Try concatenating pairs of fragments that together form a valid length
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

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Simple Levenshtein distance (insertion + deletion + substitution = 1 each).
        Row-wise DP; only keep prev and current rows to save memory.
        """
        if len(a) < len(b):
            a, b = b, a  # iterate over the shorter string in inner loop
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
        """Post-process OCR output for license plate text.

        Applies simple character substitutions and format matching for
        French plate formats (new: AB-123-CD, old: 1234 AB 56).
        Characters I, O are stripped (never valid in French plates).
        U is remapped to V.

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

        # Remove characters never found in French plates (only I and O are stripped;
        # U is already remapped to V in char_map above)
        result = re.sub(r"[IOio]", "", result)

        # Strip leading/trailing boundary digits -- OCR often adds phantom 1s at plate edges
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
        # H<->7, P<->F, P<->H -- only swap if it creates a valid format
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
                    # One extra or missing char -- check prefix match
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

    Uses Python requests with HTTPDigestAuth to avoid shell expansion
    issues with special characters in passwords (e.g. $$).
    """
    try:
        user, password = auth.split(":", 1)
        r = requests.get(
            snapshot_url,
            auth=requests.auth.HTTPDigestAuth(user, password),
            timeout=10,
        )
        if r.status_code != 200:
            return False
        with open(snap_path, "wb") as f:
            f.write(r.content)
        return os.path.getsize(snap_path) > 0
    except Exception:
        return False


def build_rtsp_url(host: str, port: int, user: str, password: str, path: str) -> str:
    """Build RTSP URL from camera configuration."""
    return f"rtsp://{user}:{password}@{host}:{port}{path}"
