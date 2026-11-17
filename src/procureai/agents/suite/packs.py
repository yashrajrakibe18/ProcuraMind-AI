"""Agents for the additional platforms (HR, Customer Support, Operations).

Same rules as the core agents: deterministic, traceable, read-only, and honest about being keyword/heuristic based.
An LLM (if configured) only adds a labelled advisory interpretation afterwards (see llm.py).
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from procureai.agents.suite import textutil as tu
from procureai.agents.suite.agents import bullets, chart, kv, need, table
from procureai.agents.suite.base import AgentContext, Result
from procureai.rag.answer_generation.answerer import generate_answer

# ------------------------------------------------------------------ HR: resume screening
_MUST_HDR = re.compile(r"^\s*(requirements?|required( skills| qualifications)?|must[- ]haves?|qualifications|what you.ll need)\s*:?\s*$", re.I)
_NICE_HDR = re.compile(r"^\s*(nice[- ]to[- ]haves?|preferred( skills| qualifications)?|bonus|good to have|plus)\s*:?\s*$", re.I)
_ANY_HDR = re.compile(r"^\s*[A-Z][A-Za-z /&]{2,40}:?\s*$")
_SKILL_SPLIT = re.compile(r",|;|/|\band\b|\bor\b|•|•")
_FILLER = re.compile(r"^(experience (with|in)|knowledge of|proficiency in|strong|good|solid|working|understanding of|familiarity with|ability to|skills? in)\s+", re.I)
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)


def _terms(line: str) -> list[str]:
    line = re.sub(r"^[\s\-*••\d.)]+", "", line)
    out = []
    for part in _SKILL_SPLIT.split(line):
        part = _FILLER.sub("", part.strip(" .:-")).strip()
        part = re.sub(r"\(.*?\)", "", part).strip()
        if 2 <= len(part) <= 40 and not _YEARS.search(part) and len(part.split()) <= 4:
            out.append(part.lower())
    return out


def parse_job_description(text: str) -> tuple[list[str], list[str], int | None]:
    must, nice, mode = [], [], None
    for line in text.splitlines():
        if _MUST_HDR.match(line):
            mode = "must"
        elif _NICE_HDR.match(line):
            mode = "nice"
        elif _ANY_HDR.match(line) and not line.strip().startswith(("-", "*", "•")):
            mode = None
        elif mode and line.strip():
            (must if mode == "must" else nice).extend(_terms(line))
    years = [int(y) for y in _YEARS.findall(text)]
    dedupe = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
    return dedupe(must), dedupe(nice), (max(years) if years else None)


def _has(term: str, text: str) -> re.Match | None:
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I)


def resume_screener(ctx: AgentContext) -> Result:
    docs = ctx.tool("project_documents")()
    jds = [d for d in docs if d.id == ctx.params.get("job_description_id")] or [d for d in docs if d.document_type == "job_description"]
    resumes = [d for d in docs if d.document_type == "resume"]
    override = str(ctx.params.get("must_have", "")).strip()
    if not jds and not override:
        return need("Upload a job description (type 'job_description') or pass 'must_have' skills separated by commas.")
    if not resumes:
        return need("Upload one or more resumes (document type 'resume').")
    jd_text = "\n".join(t for d in jds[:1] for _, t in ctx.tool("document_pages")(d))
    must, nice, min_years = parse_job_description(jd_text)
    if override:
        must = [m.strip().lower() for m in override.split(",") if m.strip()]
    if not must:
        return need("No required skills were found in the job description. Add a 'Requirements:' list, or pass 'must_have' skills.")
    rows, evidence, scores = [], [], []
    for d in resumes[:60]:
        text = "\n".join(t for _, t in ctx.tool("document_pages")(d))
        got = [m for m in must if _has(m, text)]
        miss = [m for m in must if m not in got]
        ngot = [n for n in nice if _has(n, text)]
        years = max([int(y) for y in _YEARS.findall(text)] or [0])
        exp_ok = min_years is None or years >= min_years
        score = round(70 * len(got) / len(must) + (20 * len(ngot) / len(nice) if nice else 0) + (10 if exp_ok else 10 * years / max(min_years, 1)), 1)
        if not nice:
            score = round(score / 0.8, 1) if score else 0.0
            score = min(score, 100.0)
        name = next((ln.strip() for ln in text.splitlines() if ln.strip()), d.original_filename)[:40]
        rows.append([0, d.original_filename, name, score, ", ".join(got) or "-", ", ".join(miss) or "-", ", ".join(ngot) or "-", years or "not stated"])
        if got:
            m = _has(got[0], text)
            evidence.append({"document": d.original_filename, "document_id": d.id, "page": 1, "score": score, "snippet": tu.context(text, m.start(), m.end(), 90)})
        scores.append((score, d.original_filename))
    rows.sort(key=lambda r: -r[3])
    for i, r in enumerate(rows, 1):
        r[0] = i
    secs = [
        kv("Screening basis", [["Must-have skills", ", ".join(must)], ["Nice-to-have", ", ".join(nice) or "none listed"], ["Minimum years", min_years or "not stated"], ["Resumes", len(rows)]]),
        table("Ranked candidates (keyword coverage)", ["#", "File", "Candidate (first line)", "Score /100", "Must-haves found", "Must-haves missing", "Nice-to-haves found", "Years mentioned"], rows),
        chart("Score by candidate", "bar", [r[1][:18] for r in rows], [{"name": "Score", "values": [r[3] for r in rows]}]),
        bullets("How to use this", ["This is a keyword-coverage screening aid. It cannot judge quality, context or potential.", "Age, gender, ethnicity, nationality and other protected attributes are not used.", "A human must review every candidate; do not use the score as the sole basis for a hiring decision."]),
    ]
    return Result(f"Screened {len(rows)} resume(s) against {len(must)} must-have skill(s). Top: {rows[0][1]} ({rows[0][3]}/100).", secs, evidence[:8], labels={"scoring": "70% must-haves + 20% nice-to-haves + 10% experience. Transparent heuristic, not a calibrated model."}, data={"ranking": [[r[1], r[3]] for r in rows]})


# ------------------------------------------------------------------ Support: ticket triage
CATEGORIES = {
    "Billing": r"invoice|billing|charged|charge|payment|subscription|receipt|price|overcharg",
    "Refund / Return": r"refund|return|money back|cancel(l)?ation|reimburse",
    "Account / Login": r"login|log in|password|account|locked|sign in|2fa|verification|access",
    "Technical issue": r"error|bug|crash|not working|broken|fail|slow|timeout|outage|down\b|exception|glitch",
    "Shipping / Delivery": r"shipping|delivery|deliver|package|tracking|courier|late|arrive|order status",
    "Feature request": r"feature|would be great|suggest|wish|add support|please add|enhancement",
}
HIGH = r"urgent|asap|immediately|outage|down\b|data loss|lost data|security|breach|hacked|charged twice|double charged|cannot access|can't access|production|critical"
MED = r"error|bug|not working|broken|fail|crash|slow|issue|problem|unable|can't|cannot"
NEG = set("angry terrible awful worst unacceptable furious disappointed frustrated useless horrible ridiculous bad poor never again waste scam".split())
POS = set("thanks thank great love excellent awesome helpful appreciate wonderful perfect happy".split())
_TEXT_COLS = ("subject", "title", "summary", "description", "body", "message", "text", "issue", "content")
_ID_COLS = ("ticket_id", "id", "ticket", "case", "number", "key")


def _ticket_docs(ctx):
    docs = ctx.tool("project_documents")()
    if ctx.params.get("document_id"):
        return [d for d in docs if d.id == ctx.params["document_id"]]
    t = [d for d in docs if d.document_type == "tickets"]
    return t or [d for d in docs if d.document_type == "dataset" and d.mime_type in ("text/csv",) or (d.document_type == "dataset" and d.mime_type.endswith("spreadsheetml.sheet"))]


def triage_text(text: str) -> tuple[str, str, int]:
    low = text.lower()
    cat = next((c for c, p in CATEGORIES.items() if re.search(p, low)), "General")
    scores = {c: len(re.findall(p, low)) for c, p in CATEGORIES.items()}
    if any(scores.values()):
        cat = max(scores, key=lambda k: scores[k])
    words = re.findall(r"[a-z']+", low)
    sent = sum(w in POS for w in words) - sum(w in NEG for w in words)
    pr = "High" if re.search(HIGH, low) or sent <= -3 else "Medium" if re.search(MED, low) else "Low"
    return cat, pr, sent


def ticket_triage(ctx: AgentContext) -> Result:
    docs = _ticket_docs(ctx)
    if not docs:
        return need("Upload a CSV/XLSX of tickets (document type 'tickets') with columns such as subject and description.")
    df = ctx.tool("load_dataframe")(docs[0], 5000)
    cols = {str(c).lower().strip(): c for c in df.columns}
    text_cols = [cols[c] for c in _TEXT_COLS if c in cols]
    if not text_cols:
        return need(f"No text column found. Expected one of: {', '.join(_TEXT_COLS)}. Found: {', '.join(map(str, df.columns))}.")
    id_col = next((cols[c] for c in _ID_COLS if c in cols), None)
    texts = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1).tolist()
    rows = []
    for i, t in enumerate(texts):
        cat, pr, sent = triage_text(t)
        rows.append({"id": str(df[id_col].iloc[i]) if id_col else str(i + 1), "category": cat, "priority": pr, "sentiment": sent, "text": t})
    cat_counts, pri_counts = Counter(r["category"] for r in rows), Counter(r["priority"] for r in rows)
    order = {"High": 0, "Medium": 1, "Low": 2}
    top = sorted(rows, key=lambda r: (order[r["priority"]], r["sentiment"]))[:20]
    dups = []
    if 2 <= len(texts) <= 1500:
        try:
            m = TfidfVectorizer(stop_words="english").fit_transform(texts)
            sim = (m @ m.T).toarray()
            np.fill_diagonal(sim, 0)
            for i, j in zip(*np.where(np.triu(sim) > 0.8), strict=False):
                dups.append([rows[i]["id"], rows[j]["id"], round(float(sim[i, j]), 2), texts[i][:80]])
        except ValueError:
            pass
    secs = [
        kv("Overview", [["Tickets analysed", len(rows)], ["High priority", pri_counts["High"]], ["Medium", pri_counts["Medium"]], ["Low", pri_counts["Low"]], ["Negative sentiment", sum(1 for r in rows if r["sentiment"] < 0)], ["Possible duplicates", len(dups)]]),
        chart("Tickets by category", "bar", list(cat_counts), [{"name": "Tickets", "values": list(cat_counts.values())}]),
        table("Highest-priority tickets (first 20)", ["Ticket", "Priority", "Category", "Sentiment", "Text"], [[r["id"], r["priority"], r["category"], r["sentiment"], r["text"][:140]] for r in top]),
    ]
    if dups:
        secs.append(table("Possible duplicate tickets (text similarity > 0.8)", ["Ticket A", "Ticket B", "Similarity", "Text"], dups[:20]))
    secs.append(bullets("Method", ["Category, priority and sentiment come from keyword rules, so they will miss sarcasm and unusual wording. Review high-priority items first, then spot-check others."]))
    return Result(f"Triaged {len(rows)} tickets: {pri_counts['High']} high priority, top category {cat_counts.most_common(1)[0][0]}.", secs, labels={"method": "Keyword-rule triage; not a trained classifier."}, data={"categories": dict(cat_counts), "priorities": dict(pri_counts)})


def _kb_sentences(ticket: str, evidence: list[dict], limit: int = 3) -> str:
    """Pick the knowledge-base sentences that best match the ticket and cite their source (no model involved)."""
    q = set(re.findall(r"[a-z]{4,}", ticket.lower()))
    scored = []
    for e in evidence:
        for sent in tu.sentences(e["snippet"], 20):
            w = set(re.findall(r"[a-z]{4,}", sent.lower()))
            if q & w:
                scored.append((len(q & w) / (len(w) ** 0.5), sent, e))
    seen, out = set(), []
    for _, sent, e in sorted(scored, key=lambda t: -t[0]):
        if sent not in seen and len(out) < limit:
            seen.add(sent)
            out.append(f"{sent.strip()} (Source: {e['document']}, p.{e['page']})")
    return "\n".join(out) or ans_fallback(evidence)


def ans_fallback(evidence: list[dict]) -> str:
    return evidence[0]["snippet"][:300] if evidence else ""


def support_reply(ctx: AgentContext) -> Result:
    ticket = str(ctx.params.get("ticket", "")).strip()
    if not ticket:
        return need("Paste the customer's message as 'ticket'.")
    passages = ctx.tool("retrieve")(ticket[:500], 4)
    ans = generate_answer(ticket[:500], passages, ctx.app.llm)
    evidence = [{"document": c.filename, "document_id": c.document_id, "page": c.page, "score": c.score, "snippet": c.snippet} for c in ans.citations]
    cat, pr, _ = triage_text(ticket)
    first = ctx.user.full_name
    if ans.grounded:
        answer_text = ans.answer if ans.mode == "llm" else _kb_sentences(ticket, evidence)
        body = f"Hello,\n\nThank you for contacting us.\n\n{answer_text}\n\nIf this does not resolve your issue, just reply to this message and we will look into it further.\n\nKind regards,\n{first}"
        summary = f"Drafted a reply grounded in {len(evidence)} knowledge-base passage(s). Awaiting your approval; nothing is sent."
    else:
        body = f"Hello,\n\nThank you for contacting us. We are reviewing your message and a team member will follow up shortly.\n\nKind regards,\n{first}"
        summary = "No matching knowledge-base content was found, so only a holding reply was drafted. Escalate to a human."
    secs = [kv("Triage", [["Category", cat], ["Priority", pr], ["Grounded in knowledge base", "yes" if ans.grounded else "no"]]), {"type": "draft", "title": "Draft reply (not sent)", "subject": "Re: your support request", "body": body}]
    if evidence:
        secs.append(table("Knowledge-base sources used", ["Document", "Page", "Score", "Excerpt"], [[e["document"], e["page"], e["score"], e["snippet"][:200]] for e in evidence]))
    return Result(summary, secs, evidence, llm_calls=1 if ans.mode == "llm" else 0, labels={"draft": "Drafts are never sent by the system. A person must review and send."}, data={"grounded": ans.grounded})


# ------------------------------------------------------------------ Operations: meetings, risks
_ACTION = re.compile(r"^\s*(?:[-*••]\s*)?(?:action(?:\s*items?)?|todo|to-do|task|follow[- ]up)\s*[:\-]\s*(?P<t>.+)$", re.I)
_OWNER = re.compile(r"\b(?P<o>[A-Z][a-z]{2,15})\s+(?:will|to|should|must|needs to|is going to|shall)\s+(?P<t>.+)")
_DUE = re.compile(r"\b(?:by|before|due|until)\s+(?P<d>[A-Za-z0-9 ,/\-.]{3,24})", re.I)
_DECISION = re.compile(r"\b(decided|agreed|approved|resolved|decision|we will go with|confirmed)\b", re.I)
_QUESTION = re.compile(r"\?\s*$|\bTBD\b|\bto be decided\b|\bopen question\b", re.I)


def meeting_actions(ctx: AgentContext) -> Result:
    docs = ctx.tool("project_documents")()
    sel = [d for d in docs if d.id == ctx.params.get("document_id")] or [d for d in docs if d.document_type == "meeting_notes"]
    if not sel:
        return need("Upload meeting notes (document type 'meeting_notes') or pass a document_id.")
    actions, decisions, questions = [], [], []
    for d in sel[:10]:
        for pno, text in ctx.tool("document_pages")(d):
            for line in text.splitlines():
                ln = line.strip()
                if len(ln) < 8:
                    continue
                am, om = _ACTION.match(ln), _OWNER.search(ln)
                if am or (om and re.search(r"\b(by|before|due|until|will|to)\b", ln)):
                    task = (am.group("t") if am else om.group("t")).strip()
                    owner = om.group("o") if om else "Unassigned"
                    dm = _DUE.search(task)
                    dts = tu.parse_dates(ln)
                    due = dts[0][0].isoformat() if dts else (dm.group("d").strip() if dm else "not stated")
                    overdue = bool(dts and dts[0][0] < tu.today_utc())
                    actions.append([owner, task[:200], due + (" (OVERDUE)" if overdue else ""), d.original_filename, pno])
                elif _DECISION.search(ln):
                    decisions.append([ln[:220], d.original_filename, pno])
                elif _QUESTION.search(ln):
                    questions.append([ln[:220], d.original_filename, pno])
    unassigned = sum(1 for a in actions if a[0] == "Unassigned")
    secs = [table("Action items", ["Owner", "Task", "Due", "Source", "Page"], actions), table("Decisions recorded", ["Decision", "Source", "Page"], decisions), table("Open questions / TBD", ["Item", "Source", "Page"], questions)]
    if actions:
        counts = Counter(a[0] for a in actions)
        secs.insert(1, chart("Actions per owner", "bar", list(counts), [{"name": "Actions", "values": list(counts.values())}]))
    return Result(f"Found {len(actions)} action item(s) ({unassigned} without an owner), {len(decisions)} decision(s) and {len(questions)} open question(s).", secs, labels={"method": "Pattern-based extraction (e.g. 'Action: ...', 'Name will ... by <date>'). Check against the original notes."})


RISK_WORDS = [
    ("Schedule", r"delay|late\b|behind schedule|deadline|slip|overdue|missed"),
    ("Budget", r"overrun|over budget|cost increase|budget|funding|expensive|shortfall"),
    ("Resource", r"shortage|short[- ]staffed|attrition|capacity|unavailable|resource"),
    ("Technical", r"outage|bug|defect|vulnerab|incompatib|integration|performance|security|breach"),
    ("Dependency", r"blocked|dependency|depends on|waiting (on|for)|third[- ]party"),
    ("Compliance", r"compliance|audit|penalt|regulat|non[- ]complian|legal"),
]
SEV_HIGH = r"blocked|critical|breach|outage|cannot|missed|major|severe|penalt|non[- ]complian|shortfall"
SEV_MED = r"delay|risk|overrun|dependency|concern|slip|shortage|vulnerab|behind"


def risk_register(ctx: AgentContext) -> Result:
    docs = ctx.tool("project_documents")()
    sel = [d for d in docs if d.id == ctx.params.get("document_id")] or [d for d in docs if d.document_type in ("meeting_notes", "other", "policy")] or docs
    if not sel:
        return need("Upload project documents (status reports, meeting notes) to scan for risks.")
    reg, seen = [], set()
    for d in sel[:15]:
        for pno, text in ctx.tool("document_pages")(d):
            for s in tu.sentences(text, 25):
                cat = next((c for c, p in RISK_WORDS if re.search(p, s, re.I)), None)
                if not cat or s.lower() in seen:
                    continue
                seen.add(s.lower())
                sev = "High" if re.search(SEV_HIGH, s, re.I) else "Medium" if re.search(SEV_MED, s, re.I) else "Low"
                reg.append([f"R-{len(reg) + 1:03d}", cat, sev, s[:220], d.original_filename, pno, "Unassigned"])
    order = {"High": 0, "Medium": 1, "Low": 2}
    reg.sort(key=lambda r: order[r[2]])
    for i, r in enumerate(reg, 1):
        r[0] = f"R-{i:03d}"
    if not reg:
        return Result("No risk statements were detected in the selected documents.", [bullets("Note", ["Absence of flagged text is not evidence that there are no risks."])])
    cc = Counter(r[1] for r in reg)
    secs = [table("Risk register (draft)", ["ID", "Category", "Severity (keywords)", "Statement", "Source", "Page", "Owner"], reg[:60]), chart("Risks by category", "bar", list(cc), [{"name": "Risks", "values": list(cc.values())}]), bullets("Method", ["Statements are flagged by keywords and ranked by severity words only. Likelihood, impact, owners and mitigations must be assessed by people."])]
    return Result(f"Flagged {len(reg)} risk statement(s); {sum(1 for r in reg if r[2] == 'High')} high severity.", secs, labels={"method": "Keyword-based flagging; a starting point for a human-maintained register."})
