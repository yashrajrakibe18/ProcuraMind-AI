"""Document upload validation, processing (text/OCR/tables), classification, indexing and deletion."""

from __future__ import annotations

import logging
import re
from pathlib import PurePath

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.application.context import AppContext
from procureai.application.services.access import get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.document_processing.classification.classifier import classify_text
from procureai.document_processing.extraction.historical import (
    looks_like_historical_csv,
    parse_historical_csv,
)
from procureai.document_processing.loaders.loader import PageContent, count_pdf_pages, load_pages
from procureai.infrastructure.database.models import Document, DocumentPage, HistoricalPurchase, User
from procureai.shared.enums import DocumentType, ProcessingStatus
from procureai.shared.errors import ConflictError, NotFoundError, ProcessingError, ValidationAppError

logger = logging.getLogger(__name__)

_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_ZIP = (b"PK\x03\x04",)
_MAGIC = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _ZIP,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _ZIP,
    "application/pdf": (b"%PDF",), "image/png": (b"\x89PNG",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
AUTO = "auto"


def safe_filename(name: str) -> str:
    base = PurePath((name or "").replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._\- ()]", "_", base).strip(" .")
    return base[:200] or "document"


def validate_upload(filename: str, data: bytes, ctx: AppContext) -> tuple[str, str, str]:
    """Validate extension, size, content signature and (for PDFs) page count. Returns (name, ext, mime)."""
    s = ctx.settings
    name = safe_filename(filename)
    ext = PurePath(name).suffix.lower()
    if ext not in s.extensions or ext not in _MIME_BY_EXT:
        raise ValidationAppError(f"File type '{ext or 'unknown'}' is not allowed.", {"allowed": sorted(s.extensions)})
    if not data:
        raise ValidationAppError("The uploaded file is empty.")
    if len(data) > s.max_upload_bytes:
        raise ValidationAppError(f"File exceeds the {s.max_upload_size_mb} MB size limit.")
    mime = _MIME_BY_EXT[ext]
    if mime in _MAGIC:
        if not data.startswith(_MAGIC[mime]):
            raise ValidationAppError("File content does not match its extension.")
    else:
        if b"\x00" in data[:4096]:
            raise ValidationAppError("File content does not look like text.")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationAppError("Text files must be UTF-8 encoded.") from exc
    return name, ext, mime


def upload_document(
    session: Session,
    ctx: AppContext,
    user: User,
    project_id: str,
    filename: str,
    data: bytes,
    document_type: str = AUTO,
) -> Document:
    project = get_project_for_user(session, user, project_id, write=True)
    if document_type != AUTO and document_type not in {t.value for t in DocumentType}:
        raise ValidationAppError(f"Unknown document_type '{document_type}'.")
    name, ext, mime = validate_upload(filename, data, ctx)
    key, checksum = ctx.storage.save(data, ext)
    try:
        if mime == "application/pdf":
            try:
                pages = count_pdf_pages(ctx.storage.path_for(key))
            except Exception as exc:  # corrupt/encrypted PDFs raise assorted fitz errors
                raise ValidationAppError("The PDF could not be read (corrupt or encrypted).") from exc
            if pages > ctx.settings.max_pdf_pages:
                raise ValidationAppError(f"PDF exceeds the {ctx.settings.max_pdf_pages}-page limit.")
        if session.scalar(select(Document.id).where(Document.project_id == project.id, Document.checksum == checksum)):
            raise ConflictError("This exact file has already been uploaded to the project.")
    except Exception:
        ctx.storage.delete(key)
        raise
    doc = Document(
        project_id=project.id,
        storage_key=key,
        original_filename=name,
        mime_type=mime,
        size_bytes=len(data),
        document_type=DocumentType.OTHER.value if document_type == AUTO else document_type,
        checksum=checksum,
        processing_status=ProcessingStatus.PENDING.value,
        uploaded_by=user.id,
    )
    doc.classification_confidence = 0.0 if document_type == AUTO else 1.0
    doc.auto_classify = document_type == AUTO
    session.add(doc)
    session.flush()
    record_audit(
        session,
        actor_id=user.id,
        action="document.uploaded",
        resource_type="document",
        resource_id=doc.id,
        project_id=project.id,
        metadata={"mime": mime, "size_bytes": len(data), "requested_type": document_type},
    )
    session.commit()
    return doc


def process_document(session: Session, ctx: AppContext, document_id: str) -> Document:
    """Extract text per page (OCR fallback), classify, persist pages, ingest history and index vectors."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document not found.")
    auto = doc.auto_classify
    doc.processing_error = None
    try:
        pages: list[PageContent] = load_pages(
            ctx.storage.path_for(doc.storage_key),
            doc.mime_type,
            ctx.settings.ocr_min_chars_per_page,
            ctx.settings.max_pdf_pages,
        )
        full_text = "\n".join(p.text for p in pages)
        if not full_text.strip():
            raise ProcessingError("No readable text was found in the document (OCR also produced no text).")
        if auto:
            if doc.mime_type == "text/csv" and looks_like_historical_csv(full_text):
                doc.document_type, doc.classification_confidence = DocumentType.HISTORICAL.value, 0.9
            else:
                dtype, conf = classify_text(full_text, doc.original_filename)
                doc.document_type, doc.classification_confidence = dtype.value, conf
        session.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
        session.add_all(
            DocumentPage(document_id=doc.id, page_number=p.page_number, text=p.text, ocr_used=p.ocr_used) for p in pages
        )
        doc.page_count = len(pages)
        if doc.document_type == DocumentType.HISTORICAL.value:
            _ingest_history(session, doc, full_text)
        else:
            ctx.indexer.index(
                project_id=doc.project_id,
                document_id=doc.id,
                document_type=doc.document_type,
                filename=doc.original_filename,
                pages=[(p.page_number, p.text) for p in pages],
            )
        doc.processing_status = ProcessingStatus.PROCESSED.value
    except ProcessingError as exc:
        doc.processing_status, doc.processing_error = ProcessingStatus.FAILED.value, exc.message
    except Exception:  # boundary: never leak internals; keep the stack trace in logs
        logger.exception("Unexpected document processing failure", extra={"document_id": doc.id})
        doc.processing_status = ProcessingStatus.FAILED.value
        doc.processing_error = "Processing failed unexpectedly. The incident was logged."
    record_audit(
        session,
        actor_id=doc.uploaded_by,
        action="document.processed",
        resource_type="document",
        resource_id=doc.id,
        project_id=doc.project_id,
        metadata={"status": doc.processing_status, "type": doc.document_type, "pages": doc.page_count},
    )
    session.commit()
    return doc


def _ingest_history(session: Session, doc: Document, text: str) -> None:
    rows, skipped = parse_historical_csv(text)
    if not rows:
        raise ProcessingError("No valid purchase rows found. Expected columns such as item, unit_price, currency.")
    session.execute(
        delete(HistoricalPurchase).where(
            HistoricalPurchase.project_id == doc.project_id, HistoricalPurchase.source_document_id == doc.id
        )
    )
    session.add_all(
        HistoricalPurchase(
            project_id=doc.project_id,
            source_document_id=doc.id,
            item_category=r.item_category,
            unit_price=r.unit_price,
            currency=r.currency,
            purchased_on=r.purchased_on,
            supplier=r.supplier,
        )
        for r in rows
    )
    if skipped:
        logger.info("Skipped %s invalid historical rows", skipped, extra={"document_id": doc.id})


def get_document(session: Session, user: User, document_id: str) -> Document:
    doc = session.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document not found.")
    get_project_for_user(session, user, doc.project_id)
    return doc


def list_documents(session: Session, user: User, project_id: str) -> list[Document]:
    get_project_for_user(session, user, project_id)
    return list(
        session.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at))
    )


def get_pages(session: Session, doc: Document) -> list[DocumentPage]:
    return list(
        session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == doc.id).order_by(DocumentPage.page_number)
        )
    )


def delete_document(session: Session, ctx: AppContext, user: User, document_id: str) -> None:
    doc = get_document(session, user, document_id)
    get_project_for_user(session, user, doc.project_id, write=True)
    ctx.store.delete_document(doc.id)
    ctx.storage.delete(doc.storage_key)
    record_audit(
        session,
        actor_id=user.id,
        action="document.deleted",
        resource_type="document",
        resource_id=doc.id,
        project_id=doc.project_id,
    )
    session.delete(doc)
    session.commit()
