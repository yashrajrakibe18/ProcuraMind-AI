# 06. Platforms (one system, many workspaces)

ProcuraMind AI is a single system. A **platform** is a workspace type: it has its own agents, expected document types and
starter prompts, but shares everything else (organizations, roles, plans, projects, RAG, orchestrator, workflows,
approvals, notifications, webhooks, audit, LLM layer, UI). A project's `domain` is its platform id.

| Platform | Own agents | Document types | What it does (and does not) |
|---|---|---|---|
| Procurement & Vendors | Procurement, Vendor Intelligence, Compliance, Communication | tender, quotation, policy, historical | Original ProcureAI pipeline: requirements, quotations, compliance, price, evidence, human review |
| HR & Recruitment | **Resume Screening** | job_description, resume, policy | Ranks resumes by must-have / nice-to-have keyword coverage and experience. Advisory; ignores protected attributes; cannot judge quality |
| Customer Support | **Ticket Triage**, **Support Reply** | tickets (CSV/XLSX), knowledge_base | Keyword triage (category, priority, sentiment, duplicates). Replies are grounded in the KB with citations and always need approval; never sent |
| Legal & Contracts | Contract Intelligence | contract, policy | Clauses, dates, risk indicators, renewal reminders. Not legal advice |
| Finance & BI | Financial Analysis, Data Analyst | financial, dataset | Budget variance, quotation cost comparison, trends, IQR anomalies |
| Projects & Operations | **Meeting Actions**, **Risk Register**, Report | meeting_notes, other | Pattern-based action/decision extraction; keyword risk flagging for humans to assess |
| Knowledge & Research | RAG, Research, Document Intelligence | policy, knowledge_base, other | Cited answers across any documents |

Shared by every platform: RAG, Research, Document Intelligence, Report, Supervisor, workflows, LLM interpretation.
Bold agents were added in this release (18 agents total: 12 core + 5 platform agents + supervisor/workflow).

## Adding a platform
1. Add handlers in `agents/suite/` and register `AgentSpec(..., platform="<id>")` in `registry.py`.
2. Add the platform to `saas/platforms.py` and its id to `ProjectCreate.domain`.
3. Add any new `DocumentType` values + classifier keywords. The UI picks everything else up from `/api/v1/platforms`.

## Sample data
`make samples` also writes **synthetic** files to `data/samples/platforms/` (job description, 3 resumes, tickets CSV,
support knowledge base, meeting notes). They are fictional and exist only for demos and tests.

## Verification
`tests/api/test_platform_packs.py` (13 tests) and a browser run that creates an HR, Support and Operations project,
uploads files, runs the agents, approves a drafted reply and checks the results.
