from __future__ import annotations

from sqlalchemy.orm import Session

from procureai.application.context import AppContext
from procureai.application.dto.schemas import AssistantAnswer, AssistantQuery, CitationOut
from procureai.application.services.access import get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.infrastructure.database.models import User
from procureai.rag.answer_generation.answerer import generate_answer


def ask(session: Session, ctx: AppContext, user: User, data: AssistantQuery) -> AssistantAnswer:
    """Grounded Q&A restricted to the caller's own project documents."""
    project = get_project_for_user(session, user, data.project_id)
    passages = ctx.retriever.retrieve(project.id, data.question, top_k=data.top_k)
    answer = generate_answer(data.question, passages, ctx.llm)
    record_audit(
        session,
        actor_id=user.id,
        action="assistant.queried",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
        metadata={"mode": answer.mode, "citations": len(answer.citations), "question_length": len(data.question)},
    )
    session.commit()
    return AssistantAnswer(
        answer=answer.answer,
        grounded=answer.grounded,
        mode=answer.mode,
        citations=[CitationOut(**c.__dict__) for c in answer.citations],
    )
