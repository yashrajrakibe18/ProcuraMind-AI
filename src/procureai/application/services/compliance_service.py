"""Technical/commercial compliance: deterministic rules; the LLM may only add an advisory note to ambiguous cases."""

from __future__ import annotations

import difflib
import json
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.agents.prompts.templates import INTERPRET_SYSTEM, interpret_user_prompt
from procureai.domain.compliance.rules import (
    ComplianceOutcome,
    OfferedValue,
    RequirementSpec,
    evaluate_requirement,
)
from procureai.infrastructure.database.models import (
    ComplianceResult,
    TenderRequirement,
    Vendor,
    VendorQuotation,
    VendorSpecification,
)
from procureai.infrastructure.llm.client import LLMClient
from procureai.shared.enums import ComplianceStatus, Operator
from procureai.shared.errors import ExternalServiceError

logger = logging.getLogger(__name__)
COMMERCIAL_FIELDS = {"delivery_time", "warranty"}
FUZZY_CUTOFF = 0.86


def find_spec(requirement_field: str, specs: list[VendorSpecification]) -> tuple[VendorSpecification | None, bool]:
    """Exact canonical match first; then a strict fuzzy match. Returns (spec, was_fuzzy)."""
    for s in specs:
        if s.field == requirement_field:
            return s, False
    best, score = None, 0.0
    for s in specs:
        ratio = difflib.SequenceMatcher(None, s.field, requirement_field).ratio()
        if ratio > score:
            best, score = s, ratio
    return (best, True) if best is not None and score >= FUZZY_CUTOFF else (None, False)


def latest_quotation(vendor: Vendor) -> VendorQuotation | None:
    return max(vendor.quotations, key=lambda q: q.created_at, default=None)


def _interpret(llm: LLMClient, req: TenderRequirement, spec: VendorSpecification) -> dict | None:
    """Advisory only. Output must be valid JSON and its quote must really occur in the vendor text."""
    if not llm.available():
        return None
    try:
        raw = llm.complete(
            INTERPRET_SYSTEM,
            interpret_user_prompt(
                f"{req.label} {req.operator} {req.required_value} {req.unit or ''}".strip(),
                spec.source_text or spec.value_text,
            ),
        )
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        verdict = data.get("verdict")
        if verdict not in {"likely_meets", "likely_does_not_meet", "uncertain"}:
            return None
        quote = str(data.get("evidence_quote", ""))
        if quote and quote.lower() not in (spec.source_text or spec.value_text).lower():
            return None  # hallucinated evidence: discard
        return {"verdict": verdict, "rationale": str(data.get("rationale", ""))[:300], "evidence_quote": quote}
    except (ExternalServiceError, ValueError, KeyError):
        logger.warning("LLM interpretation unavailable or invalid; leaving case for human review")
        return None


def run_compliance(session: Session, run_id: str, project_id: str, llm: LLMClient) -> dict:
    requirements = list(
        session.scalars(
            select(TenderRequirement)
            .where(TenderRequirement.project_id == project_id, TenderRequirement.confirmed.is_(True))
            .order_by(TenderRequirement.created_at, TenderRequirement.id)
        )
    )
    vendors = list(session.scalars(select(Vendor).where(Vendor.project_id == project_id).order_by(Vendor.created_at)))
    session.execute(delete(ComplianceResult).where(ComplianceResult.run_id == run_id))
    counts = {s.value: 0 for s in ComplianceStatus}
    for vendor in vendors:
        quote = latest_quotation(vendor)
        specs = list(quote.specifications) if quote else []
        for req in requirements:
            spec, fuzzy = find_spec(req.field, specs)
            offered = None
            if spec is not None:
                offered = OfferedValue(
                    spec.value_text,
                    spec.value_numeric,
                    spec.unit,
                    min(spec.confidence, 0.8) if fuzzy else spec.confidence,
                )
            outcome: ComplianceOutcome = evaluate_requirement(
                RequirementSpec(
                    req.field, Operator(req.operator), req.required_value, req.unit, req.required_value_max, req.label
                ),
                offered,
            )
            method, advisory = outcome.method, None
            if outcome.status == ComplianceStatus.REVIEW and spec is not None:
                advisory = _interpret(llm, req, spec)
                if advisory:
                    method = "deterministic+llm_advisory"
            explanation = outcome.explanation + (" Matched by similar field name." if fuzzy and spec else "")
            if advisory:
                explanation += (
                    f" Model interpretation (advisory, unverified): {advisory['verdict'].replace('_', ' ')}"
                    f" - {advisory['rationale']}"
                )
            session.add(
                ComplianceResult(
                    run_id=run_id,
                    project_id=project_id,
                    vendor_id=vendor.id,
                    requirement_id=req.id,
                    status=outcome.status.value,
                    method=method,
                    explanation=explanation,
                    evidence={
                        "category": "commercial" if req.field in COMMERCIAL_FIELDS else "technical",
                        "offered": {
                            "label": spec.label,
                            "value": spec.value_text,
                            "unit": spec.unit,
                            "document_id": quote.document_id if quote else None,
                            "page": spec.source_page,
                            "text": spec.source_text,
                        }
                        if spec
                        else None,
                        "required": {
                            "document_id": req.source_document_id,
                            "page": req.source_page,
                            "text": req.source_text,
                        },
                        "model_interpretation": advisory,
                        "outcome_detail": outcome.detail,
                    },
                    review_required=outcome.review_required,
                    verified_unconfirmed_input=bool(quote and not quote.confirmed),
                )
            )
            counts[outcome.status.value] += 1
    session.flush()
    return {"vendors": len(vendors), "requirements": len(requirements), "counts": counts}
