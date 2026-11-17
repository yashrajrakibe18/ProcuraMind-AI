# 03. Feature status

Legend: **Implemented** = coded and covered by an automated test or the browser end-to-end run. **Partial** = works with
stated limits. **Roadmap** = not built.

| Area | Status | Verified by / limits |
|---|---|---|
| Organizations, roles, personal org | Implemented | `test_platform.py` (isolation, viewer read-only, member quota) |
| Plans & quotas (402) | Implemented | tests; **no payment integration** |
| 12 agents + supervisor | Implemented | tests on sample data; deterministic, rule-based |
| Tool permissions (agents can never send/approve externally) | Implemented | `test_agent_tool_permissions_are_enforced` |
| Hybrid RAG + citations + refusal gate | Implemented | tests; embedder is lexical-hash, not semantic |
| Retrieval evaluation | Partial | `scripts/evaluate_retrieval.py`; tiny synthetic gold set |
| Workflows with approval, cancel, failure tracking | Implemented | tests |
| Scheduled workflows | Partial | in-process loop, single replica; tested via `run_due_workflows` |
| Notifications | Implemented | in-app only; no email/SMS delivery |
| Webhooks (signed, SSRF-guarded) | Implemented | tests with fake sender; not exercised against a real endpoint |
| Global search | Implemented | projects, documents, vendors, workflows, conversations |
| DOCX / XLSX ingestion | Implemented | tests |
| Contract, financial, BI agents | Implemented | tests on generated data |
| Web app (21 views: landing, auth, dashboard, projects, project workspace, assistant, marketplace, execution center, documents, procurement, vendors, financial, BI, contracts, workflows, reports, notifications, activity, team, plan & usage, settings) | Implemented | Playwright end-to-end run, no JS errors; light/dark; mobile layout |
| Multi-platform hub (7 platforms), HR / Support / Operations agents | Implemented | `test_platform_packs.py` + browser run; heuristic (keyword) analysis, synthetic samples only |
| Onboarding wizard | Roadmap | empty states guide first steps instead |
| Distributed/parallel agent execution | Roadmap | agents run in-process, sequentially |
| LLM interpretation, LLM routing, grounded LLM answers | Implemented (fake-provider tests) | **not run against a live API**; see 05-llm.md |
| Autonomous LLM tool-use / free-form agent loops | Roadmap | by design agents compute deterministically; LLM is advisory |
| Billing, email/Slack delivery, SSO | Roadmap | |
| Real-data accuracy claims | None made | all sample data is synthetic |
