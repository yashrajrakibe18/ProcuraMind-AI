# Known limitations and honest caveats

* **Synthetic only.** All development and tests used synthetic documents. Extraction/compliance accuracy on real tenders
  and quotations is **unmeasured**. Expect to review and correct extracted fields (the UI is built for that).
* **Rule-based extraction.** Requirements/specs are parsed from "Field: value" lines, pipe rows and simple tables with
  regexes and unit tables. Free-form prose, complex multi-column tables and unusual layouts will be missed (reported as
  missing/review, never guessed). No LLM extraction fallback is implemented.
* **Text compliance is conservative.** Categorical mismatches (e.g. "Windows 11 Home" vs "Pro") are sent to human review rather
  than failed. Numeric rules with unit conversion are deterministic.
* **Retrieval quality.** The default embedder is a local lexical (hashed n-gram) model: no downloads, deterministic, weaker on
  paraphrase. On the 10-query synthetic gold set: Precision@3 = 0.23, Recall@3 = 0.70, MRR = 0.70 (`make eval`). Chunk size
  made no difference on this small set. Treat these as a baseline, not a quality claim. Swap in a neural embedder behind
  `rag/embeddings` for real corpora. Extractive answers do not detect conflicting passages.
* **Pricing.** Statistical baselines only (peer leave-one-out, historical median/IQR or MAD). Assumes quoted prices exclude tax.
  FX uses a **static, illustrative** table from configuration: set real rates. The IsolationForest signal is advisory and
  unvalidated (no labelled outcomes exist). Flags mean "review", never "overpriced" or "fraud".
* **Legal/eligibility screening** (vendor eligibility, legal clauses) is out of scope; "technical" and "commercial" categories only.
* **Scale.** Single-process background tasks (FastAPI `BackgroundTasks`), SQLite default, in-process rate limiter, local file
  storage. For many users use PostgreSQL, a job queue/worker, object storage and a shared rate limiter.
* **Step timeouts** stop waiting for a step but cannot kill its worker thread.
* **Not verified in the build sandbox:** Docker image builds, PostgreSQL runtime (SQLite used; SQLAlchemy models are portable and
  Alembic migrations were verified on SQLite), live LLM providers, OCR on real scans (only a rendered-text sample).
