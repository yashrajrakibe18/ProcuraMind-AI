"""Rule-based extraction of tender requirements with source page provenance.

Recognised forms (one requirement per line):
  * ``REQ-01 | RAM | >= | 16 | GB | Mandatory``      (pipe/table rows)
  * ``Minimum RAM: 16 GB (mandatory)``
  * ``Warranty: at least 3 years``
  * ``Display size: 14 to 15.6 inches``
  * ``Operating system: Windows 11 Pro``             (only inside a requirements section)
Anything not matching is ignored, never guessed. Users confirm results in the review step.
"""

from __future__ import annotations

import re

from procureai.document_processing.extraction.models import ExtractedRequirement
from procureai.domain.requirements.fields import clean_label, normalize_field
from procureai.domain.requirements.units import canonical_unit
from procureai.shared.enums import Criticality, Operator

_OP_PHRASES: list[tuple[Operator, list[str]]] = [
    (
        Operator.GTE,
        [
            ">=",
            "≥",
            "at least",
            "minimum of",
            "minimum",
            "min.",
            "min",
            "not less than",
            "no less than",
            "greater than or equal to",
        ],
    ),
    (
        Operator.LTE,
        [
            "<=",
            "≤",
            "at most",
            "maximum of",
            "maximum",
            "max.",
            "max",
            "not more than",
            "no more than",
            "not exceeding",
            "up to",
            "within",
            "no later than",
            "not later than",
        ],
    ),
    (Operator.GT, ["more than", "greater than", ">"]),
    (Operator.LT, ["less than", "below", "<"]),
    (Operator.EQ, ["==", "exactly", "equal to", "="]),
]
_PHRASE_LOOKUP: list[tuple[str, Operator]] = sorted(
    ((p, op) for op, ps in _OP_PHRASES for p in ps), key=lambda t: -len(t[0])
)
_SYMBOLS = {">=", "≥", "<=", "≤", ">", "<", "==", "="}
_MANDATORY = re.compile(r"\b(mandatory|required|must|essential)\b", re.I)
_DESIRABLE = re.compile(r"\b(desirable|optional|preferred|nice to have|good to have)\b", re.I)
_TAG = re.compile(r"\s*[\(\[]\s*(mandatory|required|must|essential|desirable|optional|preferred)\s*[\)\]]\s*", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[\.\)]|(?:REQ|R|TR)[-_ ]?\d+[\.:)]?)\s*", re.I)
_NUM = r"\d[\d,]*(?:\.\d+)?"
_BETWEEN = re.compile(
    rf"^(?P<a>{_NUM})\s*(?P<u1>[A-Za-z%\"]+)?\s*(?:to|-|–|and)\s*(?P<b>{_NUM})\s*(?P<u2>[A-Za-z%\"]+)?\b", re.I
)
_VALUE = re.compile(rf"^(?P<num>{_NUM})\s*(?P<unit>[A-Za-z%\"]+)?(?P<rest>.*)$")
_SECTION_HEAD = re.compile(r"(technical )?(requirements?|specifications?)|bill of quantit", re.I)
_EXCLUDED_FIELDS = {
    "tender",
    "tender no",
    "tender number",
    "tender title",
    "title",
    "date",
    "closing date",
    "issue date",
    "issued by",
    "submission deadline",
    "deadline",
    "contact",
    "email",
    "phone",
    "location",
    "delivery location",
    "reference",
    "ref",
    "project",
    "department",
    "subject",
    "page",
    "version",
    "note",
    "notes",
    "validity",
}


def _heading_like(line: str) -> bool:
    s = line.strip()
    return bool(s) and ":" not in s and len(s.split()) <= 8 and not any(sym in s for sym in ("|", ">", "<", "="))


def _split_operator(text: str) -> tuple[Operator | None, str]:
    low = text.lower().lstrip()
    for phrase, op in _PHRASE_LOOKUP:
        if phrase in _SYMBOLS or not phrase[0].isalpha():
            if low.startswith(phrase):
                return op, low and text.lstrip()[len(phrase) :].lstrip(" :")
        elif re.match(rf"{re.escape(phrase)}\b", low):
            return op, text.lstrip()[len(phrase) :].lstrip(" :")
    return None, text


def _criticality(text: str) -> tuple[Criticality, str]:
    m = _TAG.search(text)
    crit = Criticality.MANDATORY
    if m:
        tag = m.group(1).lower()
        crit = Criticality.DESIRABLE if _DESIRABLE.fullmatch(tag) else Criticality.MANDATORY
        text = _TAG.sub(" ", text).strip()
    elif _DESIRABLE.search(text):
        crit = Criticality.DESIRABLE
    return crit, text


