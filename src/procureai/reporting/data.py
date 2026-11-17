"""Assembles everything a report needs from one analysis run, with provenance labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.application.dto.schemas import ComplianceResultOut, PriceAnalysisOut
from procureai.application.services import analysis_service
from procureai.infrastructure.database.models import (
    AgentRun,
    Document,
    PolicyEvidence,
    ProcurementProject,
    ReviewItem,
    TenderRequirement,
    Vendor,
)
from procureai.shared.enums import ComplianceStatus

LEGEND = {
    "Source fact": "Value read from an uploaded document; cited with document and page.",
    "Calculated": "Computed deterministically by the system (totals, deviations, rule outcomes).",
    "Model interpretation": "Advisory text produced by a language model. Never decides a result.",
    "Unresolved": "Open question that needs a person's review before relying on the result.",
}
DISCLAIMER = (
    "ProcureAI is decision-support software. It does not award contracts. Statistical price flags "
    "indicate deviation for review only and are not findings of overpricing or misconduct."
)
STATUS_ORDER = [s.value for s in ComplianceStatus]


@dataclass
class ReportData:
    project: ProcurementProject
    run: AgentRun
    generated_at: datetime
    documents: dict[str, str]
    requirements: list[TenderRequirement]
    vendors: list[Vendor]
    compliance: list[ComplianceResultOut]
    prices: list[PriceAnalysisOut]
    policy: list[PolicyEvidence]
    reviews: list[ReviewItem]
    counts_by_vendor: dict[str, dict[str, int]] = field(default_factory=dict)

    def doc_name(self, document_id: str | None) -> str:
        return self.documents.get(document_id or "", "unknown document")


def collect(session: Session, project_id: str, run: AgentRun) -> ReportData:
    from procureai.shared.types import utcnow

    project = session.get(ProcurementProject, project_id)
    docs = {
        d.id: d.original_filename for d in session.scalars(select(Document).where(Document.project_id == project_id))
    }
    compliance = analysis_service.compliance_rows(session, run)
    counts: dict[str, dict[str, int]] = {}
    for r in compliance:
        counts.setdefault(r.vendor_name, {s: 0 for s in STATUS_ORDER})[r.effective_status] += 1
    return ReportData(
        project=project,
        run=run,
        generated_at=utcnow(),
        documents=docs,
        requirements=list(
            session.scalars(
                select(TenderRequirement)
                .where(TenderRequirement.project_id == project_id, TenderRequirement.confirmed.is_(True))
                .order_by(TenderRequirement.created_at, TenderRequirement.id)
            )
        ),
        vendors=list(
            session.scalars(select(Vendor).where(Vendor.project_id == project_id).order_by(Vendor.created_at))
        ),
        compliance=compliance,
        prices=analysis_service.price_rows(session, run),
        policy=analysis_service.policy_evidence_rows(session, run),
        reviews=list(
            session.scalars(
                select(ReviewItem)
                .where(ReviewItem.run_id == run.id)
                .order_by(ReviewItem.status.desc(), ReviewItem.kind)
            )
        ),
        counts_by_vendor=counts,
    )


def req_text(r: TenderRequirement) -> str:
    return (
        f"{r.operator} {r.required_value}"
        + (f"–{r.required_value_max}" if r.required_value_max else "")
        + (f" {r.unit}" if r.unit else "")
    )
