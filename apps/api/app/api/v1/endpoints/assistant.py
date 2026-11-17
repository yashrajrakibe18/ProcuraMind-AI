from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB, Ctx, CurrentUser
from procureai.application.dto.schemas import AssistantAnswer, AssistantQuery
from procureai.application.services import assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/query",
    response_model=AssistantAnswer,
    summary="Ask a grounded question against this project's documents (cited or 'insufficient evidence')",
)
def query(data: AssistantQuery, db: DB, ctx: Ctx, user: CurrentUser):
    return assistant_service.ask(db, ctx, user, data)