def _parse_value(value_text: str, op: Operator | None) -> tuple[Operator, str, str | None, str | None] | None:
    """Return (operator, value, value_max, unit)."""
    value_text = value_text.strip().rstrip(".;,")
    if not value_text:
        return None
    between = _BETWEEN.match(value_text)
    if between and (op is None or op == Operator.BETWEEN):
        unit = between.group("u2") or between.group("u1")
        return Operator.BETWEEN, between.group("a").replace(",", ""), between.group("b").replace(",", ""), unit
    m = _VALUE.match(value_text)
    if m and (not m.group("rest").strip() or m.group("rest").strip().startswith(("(", "per", "or"))):
        unit = m.group("unit")
        canon, dim, _ = canonical_unit(unit)
        return (op or Operator.GTE), m.group("num").replace(",", ""), None, unit if (dim or unit) else None
    if m is None:
        return (op or Operator.EQ), value_text, None, None  # categorical text
    return (op or Operator.EQ), value_text, None, None  # numeric prefix but free text (e.g. '8th gen CPU')


def parse_requirement_line(line: str, page: int, in_section: bool) -> ExtractedRequirement | None:
    raw = line.strip()
    if not raw or len(raw) > 240:
        return None
    body = _BULLET.sub("", raw, count=1).strip()
    criticality, body = _criticality(body)

    # Pipe / table row
    if "|" in body:
        parts = [p.strip() for p in body.strip("|").split("|")]
        if parts and re.fullmatch(r"(?i)(req|r|tr)?[-_ ]?\d+", parts[0]):
            parts = parts[1:]
        if len(parts) >= 3:
            field_label, op_txt, value = parts[0], parts[1], parts[2]
            op, _ = _split_operator(op_txt)
            if op is None and op_txt.lower() == "between":
                op = Operator.BETWEEN
            if op is None or not value or field_label.lower() in {"field", "requirement", "parameter", "specification"}:
                return None
            unit = (
                parts[3]
                if len(parts) > 3 and parts[3] and not _MANDATORY.search(parts[3]) and not _DESIRABLE.search(parts[3])
                else None
            )
            tail = " ".join(parts[3:]) if len(parts) > 3 else ""
            crit = Criticality.DESIRABLE if _DESIRABLE.search(tail) else criticality
            value_max = None
            if op == Operator.BETWEEN:
                bm = _BETWEEN.match(value)
                if not bm:
                    return None
                value, value_max = bm.group("a"), bm.group("b")
            return ExtractedRequirement(
                normalize_field(field_label),
                clean_label(field_label),
                op,
                value.replace(",", ""),
                unit,
                crit,
                page,
                raw,
                value_max,
            )
        return None

    explicit = False
    op: Operator | None = None
    if ":" in body:
        left, right = (s.strip() for s in body.split(":", 1))
    else:
        m = re.match(r"^(?P<f>[A-Za-z][A-Za-z /\-\.]{1,40}?)\s*(?P<op>>=|<=|≥|≤|==|=|>|<)\s*(?P<v>.+)$", body)
        if not m:
            return None
        left, right = m.group("f"), m.group("op") + " " + m.group("v")
        explicit = True

    prefix = re.match(r"^(minimum|min\.?|maximum|max\.?)\s+(.*)$", left, re.I)
    if prefix:
        op = Operator.GTE if prefix.group(1).lower().startswith("min") else Operator.LTE
        left = prefix.group(2)
        explicit = True
    right_op, right_rest = _split_operator(right)
    if right_op is not None:
        op, right, explicit = right_op, right_rest, True
    if not left or len(left.split()) > 6 or not re.search(r"[A-Za-z]", left):
        return None
    if clean_label(left).lower() in _EXCLUDED_FIELDS:
        return None
    if not (explicit or in_section or _MANDATORY.search(raw) or _DESIRABLE.search(raw)):
        return None
    parsed = _parse_value(right, op)
    if parsed is None:
        return None
    operator, value, value_max, unit = parsed
    return ExtractedRequirement(
        normalize_field(left), clean_label(left), operator, value, unit, criticality, page, raw, value_max
    )


def extract_requirements(pages: list[tuple[int, str]]) -> list[ExtractedRequirement]:
    """``pages`` = [(page_number, text)]. Returns de-duplicated requirements in document order."""
    results: list[ExtractedRequirement] = []
    seen: set[tuple[str, str, str]] = set()
    in_section = False
    for page_number, text in pages:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped == "[TABLE]":
                continue
            if _heading_like(stripped):
                if _SECTION_HEAD.search(stripped):
                    in_section = True
                elif len(stripped.split()) <= 6 and (
                    stripped.isupper() or stripped.istitle() or _BULLET.match(stripped)
                ):
                    in_section = False
                continue
            req = parse_requirement_line(stripped, page_number, in_section)
            if req is None:
                continue
            key = (req.field, req.operator.value, req.value)
            if key in seen:
                continue
            seen.add(key)
            results.append(req)
    return results
