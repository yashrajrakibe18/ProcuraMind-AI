"""Quantity parsing and unit normalization (deterministic, no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# unit alias -> (dimension, factor to canonical unit)
_UNITS: dict[str, tuple[str, float]] = {}
_DIM_CANON: dict[str, str] = {}


def _reg(dimension: str, canonical: str, aliases: dict[str, float]) -> None:
    _DIM_CANON[dimension] = canonical
    _UNITS[canonical] = (dimension, 1.0)
    for alias, factor in aliases.items():
        _UNITS[alias] = (dimension, factor)


_reg("storage", "gb", {"b": 1 / 1e9, "kb": 1e-6, "mb": 1e-3, "gb": 1.0, "tb": 1e3, "gib": 1.0737, "tib": 1099.5})
_reg("duration_months", "months", {"month": 1, "months": 1, "mo": 1, "year": 12, "years": 12, "yr": 12, "yrs": 12})
_reg("duration_days", "days", {"day": 1, "days": 1, "week": 7, "weeks": 7, "wk": 7, "wks": 7})
_reg("frequency", "ghz", {"mhz": 1e-3, "ghz": 1.0})
_reg("power", "w", {"w": 1.0, "watt": 1.0, "watts": 1.0, "kw": 1e3})
_reg("mass", "kg", {"g": 1e-3, "kg": 1.0, "kgs": 1.0, "lb": 0.45359, "lbs": 0.45359})
_reg("length", "inch", {"inch": 1.0, "inches": 1.0, "in": 1.0, '"': 1.0, "cm": 0.3937, "mm": 0.03937})
_reg("percent", "%", {"%": 1.0, "percent": 1.0})
_reg(
    "count",
    "units",
    {
        "unit": 1,
        "units": 1,
        "pcs": 1,
        "pc": 1,
        "nos": 1,
        "no": 1,
        "cores": 1,
        "core": 1,
        "ports": 1,
        "port": 1,
        "pieces": 1,
        "piece": 1,
        "licenses": 1,
        "licences": 1,
    },
)
_reg("duration_hours", "hours", {"hour": 1, "hours": 1, "hr": 1, "hrs": 1, "h": 1})

_NUMBER = r"[-+]?\d[\d,]*(?:\.\d+)?"
_QTY_RE = re.compile(rf"^\s*(?P<num>{_NUMBER})[\s-]*(?P<unit>[A-Za-z%\"]+)?(?P<tail>.*)$")


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str | None  # canonical unit or None
    dimension: str | None
    raw_unit: str | None = None


def parse_number(text: str) -> float | None:
    m = re.search(_NUMBER, text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def canonical_unit(unit: str | None) -> tuple[str | None, str | None, float]:
    """Return (canonical_unit, dimension, factor). Unknown units return (raw, None, 1.0)."""
    if not unit:
        return None, None, 1.0
    key = unit.strip().lower().rstrip(".")
    if key in _UNITS:
        dim, factor = _UNITS[key]
        return _DIM_CANON[dim], dim, factor
    return key, None, 1.0


def parse_quantity(text: str) -> Quantity | None:
    """Parse '16 GB', '3 years', '1,200', '36 months' into a canonical-unit Quantity."""
    if text is None:
        return None
    m = _QTY_RE.match(text.strip())
    if not m:
        return None
    value = float(m.group("num").replace(",", ""))
    raw_unit = m.group("unit")
    canon, dim, factor = canonical_unit(raw_unit)
    tail = m.group("tail").strip(" .;,")
    # Free text after an unrecognised unit (e.g. '8th gen CPU') is not a quantity.
    if tail and raw_unit and dim is None:
        return None
    if tail and not raw_unit and not tail.startswith("("):
        return None
    return Quantity(value * factor if dim else value, canon, dim, raw_unit)


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Convert between units of the same dimension. None if incompatible."""
    _, d1, f1 = canonical_unit(from_unit)
    _, d2, f2 = canonical_unit(to_unit)
    if d1 and d2 and d1 == d2:
        return value * f1 / f2
    if not from_unit and not to_unit:
        return value
    return None


def dimension_of(unit: str | None) -> str | None:
    return canonical_unit(unit)[1]
