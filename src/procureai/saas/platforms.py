"""Platform catalogue: each platform is a workspace type with its own agents, document types and starter prompts.

All platforms run on the same engine (organizations, projects, RAG, orchestrator, workflows, approvals, LLM layer).
A project's ``domain`` is the id of the platform it belongs to (or ``general``).
"""

from __future__ import annotations

SHARED_AGENTS = ("rag", "research", "document_intelligence", "report")

PLATFORMS: dict[str, dict] = {
    "procurement": {"name": "Procurement & Vendors", "icon": "⚖", "tagline": "Compare quotations, check compliance, score vendors.", "doc_types": ["tender", "quotation", "policy", "historical"], "starters": ["Analyze these vendor quotations", "Which requirements are not met?", "Which vendor is the lowest risk?"]},
    "hr": {"name": "HR & Recruitment", "icon": "☺", "tagline": "Screen resumes against a job description; answer HR policy questions.", "doc_types": ["job_description", "resume", "policy"], "starters": ["Shortlist candidates for this job description", "What is the leave policy?"]},
    "support": {"name": "Customer Support", "icon": "✉", "tagline": "Triage tickets and draft knowledge-base-grounded replies for approval.", "doc_types": ["tickets", "knowledge_base", "policy"], "starters": ["Triage the support tickets", "Customer asks: how do I get a refund for a duplicate charge?"]},
    "legal": {"name": "Legal & Contracts", "icon": "✎", "tagline": "Clauses, key dates, risk indicators and renewal reminders.", "doc_types": ["contract", "policy"], "starters": ["Find all contracts expiring in the next 60 days", "Which contracts have unlimited liability?"]},
    "finance": {"name": "Finance & BI", "icon": "$", "tagline": "Budget variance, spend analysis, trends and anomalies.", "doc_types": ["financial", "dataset"], "starters": ["Compare the project budget with actual expenses", "Analyze this dataset and generate insights"]},
    "operations": {"name": "Projects & Operations", "icon": "▣", "tagline": "Meeting actions, risk register, reports and automated workflows.", "doc_types": ["meeting_notes", "other"], "starters": ["List action items from the meeting notes", "Identify project risks from the documents"]},
    "knowledge": {"name": "Knowledge & Research", "icon": "✦", "tagline": "Ask questions across any documents and get cited answers.", "doc_types": ["policy", "knowledge_base", "other"], "starters": ["What is the maximum delivery time allowed?", "Summarize this company policy"]},
}


def catalogue(agents: dict) -> list[dict]:
    out = []
    for pid, p in PLATFORMS.items():
        own = [a.id for a in agents.values() if a.platform == pid]
        ids = list(dict.fromkeys(own + [a for a in SHARED_AGENTS if a in agents]))
        out.append({"id": pid, **p, "agents": ids, "core_agents": own})
    return out
