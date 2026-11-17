from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.application.context import AppContext
from procureai.application.services import analysis_service
from procureai.application.services.access import get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.infrastructure.database.models import Report, User
from procureai.reporting.data import collect
from procureai.reporting.excel.builder import build_excel
from procureai.reporting.pdf.builder import build_pdf
from procureai.shared.enums import ReportType
from procureai.shared.errors import NotFoundError, ValidationAppError


def generate_report(
    session: Session, ctx: AppContext, user: User, project_id: str, report_type: str, run_id: str | None
) -> Report:
    project = get_project_for_user(session, user, project_id, write=True)
    run = analysis_service.latest_result_run(session, project.id, run_id)
    if run is None or run.status not in analysis_service.FINISHED:
        raise ValidationAppError("A finished analysis run is required to generate a report.")
    data = collect(session, project.id, run)
    if report_type == ReportType.PDF.value:
        blob, ext = build_pdf(data), ".pdf"
    else:
        blob, ext = build_excel(data), ".xlsx"
    key, _ = ctx.storage.save(blob, ext, prefix="report-")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", project.title).strip("-")[:40] or "project"
    report = Report(
        project_id=project.id,
        run_id=run.id,
        report_type=report_type,
        storage_key=key,
        filename=f"ProcureAI-{slug}-{run.id[:8]}{ext}",
        generated_by=user.id,
    )
    session.add(report)
    session.flush()
    record_audit(
        session,
        actor_id=user.id,
        action="report.generated",
        resource_type="report",
        resource_id=report.id,
        project_id=project.id,
        metadata={"type": report_type, "run_id": run.id},
    )
    session.commit()
    return report


def list_reports(session: Session, user: User, project_id: str) -> list[Report]:
    get_project_for_user(session, user, project_id)
    return list(
        session.scalars(select(Report).where(Report.project_id == project_id).order_by(Report.generated_at.desc()))
    )


def get_report_file(session: Session, ctx: AppContext, user: User, report_id: str) -> tuple[Report, bytes]:
    report = session.get(Report, report_id)
    if report is None:
        raise NotFoundError("Report not found.")
    get_project_for_user(session, user, report.project_id)
    record_audit(
        session,
        actor_id=user.id,
        action="report.downloaded",
        resource_type="report",
        resource_id=report.id,
        project_id=report.project_id,
    )
    session.commit()
    return report, ctx.storage.read(report.storage_key)
