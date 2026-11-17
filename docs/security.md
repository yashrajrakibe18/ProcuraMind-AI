# Security notes

* **AuthN:** scrypt password hashes; JWT (HS256) access tokens; login rate limit (in-process: use a shared store when
  running several API workers). Production refuses weak/default `SECRET_KEY`.
* **AuthZ:** every project/document/run/report access goes through `get_project_for_user`; non-owners get 404 (existence not
  revealed); admins can access all. Tests cover cross-user access to projects, documents, assistant and retrieval.
* **Uploads:** extension allow-list, size limit (bounded read), magic-byte check, UTF-8 check for text, PDF page limit,
  duplicate detection by SHA-256, sanitized display name, server-generated storage key, path-traversal guard.
* **Prompt injection:** document text is passed as quoted, tag-escaped data; instructions say never to follow it; the model
  has no tools; its outputs are validated (citations, quotes) and compliance decisions never depend on it.
* **Privacy:** prompts, document text and secrets are not logged; audit metadata carries ids/counts only; project deletion
  (`DELETE /projects/{id}?permanent=true`) purges files, vectors and records.
* **Transport/headers:** `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, restrictive CORS. Terminate TLS in front of the API.
* **Not done:** SSO/MFA, per-project sharing and roles beyond owner/admin, encryption at rest, malware scanning of uploads,
  token revocation. See `limitations.md`.
