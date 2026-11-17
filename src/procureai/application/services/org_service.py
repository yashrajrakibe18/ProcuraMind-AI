"""Organizations, memberships, plan limits and usage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.application.services.audit import record_audit
from procureai.infrastructure.database.models import (
    AgentTask,
    Membership,
    Organization,
    ProcurementProject,
    UsageEvent,
    User,
    Webhook,
)
from procureai.saas.plans import PLANS, UNLIMITED, get_plan, within
from procureai.shared.enums import Role
from procureai.shared.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationAppError
from procureai.shared.types import utcnow

ORG_ROLES = ("owner", "admin", "member", "viewer")
MANAGE_ROLES = ("owner", "admin")


class PlanLimitError(ConflictError):
    status_code = 402
    code = "plan_limit_reached"


def create_personal_org(session: Session, user: User) -> Organization:
    org = Organization(name=f"{user.full_name.split()[0] if user.full_name else 'My'}'s workspace", created_by=user.id)
    session.add(org)
    session.flush()
    session.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    session.flush()
    return org


def memberships_for(session: Session, user: User) -> list[tuple[Organization, Membership]]:
    rows = session.execute(
        select(Organization, Membership).join(Membership, Membership.org_id == Organization.id).where(Membership.user_id == user.id).order_by(Organization.created_at)
    ).all()
    if not rows:  # users created before orgs existed
        create_personal_org(session, user)
        session.commit()
        return memberships_for(session, user)
    return [(o, m) for o, m in rows]


def resolve_org(session: Session, user: User, org_id: str | None = None) -> tuple[Organization, Membership]:
    rows = memberships_for(session, user)
    if org_id:
        for o, m in rows:
            if o.id == org_id:
                return o, m
        raise NotFoundError("Organization not found.")
    return rows[0]


def role_in_org(session: Session, user: User, org_id: str | None) -> str | None:
    if org_id is None:
        return None
    m = session.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user.id))
    return m.role if m else None


def require_manage(session: Session, user: User, org_id: str) -> Organization:
    org = session.get(Organization, org_id)
    role = role_in_org(session, user, org_id)
    if org is None or role is None:
        raise NotFoundError("Organization not found.")
    if role not in MANAGE_ROLES:
        raise PermissionDeniedError("Only organization owners and admins can do this.")
    return org


def create_org(session: Session, user: User, name: str) -> Organization:
    org = Organization(name=name.strip(), created_by=user.id)
    session.add(org)
    session.flush()
    session.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    record_audit(session, actor_id=user.id, action="org.created", resource_type="organization", resource_id=org.id)
    session.commit()
    return org


def list_members(session: Session, user: User, org_id: str) -> list[dict]:
    resolve_org(session, user, org_id)
    rows = session.execute(
        select(User, Membership).join(Membership, Membership.user_id == User.id).where(Membership.org_id == org_id).order_by(Membership.created_at)
    ).all()
    return [{"user_id": u.id, "email": u.email, "full_name": u.full_name, "role": m.role} for u, m in rows]


def add_member(session: Session, actor: User, org_id: str, email: str, role: str) -> dict:
    org = require_manage(session, actor, org_id)
    if role not in ORG_ROLES or role == "owner":
        raise ValidationAppError("Role must be admin, member or viewer.")
    target = session.scalar(select(User).where(User.email == email.strip().lower()))
    if target is None:
        raise NotFoundError("No registered user has that email. Ask them to sign up first.")
    if session.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == target.id)):
        raise ConflictError("That user is already a member.")
    count = session.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org_id)) or 0
    if not within(get_plan(org.plan).members, count):
        raise PlanLimitError(f"The {get_plan(org.plan).name} plan allows {get_plan(org.plan).members} member(s). Upgrade to add more.")
    session.add(Membership(org_id=org_id, user_id=target.id, role=role))
    record_audit(session, actor_id=actor.id, action="org.member_added", resource_type="organization", resource_id=org_id, metadata={"role": role})
    session.commit()
    return {"user_id": target.id, "email": target.email, "full_name": target.full_name, "role": role}


def change_role(session: Session, actor: User, org_id: str, user_id: str, role: str) -> None:
    require_manage(session, actor, org_id)
    m = session.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id))
    if m is None:
        raise NotFoundError("Member not found.")
    if m.role == "owner":
        raise PermissionDeniedError("The owner's role cannot be changed.")
    if role not in ORG_ROLES or role == "owner":
        raise ValidationAppError("Role must be admin, member or viewer.")
    m.role = role
    record_audit(session, actor_id=actor.id, action="org.role_changed", resource_type="organization", resource_id=org_id, metadata={"role": role})
    session.commit()


def remove_member(session: Session, actor: User, org_id: str, user_id: str) -> None:
    require_manage(session, actor, org_id)
    m = session.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id))
    if m is None:
        raise NotFoundError("Member not found.")
    if m.role == "owner":
        raise PermissionDeniedError("The owner cannot be removed.")
    session.delete(m)
    record_audit(session, actor_id=actor.id, action="org.member_removed", resource_type="organization", resource_id=org_id)
    session.commit()


def set_plan(session: Session, actor: User, org_id: str, plan: str) -> Organization:
    org = session.get(Organization, org_id)
    if org is None or role_in_org(session, actor, org_id) != "owner":
        raise PermissionDeniedError("Only the organization owner can change the plan.")
    if plan not in PLANS:
        raise ValidationAppError("Unknown plan.")
    org.plan = plan  # NOTE: no payment processing yet; this is a plan flag used for limit enforcement.
    record_audit(session, actor_id=actor.id, action="org.plan_changed", resource_type="organization", resource_id=org_id, metadata={"plan": plan})
    session.commit()
    return org


def month_start() -> datetime:
    now = utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_summary(session: Session, org: Organization) -> dict:
    plan = get_plan(org.plan)
    projects = session.scalar(select(func.count()).select_from(ProcurementProject).where(ProcurementProject.org_id == org.id, ProcurementProject.status != "archived")) or 0
    members = session.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == org.id)) or 0
    tasks = session.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.org_id == org.id, AgentTask.created_at >= month_start())) or 0
    llm = session.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(UsageEvent.org_id == org.id, UsageEvent.kind == "llm_call", UsageEvent.created_at >= month_start())) or 0
    hooks = session.scalar(select(func.count()).select_from(Webhook).where(Webhook.org_id == org.id)) or 0

    def row(used: int, limit: int) -> dict:
        return {"used": used, "limit": None if limit == UNLIMITED else limit}

    return {
        "plan": plan.key,
        "plan_name": plan.name,
        "projects": row(projects, plan.projects),
        "members": row(members, plan.members),
        "agent_tasks_month": row(tasks, plan.agent_tasks_month),
        "webhooks": row(hooks, plan.webhooks),
        "llm_calls_month": llm,
        "token_tracking": "Token counts are recorded only when an LLM provider is configured; this deployment counts LLM calls.",
    }


def check_quota(session: Session, org_id: str | None, what: str) -> None:
    """Raise PlanLimitError when the organization's plan limit for ``what`` is reached."""
    if org_id is None:
        return
    org = session.get(Organization, org_id)
    if org is None:
        return
    plan, u = get_plan(org.plan), usage_summary(session, org)
    mapping = {"projects": plan.projects, "agent_tasks_month": plan.agent_tasks_month, "webhooks": plan.webhooks}
    limit = mapping[what]
    if not within(limit, u[what]["used"]):
        raise PlanLimitError(f"The {plan.name} plan limit for {what.replace('_', ' ')} ({limit}) has been reached. Upgrade the plan to continue.")


def record_usage(session: Session, org_id: str | None, user_id: str | None, kind: str, quantity: int = 1) -> None:
    session.add(UsageEvent(org_id=org_id, user_id=user_id, kind=kind, quantity=quantity))


def is_platform_admin(user: User) -> bool:
    return user.role == Role.ADMIN
