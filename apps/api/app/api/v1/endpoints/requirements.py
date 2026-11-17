from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import DB, CurrentUser
from procureai.application.dto.schemas import (
    ExtractionReport,
    RequirementIn,
    RequirementOut,
    RequirementUpdate,
)
from procureai.application.services import extraction_service
from procureai.application.services.access import get_project_for_user

router = APIRouter(tags=["requirements"])


@router.post("/projects/{project_id}/requirements/extract", response_model=ExtractionReport)
def extract(project_id: str, db: DB, user: CurrentUser):
    get_project_for_user(db, user, project_id, write=True)
    return extraction_service.extract_project_requirements(db, project_id, user.id)


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementOut])
def list_requirements(project_id: str, db: DB, user: CurrentUser):
    return extraction_service.list_requirements(db, user, project_id)


@router.post("/projects/{project_id}/requirements", response_model=RequirementOut, status_code=201)
def add_requirement(project_id: str, data: RequirementIn, db: DB, user: CurrentUser):
    return extraction_service.add_requirement(db, user, project_id, data)


@router.post("/projects/{project_id}/requirements/confirm-all")
def confirm_all(project_id: str, db: DB, user: CurrentUser) -> dict:
    get_project_for_user(db, user, project_id, write=True)
    return {"confirmed": extraction_service.confirm_all_requirements(db, project_id, user.id)}


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut)
def update_requirement(requirement_id: str, data: RequirementUpdate, db: DB, user: CurrentUser):
    return extraction_service.update_requirement(db, user, requirement_id, data)


@router.delete("/requirements/{requirement_id}", status_code=204)
def delete_requirement(requirement_id: str, db: DB, user: CurrentUser) -> Response:
    extraction_service.delete_requirement(db, user, requirement_id)
    return Response(status_code=204)
