"""Platform API: organizations, plans/usage, webhooks, agents, tasks, chat, workflows, notifications, search."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, Ctx, CurrentUser
from procureai.agents.suite import orchestrator
from procureai.agents.suite.registry import AGENTS, public_catalog
from procureai.application.services import org_service, platform_service
from procureai.infrastructure.database.models import Organization, Webhook, Workflow, WorkflowRun
from procureai.saas import webhooks as hooks
from procureai.saas.plans import PLANS
from procureai.saas.platforms import catalogue
from procureai.shared.enums import Role
from procureai.shared.errors import NotFoundError, PermissionDeniedError, ValidationAppError

router = APIRouter(tags=["platform"])


# ------------------------------------------------------------------ organizations / plans
class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class MemberIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = "member"


class RoleIn(BaseModel):
    role: str


class PlanIn(BaseModel):
    plan: str


def _org_out(o: Organization, role: str) -> dict:
    return {"id": o.id, "name": o.name, "plan": o.plan, "role": role}


@router.get("/orgs")
def my_orgs(db: DB, user: CurrentUser):
    return [_org_out(o, m.role) for o, m in org_service.memberships_for(db, user)]


@router.post("/orgs", status_code=201)
def create_org(data: OrgIn, db: DB, user: CurrentUser):
    return _org_out(org_service.create_org(db, user, data.name), "owner")


@router.get("/orgs/{org_id}/members")
def members(org_id: str, db: DB, user: CurrentUser):
    return org_service.list_members(db, user, org_id)


@router.post("/orgs/{org_id}/members", status_code=201)
def add_member(org_id: str, data: MemberIn, db: DB, user: CurrentUser):
    return org_service.add_member(db, user, org_id, data.email, data.role)


@router.patch("/orgs/{org_id}/members/{user_id}")
def change_role(org_id: str, user_id: str, data: RoleIn, db: DB, user: CurrentUser):
    org_service.change_role(db, user, org_id, user_id, data.role)
    return {"ok": True}


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204)
def remove_member(org_id: str, user_id: str, db: DB, user: CurrentUser):
    org_service.remove_member(db, user, org_id, user_id)


@router.get("/plans")
def plans():
    return [{"key": p.key, "name": p.name, "price_usd_month": p.price_usd_month, "projects": p.projects, "members": p.members, "agent_tasks_month": p.agent_tasks_month, "documents_per_project": p.documents_per_project, "webhooks": p.webhooks, "features": list(p.features), "billing": "Not connected: plan changes only switch limits; no payment is taken."} for p in PLANS.values()]


@router.get("/orgs/{org_id}/usage")
def usage(org_id: str, db: DB, user: CurrentUser):
    org, _ = org_service.resolve_org(db, user, org_id)
    return org_service.usage_summary(db, org)


@router.put("/orgs/{org_id}/plan")
def set_plan(org_id: str, data: PlanIn, db: DB, user: CurrentUser):
    o = org_service.set_plan(db, user, org_id, data.plan)
    return {"id": o.id, "plan": o.plan}


# ------------------------------------------------------------------ webhooks
class HookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(default_factory=list)


def _hook_out(h: Webhook, reveal: bool = False) -> dict:
    d = {"id": h.id, "url": h.url, "events": h.events, "is_active": h.is_active, "last_status": h.last_status}
    if reveal:
        d["secret"] = h.secret
    return d


@router.get("/orgs/{org_id}/webhooks")
def list_hooks(org_id: str, db: DB, user: CurrentUser):
    org_service.require_manage(db, user, org_id)
    return [_hook_out(h) for h in db.scalars(select(Webhook).where(Webhook.org_id == org_id))]


@router.get("/webhook-events")
def hook_events():
    return list(hooks.EVENTS)


@router.post("/orgs/{org_id}/webhooks", status_code=201)
def create_hook(org_id: str, data: HookIn, db: DB, user: CurrentUser):
    org_service.require_manage(db, user, org_id)
    org_service.check_quota(db, org_id, "webhooks")
    hooks.validate_url(data.url)
    bad = [e for e in data.events if e not in hooks.EVENTS]
    if bad:
        raise ValidationAppError("Unknown event(s): " + ", ".join(bad))
    h = Webhook(org_id=org_id, url=data.url, secret=secrets.token_hex(24), events=data.events)
    db.add(h)
    db.commit()
    return _hook_out(h, reveal=True)  # the secret is shown once, at creation


@router.delete("/webhooks/{hook_id}", status_code=204)
def delete_hook(hook_id: str, db: DB, user: CurrentUser):
    h = db.get(Webhook, hook_id)
    if h is None:
        raise NotFoundError("Webhook not found.")
    org_service.require_manage(db, user, h.org_id)
    db.delete(h)
    db.commit()


@router.post("/webhooks/{hook_id}/test")
def test_hook(hook_id: str, db: DB, user: CurrentUser):
    h = db.get(Webhook, hook_id)
    if h is None:
        raise NotFoundError("Webhook not found.")
    org_service.require_manage(db, user, h.org_id)
    n = hooks.dispatch(db, h.org_id, h.events[0] if h.events else "agent.task.completed", {"test": True})
    db.commit()
    return {"delivered": n, "last_status": h.last_status}


# ------------------------------------------------------------------ agents & tasks
class RunIn(BaseModel):
    project_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class DecisionIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=2000)


@router.get("/agents")
def agents():
    return public_catalog()


@router.post("/agents/{agent_id}/run")
def run_agent(agent_id: str, data: RunIn, db: DB, ctx: Ctx, user: CurrentUser):
    return platform_service.task_out(orchestrator.run_agent(db, ctx, user, agent_id, project_id=data.project_id, params=data.params))


@router.get("/tasks")
def tasks(db: DB, user: CurrentUser, project_id: str | None = None, agent: str | None = None, status: str | None = None, limit: int = Query(50, ge=1, le=200)):
    return [platform_service.task_out(t, full=False) for t in platform_service.list_tasks(db, user, project_id, agent, status, limit)]


@router.get("/tasks/{task_id}")
def task(task_id: str, db: DB, user: CurrentUser):
    t = platform_service.get_task(db, user, task_id)
    children = [platform_service.task_out(c, full=False) for c in db.scalars(select(type(t)).where(type(t).parent_id == t.id).order_by(type(t).created_at))]
    return {**platform_service.task_out(t), "children": children}


@router.post("/tasks/{task_id}/decision")
def decision(task_id: str, data: DecisionIn, db: DB, ctx: Ctx, user: CurrentUser):
    return platform_service.task_out(orchestrator.decide(db, ctx, user, task_id, data.approve, data.note), full=False)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, db: DB, user: CurrentUser):
    return platform_service.task_out(orchestrator.cancel(db, user, task_id), full=False)


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: str, db: DB, ctx: Ctx, user: CurrentUser):
    return platform_service.task_out(orchestrator.retry(db, ctx, user, task_id))


# ------------------------------------------------------------------ chat
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None
    conversation_id: str | None = None
    agent: str = "auto"


@router.post("/chat")
def chat(data: ChatIn, db: DB, ctx: Ctx, user: CurrentUser):
    return platform_service.chat(db, ctx, user, data.message, data.project_id, data.conversation_id, data.agent)


@router.get("/conversations")
def conversations(db: DB, user: CurrentUser, project_id: str | None = None):
    return platform_service.list_conversations(db, user, project_id)


@router.get("/conversations/{cid}")
def conversation(cid: str, db: DB, user: CurrentUser):
    return platform_service.get_conversation(db, user, cid)


@router.delete("/conversations/{cid}", status_code=204)
def delete_conversation(cid: str, db: DB, user: CurrentUser):
    platform_service.delete_conversation(db, user, cid)


# ------------------------------------------------------------------ workflows
class WorkflowIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str = Field(default="", max_length=2000)
    steps: list[dict[str, Any]]
    project_id: str | None = None
    schedule_minutes: int | None = Field(default=None, ge=5, le=525600)


def _wf_out(w: Workflow) -> dict:
    return {"id": w.id, "name": w.name, "description": w.description, "steps": w.steps, "project_id": w.project_id, "schedule_minutes": w.schedule_minutes, "next_run_at": w.next_run_at.isoformat() if w.next_run_at else None, "is_active": w.is_active, "created_at": w.created_at.isoformat()}


def _run_out(r: WorkflowRun) -> dict:
    return {"id": r.id, "workflow_id": r.workflow_id, "project_id": r.project_id, "status": r.status, "cursor": r.cursor, "trigger": r.trigger, "error": r.error, "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None}


@router.get("/workflows")
def workflows(db: DB, user: CurrentUser, project_id: str | None = None):
    from procureai.application.services.access import accessible_org_ids

    stmt = select(Workflow).where(Workflow.org_id.in_(accessible_org_ids(db, user)), Workflow.is_active.is_(True))
    if project_id:
        stmt = stmt.where((Workflow.project_id == project_id) | (Workflow.project_id.is_(None)))
    return [_wf_out(w) for w in db.scalars(stmt.order_by(Workflow.created_at.desc()))]


@router.post("/workflows", status_code=201)
def create_workflow(data: WorkflowIn, db: DB, user: CurrentUser):
    return _wf_out(orchestrator.create_workflow(db, user, data.name, data.description, data.steps, data.project_id, data.schedule_minutes))


@router.delete("/workflows/{wid}", status_code=204)
def delete_workflow(wid: str, db: DB, user: CurrentUser):
    w = orchestrator.get_workflow(db, user, wid, write=True)
    w.is_active = False
    db.commit()


class RunWf(BaseModel):
    project_id: str | None = None


@router.post("/workflows/{wid}/run")
def run_workflow(wid: str, data: RunWf, db: DB, ctx: Ctx, user: CurrentUser):
    return _run_out(orchestrator.run_workflow(db, ctx, user, wid, data.project_id))


@router.get("/workflows/{wid}/runs")
def workflow_runs(wid: str, db: DB, user: CurrentUser):
    orchestrator.get_workflow(db, user, wid)
    return [_run_out(r) for r in db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == wid).order_by(WorkflowRun.started_at.desc()).limit(30))]


@router.post("/workflow-runs/{rid}/cancel")
def cancel_workflow_run(rid: str, db: DB, user: CurrentUser):
    return _run_out(orchestrator.cancel_run(db, user, rid))


@router.post("/workflows/run-due")
def run_due(ctx: Ctx, user: CurrentUser):
    if user.role != Role.ADMIN:
        raise PermissionDeniedError("Only a platform administrator can trigger the scheduler.")
    return {"ran": orchestrator.run_due_workflows(ctx)}


# ------------------------------------------------------------------ notifications, search, activity, dashboard
@router.get("/notifications")
def notifications(db: DB, user: CurrentUser, unread_only: bool = False):
    rows = platform_service.notifications(db, user, unread_only)
    return {"unread": sum(1 for n in platform_service.notifications(db, user, True, 200)), "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in rows]}


@router.post("/notifications/read")
def read_notifications(db: DB, user: CurrentUser, notification_id: str | None = None):
    return {"marked": platform_service.mark_read(db, user, notification_id)}


@router.get("/search")
def search(q: str, db: DB, user: CurrentUser):
    return platform_service.search(db, user, q)


@router.get("/activity")
def activity(db: DB, user: CurrentUser, project_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return platform_service.activity(db, user, project_id, limit, offset)


@router.get("/dashboard")
def dashboard(db: DB, user: CurrentUser, org_id: str | None = None):
    return platform_service.dashboard(db, user, org_id)


@router.get("/documents-all")
def documents_all(db: DB, user: CurrentUser):
    return platform_service.all_documents(db, user)


@router.get("/reports-all")
def reports_all(db: DB, user: CurrentUser):
    return platform_service.all_reports(db, user)


# ------------------------------------------------------------------ LLM provider status
@router.get("/llm/status")
def llm_status(ctx: Ctx, user: CurrentUser):
    c = ctx.llm
    return {"configured": c.available(), "provider": c.name, "model": c.model or None,
            "mode": "LLM-assisted (interpretation, routing, grounded answers)" if c.available() else "Deterministic only (no LLM configured)",
            "how_to_enable": "Set LLM_PROVIDER (anthropic | openai), LLM_API_KEY and LLM_MODEL in .env and restart. LLM_BASE_URL allows any OpenAI-compatible endpoint."}


@router.post("/orgs/{org_id}/llm/test")
def llm_test(org_id: str, db: DB, ctx: Ctx, user: CurrentUser):
    org_service.require_manage(db, user, org_id)
    if not ctx.llm.available():
        return {"ok": False, "error": "No LLM provider is configured."}
    try:
        ctx.llm.complete("Reply with the single word OK.", "ping", max_tokens=8)
    except Exception as exc:  # report, never leak internals
        return {"ok": False, "error": getattr(exc, "message", "The language model service is unavailable.")}
    org_service.record_usage(db, org_id, user.id, "llm_call", 1)
    db.commit()
    return {"ok": True, "provider": ctx.llm.name, "model": ctx.llm.model}


# ------------------------------------------------------------------ platform catalogue
@router.get("/platforms")
def platforms(user: CurrentUser):
    return catalogue(AGENTS)
