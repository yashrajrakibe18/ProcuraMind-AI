"""Policy evidence retrieval (project-scoped RAG) attached to a run."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.infrastructure.database.models import PolicyEvidence, TenderRequirement
from procureai.rag.retrieval.retriever import Retriever
from procureai.shared.enums import DocumentType

GENERAL_QUERIES = ["evaluation criteria and award procedure", "approval authority and bidding thresholds"]


def collect_policy_evidence(
    session: Session, run_id: str, project_id: str, retriever: Retriever, top_k: int = 2
) -> dict:
    session.execute(delete(PolicyEvidence).where(PolicyEvidence.run_id == run_id))
    reqs = list(
        session.scalars(
            select(TenderRequirement).where(
                TenderRequirement.project_id == project_id, TenderRequirement.confirmed.is_(True)
            )
        )
    )
    queries: list[tuple[str | None, str]] = [
        (r.id, f"{r.label} {r.required_value} {r.unit or ''} requirement") for r in reqs
    ]
    queries += [(None, q) for q in GENERAL_QUERIES]
    stored = 0
    for requirement_id, query in queries:
        for p in retriever.retrieve(project_id, query, top_k=top_k, document_types=[DocumentType.POLICY.value]):
            session.add(
                PolicyEvidence(
                    run_id=run_id,
                    project_id=project_id,
                    requirement_id=requirement_id,
                    chunk_id=p.chunk_id,
                    document_id=p.document_id,
                    page=p.page,
                    snippet=p.text[:600],
                    score=p.score,
                )
            )
            stored += 1
    session.flush()
    return {"queries": len(queries), "evidence_rows": stored}
