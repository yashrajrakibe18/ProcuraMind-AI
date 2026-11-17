"""Index a document's pages into the vector store with page/section metadata."""

from __future__ import annotations

from procureai.config.settings import Settings
from procureai.infrastructure.vector_store.chroma_store import ChromaVectorStore, StoredChunk
from procureai.rag.chunking.chunker import chunk_pages
from procureai.rag.embeddings.hashing import HashingEmbedder


def build_embedder(settings: Settings) -> HashingEmbedder:
    return HashingEmbedder(settings.embedding_dim)


class DocumentIndexer:
    def __init__(self, store: ChromaVectorStore, embedder: HashingEmbedder, target_tokens: int, overlap_tokens: int):
        self.store, self.embedder = store, embedder
        self.target_tokens, self.overlap_tokens = target_tokens, overlap_tokens

    def index(
        self, *, project_id: str, document_id: str, document_type: str, filename: str, pages: list[tuple[int, str]]
    ) -> int:
        self.store.delete_document(document_id)  # re-indexing is idempotent
        chunks = chunk_pages(pages, self.target_tokens, self.overlap_tokens)
        if not chunks:
            return 0
        embeddings = self.embedder.embed([c.text for c in chunks])
        stored = []
        for c, emb in zip(chunks, embeddings, strict=True):
            chunk_id = f"{document_id}:{c.index}"
            stored.append(
                StoredChunk(
                    chunk_id,
                    c.text,
                    emb,
                    {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "project_id": project_id,
                        "page": c.page,
                        "section": c.section,
                        "document_type": document_type,
                        "filename": filename,
                    },
                )
            )
        self.store.upsert(stored)
        return len(stored)
