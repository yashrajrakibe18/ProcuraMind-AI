from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DB, Ctx, CurrentUser
from procureai.application.dto.schemas import ProjectCreate, ProjectOut, ProjectSummary, ProjectUpdate
from procureai.application.services import project_service
from procureai.application.services.access import get_project_for_user

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def list_projects(
    db: DB,
    user: CurrentUser,
    include_archived: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    org_id: str | None = None,
):
    return project_service.list_projects(db, user, include_archived, limit, offset, org_id)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: DB, user: CurrentUser):
    return project_service.create_project(db, user, data, data.org_id, data.domain)


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str, db: DB, user: CurrentUser):
    return project_service.summarize(db, get_project_for_user(db, user, project_id))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, data: ProjectUpdate, db: DB, user: CurrentUser):
    return project_service.update_project(db, user, project_id, data)


@router.delete(
    "/{project_id}", status_code=204, summary="Archive a project; with ?permanent=true purge files, vectors and records"
)
def delete_project(project_id: str, db: DB, ctx: Ctx, user: CurrentUser, permanent: bool = False) -> None:
    if permanent:
        project_service.purge_project(db, user, project_id, ctx.storage, ctx.store)
    else:
        project_service.archive_project(db, user, project_id)
