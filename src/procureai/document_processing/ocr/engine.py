"""OCR via Tesseract with a hard timeout. Failure degrades to empty text (logged), never crashes ingestion."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)
OCR_TIMEOUT_SECONDS = 40


def ocr_image_bytes(data: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:  # pragma: no cover
        logger.warning("OCR dependencies missing; skipping OCR")
        return ""
    try:
        with Image.open(io.BytesIO(data)) as img:
            return pytesseract.image_to_string(img.convert("L"), timeout=OCR_TIMEOUT_SECONDS).strip()
    except Exception as exc:  # boundary: OCR engine/timeouts must not crash ingestion
        logger.warning("OCR failed: %s", type(exc).__name__)
        return ""


def ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
