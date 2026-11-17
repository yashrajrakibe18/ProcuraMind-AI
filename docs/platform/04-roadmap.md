# 04. Roadmap and technology recommendations

Done: audit → design → core (orgs/plans) → agents → RAG → modules → automation → UI → hardening (tests).

Next, in priority order:
1. **Real embeddings** (e.g. a sentence-transformer or hosted embedding model) behind the existing `Embedder` interface; re-run the retrieval evaluation on a larger, real gold set.
2. **Job queue** (Celery/RQ/Arq + Redis) so agents and scheduled workflows survive restarts and run in parallel.
3. **PostgreSQL by default** and per-org row-level security review.
4. **Email/Slack notification delivery** with templates and per-user preferences; approval via email link.
5. **Billing** (Stripe) wired to the existing plan limits; usage-based tokens once an LLM is enabled.
6. **SSO/SAML**, org-level audit export, data-retention controls.
7. **LLM-assisted agents** with the same permission model, evidence-must-exist checks and approval gates.
8. Frontend: onboarding wizard, drag-and-drop workflow canvas, i18n.
