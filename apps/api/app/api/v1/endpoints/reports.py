from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import DB, Ctx, CurrentUser
from procureai.application.dto.schemas import ReportCreate, ReportOut
from procureai.application.services import dashboard_service, report_service

router = APIRouter(tags=["reports"])
_MEDIA = {"pdf": "application/pdf", "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@router.post("/projects/{project_id}/reports", response_model=ReportOut, status_code=201)
def create_report(project_id: str, data: ReportCreate, db: DB, ctx: Ctx, user: CurrentUser):
    return report_service.generate_report(db, ctx, user, project_id, data.report_type, data.run_id)


@router.get("/projects/{project_id}/reports", response_model=list[ReportOut])
def list_reports(project_id: str, db: DB, user: CurrentUser):
    return report_service.list_reports(db, user, project_id)


@router.get("/reports/{report_id}/download")
def download(report_id: str, db: DB, ctx: Ctx, user: CurrentUser) -> Response:
    report, blob = report_service.get_report_file(db, ctx, user, report_id)
    return Response(
        blob,
        media_type=_MEDIA[report.report_type],
        headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
    )


@router.get("/dashboard/overview", tags=["dashboard"], summary="Database-backed KPIs for the Overview page")
def overview(db: DB, user: CurrentUser) -> dict:
    return dashboard_service.overview(db, user)
