"""Overview KPIs computed from real database rows only."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.application.dto.schemas import AuditEventOut, ProjectSummary
from procureai.application.services.project_service import list_projects
from procureai.infrastructure.database.models import (
    AgentRun,
    AuditEvent,
    Document,
    ProcurementProject,
    ReviewItem,
    User,
    Vendor,
)
from procureai.shared.enums import Role


def overview(session: Session, user: User) -> dict[str, Any]:
    admin = user.role == Role.ADMIN
    proj_ids = select(ProcurementProject.id)
    if not admin:
        proj_ids = proj_ids.where(ProcurementProject.owner_id == user.id)

    def count(model, *conds) -> int:
        return session.scalar(select(func.count()).select_from(model).where(*conds)) or 0

    runs_by_status = dict(
        session.execute(
            select(AgentRun.status, func.count()).where(AgentRun.project_id.in_(proj_ids)).group_by(AgentRun.status)
        ).all()
    )
    recent_events = session.scalars(
        select(AuditEvent)
        .where((AuditEvent.project_id.in_(proj_ids)) | (AuditEvent.actor_id == user.id))
        .order_by(AuditEvent.timestamp.desc())
        .limit(10)
    )
    recent_runs = session.scalars(
        select(AgentRun).where(AgentRun.project_id.in_(proj_ids)).order_by(AgentRun.created_at.desc()).limit(5)
    )
    projects: list[ProjectSummary] = list_projects(session, user, limit=5)
    return {
        "kpis": {
            "projects": count(ProcurementProject, ProcurementProject.id.in_(proj_ids)),
            "documents": count(Document, Document.project_id.in_(proj_ids)),
            "vendors": count(Vendor, Vendor.project_id.in_(proj_ids)),
            "analysis_runs": sum(runs_by_status.values()),
            "pending_reviews": count(ReviewItem, ReviewItem.project_id.in_(proj_ids), ReviewItem.status == "open"),
            "runs_awaiting_review": runs_by_status.get("awaiting_human_review", 0),
        },
        "runs_by_status": runs_by_status,
        "recent_projects": [p.model_dump(mode="json") for p in projects],
        "recent_runs": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "error": r.error,
            }
            for r in recent_runs
        ],
        "recent_activity": [AuditEventOut.model_validate(e).model_dump(mode="json") for e in recent_events],
    }
