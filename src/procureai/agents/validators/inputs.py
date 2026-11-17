"""Pre-flight validation of a project's inputs before any analysis runs."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.infrastructure.database.models import Document, TenderRequirement
from procureai.shared.enums import DocumentType, ProcessingStatus
from procureai.shared.errors import ValidationAppError


def validate_inputs(session: Session, project_id: str, auto_confirm: bool) -> dict:
    def n(dtype: DocumentType) -> int:
        return (
            session.scalar(
                select(func.count())
                .select_from(Document)
                .where(
                    Document.project_id == project_id,
                    Document.document_type == dtype.value,
                    Document.processing_status == ProcessingStatus.PROCESSED.value,
                )
            )
            or 0
        )

    pending = (
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.project_id == project_id, Document.processing_status == ProcessingStatus.PENDING.value)
        )
        or 0
    )
    if pending:
        raise ValidationAppError(f"{pending} document(s) are still processing. Try again when they finish.")
    problems = []
    if n(DocumentType.TENDER) == 0:
        problems.append("a processed tender document")
    if n(DocumentType.QUOTATION) == 0:
        problems.append("at least one processed vendor quotation")
    if problems:
        raise ValidationAppError("Missing required input: " + " and ".join(problems) + ".")
    if not auto_confirm:
        unconfirmed = (
            session.scalar(
                select(func.count())
                .select_from(TenderRequirement)
                .where(TenderRequirement.project_id == project_id, TenderRequirement.confirmed.is_(False))
            )
            or 0
        )
        if unconfirmed:
            raise ValidationAppError(
                f"{unconfirmed} extracted requirement(s) are not confirmed. Review and confirm them first, "
                "or start the analysis with auto_confirm enabled."
            )
    return {
        "tender_documents": n(DocumentType.TENDER),
        "quotation_documents": n(DocumentType.QUOTATION),
        "policy_documents": n(DocumentType.POLICY),
        "historical_documents": n(DocumentType.HISTORICAL),
    }
