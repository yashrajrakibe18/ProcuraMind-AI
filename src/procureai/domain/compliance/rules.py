"""Deterministic compliance rules. No I/O, no LLM: pure functions over normalized values."""

from __future__ import annotations

from dataclasses import dataclass, field

from procureai.domain.requirements.units import canonical_unit, convert, parse_number
from procureai.shared.enums import ComplianceStatus, Operator

LOW_CONFIDENCE = 0.6


@dataclass(frozen=True)
class RequirementSpec:
    field: str
    operator: Operator
    value: str
    unit: str | None = None
    value_max: str | None = None
    label: str = ""


@dataclass(frozen=True)
class OfferedValue:
    value_text: str
    value_numeric: float | None = None
    unit: str | None = None
    confidence: float = 0.9


@dataclass
class ComplianceOutcome:
    status: ComplianceStatus
    explanation: str
    review_required: bool = False
    method: str = "deterministic"
    detail: dict = field(default_factory=dict)


def _norm_text(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").split())


def _numeric_compare(op: Operator, offered: float, required: float, required_max: float | None) -> bool:
    if op == Operator.GTE:
        return offered >= required
    if op == Operator.LTE:
        return offered <= required
    if op == Operator.GT:
        return offered > required
    if op == Operator.LT:
        return offered < required
    if op == Operator.EQ:
        return abs(offered - required) < 1e-9
    if op == Operator.BETWEEN and required_max is not None:
        return required <= offered <= required_max
    raise ValueError(f"Unsupported numeric operator: {op}")


def evaluate_requirement(req: RequirementSpec, offered: OfferedValue | None) -> ComplianceOutcome:
    """Evaluate one requirement against one vendor value."""
    if offered is None:
        return ComplianceOutcome(
            ComplianceStatus.MISSING,
            f"No value for '{req.label or req.field}' was found in the vendor quotation.",
            review_required=True,
        )
    if offered.confidence < LOW_CONFIDENCE:
        return ComplianceOutcome(
            ComplianceStatus.REVIEW,
            f"Extraction confidence ({offered.confidence:.0%}) is too low to decide automatically.",
            review_required=True,
        )

    req_is_numeric_op = req.operator in (Operator.GTE, Operator.LTE, Operator.GT, Operator.LT, Operator.BETWEEN) or (
        req.operator == Operator.EQ and parse_number(req.value) is not None and _looks_numeric(req.value)
    )

    if not req_is_numeric_op:
        return _categorical(req, offered)

    required = parse_number(req.value)
    required_max = parse_number(req.value_max) if req.value_max else None
    if required is None or offered.value_numeric is None:
        return ComplianceOutcome(
            ComplianceStatus.REVIEW,
            f"Offered value '{offered.value_text}' is not numeric; cannot compare with "
            f"'{req.operator.value} {req.value}'. A person must interpret it.",
            review_required=True,
        )

    off_value = offered.value_numeric
    off_unit, req_unit = offered.unit, req.unit
    if req_unit and not off_unit:
        return ComplianceOutcome(
            ComplianceStatus.REVIEW,
            f"Offered value {offered.value_text} has no unit but the requirement is in {req_unit}.",
            review_required=True,
        )
    if req_unit and off_unit:
        converted = convert(off_value, off_unit, req_unit)
        if converted is None:
            return ComplianceOutcome(
                ComplianceStatus.REVIEW,
                f"Units are not comparable: offered '{off_unit}' vs required '{req_unit}'.",
                review_required=True,
            )
        off_value = converted

    ok = _numeric_compare(req.operator, off_value, required, required_max)
    unit_txt = f" {canonical_unit(req_unit)[0] or req_unit}" if req_unit else ""
    bound = f"{required:g}" + (f"–{required_max:g}" if required_max is not None else "")
    detail = {"offered_normalized": off_value, "required": required, "required_max": required_max}
    if ok:
        return ComplianceOutcome(
            ComplianceStatus.MEETS,
            f"Offered {off_value:g}{unit_txt} satisfies {req.operator.value} {bound}{unit_txt}.",
            detail=detail,
        )
    return ComplianceOutcome(
        ComplianceStatus.FAILS,
        f"Offered {off_value:g}{unit_txt} does not satisfy {req.operator.value} {bound}{unit_txt}.",
        detail=detail,
    )


def _looks_numeric(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and (stripped[0].isdigit() or stripped[0] in "+-")


def _categorical(req: RequirementSpec, offered: OfferedValue) -> ComplianceOutcome:
    required_tokens = [t.strip() for t in req.value.replace(" or ", ",").replace("/", ",").split(",") if t.strip()]
    offered_norm = _norm_text(offered.value_text)
    if not required_tokens:
        return ComplianceOutcome(ComplianceStatus.REVIEW, "Requirement value is empty.", review_required=True)

    if req.operator == Operator.CONTAINS:
        hit = all(_norm_text(t) in offered_norm for t in required_tokens)
    else:
        hit = any(_norm_text(t) == offered_norm or _norm_text(t) in offered_norm for t in required_tokens)

    if hit:
        return ComplianceOutcome(
            ComplianceStatus.MEETS, f"Offered '{offered.value_text}' matches required '{req.value}'."
        )
    # A text mismatch may be a synonym or wording difference: do not assert failure automatically.
    return ComplianceOutcome(
        ComplianceStatus.REVIEW,
        f"Offered '{offered.value_text}' does not literally match required '{req.value}'. "
        "It may be a wording difference; a person should confirm.",
        review_required=True,
    )
