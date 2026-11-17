"""Cross-project platform queries: dashboard, global search, activity, notifications, conversations."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from procureai.agents.suite import orchestrator
from procureai.agents.suite.registry import AGENTS
from procureai.application.context import AppContext
from procureai.application.services import org_service
from procureai.application.services.access import accessible_org_ids, get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.infrastructure.database.models import (
    AgentRun,
    AgentTask,
    AuditEvent,
    Conversation,
    Document,
    Message,
    Notification,
    ProcurementProject,
    Report,
    ReviewItem,
    User,
    Vendor,
    Workflow,
)
from procureai.shared.enums import Role
from procureai.shared.errors import NotFoundError, ValidationAppError
from procureai.shared.types import utcnow


def visible_project_ids(session: Session, user: User) -> list[str]:
    stmt = select(ProcurementProject.id)
    if user.role != Role.ADMIN:
        stmt = stmt.where(or_(ProcurementProject.owner_id == user.id, ProcurementProject.org_id.in_(accessible_org_ids(session, user))))
    return list(session.scalars(stmt))


def dashboard(session: Session, user: User, org_id: str | None) -> dict:
    org, role = org_service.resolve_org(session, user, org_id)
    pids = list(session.scalars(select(ProcurementProject.id).where(ProcurementProject.org_id == org.id)))
    projects = list(session.scalars(select(ProcurementProject).where(ProcurementProject.org_id == org.id).order_by(ProcurementProject.updated_at.desc()).limit(6)))

    def count(model, *conds) -> int:
        return session.scalar(select(func.count()).select_from(model).where(*conds)) or 0

    by_status = dict(session.execute(select(AgentTask.status, func.count()).where(AgentTask.org_id == org.id).group_by(AgentTask.status)).all())
    by_agent = dict(session.execute(select(AgentTask.agent, func.count()).where(AgentTask.org_id == org.id).group_by(AgentTask.agent).order_by(func.count().desc()).limit(8)).all())
    pending = list(session.scalars(select(AgentTask).where(AgentTask.org_id == org.id, AgentTask.status == "awaiting_approval").order_by(AgentTask.created_at.desc()).limit(8)))
    open_reviews = count(ReviewItem, ReviewItem.project_id.in_(pids), ReviewItem.status == "open") if pids else 0
    recent = list(session.scalars(select(AuditEvent).where(AuditEvent.project_id.in_(pids)).order_by(AuditEvent.timestamp.desc()).limit(10))) if pids else []
    return {
        "org": {"id": org.id, "name": org.name, "role": role.role},
        "kpis": {
            "projects": count(ProcurementProject, ProcurementProject.org_id == org.id, ProcurementProject.status != "archived"),
            "documents": count(Document, Document.project_id.in_(pids)) if pids else 0,
            "vendors": count(Vendor, Vendor.project_id.in_(pids)) if pids else 0,
            "agent_tasks": sum(by_status.values()),
            "pending_approvals": len(pending),
            "open_review_items": open_reviews,
            "reports": count(Report, Report.project_id.in_(pids)) if pids else 0,
        },
        "tasks_by_status": by_status,
        "tasks_by_agent": by_agent,
        "pending_approvals": [{"id": t.id, "agent": t.agent, "project_id": t.project_id, "summary": (t.output or {}).get("summary", "")[:160], "created_at": t.created_at.isoformat()} for t in pending],
        "recent_projects": [{"id": p.id, "title": p.title, "status": p.status, "domain": p.domain, "updated_at": p.updated_at.isoformat()} for p in projects],
        "recent_activity": [{"action": a.action, "resource_type": a.resource_type, "timestamp": a.timestamp.isoformat(), "project_id": a.project_id} for a in recent],
        "usage": org_service.usage_summary(session, org),
    }


def search(session: Session, user: User, q: str, limit: int = 8) -> dict:
    q = q.strip()
    if len(q) < 2:
        return {"projects": [], "documents": [], "vendors": [], "workflows": [], "conversations": []}
    pids, like = visible_project_ids(session, user), f"%{q}%"
    titles = {p.id: p.title for p in session.scalars(select(ProcurementProject).where(ProcurementProject.id.in_(pids)))} if pids else {}
    projects = [{"id": p.id, "title": p.title, "domain": p.domain} for p in session.scalars(select(ProcurementProject).where(ProcurementProject.id.in_(pids), ProcurementProject.title.ilike(like)).limit(limit))] if pids else []
    docs = [{"id": d.id, "filename": d.original_filename, "type": d.document_type, "project_id": d.project_id, "project": titles.get(d.project_id, "")} for d in session.scalars(select(Document).where(Document.project_id.in_(pids), Document.original_filename.ilike(like)).limit(limit))] if pids else []
    vendors = [{"id": v.id, "name": v.vendor_name, "project_id": v.project_id, "project": titles.get(v.project_id, "")} for v in session.scalars(select(Vendor).where(Vendor.project_id.in_(pids), Vendor.vendor_name.ilike(like)).limit(limit))] if pids else []
    orgs = accessible_org_ids(session, user)
    wfs = [{"id": w.id, "name": w.name} for w in session.scalars(select(Workflow).where(Workflow.org_id.in_(orgs), Workflow.name.ilike(like)).limit(limit))]
    convs = [{"id": c.id, "title": c.title} for c in session.scalars(select(Conversation).where(Conversation.user_id == user.id, Conversation.title.ilike(like)).limit(limit))]
    return {"projects": projects, "documents": docs, "vendors": vendors, "workflows": wfs, "conversations": convs}


def activity(session: Session, user: User, project_id: str | None, limit: int = 50, offset: int = 0) -> list[dict]:
    if project_id:
        get_project_for_user(session, user, project_id)
        pids = [project_id]
    else:
        pids = visible_project_ids(session, user)
    stmt = select(AuditEvent).where(or_(AuditEvent.project_id.in_(pids), AuditEvent.actor_id == user.id)).order_by(AuditEvent.timestamp.desc()).limit(limit).offset(offset)
    names = {u.id: u.full_name for u in session.scalars(select(User))}
    return [{"id": a.id, "action": a.action, "resource_type": a.resource_type, "resource_id": a.resource_id, "project_id": a.project_id, "actor": names.get(a.actor_id or "", "system"), "timestamp": a.timestamp.isoformat(), "metadata": a.event_metadata} for a in session.scalars(stmt)]


def list_tasks(session: Session, user: User, project_id: str | None, agent: str | None, status: str | None, limit: int = 50) -> list[AgentTask]:
    if project_id:
        get_project_for_user(session, user, project_id)
        stmt = select(AgentTask).where(AgentTask.project_id == project_id)
    else:
        stmt = select(AgentTask).where(or_(AgentTask.org_id.in_(accessible_org_ids(session, user)), AgentTask.user_id == user.id))
    if agent:
        stmt = stmt.where(AgentTask.agent == agent)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    return list(session.scalars(stmt.order_by(AgentTask.created_at.desc()).limit(limit)))


def get_task(session: Session, user: User, task_id: str) -> AgentTask:
    return orchestrator._task_for(session, user, task_id, write=False)


def task_out(t: AgentTask, full: bool = True) -> dict:
    out = t.output or {}
    d = {"id": t.id, "agent": t.agent, "agent_name": AGENTS[t.agent].name if t.agent in AGENTS else t.agent.title(), "project_id": t.project_id, "parent_id": t.parent_id, "workflow_run_id": t.workflow_run_id, "status": t.status, "summary": out.get("summary", ""), "needs_input": out.get("needs_input"), "error": t.error, "duration_ms": t.duration_ms, "attempts": t.attempts, "llm_calls": t.llm_calls, "requires_approval": t.requires_approval, "created_at": t.created_at.isoformat(), "finished_at": t.finished_at.isoformat() if t.finished_at else None, "params": t.params}
    if full:
        d["output"] = out
    return d


# ---------------------------------------------------------------- notifications
def notifications(session: Session, user: User, unread_only: bool = False, limit: int = 50) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return list(session.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)))


def mark_read(session: Session, user: User, notification_id: str | None) -> int:
    stmt = select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    if notification_id:
        stmt = stmt.where(Notification.id == notification_id)
    rows = list(session.scalars(stmt))
    for n in rows:
        n.is_read = True
    session.commit()
    return len(rows)


# ---------------------------------------------------------------- chat / conversations
def _conv(session: Session, user: User, conversation_id: str) -> Conversation:
    c = session.get(Conversation, conversation_id)
    if c is None or c.user_id != user.id:
        raise NotFoundError("Conversation not found.")
    return c


def chat(session: Session, app: AppContext, user: User, message: str, project_id: str | None, conversation_id: str | None, agent: str = "auto") -> dict:
    message = message.strip()
    if not message:
        raise ValidationAppError("Message is empty.")
    if conversation_id:
        conv = _conv(session, user, conversation_id)
        project_id = project_id or conv.project_id
    else:
        conv = Conversation(user_id=user.id, project_id=project_id, title=message[:60])
        session.add(conv)
        session.flush()
    if project_id:
        get_project_for_user(session, user, project_id)
        conv.project_id = project_id
    session.add(Message(conversation_id=conv.id, role="user", content=message))
    session.commit()
    payload: dict = {}
    if not project_id:
        hits = search(session, user, message.split("?")[0][:60])
        n = sum(len(v) for v in hits.values())
        reply = "Select a project to run agents on its documents. " + (f"I found {n} matching item(s) across your workspace." if n else "Nothing in your workspace matched that text yet.")
        payload = {"search": hits}
    else:
        history = [m.content for m in session.scalars(select(Message).where(Message.conversation_id == conv.id, Message.role == "user").order_by(Message.created_at.desc()).limit(3))]
        text = message
        if len(message.split()) < 6 and len(history) > 1:  # short follow-up: carry the previous question for context
            text = f"{history[1]} {message}"
        if agent == "auto":
            task = orchestrator.run_agent(session, app, user, "supervisor", project_id=project_id, params={"request": text})
        else:
            if agent not in AGENTS:
                raise ValidationAppError("Unknown agent.")
            task = orchestrator.run_agent(session, app, user, agent, project_id=project_id, params=_agent_params(agent, text))
        out = task.output or {}
        reply = out.get("summary", "") if task.status != "needs_input" else f"I need more input: {out.get('needs_input')}"
        payload = {"task": task_out(task, full=True)}
    session.add(Message(conversation_id=conv.id, role="assistant", content=reply, payload=_trim(payload)))
    conv.updated_at = utcnow()
    record_audit(session, actor_id=user.id, action="chat.message", resource_type="conversation", resource_id=conv.id, project_id=project_id, metadata={"agent": agent, "length": len(message)})
    session.commit()
    return {"conversation_id": conv.id, "reply": reply, **payload}


def _agent_params(agent: str, text: str) -> dict:
    from procureai.agents.suite import router

    return router.params_for(agent, text, {})


def _trim(payload: dict) -> dict:
    return payload


def list_conversations(session: Session, user: User, project_id: str | None = None) -> list[dict]:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if project_id:
        stmt = stmt.where(Conversation.project_id == project_id)
    return [{"id": c.id, "title": c.title, "project_id": c.project_id, "updated_at": c.updated_at.isoformat() if hasattr(c.updated_at, "isoformat") else str(c.updated_at)} for c in session.scalars(stmt.order_by(Conversation.updated_at.desc()).limit(50))]


def get_conversation(session: Session, user: User, conversation_id: str) -> dict:
    c = _conv(session, user, conversation_id)
    msgs = session.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at))
    return {"id": c.id, "title": c.title, "project_id": c.project_id, "messages": [{"id": m.id, "role": m.role, "content": m.content, "payload": m.payload, "created_at": m.created_at.isoformat()} for m in msgs]}


def delete_conversation(session: Session, user: User, conversation_id: str) -> None:
    session.delete(_conv(session, user, conversation_id))
    session.commit()


def all_documents(session: Session, user: User, limit: int = 200) -> list[dict]:
    pids = visible_project_ids(session, user)
    if not pids:
        return []
    titles = {p.id: p.title for p in session.scalars(select(ProcurementProject).where(ProcurementProject.id.in_(pids)))}
    rows = session.scalars(select(Document).where(Document.project_id.in_(pids)).order_by(Document.created_at.desc()).limit(limit))
    return [{"id": d.id, "filename": d.original_filename, "type": d.document_type, "status": d.processing_status, "pages": d.page_count, "size_bytes": d.size_bytes, "project_id": d.project_id, "project": titles.get(d.project_id, ""), "created_at": d.created_at.isoformat()} for d in rows]


def all_reports(session: Session, user: User, limit: int = 100) -> list[dict]:
    pids = visible_project_ids(session, user)
    if not pids:
        return []
    titles = {p.id: p.title for p in session.scalars(select(ProcurementProject).where(ProcurementProject.id.in_(pids)))}
    return [{"id": r.id, "filename": r.filename, "type": r.report_type, "project_id": r.project_id, "project": titles.get(r.project_id, ""), "generated_at": r.generated_at.isoformat()} for r in session.scalars(select(Report).where(Report.project_id.in_(pids)).order_by(Report.generated_at.desc()).limit(limit))]


def latest_runs_exist(session: Session, project_id: str) -> bool:
    return bool(session.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.project_id == project_id)))
