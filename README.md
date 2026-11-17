# ProcuraMind AI (built on ProcureAI)

**One system, many platforms: Procurement, HR & Recruitment, Customer Support, Legal & Contracts, Finance & BI, Projects & Operations, Knowledge & Research.** Multi-organization, multi-project, multi-agent (18 agents) with RAG, an optional LLM API and human approval checkpoints.
18 agents: 12 core (research, RAG, data analyst, procurement, vendor, financial, document, contract, compliance, report,
communication, workflow) + resume screening, ticket triage, support reply, meeting actions, risk register, under a Supervisor; hybrid BM25 + vector retrieval with page citations; workflows with approval
steps; organizations, roles and plan limits; signed webhooks; a modern web app. Agents analyse and draft; **people approve**.
Agents can never send external messages or approve payments. No payment system is integrated.

```bash
make install-dev && cp .env.example .env
make run-api                      # then open http://localhost:8000/app/   (new web app)   |  /docs (API)
```
**Use an LLM API:** set `LLM_PROVIDER` (`anthropic` or `openai`/compatible), `LLM_API_KEY`, `LLM_MODEL` in `.env` (see [docs/platform/05-llm.md](docs/platform/05-llm.md)). Without a key everything still works deterministically.

Register in the web app, create a project, upload documents (`make samples` writes synthetic ones), then run agents.
Platform docs: [docs/platform](docs/platform/README.md) (audit, architecture, honest feature status, roadmap).
The original Streamlit UI (`make run-web`) still works. The original ProcureAI documentation follows.

---

# ProcureAI

Agentic procurement intelligence and **decision support**. Upload a tender, vendor quotations, policies and purchase
history; ProcureAI extracts requirements, evaluates each vendor requirement-by-requirement with cited evidence,
normalises and benchmarks prices, answers grounded questions, and exports PDF/Excel reports.
**People keep approval responsibility. The system never awards a contract.**

## What is in this repository

| Area | Where | Notes |
|---|---|---|
| Domain rules (units, compliance, pricing) | `src/procureai/domain` | Pure, deterministic, unit-tested |
| Document processing | `src/procureai/document_processing` | PyMuPDF text, pdfplumber tables, Tesseract OCR fallback, classification, extraction |
| RAG | `src/procureai/rag`, `infrastructure/vector_store` | Section-aware chunks, ChromaDB, project-scoped retrieval, cited answers |
| Agent workflow | `src/procureai/agents` | LangGraph supervisor, parallel compliance + price, retries, timeouts, persisted step events |
| Services / use cases | `src/procureai/application` | Authorization, audit, orchestration |
| API | `apps/api` | FastAPI, 36 endpoints under `/api/v1`, JWT auth, consistent errors |
| UI | `apps/web` | Streamlit, 9 pages, talks to the API only |
| Reports | `src/procureai/reporting` | PDF (ReportLab) and Excel (openpyxl) with provenance labels |
| Tests | `tests/` | unit, API, workflow/failure paths, UI smoke, migrations |
| Ops | `docker/`, `docker-compose.yml`, `.github/workflows/ci.yml`, `Makefile`, `alembic` | |

## Quick start (no Docker, no API keys)

```bash
python -m venv .venv && source .venv/bin/activate
make install-dev                   # pip install -r requirements-dev.txt && pip install -e .
cp .env.example .env               # defaults work locally (SQLite, local vector store, no LLM)
sudo apt-get install tesseract-ocr # optional: only needed for scanned PDFs / images
make run-api                       # terminal 1 -> http://localhost:8000/docs
make run-web                       # terminal 2 -> http://localhost:8501
make seed                          # optional: loads synthetic demo project via the API
```

Sign in with `demo@procureai.local` / `DemoPassw0rd!` (created by `make seed`; local use only), or register a user:
the **first registered user becomes admin**. Then: *Documents* → upload → *Tender requirements* → confirm →
*Compliance* → Start analysis → resolve review items → approve → *Reports*.

## Docker

```bash
cp .env.example .env   # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
```
PostgreSQL + API (runs `alembic upgrade head` on start) + UI. Dockerfiles run as a non-root user and have health checks.
*The Docker files were written to spec but could not be built in the sandbox this project was produced in; run
`docker compose build` once and report any issue.*

## Configuration
All settings are environment variables (see `.env.example`). Production (`APP_ENV=production`) refuses to start with a
weak `SECRET_KEY`. Secrets are never logged or returned by the API.

### Optional LLM
`LLM_PROVIDER=none` (default) is fully functional: extraction, compliance, pricing and extractive assistant answers are
deterministic. Set `LLM_PROVIDER=anthropic|openai`, `LLM_API_KEY`, `LLM_MODEL` to enable (a) advisory interpretation of
*ambiguous* specifications and (b) generated assistant answers. The model **never decides** a compliance result: its
output is stored as "advisory", its evidence quote must exist verbatim in the vendor text, and model answers without
valid citations are discarded. The LLM paths are tested with a fake provider only; they have not been exercised against
a live provider in this build.

## Commands
`make test` · `make lint` · `make eval` (retrieval metrics) · `make samples` · `make migrate` · `make inspect`
(`python scripts/inspect_environment.py`).

## Documentation
`docs/architecture.md`, `docs/workflow.md`, `docs/security.md`, `docs/limitations.md`, `docs/testing.md`,
`docs/audit.md` (what existed before this build), `docs/decisions/` (ADRs). Interactive API docs at `/docs`.

## Synthetic data
Everything in `data/samples/` is **synthetic**: fictional vendors, prices and policies. See `docs/limitations.md`.
