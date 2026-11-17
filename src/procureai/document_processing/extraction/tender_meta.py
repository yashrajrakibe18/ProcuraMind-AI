"""Tender-level metadata (item and quantity) used by pricing when a quotation omits quantity."""

from __future__ import annotations

import re
from dataclasses import dataclass

from procureai.domain.requirements.units import parse_number

_ITEM = re.compile(r"^\s*(?:item|subject|title|tender title|description of (?:goods|item)|goods)\s*[:\-]\s*(.+)$", re.I)
_QTY = re.compile(r"^\s*(?:quantity|qty|total quantity|quantity required)\s*[:\-]\s*(.+)$", re.I)


@dataclass
class TenderMetadata:
    item_description: str | None = None
    quantity: float | None = None


def extract_tender_metadata(pages: list[tuple[int, str]]) -> TenderMetadata:
    meta = TenderMetadata()
    for _, text in pages:
        for line in text.splitlines():
            if meta.item_description is None and (m := _ITEM.match(line)):
                meta.item_description = m.group(1).strip()[:250]
            elif meta.quantity is None and (m := _QTY.match(line)):
                meta.quantity = parse_number(m.group(1))
    return meta
