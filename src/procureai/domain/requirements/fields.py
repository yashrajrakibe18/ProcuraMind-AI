"""Field-name normalization so tender requirements and vendor specs line up."""

from __future__ import annotations

import re

_ALIASES: dict[str, set[str]] = {
    "ram": {"ram", "memory", "system memory", "ram size", "installed memory", "main memory"},
    "processor_cores": {"processor cores", "cpu cores", "cores", "core count", "number of cores"},
    "processor_speed": {"processor speed", "cpu speed", "clock speed", "base clock", "cpu frequency"},
    "storage": {"storage", "storage capacity", "ssd", "ssd capacity", "disk", "disk capacity", "hard disk"},
    "display_size": {"display size", "screen size", "display", "screen"},
    "weight": {"weight", "device weight"},
    "battery_life": {"battery life", "battery backup", "battery"},
    "power_consumption": {"power consumption", "power rating", "power"},
    "operating_system": {"operating system", "os", "preinstalled os"},
    "warranty": {"warranty", "warranty period", "warranty term", "standard warranty"},
    "delivery_time": {"delivery time", "delivery", "delivery period", "lead time", "delivery lead time"},
    "ports": {"usb ports", "ports", "number of ports"},
    "certifications": {"certifications", "certification", "compliance certifications", "standards"},
}
_LOOKUP = {alias: canon for canon, aliases in _ALIASES.items() for alias in aliases}

_COMMERCIAL = {
    "vendor": {"vendor", "vendor name", "supplier", "supplier name", "bidder", "company", "quoted by"},
    "reference": {
        "quotation reference",
        "quote reference",
        "quotation no",
        "quotation number",
        "reference",
        "ref",
        "quote no",
        "offer reference",
    },
    "unit_price": {"unit price", "price per unit", "rate per unit", "price", "unit rate"},
    "quantity": {"quantity", "qty", "units offered", "order quantity"},
    "currency": {"currency"},
    "tax": {"tax", "gst", "vat", "sales tax", "tax rate", "tax percent"},
    "delivery_cost": {"delivery charges", "delivery cost", "shipping", "shipping cost", "freight", "freight charges"},
    "category": {"item category", "category", "item", "product", "product category"},
    "contact": {"contact", "contact email", "email"},
}
COMMERCIAL_LOOKUP = {alias: canon for canon, aliases in _COMMERCIAL.items() for alias in aliases}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def clean_label(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^\W+|\W+$", "", text)).strip()


def normalize_field(label: str) -> str:
    """Map a human label ('Minimum RAM', 'System Memory') to a canonical field key."""
    key = clean_label(label).lower()
    key = re.sub(r"^(minimum|min\.?|maximum|max\.?)\s+", "", key)
    key = re.sub(r"\s*\(.*?\)\s*", " ", key).strip()
    if key in _LOOKUP:
        return _LOOKUP[key]
    return slug(key)
