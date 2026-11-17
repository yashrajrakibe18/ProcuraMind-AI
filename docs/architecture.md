# Architecture

```
Streamlit UI (apps/web)  --HTTP-->  FastAPI (apps/api)  -->  application services  -->  domain rules
                                         |                        |                       (pure)
                                         |                        +--> LangGraph workflow (agents)
                                         v
              SQLAlchemy (SQLite | PostgreSQL)   ChromaDB (vectors)   Local file storage   Optional LLM
```

**Dependency rule:** UI -> API client only. API endpoints are thin: validate, authorize via a service, return a DTO.
Services own transactions, authorization (`access.get_project_for_user`) and audit events. Domain code
(`domain/`, `analytics/`) has no I/O. Infrastructure adapters (storage, vector store, LLM) are built once in
`application/context.py`.

**Data model** (`infrastructure/database/models/entities.py`): users, projects, documents, document_pages, tender
requirements, vendors, quotations, specifications, historical purchases, agent runs, agent steps, compliance
results, price analyses, policy evidence, review items, reports, audit events. Results are keyed by `run_id`, so
re-running keeps history. Deleting a project cascades through the database and purges files and vectors.

**Why these choices:** see `docs/decisions/`.
