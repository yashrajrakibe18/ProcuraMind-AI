"""Orchestrator: the only way agents run. Handles limits, timeouts, retries, tracking, approvals, usage and events.

Agents never call each other. The Supervisor (and workflows) call back into ``run_agent``, so every execution is
permission-checked, recorded as an ``AgentTask`` and audited. No agent can send external messages or take
irreversible actions; steps that produce drafts stop at ``awaiting_approval``.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.agents.suite import llm as llm_layer
from procureai.agents.suite import router
from procureai.agents.suite.base import AgentContext, Result
from procureai.agents.suite.registry import AGENTS
from procureai.application.context import AppContext
from procureai.application.services import org_service
from procureai.application.services.access import get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.infrastructure.database.models import (
    AgentTask,
    Notification,
    Organization,
    ProcurementProject,
    User,
    Workflow,
    WorkflowRun,
)
from procureai.infrastructure.database.session import get_session_factory
from procureai.saas import webhooks
from procureai.shared.errors import (
    AppError,
    ExternalServiceError,
    NotFoundError,
    ValidationAppError,
)
from procureai.shared.types import utcnow

logger = logging.getLogger(__name__)
TERMINAL = ("completed", "failed", "cancelled", "rejected")


def _jsonable(o: Any) -> Any:
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def _clean(obj: dict) -> dict:
    return json.loads(json.dumps(obj, default=_jsonable))


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, (ExternalServiceError, FutureTimeout, TimeoutError))


def _call_handler(app: AppContext, user_id: str, project_id: str | None, spec, params: dict, task_id: str) -> tuple[Result, list[str]]:
    session = get_session_factory()()
    try:
        ctx = AgentContext(session, app, session.get(User, user_id), session.get(ProcurementProject, project_id) if project_id else None, params, spec, task_id)
        res = spec.handler(ctx)
        session.commit()
        return res, ctx.tools_used
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_agent(
    session: Session,
    app: AppContext,
    user: User,
    agent_id: str,
    *,
    project_id: str | None = None,
    params: dict | None = None,
    parent_id: str | None = None,
    workflow_run_id: str | None = None,
) -> AgentTask:
    spec = AGENTS.get(agent_id)
    if spec is None:
        raise NotFoundError(f"Unknown agent '{agent_id}'.")
    params = dict(params or {})
    project = None
    if spec.requires_project and not project_id:
        raise ValidationAppError(f"The {spec.name} needs a project.")
    if project_id:
        project = get_project_for_user(session, user, project_id, write=spec.writes)
    org_id = project.org_id if project else org_service.resolve_org(session, user, params.get("org_id"))[0].id
    org_service.check_quota(session, org_id, "agent_tasks_month")
    task = AgentTask(org_id=org_id, project_id=project.id if project else None, user_id=user.id, agent=agent_id, parent_id=parent_id, workflow_run_id=workflow_run_id, params=_clean(params), status="running", requires_approval=spec.requires_approval)
    session.add(task)
    session.commit()
    started = time.perf_counter()
    result: Result | None = None
    tools: list[str] = []
    error: str | None = None
    attempts = 0
    while attempts <= spec.max_retries:
        attempts += 1
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"agent-{agent_id}")
        try:
            result, tools = pool.submit(_call_handler, app, user.id, project.id if project else None, spec, params, task.id).result(timeout=spec.timeout_s)
            error = None
            break
        except Exception as exc:  # boundary: classify, never leak internals
            if isinstance(exc, FutureTimeout):
                error = f"The agent timed out after {spec.timeout_s}s."
            elif isinstance(exc, AppError):
                error = exc.message
            else:
                logger.exception("Agent crashed", extra={"agent": agent_id, "task_id": task.id})
                error = "The agent failed unexpectedly. The incident was logged."
            if not _transient(exc):
                break
            logger.warning("Transient agent failure (attempt %s)", attempts, extra={"agent": agent_id})
        finally:
            pool.shutdown(wait=False)
    session.expire_all()
    task = session.get(AgentTask, task.id)
    task.attempts = attempts
    task.duration_ms = int((time.perf_counter() - started) * 1000)
    task.finished_at = utcnow()
    if result is None or result.status == "failed":
        task.status, task.error = "failed", error or result.summary
        task.output = _clean({"summary": task.error, "sections": [], "evidence": [], "needs_input": None, "labels": {}, "data": {}, "tools_used": tools})
    else:
        status = "awaiting_approval" if (spec.requires_approval and result.status == "completed") else result.status
        if status == "completed" and params.get("use_llm", True) is not False:
            llm_layer.attach_interpretation(app, spec, result)
        task.status = status
        task.llm_calls = result.llm_calls
        task.output = _clean({**result.to_dict(), "tools_used": tools, "agent_name": spec.name})
    org_service.record_usage(session, org_id, user.id, "agent_task")
    if task.llm_calls:
        org_service.record_usage(session, org_id, user.id, "llm_call", task.llm_calls)
    record_audit(session, actor_id=user.id, action=f"agent.task.{task.status}", resource_type="agent_task", resource_id=task.id, project_id=task.project_id, metadata={"agent": agent_id, "ms": task.duration_ms, "attempts": attempts})
    if parent_id is None and workflow_run_id is None and task.status in ("failed", "awaiting_approval", "needs_input", "completed"):
        title = {"failed": f"{spec.name} failed", "awaiting_approval": f"{spec.name}: approval needed", "needs_input": f"{spec.name}: input needed", "completed": f"{spec.name} finished"}[task.status]
        session.add(Notification(user_id=user.id, kind="agent", title=title, body=(task.output or {}).get("summary", "")[:400], link=f"#/executions/{task.id}"))
    session.commit()
    if task.status in ("completed", "failed", "awaiting_approval"):
        webhooks.dispatch(session, org_id, f"agent.task.{task.status}", {"task_id": task.id, "agent": agent_id, "project_id": task.project_id, "status": task.status})
        session.commit()
    return task


# ------------------------------------------------------------------ supervisor
def supervise(ctx: AgentContext) -> Result:
    request = str(ctx.params.get("request", "")).strip()
    if not request:
        return Result("A request is needed.", status="needs_input", needs_input="Describe what you want done, e.g. 'Analyze these vendor quotations'.")
    forced = ctx.params.get("agents")
    if forced:
        p = {"agents": [a for a in forced if a in AGENTS and a not in ("supervisor", "workflow")], "reasons": {a: "selected by the user" for a in forced}, "by": "user"}
    else:
        p = (llm_layer.plan_with_llm(ctx.app, request, ctx.project is not None) if ctx.params.get("use_llm", True) is not False else None) or {**router.plan(request), "by": "rules"}
        if p["by"] == "llm":
            ctx.llm_used = 1
    agents = [a for a in p["agents"] if a != "workflow"] if ctx.project else p["agents"]
    if "workflow" in p["agents"]:
        wf = ctx.session.scalar(select(Workflow).where(Workflow.org_id == ctx.project.org_id, Workflow.is_active.is_(True)))
        named = [w for w in ctx.session.scalars(select(Workflow).where(Workflow.org_id == ctx.project.org_id)) if w.name.lower() in request.lower()]
        if named:
            agents.append("workflow")
            ctx.params["workflow_id"] = named[0].id
        del wf
    rows, child_ids, parts, overall, need_msg, evidence = [], [], [], "completed", None, []
    stopped = False
    for a in agents:
        if stopped:
            rows.append([AGENTS[a].name, p["reasons"].get(a, ""), "skipped", "A previous step needs attention first."])
            continue
        child = run_agent(ctx.session, ctx.app, ctx.user, a, project_id=ctx.project.id, params=router.params_for(a, request, {"workflow_id": ctx.params.get("workflow_id")} if a == "workflow" else {}), parent_id=ctx.task_id)
        child_ids.append(child.id)
        summ = (child.output or {}).get("summary", "")
        rows.append([AGENTS[a].name, p["reasons"].get(a, ""), child.status, summ[:240]])
        parts.append(f"{AGENTS[a].name}: {summ}")
        evidence += (child.output or {}).get("evidence", [])[:3]
        if child.status in ("needs_input", "failed"):
            stopped, need_msg = True, ((child.output or {}).get("needs_input") or summ)
            overall = "needs_input" if child.status == "needs_input" else "failed"
        elif child.status == "awaiting_approval" and overall == "completed":
            overall = "awaiting_approval"
    secs = [{"type": "table", "title": "Execution plan", "columns": ["Agent", "Why it was chosen", "Status", "Result"], "rows": rows}]
    # surface the first rich section of each completed child so the answer is readable in one place
    for cid in child_ids:
        c = ctx.session.get(AgentTask, cid)
        for s in ((c.output or {}).get("sections") or [])[:3]:
            secs.append({**s, "title": f"{AGENTS[c.agent].name}: {s.get('title', '')}"})
    summary = "Supervisor summary: " + " | ".join(parts) if parts else "No agent was run."
    return Result(summary, secs, evidence[:10], status=overall, needs_input=need_msg if overall == "needs_input" else None, data={"child_task_ids": child_ids, "plan": p}, labels={"routing": {"llm": "Agents were chosen by the language model (validated against the agent registry).", "user": "Agents were chosen by the user."}.get(p.get("by"), "Routing is rule-based; each step below was run and recorded as its own task.")}, llm_calls=ctx.llm_used)


# ------------------------------------------------------------------ approvals / cancel / retry
def _task_for(session: Session, user: User, task_id: str, write: bool) -> AgentTask:
    t = session.get(AgentTask, task_id)
    if t is None:
        raise NotFoundError("Task not found.")
    if t.project_id:
        get_project_for_user(session, user, t.project_id, write=write)
    elif t.user_id != user.id:
        raise NotFoundError("Task not found.")
    return t


def decide(session: Session, app: AppContext, user: User, task_id: str, approve: bool, note: str = "") -> AgentTask:
    t = _task_for(session, user, task_id, write=True)
    if t.status != "awaiting_approval":
        raise ValidationAppError("This task is not waiting for approval.")
    t.status = "completed" if approve else "rejected"
    t.approved_by = user.id
    out = dict(t.output or {})
    out["decision"] = {"approved": approve, "by": user.full_name, "note": note, "at": utcnow().isoformat()}
    t.output = out
    for child in session.scalars(select(AgentTask).where(AgentTask.parent_id == t.id, AgentTask.status == "awaiting_approval")):
        child.status, child.approved_by = ("completed" if approve else "rejected"), user.id
    record_audit(session, actor_id=user.id, action="agent.task.approved" if approve else "agent.task.rejected", resource_type="agent_task", resource_id=t.id, project_id=t.project_id, metadata={"agent": t.agent, "note_length": len(note)})
    session.add(Notification(user_id=t.user_id, kind="approval", title=f"{'Approved' if approve else 'Rejected'}: {t.agent.replace('_', ' ')}", body=note[:300], link=f"#/executions/{t.id}"))
    session.commit()
    if t.workflow_run_id:
        run = session.get(WorkflowRun, t.workflow_run_id)
        if run and run.status == "awaiting_approval":
            if approve:
                run.status = "running"
                session.commit()
                _advance(session, app, session.get(User, run.created_by), run)
            else:
                run.status, run.finished_at, run.error = "cancelled", utcnow(), "Rejected at an approval checkpoint."
                session.commit()
    return t


def cancel(session: Session, user: User, task_id: str) -> AgentTask:
    t = _task_for(session, user, task_id, write=True)
    if t.status not in ("awaiting_approval", "needs_input"):
        raise ValidationAppError("Only tasks waiting for approval or input can be cancelled (agents run to completion in-process).")
    t.status, t.finished_at = "cancelled", utcnow()
    record_audit(session, actor_id=user.id, action="agent.task.cancelled", resource_type="agent_task", resource_id=t.id, project_id=t.project_id)
    if t.workflow_run_id:
        run = session.get(WorkflowRun, t.workflow_run_id)
        if run and run.status in ("running", "awaiting_approval"):
            run.status, run.finished_at = "cancelled", utcnow()
    session.commit()
    return t


def retry(session: Session, app: AppContext, user: User, task_id: str) -> AgentTask:
    t = _task_for(session, user, task_id, write=True)
    if t.status not in ("failed", "needs_input", "cancelled"):
        raise ValidationAppError("Only failed, cancelled or input-needed tasks can be retried.")
    return run_agent(session, app, user, t.agent, project_id=t.project_id, params=t.params)


# ------------------------------------------------------------------ workflows
MAX_STEPS = 20


def validate_steps(steps: list[dict]) -> list[dict]:
    if not steps or len(steps) > MAX_STEPS:
        raise ValidationAppError(f"A workflow needs 1-{MAX_STEPS} steps.")
    out = []
    for i, s in enumerate(steps, 1):
        if s.get("type") == "approval":
            out.append({"type": "approval", "title": str(s.get("title") or "Approval checkpoint")[:120]})
        else:
            a = s.get("agent")
            if a not in AGENTS or a in ("supervisor", "workflow"):
                raise ValidationAppError(f"Step {i}: unknown or non-schedulable agent '{a}'.")
            if not isinstance(s.get("params", {}), dict):
                raise ValidationAppError(f"Step {i}: params must be an object.")
            out.append({"type": "agent", "agent": a, "params": s.get("params", {})})
    return out


def create_workflow(session: Session, user: User, name: str, description: str, steps: list[dict], project_id: str | None, schedule_minutes: int | None) -> Workflow:
    steps = validate_steps(steps)
    org_id = None
    if project_id:
        org_id = get_project_for_user(session, user, project_id, write=True).org_id
    else:
        org_id = org_service.resolve_org(session, user)[0].id
    if schedule_minutes:
        org = session.get(Organization, org_id)
        if org and org.plan == "free":
            raise org_service.PlanLimitError("Scheduled workflows need the Professional plan or higher.")
        if not project_id:
            raise ValidationAppError("A scheduled workflow must be bound to a project.")
        if schedule_minutes < 5:
            raise ValidationAppError("The minimum schedule interval is 5 minutes.")
    wf = Workflow(org_id=org_id, project_id=project_id, name=name.strip(), description=description, steps=steps, schedule_minutes=schedule_minutes, next_run_at=(utcnow() + timedelta(minutes=schedule_minutes)) if schedule_minutes else None, created_by=user.id)
    session.add(wf)
    session.flush()
    record_audit(session, actor_id=user.id, action="workflow.created", resource_type="workflow", resource_id=wf.id, project_id=project_id, metadata={"steps": len(steps)})
    session.commit()
    return wf


def get_workflow(session: Session, user: User, workflow_id: str, write: bool = False) -> Workflow:
    wf = session.get(Workflow, workflow_id)
    if wf is None:
        raise NotFoundError("Workflow not found.")
    if wf.project_id:
        get_project_for_user(session, user, wf.project_id, write=write)
    elif org_service.role_in_org(session, user, wf.org_id) is None:
        raise NotFoundError("Workflow not found.")
    return wf


def run_workflow(session: Session, app: AppContext, user: User, workflow_id: str, project_id: str | None = None, trigger: str = "manual") -> WorkflowRun:
    wf = get_workflow(session, user, workflow_id, write=True)
    pid = wf.project_id or project_id
    if not pid:
        raise ValidationAppError("Choose a project to run this workflow against.")
    get_project_for_user(session, user, pid, write=True)
    run = WorkflowRun(workflow_id=wf.id, project_id=pid, org_id=wf.org_id, created_by=user.id, trigger=trigger)
    session.add(run)
    session.flush()
    record_audit(session, actor_id=user.id, action="workflow.run.started", resource_type="workflow_run", resource_id=run.id, project_id=pid, metadata={"trigger": trigger})
    session.commit()
    _advance(session, app, user, run)
    return run


def _finish(session: Session, run: WorkflowRun, status: str, error: str | None = None) -> None:
    run.status, run.error, run.finished_at = status, error, utcnow()
    session.add(Notification(user_id=run.created_by, kind="workflow", title=f"Workflow {status}", body=(error or "")[:300], link=f"#/workflows/{run.workflow_id}"))
    record_audit(session, actor_id=run.created_by, action=f"workflow.run.{status}", resource_type="workflow_run", resource_id=run.id, project_id=run.project_id)
    session.commit()
    if status in ("completed", "failed"):
        webhooks.dispatch(session, run.org_id, f"workflow.run.{status}", {"run_id": run.id, "workflow_id": run.workflow_id, "status": status})
        session.commit()


def _advance(session: Session, app: AppContext, user: User, run: WorkflowRun) -> None:
    wf = session.get(Workflow, run.workflow_id)
    steps = wf.steps
    while run.cursor < len(steps):
        step = steps[run.cursor]
        run.cursor += 1
        session.commit()
        if step.get("type") == "approval":
            session.add(AgentTask(org_id=run.org_id, project_id=run.project_id, user_id=run.created_by, agent="approval", workflow_run_id=run.id, params=step, status="awaiting_approval", requires_approval=True, output={"summary": step.get("title", "Approval checkpoint"), "sections": [], "evidence": [], "needs_input": None, "labels": {}, "data": {}}))
            run.status = "awaiting_approval"
            session.add(Notification(user_id=run.created_by, kind="approval", title="Workflow waiting for approval", body=step.get("title", ""), link="#/executions"))
            session.commit()
            return
        t = run_agent(session, app, user, step["agent"], project_id=run.project_id, params=step.get("params"), workflow_run_id=run.id)
        if t.status in ("failed", "needs_input"):
            msg = (t.output or {}).get("needs_input") or t.error or (t.output or {}).get("summary", "")
            _finish(session, run, "failed", f"Step {run.cursor} ({step['agent']}) {'needs input' if t.status == 'needs_input' else 'failed'}: {msg}")
            return
        if t.status == "awaiting_approval":
            run.status = "awaiting_approval"
            session.commit()
            return
    _finish(session, run, "completed")


def cancel_run(session: Session, user: User, run_id: str) -> WorkflowRun:
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("Workflow run not found.")
    get_workflow(session, user, run.workflow_id, write=True)
    if run.status not in ("running", "awaiting_approval"):
        raise ValidationAppError("This run has already finished.")
    for t in session.scalars(select(AgentTask).where(AgentTask.workflow_run_id == run.id, AgentTask.status == "awaiting_approval")):
        t.status, t.finished_at = "cancelled", utcnow()
    _finish(session, run, "cancelled", "Cancelled by a user.")
    return run


def run_workflow_agent(ctx: AgentContext) -> Result:
    wid = ctx.params.get("workflow_id")
    if not wid:
        return Result("workflow_id is required.", status="needs_input", needs_input="Choose a saved workflow to run.")
    run = run_workflow(ctx.session, ctx.app, ctx.user, wid, ctx.params.get("project_id") or (ctx.project.id if ctx.project else None))
    steps = ctx.session.scalars(select(AgentTask).where(AgentTask.workflow_run_id == run.id).order_by(AgentTask.created_at)).all()
    rows = [[t.agent, t.status, (t.output or {}).get("summary", "")[:200]] for t in steps]
    status = "awaiting_approval" if run.status == "awaiting_approval" else "completed"
    return Result(f"Workflow run {run.status}." + (f" {run.error}" if run.error else ""), [{"type": "table", "title": "Steps", "columns": ["Agent", "Status", "Result"], "rows": rows}], status="failed" if run.status == "failed" else status, data={"workflow_run_id": run.id, "run_status": run.status})


def run_due_workflows(app: AppContext) -> int:
    """Execute workflows whose schedule is due. Called by the in-process scheduler or POST /workflows/run-due."""
    factory = get_session_factory()
    ran = 0
    with factory() as s:
        due = list(s.scalars(select(Workflow).where(Workflow.is_active.is_(True), Workflow.schedule_minutes.is_not(None), Workflow.next_run_at <= utcnow())))
        for wf in due:
            wf.next_run_at = utcnow() + timedelta(minutes=wf.schedule_minutes or 60)
            s.commit()
            owner = s.get(User, wf.created_by)
            if owner is None or not owner.is_active:
                continue
            try:
                run_workflow(s, app, owner, wf.id, trigger="schedule")
                ran += 1
            except AppError as exc:
                logger.warning("Scheduled workflow could not start: %s", exc.message)
                s.rollback()
    return ran
