"""Worker nodes. Each has one narrow responsibility and calls application services; none touch the UI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.agents.state import WorkflowState
from procureai.agents.tools.step_runner import RunContext, StepOutcome, run_step
from procureai.agents.validators.inputs import validate_inputs
from procureai.application.services import (
    compliance_service,
    evidence_service,
    extraction_service,
    price_service,
    verification_service,
)
from procureai.infrastructure.database.models import TenderRequirement, Vendor
from procureai.shared.errors import ValidationAppError

Node = Callable[[WorkflowState], dict[str, Any]]


def _result(outcome: StepOutcome, flag: str) -> dict[str, Any]:
    if outcome.ok:
        return {flag: True, "metrics": {flag: outcome.metadata}}
    return {"errors": [outcome.error or "unknown failure"], flag: False}


def make_nodes(ctx: RunContext) -> dict[str, Node]:
    def validate_documents(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            return validate_inputs(s, ctx.project_id, state.get("auto_confirm", False))

        return _result(run_step(ctx, "validate_documents", fn), "documents_valid")

    def document_intelligence(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            if state.get("auto_confirm"):
                extraction_service.confirm_all_requirements(s, ctx.project_id, ctx.actor_id)
            have = (
                s.scalar(
                    select(func.count())
                    .select_from(TenderRequirement)
                    .where(TenderRequirement.project_id == ctx.project_id)
                )
                or 0
            )
            if have == 0:
                rep = extraction_service.extract_project_requirements(s, ctx.project_id, ctx.actor_id)
                if state.get("auto_confirm"):
                    extraction_service.confirm_all_requirements(s, ctx.project_id, ctx.actor_id)
                have = rep.created
            confirmed = (
                s.scalar(
                    select(func.count())
                    .select_from(TenderRequirement)
                    .where(TenderRequirement.project_id == ctx.project_id, TenderRequirement.confirmed.is_(True))
                )
                or 0
            )
            if confirmed == 0:
                raise ValidationAppError("No confirmed tender requirements are available to evaluate against.")
            return {"requirements": have, "confirmed_requirements": confirmed}

        return _result(run_step(ctx, "document_intelligence", fn), "extraction_done")

    def vendor_analysis(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            # Idempotent per document: quotations that were already extracted are skipped.
            created = extraction_service.extract_project_vendors(s, ctx.project_id, ctx.actor_id).created
            if state.get("auto_confirm"):
                extraction_service.confirm_all_quotations(s, ctx.project_id)
            total = s.scalar(select(func.count()).select_from(Vendor).where(Vendor.project_id == ctx.project_id)) or 0
            if total == 0:
                raise ValidationAppError("No vendor quotations could be extracted from the uploaded documents.")
            return {"vendors": total, "newly_extracted": created}

        return _result(run_step(ctx, "vendor_analysis", fn), "vendors_done")

    def technical_compliance(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            return compliance_service.run_compliance(s, ctx.run_id, ctx.project_id, ctx.app.llm)

        return _result(run_step(ctx, "technical_compliance", fn), "compliance_done")

    def price_intelligence(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            return price_service.run_price_analysis(s, ctx.run_id, ctx.project_id, ctx.app.settings)

        return _result(run_step(ctx, "price_intelligence", fn), "price_done")

    def procurement_rag(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            return evidence_service.collect_policy_evidence(s, ctx.run_id, ctx.project_id, ctx.app.retriever)

        outcome = run_step(ctx, "procurement_rag", fn)
        if outcome.ok:
            return _result(outcome, "evidence_done")
        # Retrieval failure is non-fatal: the analysis still stands, but the gap is visible to the reviewer.
        return {"evidence_done": True, "notes": [f"Policy evidence unavailable: {outcome.error}"]}

    def verification(state: WorkflowState) -> dict[str, Any]:
        def fn(s: Session) -> dict:
            return verification_service.verify_run(s, ctx.run_id, ctx.project_id)

        return _result(run_step(ctx, "verification", fn), "verified")

    return {
        "validate_documents": validate_documents,
        "document_intelligence": document_intelligence,
        "vendor_analysis": vendor_analysis,
        "technical_compliance": technical_compliance,
        "price_intelligence": price_intelligence,
        "procurement_rag": procurement_rag,
        "verification": verification,
    }
