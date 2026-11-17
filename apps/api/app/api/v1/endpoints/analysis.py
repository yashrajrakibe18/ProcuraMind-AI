from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Response
from sqlalchemy import select

from app.api.deps import DB, Ctx, CurrentUser
from procureai.application.context import AppContext
from procureai.application.dto.schemas import (
    ComplianceResultOut,
    HistoricalPurchaseOut,
    PolicyEvidenceOut,
    PriceAnalysisOut,
    ReviewItemOut,
    ReviewResolve,
    RunCreate,
    RunOut,
)
from procureai.application.services import analysis_service
from procureai.application.services.access import get_project_for_user
from procureai.infrastructure.database.models import HistoricalPurchase
from procureai.infrastructure.database.session import get_session_factory

router = APIRouter(tags=["analysis"])


def _execute(ctx: AppContext, run_id: str) -> None:
    analysis_service.execute_run(ctx, get_session_factory(), run_id)


@router.post(
    "/projects/{project_id}/analysis-runs",
    response_model=RunOut,
    status_code=202,
    summary="Start an analysis (idempotent: returns the active run if one exists)",
)
def start(
    project_id: str,
    data: RunCreate,
    background: BackgroundTasks,
    response: Response,
    db: DB,
    ctx: Ctx,
    user: CurrentUser,
):
    run, created = analysis_service.start_run(db, ctx, user, project_id, data.auto_confirm)
    if created:
        background.add_task(_execute, ctx, run.id)
    response.headers["Location"] = f"/api/v1/analysis-runs/{run.id}"
    return run


@router.get("/projects/{project_id}/analysis-runs", response_model=list[RunOut])
def list_runs(project_id: str, db: DB, user: CurrentUser):
    return analysis_service.list_runs(db, user, project_id)


@router.get("/analysis-runs/{run_id}", response_model=RunOut, summary="Status, steps and summary of a run")
def get_run(run_id: str, db: DB, user: CurrentUser):
    return analysis_service.get_run(db, user, run_id)


@router.get("/analysis-runs/{run_id}/review-items", response_model=list[ReviewItemOut])
def review_items(run_id: str, db: DB, user: CurrentUser):
    return analysis_service.review_items(db, user, run_id)


@router.post("/review-items/{item_id}/resolve", response_model=ReviewItemOut)
def resolve(item_id: str, data: ReviewResolve, db: DB, user: CurrentUser):
    return analysis_service.resolve_review_item(db, user, item_id, data)


@router.post(
    "/analysis-runs/{run_id}/approve",
    response_model=RunOut,
    summary="Human sign-off; blocked while review items are open",
)
def approve(run_id: str, db: DB, user: CurrentUser):
    return analysis_service.approve_run(db, user, run_id)


def _result_run(db, user, project_id: str, run_id: str | None):
    get_project_for_user(db, user, project_id)
    return analysis_service.latest_result_run(db, project_id, run_id)


@router.get(
    "/projects/{project_id}/compliance",
    response_model=list[ComplianceResultOut],
    summary="Requirement-wise compliance results (latest finished run unless run_id is given)",
)
def compliance(project_id: str, db: DB, user: CurrentUser, run_id: str | None = None):
    run = _result_run(db, user, project_id, run_id)
    return analysis_service.compliance_rows(db, run) if run else []


@router.get("/projects/{project_id}/price-analysis", response_model=list[PriceAnalysisOut])
def price_analysis(project_id: str, db: DB, user: CurrentUser, run_id: str | None = None):
    run = _result_run(db, user, project_id, run_id)
    return analysis_service.price_rows(db, run) if run else []


@router.get("/projects/{project_id}/policy-evidence", response_model=list[PolicyEvidenceOut])
def policy_evidence(project_id: str, db: DB, user: CurrentUser, run_id: str | None = None):
    run = _result_run(db, user, project_id, run_id)
    return analysis_service.policy_evidence_rows(db, run) if run else []


@router.get("/projects/{project_id}/historical-purchases", response_model=list[HistoricalPurchaseOut])
def historical(project_id: str, db: DB, user: CurrentUser):
    get_project_for_user(db, user, project_id)
    return list(
        db.scalars(
            select(HistoricalPurchase)
            .where(HistoricalPurchase.project_id == project_id)
            .order_by(HistoricalPurchase.purchased_on)
        )
    )
