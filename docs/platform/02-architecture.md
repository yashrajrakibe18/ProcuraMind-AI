# 02. Architecture

```
 Browser SPA (apps/web_next)  ──►  FastAPI /api/v1  ──►  application services  ──►  SQLAlchemy / ChromaDB
                                      │                         │
                                      │                         ├─ org_service      orgs, roles, plans, quotas, usage
                                      │                         ├─ platform_service dashboard, search, chat, notifications
                                      │                         └─ project/document/analysis services (original)
                                      ▼
                          agents/suite  (orchestrator)
        Supervisor ─► router.plan() ─► child AgentTasks (parent_id)
        Workflow engine ─► steps = agent | approval checkpoint ─► resume on approval
        12 agents ─► permission-checked tools ─► Result{summary, sections, evidence}
```

## Multi-agent design
* An **agent** is an `AgentSpec`: id, domain, handler, declared tools, permissions, input schema, `requires_approval`,
  `timeout_s`, `max_retries`.
* **Tools** are reached only through `AgentContext.tool(name)`, which checks that the agent declared the tool and holds the
  permission it needs (`read`, `write_results`, `notify`, `generate_files`). `external_send` and `irreversible` are never
  granted to any agent. Enforced by test.
* `run_agent` creates an `AgentTask` row, runs the handler in a worker thread with its own DB session, enforces the
  timeout, and retries **only transient** errors. Statuses: running, completed, needs_input, awaiting_approval, failed,
  cancelled, rejected.
* **Supervisor**: rule-based intent router (transparent: it records why each agent was chosen), runs children in order,
  stops at the first child that needs input or fails, and consolidates their stored summaries (no new claims).
* **Workflows**: ordered steps, each an agent or a human approval checkpoint. A cursor allows pause/resume; approval
  resumes the run, rejection cancels it, failures are recorded (never silent). Optional scheduler
  (`SCHEDULER_ENABLED=true`, single process) runs due scheduled workflows; schedules need a paid plan.
* Agents are **deterministic and explainable**. A configured LLM adds advisory interpretation, routing and grounded
  answers on top (see 05-llm.md). Agents run synchronously in-process; there is no distributed queue (see roadmap).

## Multi-organization / multi-project
* `Organization` ← `Membership(role: owner|admin|member|viewer)`; a personal org is created at registration.
* `projects.org_id` and `projects.domain` (general, procurement, contracts, finance, …). Existing projects keep working
  (`org_id` nullable; an additive `ALTER TABLE` upgrades existing SQLite DBs, Alembic revision `0002_platform` for others).
* Access rule (`get_project_for_user`): owner, platform admin, or org member may open a project; viewers are read-only;
  everyone else gets **404** (existence is not revealed).
* Retrieval is always scoped to one project id.

## Plans (no payments)
Free / Professional / Team / Enterprise define limits for projects, members, agent tasks per month and webhooks.
Limits are enforced server-side (HTTP 402). Switching plan only changes limits. **No payment provider is integrated.**

## Hybrid retrieval
BM25 (built per query from the project's chunks) + vector similarity, fused with RRF, heuristic rerank by query-term
coverage, and a lexical relevance gate so unrelated questions are refused rather than answered from the nearest chunk.
Modes `vector | bm25 | hybrid` (default). On the small synthetic gold set all modes score the same
(P@3 0.233, R@3 0.700, MRR 0.700); the measurable benefit is the refusal gate, not a ranking gain.

## Webhooks
HMAC-SHA256 signature in `X-ProcuraMind-Signature`; HTTPS only; private/loopback targets rejected; delivery failures never
break the triggering action; the secret is shown once.

## Schema additions (27 tables total)
`organizations, memberships, conversations, messages, agent_tasks, workflows, workflow_runs, notifications, webhooks,
usage_events` + `projects.org_id`, `projects.domain`.

## API additions (`/api/v1`)
Orgs & members, plans & usage, webhooks, agents (`/agents`, `/agents/{id}/run`), tasks (`/tasks`, decision / cancel /
retry), chat & conversations, workflows & runs, notifications, global search, dashboard, activity, documents-all, reports-all.
Interactive docs at `/docs`.
