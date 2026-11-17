# Agent workflow

Implemented in `src/procureai/agents/graphs/workflow.py` (LangGraph, typed `WorkflowState`).

```
START -> supervisor -> validate_documents -> supervisor -> document_intelligence -> supervisor -> vendor_analysis
      -> supervisor -> [technical_compliance || price_intelligence] -> supervisor -> procurement_rag
      -> supervisor -> verification -> supervisor -> finalize -> END
```
The supervisor is a pure routing function (`supervisor_route`, unit-tested) over progress flags. Any recorded error
routes to `finalize` (status `failed`, with the reason). A hop counter and LangGraph's recursion limit bound the loop.

* **Step runner** (`agents/tools/step_runner.py`): every step runs with a timeout and each attempt is persisted as an
  `agent_steps` row. Only transient failures (external service, timeout) are retried (default 2 retries); deterministic
  errors fail fast. Unexpected exceptions are logged and surface to users as a generic message.
* **Parallelism:** compliance and price analysis run concurrently only after validation, extraction and vendor analysis
  succeed; each uses its own DB session.
* **Retrieval failure is non-fatal:** the run continues and records a visible note.
* **Verification** is independent code: every vendor x requirement pair has a result; statuses are valid; decided results
  have a source page; unconfirmed or conflicting quotation data, unpriceable quotes and price flags become review items.
* **Human review:** a run with open review items is `awaiting_human_review`. Compliance items can be resolved with
  meets / fails / not applicable (the original system status is kept alongside the human decision). Approval is blocked
  while items are open. Approval is recorded in the audit log.
* **Starting a run is idempotent** while another run is queued/running for the project.
