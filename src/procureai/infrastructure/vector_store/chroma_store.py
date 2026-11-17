"""ChromaDB adapter. Every read is filtered by project_id: one project can never retrieve another's chunks."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import chromadb
from chromadb.config import Settings as ChromaSettings

from procureai.shared.errors import ExternalServiceError

logger = logging.getLogger(__name__)
T = TypeVar("T")
COLLECTION = "procureai_chunks"
_clients: dict[str, chromadb.api.ClientAPI] = {}


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    text: str
    embedding: list[float]
    metadata: dict


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    text: str
    score: float
    metadata: dict


def _retry(fn: Callable[[], T], attempts: int = 3) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # boundary: vector DB driver raises many types
            last = exc
            logger.warning("Vector store operation failed (attempt %s): %s", i + 1, type(exc).__name__)
            time.sleep(0.1 * (i + 1))
    raise ExternalServiceError("The vector store is unavailable.") from last


class ChromaVectorStore:
    def __init__(self, path: str) -> None:
        if path not in _clients:
            _clients[path] = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self._client = _clients[path]
        self._col = _retry(lambda: self._client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"}))

    def upsert(self, chunks: list[StoredChunk]) -> None:
        if not chunks:
            return
        _retry(
            lambda: self._col.upsert(
                ids=[c.chunk_id for c in chunks],
                documents=[c.text for c in chunks],
                embeddings=[c.embedding for c in chunks],
                metadatas=[c.metadata for c in chunks],
            )
        )

    def delete_document(self, document_id: str) -> None:
        _retry(lambda: self._col.delete(where={"document_id": document_id}))

    def delete_project(self, project_id: str) -> None:
        _retry(lambda: self._col.delete(where={"project_id": project_id}))

    def count(self, project_id: str) -> int:
        res = _retry(lambda: self._col.get(where={"project_id": project_id}, include=[]))
        return len(res["ids"])

    def query(
        self, project_id: str, embedding: list[float], top_k: int = 5, document_types: list[str] | None = None
    ) -> list[Hit]:
        where: dict = {"project_id": project_id}
        if document_types:
            where = {"$and": [{"project_id": project_id}, {"document_type": {"$in": document_types}}]}
        total = self.count(project_id)
        if total == 0:
            return []
        res = _retry(
            lambda: self._col.query(
                query_embeddings=[embedding],
                n_results=min(top_k, total),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        )
        hits: list[Hit] = []
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
        ):
            hits.append(Hit(cid, doc, round(1.0 - float(dist), 4), dict(meta)))
        return hits

    def all_chunks(self, project_id: str, document_types: list[str] | None = None) -> list[Hit]:
        """Every stored chunk of a project (text + metadata), used to build the lexical (BM25) index."""
        where: dict = {"project_id": project_id}
        if document_types:
            where = {"$and": [{"project_id": project_id}, {"document_type": {"$in": document_types}}]}
        res = _retry(lambda: self._col.get(where=where, include=["documents", "metadatas"]))
        return [Hit(i, d, 0.0, dict(m)) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"], strict=True)]

    def heartbeat(self) -> bool:
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False
