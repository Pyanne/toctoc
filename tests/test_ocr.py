"""Tests for OCR module."""

from anpr_gate.ocr.mock_ocr import MockOCR


class TestMockOCR:
    def test_returns_configured_result(self):
        ocr = MockOCR(result="XY-789-ZZ")
        assert ocr.read_text(None) == "XY-789-ZZ"

    def test_empty_when_disabled(self):
        ocr = MockOCR(result="AB-123-CD", enabled=False)
        assert ocr.read_text(None) == ""

    def test_call_count(self):
        ocr = MockOCR(result="TEST")
        assert ocr.call_count == 0
        ocr.read_text(None)
        assert ocr.call_count == 1

    def test_set_result(self):
        ocr = MockOCR(result="OLD")
        ocr.set_result("NEW")
        assert ocr.read_text(None) == "NEW"