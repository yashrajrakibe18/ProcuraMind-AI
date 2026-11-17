"""Load an uploaded file into per-page text (native text -> table rows -> OCR fallback)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from procureai.document_processing.ocr.engine import ocr_image_bytes
from procureai.document_processing.tables.extract import extract_table_rows
from procureai.shared.errors import ProcessingError

logger = logging.getLogger(__name__)
TABLE_MARKER = "[TABLE]"


@dataclass
class PageContent:
    page_number: int
    text: str
    ocr_used: bool = False


def load_pages(path: Path, mime_type: str, min_chars_for_ocr: int = 25, max_pages: int = 300) -> list[PageContent]:
    if mime_type == "application/pdf":
        return _load_pdf(path, min_chars_for_ocr, max_pages)
    if mime_type in ("image/png", "image/jpeg"):
        text = ocr_image_bytes(path.read_bytes())
        return [PageContent(1, text, ocr_used=True)]
    if mime_type in ("text/plain", "text/csv"):
        text = path.read_text(encoding="utf-8", errors="replace")
        # Treat form-feed as page break; otherwise chunk by ~60 lines to keep page citations meaningful.
        raw_pages = text.split("\f") if "\f" in text else _paginate_lines(text.splitlines(), 60)
        return [PageContent(i + 1, p.strip()) for i, p in enumerate(raw_pages) if p.strip()] or [PageContent(1, "")]
    if mime_type.endswith("wordprocessingml.document"):
        return _load_docx(path)
    if mime_type.endswith("spreadsheetml.sheet"):
        return _load_xlsx(path)
    raise ProcessingError(f"Unsupported content type for processing: {mime_type}")


def _load_docx(path: Path) -> list[PageContent]:
    import docx

    try:
        d = docx.Document(str(path))
    except Exception as exc:
        raise ProcessingError("The DOCX file could not be opened (corrupt or not a Word document).") from exc
    lines = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    pages = _paginate_lines(lines, 45)
    return [PageContent(i + 1, p) for i, p in enumerate(pages) if p.strip()] or [PageContent(1, "")]


def _load_xlsx(path: Path) -> list[PageContent]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise ProcessingError("The XLSX file could not be opened (corrupt or not a workbook).") from exc
    pages: list[PageContent] = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v) for v in row]
            if any(vals):
                rows.append(" | ".join(vals))
            if len(rows) >= 2000:
                break
        for chunk in _paginate_lines([f"[Sheet: {ws.title}]"] + rows, 60):
            pages.append(PageContent(len(pages) + 1, chunk))
    return pages or [PageContent(1, "")]


def _paginate_lines(lines: list[str], size: int) -> list[str]:
    return ["\n".join(lines[i : i + size]) for i in range(0, len(lines), size)]


def _load_pdf(path: Path, min_chars: int, max_pages: int) -> list[PageContent]:
    import pymupdf as fitz

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ProcessingError("The PDF could not be opened (corrupt or encrypted).") from exc
    if doc.page_count > max_pages:
        doc.close()
        raise ProcessingError(f"PDF has too many pages (limit {max_pages}).")
    pages: list[PageContent] = []
    try:
        for idx in range(doc.page_count):
            page = doc[idx]
            text = page.get_text("text").strip()
            ocr_used = False
            if len(text) < min_chars:
                pix = page.get_pixmap(dpi=200)
                ocr_text = ocr_image_bytes(pix.tobytes("png"))
                if len(ocr_text) > len(text):
                    text, ocr_used = ocr_text, True
            else:
                rows = extract_table_rows(str(path), idx)
                if rows:
                    text = f"{text}\n{TABLE_MARKER}\n" + "\n".join(rows)
            pages.append(PageContent(idx + 1, text, ocr_used))
    finally:
        doc.close()
    return pages


def count_pdf_pages(path: Path) -> int:
    import pymupdf as fitz

    with fitz.open(path) as doc:
        return doc.page_count
