from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from procureai.application.dto.schemas import ProjectCreate, ProjectSummary, ProjectUpdate
from procureai.application.services import org_service
from procureai.application.services.access import accessible_org_ids, get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.infrastructure.database.models import (
    AgentRun,
    Document,
    ProcurementProject,
    Report,
    TenderRequirement,
    User,
    Vendor,
)
from procureai.infrastructure.storage.local import LocalFileStorage
from procureai.infrastructure.vector_store.chroma_store import ChromaVectorStore
from procureai.shared.enums import ProjectStatus, Role


def create_project(
    session: Session, user: User, data: ProjectCreate, org_id: str | None = None, domain: str = "general"
) -> ProcurementProject:
    org, _ = org_service.resolve_org(session, user, org_id)
    org_service.check_quota(session, org.id, "projects")
    project = ProcurementProject(
        title=data.title.strip(), description=data.description, owner_id=user.id, org_id=org.id, domain=domain
    )
    session.add(project)
    session.flush()
    record_audit(
        session,
        actor_id=user.id,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
    )
    session.commit()
    return project


def summarize(session: Session, project: ProcurementProject) -> ProjectSummary:
    def count(model) -> int:
        return session.scalar(select(func.count()).select_from(model).where(model.project_id == project.id)) or 0

    latest = session.scalar(
        select(AgentRun.status).where(AgentRun.project_id == project.id).order_by(AgentRun.created_at.desc()).limit(1)
    )
    base = ProjectSummary.model_validate(project)
    base.document_count, base.vendor_count = count(Document), count(Vendor)
    base.requirement_count, base.latest_run_status = count(TenderRequirement), latest
    return base


def list_projects(
    session: Session, user: User, include_archived: bool = False, limit: int = 100, offset: int = 0, org_id: str | None = None
) -> list[ProjectSummary]:
    stmt = select(ProcurementProject).order_by(ProcurementProject.updated_at.desc())
    if user.role != Role.ADMIN:
        orgs = accessible_org_ids(session, user)
        stmt = stmt.where(or_(ProcurementProject.owner_id == user.id, ProcurementProject.org_id.in_(orgs)))
    if org_id:
        stmt = stmt.where(ProcurementProject.org_id == org_id)
    if not include_archived:
        stmt = stmt.where(ProcurementProject.status != ProjectStatus.ARCHIVED.value)
    return [summarize(session, p) for p in session.scalars(stmt.limit(limit).offset(offset))]


def update_project(session: Session, user: User, project_id: str, data: ProjectUpdate) -> ProcurementProject:
    project = get_project_for_user(session, user, project_id, write=True)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    record_audit(
        session,
        actor_id=user.id,
        action="project.updated",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
        metadata={"fields": sorted(data.model_dump(exclude_unset=True))},
    )
    session.commit()
    return project


def archive_project(session: Session, user: User, project_id: str) -> ProcurementProject:
    project = get_project_for_user(session, user, project_id, write=True)
    project.status = ProjectStatus.ARCHIVED.value
    record_audit(
        session,
        actor_id=user.id,
        action="project.archived",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
    )
    session.commit()
    return project


def purge_project(
    session: Session, user: User, project_id: str, storage: LocalFileStorage, store: ChromaVectorStore
) -> None:
    """Permanent deletion: files, derived vector chunks, reports and all relational records."""
    project = get_project_for_user(session, user, project_id, write=True)
    for key in session.scalars(select(Document.storage_key).where(Document.project_id == project.id)):
        storage.delete(key)
    for key in session.scalars(select(Report.storage_key).where(Report.project_id == project.id)):
        storage.delete(key)
    store.delete_project(project.id)
    record_audit(
        session,
        actor_id=user.id,
        action="project.purged",
        resource_type="project",
        resource_id=project.id,
        project_id=None,
        metadata={"title_length": len(project.title)},
    )
    session.delete(project)
    session.commit()
