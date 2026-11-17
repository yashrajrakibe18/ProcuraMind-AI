"""Table extraction (pdfplumber) -> pipe-delimited rows, so extractors can parse tabular requirement lists."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def extract_table_rows(pdf_path: str, page_index: int) -> list[str]:
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_index]
            rows: list[str] = []
            for table in page.extract_tables():
                for row in table:
                    cells = [" ".join((c or "").split()) for c in row]
                    if sum(1 for c in cells if c) >= 2:
                        rows.append(" | ".join(cells))
            return rows
    except Exception as exc:  # boundary: table parsing is best-effort
        logger.warning("Table extraction failed on page %s: %s", page_index + 1, type(exc).__name__)
        return []
