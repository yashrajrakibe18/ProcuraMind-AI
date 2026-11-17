"""Project-scoped retrieval: dense (hashed n-gram), lexical (BM25) or hybrid with reciprocal-rank fusion + rerank.

Hybrid mode adds a relevance gate: a passage must share at least one content term with the query, which stops
unrelated questions from being "answered" by whatever happens to be nearest in vector space.
"""

from __future__ import annotations

from dataclasses import dataclass

from procureai.infrastructure.vector_store.chroma_store import ChromaVectorStore, Hit
from procureai.rag.embeddings.hashing import HashingEmbedder
from procureai.rag.retrieval.bm25 import BM25, tokens

RRF_K = 60


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    document_id: str
    filename: str
    document_type: str
    page: int | None
    section: str
    text: str
    score: float


def _passage(h: Hit, score: float) -> Passage:
    m = h.metadata
    return Passage(h.chunk_id, m.get("document_id", ""), m.get("filename", ""), m.get("document_type", ""), m.get("page"), m.get("section", ""), h.text, round(score, 4))


class Retriever:
    def __init__(self, store: ChromaVectorStore, embedder: HashingEmbedder, min_score: float, mode: str = "hybrid"):
        self.store, self.embedder, self.min_score, self.mode = store, embedder, min_score, mode

    def retrieve(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
        document_types: list[str] | None = None,
        mode: str | None = None,
    ) -> list[Passage]:
        if not query.strip():
            return []
        mode = mode or self.mode
        if mode == "vector":
            return self._vector(project_id, query, top_k, document_types)
        return self._hybrid(project_id, query, top_k, document_types, lexical_only=(mode == "bm25"))

    def _vector(self, project_id: str, query: str, top_k: int, types: list[str] | None) -> list[Passage]:
        emb = self.embedder.embed([query])[0]
        return [_passage(h, h.score) for h in self.store.query(project_id, emb, top_k=top_k, document_types=types) if h.score >= self.min_score]

    def _hybrid(self, project_id: str, query: str, top_k: int, types: list[str] | None, lexical_only: bool) -> list[Passage]:
        chunks = self.store.all_chunks(project_id, types)
        if not chunks:
            return []
        q = tokens(query)
        if not q:
            return []
        bm = BM25([tokens(c.text) for c in chunks])
        lex = bm.rank(q)  # [(index, score)] only chunks sharing >=1 query term
        if not lex:
            return []
        pool = max(top_k * 4, 12)
        fused: dict[str, float] = {}
        for rank, (i, _) in enumerate(lex[:pool]):
            fused[chunks[i].chunk_id] = fused.get(chunks[i].chunk_id, 0.0) + 1 / (RRF_K + rank + 1)
        vec_score: dict[str, float] = {}
        if not lexical_only:
            emb = self.embedder.embed([query])[0]
            for rank, h in enumerate(self.store.query(project_id, emb, top_k=pool, document_types=types)):
                vec_score[h.chunk_id] = h.score
                fused[h.chunk_id] = fused.get(h.chunk_id, 0.0) + 1 / (RRF_K + rank + 1)
        by_id = {c.chunk_id: c for c in chunks}
        lex_ids = {chunks[i].chunk_id for i, _ in lex}
        qset = set(q)
        out: list[tuple[float, Passage]] = []
        for cid, rrf in fused.items():
            if cid not in lex_ids:  # relevance gate: needs lexical overlap
                continue
            c = by_id[cid]
            ctoks = set(tokens(c.text))
            coverage = len(qset & ctoks) / len(qset)  # heuristic rerank signal: share of query terms present
            score = 0.5 * min(1.0, rrf * (RRF_K + 1) / 2) + 0.5 * coverage
            out.append((score, _passage(c, score)))
        out.sort(key=lambda x: -x[0])
        return [p for _, p in out[:top_k]]
