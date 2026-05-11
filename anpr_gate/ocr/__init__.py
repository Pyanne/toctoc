"""OCR module — lightweight imports only."""

from anpr_gate.ocr.base import OCRReader, OCRError
from anpr_gate.ocr.mock_ocr import MockOCR

# EasyOCREngine imported lazily via container.py
__all__ = ["OCRReader", "OCRError", "MockOCR", "EasyOCREngine"]