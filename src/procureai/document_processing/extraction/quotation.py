"""Rule-based extraction of vendor quotations (commercial terms + specifications) with page provenance."""

from __future__ import annotations

import re
from pathlib import Path

from procureai.document_processing.extraction.models import ExtractedQuotation, ExtractedSpec
from procureai.domain.requirements.fields import COMMERCIAL_LOOKUP, clean_label, normalize_field
from procureai.domain.requirements.units import parse_number, parse_quantity

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "rs.": "INR", "rs": "INR"}
_CURRENCY_CODES = {"USD", "EUR", "GBP", "INR", "AUD", "CAD", "SGD", "AED", "JPY", "CNY"}
_AMOUNT = re.compile(
    r"(?P<pre>USD|EUR|GBP|INR|AUD|CAD|SGD|AED|JPY|CNY|Rs\.?|[$€£₹])?\s*(?P<amt>\d[\d,]*(?:\.\d+)?)\s*(?P<post>USD|EUR|GBP|INR|AUD|CAD|SGD|AED|JPY|CNY)?",
    re.I,
)
_IGNORED_KEYS = {
    "date",
    "quotation date",
    "quote date",
    "valid until",
    "validity",
    "valid for",
    "quotation validity",
    "address",
    "phone",
    "tel",
    "telephone",
    "fax",
    "website",
    "web",
    "payment terms",
    "signature",
    "name",
    "designation",
    "prepared by",
    "signed by",
    "page",
    "gstin",
    "pan",
    "tax id",
    "registration no",
}
_KEYVAL = re.compile(r"^\s*(?:[-*•]\s*)?(?P<k>[A-Za-z][A-Za-z0-9 /&\.\-\(\)]{1,50}?)\s*[:|]\s*(?P<v>\S.*)$")


def _currency_of(text: str) -> str | None:
    m = _AMOUNT.search(text)
    if not m:
        return None
    tok = (m.group("pre") or m.group("post") or "").strip()
    if not tok:
        return None
    up = tok.upper()
    if up in _CURRENCY_CODES:
        return up
    return _CURRENCY_SYMBOLS.get(tok.lower()) or _CURRENCY_SYMBOLS.get(tok)


def _amount(text: str) -> float | None:
    m = _AMOUNT.search(text)
    return float(m.group("amt").replace(",", "")) if m else None


def extract_quotation(pages: list[tuple[int, str]], filename: str = "") -> ExtractedQuotation | None:
    quote = ExtractedQuotation(vendor_name="", vendor_name_confident=False)
    seen_fields: set[str] = set()
    for page_number, text in pages:
        for line in text.splitlines():
            m = _KEYVAL.match(line.strip().strip("|").strip()) if "|" not in line.strip("| ")[1:] else _pipe_pair(line)
            if not m:
                continue
            key, value = clean_label(m["k"]), m["v"].strip()
            if len(key.split()) > 6 or not value:
                continue
            canon = COMMERCIAL_LOOKUP.get(key.lower())
            if canon == "vendor":
                if not quote.vendor_name:
                    quote.vendor_name, quote.vendor_name_confident = value, True
                    quote.source_page = page_number
                continue
            if canon == "reference":
                quote.reference = quote.reference or value
                continue
            if canon == "contact":
                quote.contact = quote.contact or value
                continue
            if canon == "unit_price":
                quote.unit_price = quote.unit_price if quote.unit_price is not None else _amount(value)
                quote.currency = quote.currency or _currency_of(value)
                continue
            if canon == "quantity":
                quote.quantity = quote.quantity if quote.quantity is not None else parse_number(value)
                continue
            if canon == "currency":
                code = value.strip().upper()[:3]
                if code in _CURRENCY_CODES:
                    quote.currency = code
                continue
            if canon == "tax":
                quote.tax_percent = quote.tax_percent if quote.tax_percent is not None else parse_number(value)
                continue
            if canon == "delivery_cost":
                quote.delivery_cost = quote.delivery_cost if quote.delivery_cost is not None else _amount(value)
                quote.currency = quote.currency or _currency_of(value)
                continue
            if canon == "category":
                quote.category = quote.category or value
                continue

            if key.lower() in _IGNORED_KEYS:
                continue
            field = normalize_field(key)
            if field in seen_fields:
                prior = next((sp for sp in quote.specs if sp.field == field), None)
                if prior and prior.value_text.strip().lower() != value.strip().lower():
                    quote.notes.append(
                        f"Conflicting values for '{key}': '{prior.value_text}' (page {prior.page}) vs "
                        f"'{value}' (page {page_number}). The first was kept; please verify."
                    )
                continue
            seen_fields.add(field)
            qty = parse_quantity(value)
            numeric = qty.value if qty else None
            unit = qty.unit if qty else None
            confidence = 0.95 if qty and qty.unit else (0.85 if qty else 0.8)
            if field == "warranty" and qty and qty.dimension == "duration_months":
                quote.warranty_months = qty.value
            if field == "delivery_time" and qty and qty.dimension in ("duration_days",):
                quote.delivery_days = qty.value
            quote.specs.append(ExtractedSpec(field, key, value, numeric, unit, page_number, line.strip(), confidence))

    if not quote.vendor_name:
        quote.vendor_name = Path(filename).stem.replace("_", " ").replace("-", " ").strip().title() or "Unknown vendor"
        quote.notes.append("Vendor name not found in text; derived from filename. Please confirm.")
    if not quote.specs and quote.unit_price is None:
        return None
    return quote


def _pipe_pair(line: str) -> dict[str, str] | None:
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    if len(parts) >= 2 and parts[0] and parts[1] and parts[0].lower() not in {"field", "parameter", "specification"}:
        value = parts[1] if len(parts) == 2 else " ".join(p for p in parts[1:] if p)
        return {"k": parts[0], "v": value}
    return None
