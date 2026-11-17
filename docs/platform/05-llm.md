# 05. LLM integration

## Enable
```bash
# Anthropic
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=<model id from your Anthropic console>

# OpenAI, or any OpenAI-compatible endpoint (Groq, OpenRouter, Ollama, vLLM, Azure gateway ...)
LLM_PROVIDER=openai
LLM_API_KEY=...
LLM_MODEL=<model id>
LLM_BASE_URL=https://api.openai.com/v1      # change for compatible providers
```
Restart the API. **Settings → AI model** shows the status and has a *Test connection* button (owners/admins).
Keys live only in the server environment; they are never stored in the database, returned by the API or logged.

## What the LLM does (and does not do)
| Where | LLM role | Safeguard |
|---|---|---|
| RAG agent / assistant answers | Writes an answer from retrieved passages | Must cite passages; answers without valid citations are discarded; falls back to extractive answer |
| Research, Data, Procurement, Vendor, Financial, Document, Compliance, Contract, Report agents | Adds an **"AI interpretation (LLM, advisory)"** block after the deterministic tables | Labelled as AI-generated; never changes the computed results; skipped on failure or when "Allow AI interpretation" is unticked |
| Supervisor | Chooses which agents to run for a free-text request | Output validated against the agent registry (unknown ids dropped); falls back to rule-based routing |
| Compliance decisions, approvals, sending, payments | **None** | Never delegated to the model |

## Safety
* Document text is untrusted: it is fenced in `<data>` tags and the system prompt instructs the model to ignore instructions inside it (tested).
* Model output is plain text only; it is rendered escaped in the UI and never executed.
* Calls use bounded retries and timeouts; prompts/responses are not logged.
* Each call is counted per organization (`llm_calls_month` in Plan & Usage). Token counts are not recorded.

## Verification status
The LLM paths are covered by automated tests using a fake provider (interpretation, routing validation, prompt fencing,
failure fallback, usage counting). The real HTTP client was also exercised end-to-end (browser → API → HTTP → OpenAI-compatible endpoint) against a local
mock server. **They have not been run against a live commercial provider in this build** because no API key was available. Test with your key using the button in Settings, then run a few agents.
