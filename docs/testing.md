# Testing

`make test` runs everything (about 2-3 minutes). Layers:

* `tests/unit` - domain rules, units, extraction, chunking, metrics, security primitives.
* `tests/api` - auth, isolation between users, upload validation, size limits, error shape, assistant grounding,
  prompt-injection inertness, purge/delete behaviour.
* `tests/agent_workflows` - the full journey (upload -> extract -> confirm -> analyse -> review -> approve -> PDF/Excel) with
  exact expected statuses and price figures; retry, retry exhaustion, non-retryable error, hidden internals, timeout,
  retrieval-failure, conflicting-evidence and routing tests.
* `tests/integration` - fake-LLM safety (citations, hallucinated quotes, advisory-only), OCR, readiness, migrations == models.
* `tests/ui` - every Streamlit page executes without exceptions when signed out, empty and populated (Streamlit AppTest).

Each test gets an isolated database, vector store and storage directory. `make eval` reproduces the retrieval metrics.
