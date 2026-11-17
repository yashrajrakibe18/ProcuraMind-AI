"""Analysis runs: start (idempotent), execute the LangGraph workflow, human review and results."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from procureai.agents.graphs.workflow import MAX_HOPS, WORKFLOW_VERSION, build_workflow
from procureai.agents.state import WorkflowState
from procureai.agents.tools.step_runner import RunContext
from procureai.application.context import AppContext
from procureai.application.dto.schemas import ComplianceResultOut, PriceAnalysisOut, ReviewResolve
from procureai.application.services.access import get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.config.logging import project_id_var, run_id_var
from procureai.infrastructure.database.models import (
    AgentRun,
    ComplianceResult,
    PolicyEvidence,
    PriceAnalysis,
    ProcurementProject,
    ReviewItem,
    TenderRequirement,
    User,
    Vendor,
    VendorQuotation,
)
from procureai.shared.enums import ComplianceStatus, ProjectStatus, RunStatus
from procureai.shared.errors import ConflictError, NotFoundError, ValidationAppError
from procureai.shared.types import utcnow

logger = logging.getLogger(__name__)
ACTIVE = (RunStatus.QUEUED.value, RunStatus.RUNNING.value)
FINISHED = (RunStatus.COMPLETED.value, RunStatus.AWAITING_REVIEW.value)
DECISION_STATUS = {
    "meets": ComplianceStatus.MEETS,
    "fails": ComplianceStatus.FAILS,
    "not_applicable": ComplianceStatus.NOT_APPLICABLE,
}


def start_run(
    session: Session, ctx: AppContext, user: User, project_id: str, auto_confirm: bool
) -> tuple[AgentRun, bool]:
    """Create a run, or return the active one (idempotent). Returns (run, created)."""
    get_project_for_user(session, user, project_id, write=True)
    active = session.scalar(
        select(AgentRun)
        .where(AgentRun.project_id == project_id, AgentRun.status.in_(ACTIVE))
        .order_by(AgentRun.created_at.desc())
    )
    if active:
        return active, False
    s = ctx.settings
    run = AgentRun(
        project_id=project_id,
        created_by=user.id,
        status=RunStatus.QUEUED.value,
        workflow_version=WORKFLOW_VERSION,
        summary={"auto_confirm": auto_confirm},
        model_info={
            "llm_provider": ctx.llm.name,
            "llm_model": ctx.llm.model or None,
            "embedding_model": ctx.embedder.name,
            "llm_role": "advisory interpretation of ambiguous specs and assistant answers only"
            if ctx.llm.available()
            else "not used (deterministic mode)",
            "fx_table": "static configured rates",
            "base_currency": s.base_currency,
        },
    )
    session.add(run)
    session.flush()
    record_audit(
        session,
        actor_id=user.id,
        action="analysis.started",
        resource_type="analysis_run",
        resource_id=run.id,
        project_id=project_id,
        metadata={"auto_confirm": auto_confirm},
    )
    session.commit()
    return run, True


def execute_run(ctx: AppContext, session_factory: sessionmaker[Session], run_id: str) -> None:
    """Runs the workflow to completion. Never raises: failures are recorded on the run."""
    with session_factory() as s:
        run = s.get(AgentRun, run_id)
        if run is None or run.status != RunStatus.QUEUED.value:
            return
        run.status, run.started_at = RunStatus.RUNNING.value, utcnow()
        project_id, auto_confirm, actor = run.project_id, bool(run.summary.get("auto_confirm")), run.created_by
        s.commit()
    run_id_var.set(run_id)
    project_id_var.set(project_id)
    rc = RunContext(ctx, session_factory, run_id, project_id, actor)

    def finalize(state: WorkflowState) -> dict[str, Any]:
        with session_factory() as fs:
            run = fs.get(AgentRun, run_id)
            errors = state.get("errors") or []
            open_items = (
                fs.scalar(
                    select(func.count())
                    .select_from(ReviewItem)
                    .where(ReviewItem.run_id == run_id, ReviewItem.status == "open")
                )
                or 0
            )
            summary = dict(run.summary)
            summary.update(
                {"metrics": state.get("metrics", {}), "notes": state.get("notes", []), "open_review_items": open_items}
            )
            run.summary, run.finished_at = summary, utcnow()
            project = fs.get(ProcurementProject, project_id)
            if errors:
                run.status, run.error = RunStatus.FAILED.value, "; ".join(errors)[:2000]
            elif open_items:
                run.status = RunStatus.AWAITING_REVIEW.value
                if project:
                    project.status = ProjectStatus.IN_REVIEW.value
            else:
                run.status = RunStatus.COMPLETED.value
                if project:
                    project.status = ProjectStatus.ANALYZED.value
            record_audit(
                fs,
                actor_id=actor,
                action=f"analysis.{run.status}",
                resource_type="analysis_run",
                resource_id=run_id,
                project_id=project_id,
                metadata={"errors": len(errors)},
            )
            fs.commit()
        return {}

    try:
        graph = build_workflow(rc, finalize)
        graph.invoke(
            {
                "run_id": run_id,
                "project_id": project_id,
                "auto_confirm": auto_confirm,
                "errors": [],
                "notes": [],
                "metrics": {},
                "next_hops": 0,
            },
            {"recursion_limit": MAX_HOPS * 3 + 6},
        )
    except Exception:  # boundary: last-resort handler so a run never stays 'running' forever
        logger.exception("Workflow crashed")
        with session_factory() as s:
            run = s.get(AgentRun, run_id)
            if run and run.status in ACTIVE:
                run.status, run.finished_at = RunStatus.FAILED.value, utcnow()
                run.error = "The workflow stopped unexpectedly. See server logs for this run id."
                s.commit()


def get_run(session: Session, user: User, run_id: str) -> AgentRun:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError("Analysis run not found.")
    get_project_for_user(session, user, run.project_id)
    return run


def list_runs(session: Session, user: User, project_id: str) -> list[AgentRun]:
    get_project_for_user(session, user, project_id)
    return list(
        session.scalars(select(AgentRun).where(AgentRun.project_id == project_id).order_by(AgentRun.created_at.desc()))
    )


def latest_result_run(session: Session, project_id: str, run_id: str | None = None) -> AgentRun | None:
    if run_id:
        run = session.get(AgentRun, run_id)
        return run if run and run.project_id == project_id else None
    return session.scalar(
        select(AgentRun)
        .where(AgentRun.project_id == project_id, AgentRun.status.in_(FINISHED))
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )


def effective_status(r: ComplianceResult) -> str:
    return r.reviewer_status or r.status


def compliance_rows(session: Session, run: AgentRun) -> list[ComplianceResultOut]:
    vendors = {v.id: v for v in session.scalars(select(Vendor).where(Vendor.project_id == run.project_id))}
    reqs = {
        r.id: r
        for r in session.scalars(select(TenderRequirement).where(TenderRequirement.project_id == run.project_id))
    }
    out = []
    for r in session.scalars(select(ComplianceResult).where(ComplianceResult.run_id == run.id)):
        rq = reqs[r.requirement_id]
        out.append(
            ComplianceResultOut(
                id=r.id,
                run_id=r.run_id,
                vendor_id=r.vendor_id,
                vendor_name=vendors[r.vendor_id].vendor_name,
                requirement_id=r.requirement_id,
                requirement_label=rq.label,
                requirement_text=f"{rq.operator} {rq.required_value}"
                + (f"–{rq.required_value_max}" if rq.required_value_max else "")
                + (f" {rq.unit}" if rq.unit else ""),
                criticality=rq.criticality,
                category=(r.evidence or {}).get("category", "technical"),
                status=r.status,
                effective_status=effective_status(r),
                method=r.method,
                explanation=r.explanation,
                evidence=r.evidence or {},
                review_required=r.review_required and r.reviewer_status is None,
                used_unconfirmed_input=r.verified_unconfirmed_input,
                reviewer_note=r.reviewer_note,
            )
        )
    out.sort(key=lambda x: (x.requirement_label, x.vendor_name))
    return out


def price_rows(session: Session, run: AgentRun) -> list[PriceAnalysisOut]:
    out = []
    for p in session.scalars(select(PriceAnalysis).where(PriceAnalysis.run_id == run.id)):
        q = session.get(VendorQuotation, p.quotation_id)
        out.append(
            PriceAnalysisOut(
                id=p.id,
                run_id=p.run_id,
                quotation_id=p.quotation_id,
                vendor_name=q.vendor.vendor_name,
                currency=q.currency,
                subtotal=p.subtotal,
                tax_amount=p.tax_amount,
                delivery_cost=p.delivery_cost,
                normalized_total=p.normalized_total,
                normalized_unit_price=p.normalized_unit_price,
                base_currency=p.base_currency,
                baseline=p.baseline,
                deviation_pct=p.deviation_pct,
                method=p.method,
                baseline_source=p.baseline_source,
                anomaly_flag=p.anomaly_flag,
                explanation=p.explanation,
            )
        )
    out.sort(key=lambda x: (x.vendor_name, x.baseline_source))
    return out


def policy_evidence_rows(session: Session, run: AgentRun) -> list[PolicyEvidence]:
    return list(
        session.scalars(
            select(PolicyEvidence).where(PolicyEvidence.run_id == run.id).order_by(PolicyEvidence.score.desc())
        )
    )


def review_items(session: Session, user: User, run_id: str) -> list[ReviewItem]:
    run = get_run(session, user, run_id)
    return list(
        session.scalars(
            select(ReviewItem)
            .where(ReviewItem.run_id == run.id)
            .order_by(ReviewItem.status.desc(), ReviewItem.kind, ReviewItem.created_at)
        )
    )


def resolve_review_item(session: Session, user: User, item_id: str, data: ReviewResolve) -> ReviewItem:
    item = session.get(ReviewItem, item_id)
    if item is None:
        raise NotFoundError("Review item not found.")
    get_project_for_user(session, user, item.project_id, write=True)
    if item.status != "open":
        raise ConflictError("This review item has already been resolved.")
    if item.kind == "compliance" and item.ref_id:
        result = session.get(ComplianceResult, item.ref_id)
        if result and data.decision in DECISION_STATUS:
            result.reviewer_status = DECISION_STATUS[data.decision].value
            result.reviewer_note, result.reviewed_by, result.reviewed_at = data.note, user.id, utcnow()
        elif data.decision != "acknowledged" and result is None:
            raise NotFoundError("The related compliance result no longer exists.")
    elif data.decision != "acknowledged":
        raise ValidationAppError(
            "Only compliance items accept a meets/fails/not_applicable decision; "
            "use 'acknowledged' with a note for other items."
        )
    item.status, item.resolution_note = "resolved", data.note
    item.resolved_by, item.resolved_at = user.id, utcnow()
    record_audit(
        session,
        actor_id=user.id,
        action="review.resolved",
        resource_type="review_item",
        resource_id=item.id,
        project_id=item.project_id,
        metadata={"kind": item.kind, "decision": data.decision},
    )
    session.commit()
    return item


def approve_run(session: Session, user: User, run_id: str) -> AgentRun:
    """Human sign-off. Only possible when every review item is resolved."""
    run = get_run(session, user, run_id)
    get_project_for_user(session, user, run.project_id, write=True)
    if run.status not in FINISHED:
        raise ConflictError("Only a finished analysis can be approved.")
    open_items = (
        session.scalar(
            select(func.count()).select_from(ReviewItem).where(ReviewItem.run_id == run.id, ReviewItem.status == "open")
        )
        or 0
    )
    if open_items:
        raise ConflictError(f"{open_items} review item(s) are still open.")
    summary = dict(run.summary)
    summary.update({"approved_by": user.id, "approved_at": utcnow().isoformat(), "open_review_items": 0})
    run.summary, run.status = summary, RunStatus.COMPLETED.value
    project = session.get(ProcurementProject, run.project_id)
    if project:
        project.status = ProjectStatus.ANALYZED.value
    record_audit(
        session,
        actor_id=user.id,
        action="analysis.approved",
        resource_type="analysis_run",
        resource_id=run.id,
        project_id=run.project_id,
    )
    session.commit()
    return run
