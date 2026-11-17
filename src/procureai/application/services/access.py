"""Authorization helpers: every protected operation goes through these."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.infrastructure.database.models import Membership, ProcurementProject, User
from procureai.shared.enums import Role
from procureai.shared.errors import NotFoundError, PermissionDeniedError


def get_project_for_user(session: Session, user: User, project_id: str, *, write: bool = False) -> ProcurementProject:
    """Owner, platform admin or a member of the project's organization may access.

    Organization ``viewer`` members are read-only. Everyone else gets 404 (never reveal that a project exists).
    """
    project = session.get(ProcurementProject, project_id)
    if project is None:
        raise NotFoundError("Project not found.")
    if project.owner_id == user.id or user.role == Role.ADMIN:
        if write and user.role == Role.REVIEWER and project.owner_id != user.id:
            raise PermissionDeniedError("Your role does not permit modifying this project.")
        return project
    member = (
        session.scalar(select(Membership).where(Membership.org_id == project.org_id, Membership.user_id == user.id))
        if project.org_id
        else None
    )
    if member is None:
        raise NotFoundError("Project not found.")
    if write and member.role == "viewer":
        raise PermissionDeniedError("Viewers have read-only access to this project.")
    if write and user.role == Role.REVIEWER:
        raise PermissionDeniedError("Your role does not permit modifying this project.")
    return project


def accessible_org_ids(session: Session, user: User) -> list[str]:
    return list(session.scalars(select(Membership.org_id).where(Membership.user_id == user.id)))
