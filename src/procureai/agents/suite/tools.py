"""Tool registry. Agents never touch the database or files directly; they call declared, permission-checked tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import select

from procureai.agents.suite.base import AgentContext
from procureai.application.services import analysis_service, extraction_service, report_service
from procureai.infrastructure.database.models import (
    AgentRun,
    AgentTask,
    AuditEvent,
    Document,
    DocumentPage,
    Notification,
    ProcurementProject,
    ReviewItem,
    Vendor,
)
from procureai.infrastructure.database.session import get_session_factory
from procureai.shared.errors import ValidationAppError
from procureai.shared.types import utcnow


@dataclass(frozen=True)
class Tool:
    name: str
    permission: str
    fn: Callable[..., Any]
    description: str


def _project(ctx: AgentContext) -> ProcurementProject:
    if ctx.project is None:
        raise ValidationAppError("This action needs a project.")
    return ctx.project


def project_documents(ctx: AgentContext, types: list[str] | None = None, mimes: tuple[str, ...] | None = None) -> list[Document]:
    p = _project(ctx)
    docs = list(ctx.session.scalars(select(Document).where(Document.project_id == p.id, Document.processing_status == "processed").order_by(Document.created_at)))
    if types:
        docs = [d for d in docs if d.document_type in types]
    if mimes:
        docs = [d for d in docs if d.mime_type in mimes]
    return docs


def document_pages(ctx: AgentContext, doc: Document) -> list[tuple[int, str]]:
    rows = ctx.session.scalars(select(DocumentPage).where(DocumentPage.document_id == doc.id).order_by(DocumentPage.page_number))
    return [(r.page_number, r.text) for r in rows]


def load_dataframe(ctx: AgentContext, doc: Document, max_rows: int = 100_000) -> pd.DataFrame:
    path = ctx.app.storage.path_for(doc.storage_key)
    if doc.mime_type == "text/csv":
        return pd.read_csv(path, nrows=max_rows)
    if doc.mime_type.endswith("spreadsheetml.sheet"):
        return pd.read_excel(path, nrows=max_rows)
    raise ValidationAppError("Only CSV and XLSX files can be loaded as datasets.")


def retrieve(ctx: AgentContext, query: str, k: int = 5, types: list[str] | None = None, mode: str | None = None):
    return ctx.app.retriever.retrieve(_project(ctx).id, query, top_k=k, document_types=types, mode=mode)


def latest_run(ctx: AgentContext) -> AgentRun | None:
    return analysis_service.latest_result_run(ctx.session, _project(ctx).id)


def compliance_rows(ctx: AgentContext, run: AgentRun):
    return analysis_service.compliance_rows(ctx.session, run)


def price_rows(ctx: AgentContext, run: AgentRun):
    return analysis_service.price_rows(ctx.session, run)


def open_review_items(ctx: AgentContext, run: AgentRun) -> list[ReviewItem]:
    return list(ctx.session.scalars(select(ReviewItem).where(ReviewItem.run_id == run.id, ReviewItem.status == "open")))


def list_vendors(ctx: AgentContext) -> list[Vendor]:
    return list(ctx.session.scalars(select(Vendor).where(Vendor.project_id == _project(ctx).id)))


def recent_tasks(ctx: AgentContext, limit: int = 20) -> list[AgentTask]:
    p = _project(ctx)
    return list(
        ctx.session.scalars(
            select(AgentTask).where(AgentTask.project_id == p.id, AgentTask.agent != "supervisor", AgentTask.status.in_(("completed", "awaiting_approval"))).order_by(AgentTask.created_at.desc()).limit(limit)
        )
    )


def recent_audit(ctx: AgentContext, limit: int = 30) -> list[AuditEvent]:
    return list(ctx.session.scalars(select(AuditEvent).where(AuditEvent.project_id == _project(ctx).id).order_by(AuditEvent.timestamp.desc()).limit(limit)))


def run_procurement(ctx: AgentContext, auto_confirm: bool = False) -> dict[str, Any]:
    """Prepare inputs and execute the existing LangGraph procurement workflow (synchronously) for this project."""
    p = _project(ctx)
    docs = project_documents(ctx)
    kinds = {d.document_type for d in docs}
    missing = [k for k in ("tender", "quotation") if k not in kinds]
    if missing:
        return {"needs_input": "Upload and process " + " and ".join(missing) + " document(s) first.", "run": None}
    reqs = extraction_service.list_requirements(ctx.session, ctx.user, p.id)
    if not reqs:
        extraction_service.extract_project_requirements(ctx.session, p.id, ctx.user.id)
        reqs = extraction_service.list_requirements(ctx.session, ctx.user, p.id)
    if not extraction_service.list_vendors(ctx.session, ctx.user, p.id):
        extraction_service.extract_project_vendors(ctx.session, p.id, ctx.user.id)
    unconfirmed = [r for r in reqs if not r.confirmed]
    if unconfirmed and not auto_confirm:
        return {"needs_input": f"{len(unconfirmed)} extracted requirement(s) need human confirmation before analysis. Review them on the Procurement page, or re-run with auto-confirm.", "run": None}
    run, created = analysis_service.start_run(ctx.session, ctx.app, ctx.user, p.id, auto_confirm)
    if created:
        analysis_service.execute_run(ctx.app, get_session_factory(), run.id)
    ctx.session.expire_all()
    run = ctx.session.get(AgentRun, run.id)
    return {"needs_input": None, "run": run}


def make_report(ctx: AgentContext, kind: str):
    return report_service.generate_report(ctx.session, ctx.app, ctx.user, _project(ctx).id, kind, None)


def notify(ctx: AgentContext, title: str, body: str = "", kind: str = "info", link: str | None = None) -> None:
    ctx.session.add(Notification(user_id=ctx.user.id, kind=kind, title=title[:255], body=body, link=link))


def today():
    return utcnow().date()


_T = [
    Tool("project_documents", "read", project_documents, "List processed documents of the project"),
    Tool("document_pages", "read", document_pages, "Read the stored text of a document, page by page"),
    Tool("load_dataframe", "read", load_dataframe, "Load a CSV/XLSX document as a table"),
    Tool("retrieve", "read", retrieve, "Hybrid (vector + BM25) retrieval within the project"),
    Tool("latest_run", "read", latest_run, "Latest finished procurement analysis run"),
    Tool("compliance_rows", "read", compliance_rows, "Vendor-by-requirement compliance results"),
    Tool("price_rows", "read", price_rows, "Normalised price analysis rows"),
    Tool("open_review_items", "read", open_review_items, "Open human-review items of a run"),
    Tool("list_vendors", "read", list_vendors, "Vendors with extracted quotations"),
    Tool("recent_tasks", "read", recent_tasks, "Recent completed agent tasks in the project"),
    Tool("recent_audit", "read", recent_audit, "Recent audit events of the project"),
    Tool("run_procurement", "write_results", run_procurement, "Execute the procurement analysis workflow"),
    Tool("make_report", "generate_files", make_report, "Generate a PDF or Excel report"),
    Tool("notify", "notify", notify, "Create an in-app notification for the requesting user"),
]
TOOLS: dict[str, Tool] = {t.name: t for t in _T}
