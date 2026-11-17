# 01. Audit of the starting point

## What existed (ProcureAI)
FastAPI `/api/v1`, SQLAlchemy 2 + Alembic, Streamlit UI, ChromaDB with a local hashing embedder, a LangGraph procurement
workflow (compliance + price in parallel, retries, timeouts, human review), JWT auth, audit table, PDF/Excel reports,
Docker/CI, 99 tests. Single-user ownership model: a project belonged to one user.

## Mismatches between the transformation prompt and the real code
The prompt describes a vanilla-JS front end, a hand-written BM25 and a built-in workflow engine. The real project uses
Streamlit, ChromaDB and LangGraph. Rather than rewrite working, tested code, the platform was added **alongside** it:

| Prompt assumption | What was actually done |
|---|---|
| Vanilla JS UI | New dependency-free SPA in `apps/web_next` (served at `/app`); Streamlit UI kept as legacy |
| BM25 + vector | BM25 added in `rag/retrieval/retriever.py`, fused with ChromaDB vectors by Reciprocal Rank Fusion |
| Built-in workflow engine | New generic workflow engine in `agents/suite/orchestrator.py`; the LangGraph procurement pipeline is wrapped as the *Procurement Agent* |
| 12 agents | 12 specialist agents + Supervisor (13 registry entries) |

## Gaps found and fixed during the work
* Out-of-domain questions ("capital of France") returned the nearest chunk. Fixed with a lexical-overlap relevance gate.
* Package name `platform` shadowed the Python stdlib; renamed to `saas` / `agents/suite`.
* Migration `0002` initially had the wrong `down_revision` and a missing index; caught by the migration test.

## Known limitations carried over
Hashing embedder (not semantic), synthetic sample data only, Docker files not built in the authoring sandbox.
