from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import DB, Ctx, CurrentUser
from procureai.application.context import AppContext
from procureai.application.dto.schemas import DocumentOut, DocumentPageOut
from procureai.application.services import document_service
from procureai.infrastructure.database.session import get_session_factory
from procureai.shared.errors import ValidationAppError

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


def _process_in_background(ctx: AppContext, document_id: str) -> None:
    with get_session_factory()() as session:
        document_service.process_document(session, ctx, document_id)


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentOut,
    status_code=201,
    summary="Upload and register a document; processing continues in the background",
)
def upload(
    project_id: str,
    background: BackgroundTasks,
    db: DB,
    ctx: Ctx,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    document_type: Annotated[str, Form()] = "auto",
):
    data = file.file.read(ctx.settings.max_upload_bytes + 1)  # bounded read: never buffer unbounded uploads
    if len(data) > ctx.settings.max_upload_bytes:
        raise ValidationAppError(f"File exceeds the {ctx.settings.max_upload_size_mb} MB size limit.")
    doc = document_service.upload_document(db, ctx, user, project_id, file.filename or "", data, document_type)
    background.add_task(_process_in_background, ctx, doc.id)
    return doc


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(project_id: str, db: DB, user: CurrentUser):
    return document_service.list_documents(db, user, project_id)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: DB, user: CurrentUser):
    return document_service.get_document(db, user, document_id)


@router.get("/documents/{document_id}/pages", response_model=list[DocumentPageOut])
def get_pages(document_id: str, db: DB, user: CurrentUser):
    return document_service.get_pages(db, document_service.get_document(db, user, document_id))


@router.get("/documents/{document_id}/file", summary="Download the original file (for side-by-side review)")
def download_original(document_id: str, db: DB, ctx: Ctx, user: CurrentUser):
    doc = document_service.get_document(db, user, document_id)
    return FileResponse(
        ctx.storage.path_for(doc.storage_key),
        media_type=doc.mime_type,
        filename=doc.original_filename,
        content_disposition_type="attachment",
    )


@router.post("/documents/{document_id}/reprocess", response_model=DocumentOut, status_code=202)
def reprocess(document_id: str, background: BackgroundTasks, db: DB, ctx: Ctx, user: CurrentUser):
    doc = document_service.get_document(db, user, document_id)
    doc.processing_status, doc.processing_error = "pending", None
    db.commit()
    background.add_task(_process_in_background, ctx, doc.id)
    return doc


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, db: DB, ctx: Ctx, user: CurrentUser) -> Response:
    document_service.delete_document(db, ctx, user, document_id)
    return Response(status_code=204)
