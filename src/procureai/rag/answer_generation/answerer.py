"""Grounded answer generation with page-level citations.

* LLM available: answer from numbered excerpts; citations are validated against the excerpts supplied.
* No LLM (or LLM failure): extractive answer built from the most relevant sentences, clearly labelled.
* No passage above the relevance threshold: an explicit 'insufficient evidence' answer (never fabricated).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from procureai.agents.prompts.templates import ANSWER_SYSTEM, answer_user_prompt
from procureai.infrastructure.llm.client import LLMClient
from procureai.rag.embeddings.hashing import analyze
from procureai.rag.retrieval.retriever import Passage
from procureai.shared.errors import ExternalServiceError

logger = logging.getLogger(__name__)
INSUFFICIENT = "I could not find sufficient evidence for this in the documents you are permitted to access."


@dataclass
class Citation:
    marker: int
    document_id: str
    filename: str
    page: int | None
    chunk_id: str
    snippet: str
    score: float


@dataclass
class Answer:
    answer: str
    grounded: bool
    mode: str  # "llm" | "extractive" | "insufficient_evidence"
    citations: list[Citation] = field(default_factory=list)


def _best_sentences(question: str, text: str, limit: int = 2) -> str:
    q = set(analyze(question))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 15]
    scored = sorted(
        ((len(q & set(analyze(s))) / (len(set(analyze(s))) ** 0.5 or 1), i, s) for i, s in enumerate(sentences)),
        reverse=True,
    )
    picked = sorted(scored[:limit], key=lambda t: t[1])
    return " ".join(s for _, _, s in picked) or text[:300]


def _citation(n: int, p: Passage) -> Citation:
    return Citation(n, p.document_id, p.filename, p.page, p.chunk_id, p.text[:400], p.score)


def generate_answer(question: str, passages: list[Passage], llm: LLMClient) -> Answer:
    if not passages:
        return Answer(INSUFFICIENT, grounded=False, mode="insufficient_evidence")
    top = passages[:5]
    citations = [_citation(i, p) for i, p in enumerate(top, 1)]
    if llm.available():
        try:
            raw = llm.complete(
                ANSWER_SYSTEM,
                answer_user_prompt(question, [(i, p.filename, p.page, p.text) for i, p in enumerate(top, 1)]),
            )
            if "INSUFFICIENT_EVIDENCE" in raw:
                return Answer(INSUFFICIENT, grounded=False, mode="insufficient_evidence")
            used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", raw) if 1 <= int(n) <= len(top)})
            if used:  # ungrounded (citation-free) model output is discarded
                return Answer(raw, grounded=True, mode="llm", citations=[c for c in citations if c.marker in used])
        except ExternalServiceError:
            logger.warning("LLM unavailable for assistant answer; using extractive fallback")
    lines = [f"{_best_sentences(question, p.text)} [{i}]" for i, p in enumerate(top[:3], 1)]
    return Answer(
        "Relevant passages (extractive summary, not model-generated):\n- " + "\n- ".join(lines),
        grounded=True,
        mode="extractive",
        citations=citations[:3],
    )
