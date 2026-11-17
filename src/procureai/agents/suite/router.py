"""Rule-based intent router used by the Supervisor and the assistant. Transparent: it returns why it chose each agent."""

from __future__ import annotations

import re

INTENTS: list[tuple[str, str, list[str]]] = [
    ("procurement", r"quotation|tender|\bbid\b|procure|compare vendor|\brfq\b|\brfp\b|vendor quot", ["procurement", "compliance", "vendor_intelligence"]),
    ("contract", r"contract|clause|renewal|expir|agreement|termination|liabilit", ["contract"]),
    ("financial", r"budget|expense|variance|spend|actual|\bcost\b|financ", ["financial"]),
    ("data", r"csv|excel|dataset|spreadsheet|trend|anomal|insight|\bkpi\b|chart|analy[sz]e this data", ["data_analyst"]),
    ("vendor", r"vendor risk|supplier risk|vendor performance|which vendor|lowest risk", ["vendor_intelligence"]),
    ("compliance", r"complian|not met|requirement", ["compliance"]),
    ("communication", r"\bemail|\bdraft\b|message|meeting|status update|task update", ["communication"]),
    ("report", r"\breport\b|export|\bpdf\b|executive summary", ["report"]),
    ("document", r"summari[sz]e|classif|missing information|extract|compare doc", ["document_intelligence"]),
    ("research", r"research|findings|investigat|missing evidence", ["research"]),
    ("workflow", r"run workflow|workflow", ["workflow"]),
    ("knowledge", r"policy|\bwho\b|\bwhat\b|\bwhen\b|\bwhere\b|\bhow\b|\bwhy\b|\?", ["rag"]),
]


# Platform-specific intents are exclusive: they short-circuit the generic procurement-oriented matching.
PACK_INTENTS: list[tuple[str, str, str]] = [
    ("support_reply", r"(reply|respond|response|answer) to .*(customer|ticket|client)|draft .*(reply|response) .*(customer|ticket)", "request is to answer a customer message"),
    ("ticket_triage", r"\btickets?\b|triage|customer complaint|support request|support queue", "request is about support tickets"),
    ("resume_screener", r"resumes?\b|\bcvs?\b|candidates?\b|shortlist|job description|applicants?", "request is about screening candidates"),
    ("meeting_actions", r"action items?|meeting notes|minutes|who is responsible|follow[- ]ups? from", "request is about meeting notes"),
    ("risk_register", r"risk register|project risks?|identify (the )?risks|scan .*risks|risks? (in|from) (the )?(notes|documents|project|report)", "request is about project risks"),
]


def plan(request: str) -> dict:
    """Return {"agents": [...], "reasons": {agent: why}}. Several intents may match; order follows INTENTS."""
    text = request.lower()
    for agent, pattern, why in PACK_INTENTS:
        if re.search(pattern, text):
            return {"agents": [agent], "reasons": {agent: why}}
    if re.search(r"(create|generate|make|export|produce|prepare)\b.*\breport", text):
        return {"agents": ["report"], "reasons": {"report": "request is to produce a report from existing results"}}
    agents: list[str] = []
    reasons: dict[str, str] = {}
    for name, pattern, chain in INTENTS:
        m = re.search(pattern, text)
        if not m:
            continue
        if name == "knowledge" and agents:  # generic question words should not add RAG to a specific intent
            continue
        for a in chain:
            if a not in agents:
                agents.append(a)
                reasons[a] = f"matched '{m.group(0).strip()}' ({name})"
    if not agents:
        agents, reasons = ["rag"], {"rag": "default: answer from project knowledge"}
    # report always last; communication after analysis agents
    for tail in ("communication", "report"):
        if tail in agents and agents[-1] != tail:
            agents.remove(tail)
            agents.append(tail)
    return {"agents": agents, "reasons": reasons}


def params_for(agent: str, request: str, base: dict) -> dict:
    p = dict(base)
    if agent == "support_reply":
        p.setdefault("ticket", request)
    if agent in ("rag", "research"):
        p.setdefault("question", request)
    if agent == "report":
        p.setdefault("kind", "pdf" if re.search(r"\bpdf\b", request.lower()) else "excel" if "excel" in request.lower() and "report" in request.lower() else "summary")
    if agent == "communication":
        low = request.lower()
        p.setdefault("kind", "vendor_followup" if re.search(r"vendor|supplier", low) else "meeting_summary" if "meeting" in low else "task_update")
    return p
