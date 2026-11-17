"""Composition root: builds long-lived infrastructure adapters from settings."""

from __future__ import annotations

from dataclasses import dataclass

from procureai.config.settings import Settings, get_settings
from procureai.infrastructure.llm.client import LLMClient, get_llm_client
from procureai.infrastructure.storage.local import LocalFileStorage
from procureai.infrastructure.vector_store.chroma_store import ChromaVectorStore
from procureai.rag.embeddings.hashing import HashingEmbedder
from procureai.rag.ingestion.indexer import DocumentIndexer, build_embedder
from procureai.rag.retrieval.retriever import Retriever


@dataclass
class AppContext:
    settings: Settings
    storage: LocalFileStorage
    store: ChromaVectorStore
    embedder: HashingEmbedder
    llm: LLMClient

    @property
    def indexer(self) -> DocumentIndexer:
        s = self.settings
        return DocumentIndexer(self.store, self.embedder, s.chunk_target_tokens, s.chunk_overlap_tokens)

    @property
    def retriever(self) -> Retriever:
        return Retriever(self.store, self.embedder, self.settings.rag_min_score)


_ctx: AppContext | None = None


def get_context() -> AppContext:
    global _ctx
    if _ctx is None:
        s = get_settings()
        s.ensure_directories()
        _ctx = AppContext(
            s,
            LocalFileStorage(s.document_storage_path),
            ChromaVectorStore(s.vector_store_path),
            build_embedder(s),
            get_llm_client(s),
        )
    return _ctx


def reset_context() -> None:
    global _ctx
    _ctx = None
