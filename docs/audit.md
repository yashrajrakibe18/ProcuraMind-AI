# Phase 0 audit

At the start of this build the workspace already contained a partial codebase (~1.5k lines): configuration, structured
logging, domain enums/errors, unit conversion, the compliance rule engine, cost/FX calculations, price baselines, PDF/OCR/table
loaders, requirement and quotation extraction, a document classifier and the SQLAlchemy models. It had no API, services,
RAG, agents, reports, UI, tests, migrations, Docker or CI. It was kept and built on.

Defects found and fixed: quantity parsing failed on values with trailing text ("16 GB DDR5"); "within N days" was not treated as a
maximum; non-commercial noise fields (validity, phone, ...) leaked into specifications; duplicate/conflicting spec values were dropped
silently (now raised as review items). Models gained review items, project tender quantity/item, document auto-classify flag,
historical-source link and baseline source. Bugs found by running the live UI: self-registering navigation entry (recursive
sidebar) and a post-login redirect to a page not yet registered; both fixed and regression-tested.
