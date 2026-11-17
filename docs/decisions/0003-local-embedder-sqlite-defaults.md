# ADR 3: Offline-first defaults
Hashed n-gram embeddings, SQLite and local storage make the project runnable with no keys or downloads; PostgreSQL, a neural embedder and an LLM are configuration swaps behind existing interfaces. Trade-off: weaker semantic retrieval (measured in limitations.md).
