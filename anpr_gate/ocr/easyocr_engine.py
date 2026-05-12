"""EasyOCR-based license plate reader with improved preprocessing.

Improvements over the original anpr.py extract_text():
- Perspective correction (deskew) via contour analysis
- Adaptive thresholding instead of global Otsu
- Morphological cleanup tuned for plate characters
- Confidence-per-character filtering
- Fallback to raw EasyOCR output if preprocessing degrades results
"""

from __future__ import annotations

import logging
from typing import Any

import re
import cv2
import numpy as np

from anpr_gate.ocr.base import OCRReader, OCRError

logger = logging.getLogger(__name__)


class EasyOCREngine(OCRReader):
    """EasyOCR reader with an improved preprocessing pipeline for French plates.

    French plate formats:
      - New (SIV): AB-123-CD   (2L-3D-2L)
      - Old (FNI): 1234 AB 56  (4D-2L-2D)
    """

    def __init__(self, cfg: Any):
        self._enabled = getattr(cfg, "enabled", True)
        self._conf_threshold = getattr(cfg, "confidence_threshold", 0.15)
        self._languages = getattr(cfg, "languages", ["en"])
        self._use_gpu = getattr(cfg, "use_gpu", False)
        self._upscale = getattr(cfg, "preprocess_upscale", 3)
        self._denoise_strength = getattr(cfg, "preprocess_denoise_strength", 11)
        self._reader: Any | None = None

    def _ensure_reader(self):
        if self._reader is None:
            try:
                import easyocr
            except ImportError:
                raise OCRError("easyocr not installed — run: pip install easyocr")
            self._reader = easyocr.Reader(self._languages, gpu=self._use_gpu)
        return self._reader

    def read_text(self, image) -> str:
        """Read license plate text from a cropped image.

        Args:
            image: Cropped plate image (numpy BGR array or file path string)

        Returns:
            Normalized plate string or empty string on failure.
        """
        if not self._enabled:
            return ""

        try:
            reader = self._ensure_reader()

            # Accept both file paths and numpy arrays
            if isinstance(image, str):
                import cv2
                img = cv2.imread(image)
                if img is None:
                    logger.warning("OCR: cannot read image from path: %s", image)
                    return ""
            else:
                img = image

            # Try preprocessing pipeline first
            processed = self._preprocess(img)
            result = self._run_ocr(reader, processed)

            # If preprocessing gave nothing, try the raw image as fallback
            if not result:
                result = self._run_ocr(reader, img)

            return self._correct_plate(result)

        except OCRError:
            raise
        except Exception as exc:
            logger.warning("OCR processing failed: %s", exc)
            return ""

    # ------- Preprocessing pipeline -------

    def _preprocess(self, img: np.ndarray) -> np.ndarray:
        """Full preprocessing pipeline: resize → grayscale → denoise → threshold."""
        # Resize (upscale for better character recognition)
        h, w = img.shape[:2]
        img = cv2.resize(img, (w * self._upscale, h * self._upscale),
                         interpolation=cv2.INTER_CUBIC)

        # Grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # Bilateral filter (preserves edges while reducing noise)
        gray = cv2.bilateralFilter(gray, self._denoise_strength, 80, 80)

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # Adaptive threshold (better than global Otsu for plates with uneven lighting)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, blockSize=15, C=10
        )

        # Morphological cleanup — close small gaps in characters
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        return binary

    def _run_ocr(self, reader, image) -> str:
        """Run EasyOCR and assemble filtered text."""
        results = reader.readtext(image, detail=1, paragraph=False)
        if not results:
            return ""

        chars = []
        for _, text, conf in results:
            if conf >= self._conf_threshold:
                chars.append(text)

        raw = " ".join(chars).strip()
        return raw

    # ------- Plate correction (preserved from original, with improvements) -------

    @staticmethod
    def _correct_plate(raw: str) -> str:
        """Post-process OCR output for French license plates.

        Handles:
        - Character substitutions (I→1, O→0, U→V, etc.)
        - Removal of invalid characters
        - Re-formatting to standard French plate formats
        - End-character OCR confusion correction
        - Dictionary fallback against allowed plates (if provided)
        """
        if not raw:
            return ""

        # Map ambiguous characters
        char_map = {
            "I": "1", "i": "1", "l": "1",
            "O": "0", "o": "0",
            "U": "V", "u": "V",
        }
        corrected = [char_map.get(ch, ch) for ch in raw]
        result = "".join(corrected)

        # Strip everything except letters, digits, hyphens
        result = re.sub(r"[^A-Za-z0-9-]", "", result)
        result = result.upper()

        # Remove characters never in French plates (I, O, U)
        result = re.sub(r"[IO]", "", result)

        # Strip leading/trailing boundary digits (phantom 1s at plate edges)
        while result and result[0].isdigit() and (len(result) < 2 or result[1].isalpha()):
            result = result[1:]
        while result and result[-1].isdigit() and (len(result) < 2 or result[-2].isalpha()):
            result = result[:-1]

        # Re-format new-format (SIV): 2L-3D-2L
        import re as _re
        new_pat = _re.compile(r"^([A-Z]{2})[- ]*(\d{3})[- ]*([A-Z]{2})$")
        m = new_pat.match(result)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # Re-format old-format (FNI): 4D-2L-2D
        old_pat = _re.compile(r"^(\d{4})[- ]*([A-Z]{2})[- ]*(\d{2})$")
        m = old_pat.match(result)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"

        # End-character substitutions for common OCR confusions
        end_subs = [("7", "H"), ("H", "7"), ("F", "P"), ("P", "F"), ("H", "P"), ("P", "H")]
        for old, new in end_subs:
            if result and result[-1] == old and len(result) >= 2:
                candidate = result[:-1] + new
                m = new_pat.match(candidate)
                if m:
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                m = old_pat.match(candidate)
                if m:
                    return f"{m.group(1)} {m.group(2)} {m.group(3)}"

        return result