"""Parse historical purchase CSVs (flexible headers) into normalized rows."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

_ITEM = ("item_category", "category", "item", "description", "product", "item_description")
_PRICE = ("unit_price", "price", "unit_cost", "rate", "price_per_unit")
_CUR = ("currency", "curr")
_DATE = ("date", "purchase_date", "purchased_on", "order_date")
_SUP = ("supplier", "vendor", "vendor_name", "supplier_name")


@dataclass
class HistoricalRow:
    item_category: str
    unit_price: float
    currency: str
    purchased_on: date | None
    supplier: str | None


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if row.get(k):
            return row[k].strip()
    return None


def _date(text: str | None) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text or "", fmt).date()
        except ValueError:
            continue
    return None


def looks_like_historical_csv(text: str) -> bool:
    header = text.splitlines()[0].lower() if text.strip() else ""
    cols = {c.strip().replace(" ", "_") for c in header.split(",")}
    return bool(cols & set(_PRICE)) and bool(cols & set(_ITEM))


def parse_historical_csv(text: str) -> tuple[list[HistoricalRow], int]:
    """Returns (rows, skipped_count)."""
    reader = csv.DictReader(io.StringIO(text))
    rows, skipped = [], 0
    for raw in reader:
        row = {(k or "").strip().lower().replace(" ", "_"): (v or "") for k, v in raw.items()}
        item, price = _pick(row, _ITEM), _pick(row, _PRICE)
        try:
            amount = float((price or "").replace(",", "").lstrip("$€£₹"))
        except ValueError:
            skipped += 1
            continue
        if not item or amount <= 0:
            skipped += 1
            continue
        rows.append(
            HistoricalRow(
                item, amount, (_pick(row, _CUR) or "USD").upper()[:8], _date(_pick(row, _DATE)), _pick(row, _SUP)
            )
        )
    return rows, skipped
