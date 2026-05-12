"""Abstract OCR reader interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class OCRError(Exception):
    """Raised when OCR processing fails."""


class OCRReader(ABC):
    """Extract text from a cropped license plate image."""

    @abstractmethod
    def read_text(self, image) -> str:
        """Read text from a plate image. Returns normalized plate string or empty."""
        ...

    def release(self) -> None:
        pass