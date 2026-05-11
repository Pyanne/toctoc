"""Mock OCR reader for testing."""

from __future__ import annotations

from anpr_gate.ocr.base import OCRReader


class MockOCR(OCRReader):
    """Returns a fixed plate string for testing.

    Set result to empty string to simulate OCR failure.
    """

    def __init__(self, result: str = "AB-123-CD", *, enabled: bool = True):
        super().__init__()
        self._result = result
        self._enabled = enabled
        self.call_count = 0

    def read_text(self, image) -> str:
        if not self._enabled:
            return ""
        self.call_count += 1
        return self._result

    def set_result(self, text: str):
        self._result = text