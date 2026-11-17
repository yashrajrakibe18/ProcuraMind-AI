"""The agent implementations. Everything here is deterministic and traceable; language models are never required.

Each handler reads data only through ``ctx.tool(...)`` and returns a standard ``Result``.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from procureai.agents.suite import textutil as tu
from procureai.agents.suite.base import AgentContext, Result
from procureai.rag.answer_generation.answerer import generate_answer


# ---------------------------------------------------------------- section helpers
def table(title: str, columns: list[str], rows: list[list[Any]]) -> dict:
    return {"type": "table", "title": title, "columns": columns, "rows": rows}


def bullets(title: str, items: list[str]) -> dict:
    return {"type": "bullets", "title": title, "items": items}


def kv(title: str, items: list[list[Any]]) -> dict:
    return {"type": "kv", "title": title, "items": items}


def chart(title: str, kind: str, labels: list[str], series: list[dict]) -> dict:
    return {"type": "chart", "title": title, "kind": kind, "labels": labels, "series": series}


def need(msg: str) -> Result:
    return Result("More input is needed before this agent can run.", status="needs_input", needs_input=msg)


# ---------------------------------------------------------------- RAG knowledge agent
def rag_agent(ctx: AgentContext) -> Result:
    q = str(ctx.params.get("question", "")).strip()
    if not q:
        return need("Provide a 'question' to search the project's documents.")
    passages = ctx.tool("retrieve")(q, int(ctx.params.get("top_k", 5)))
    ans = generate_answer(q, passages, ctx.app.llm)
    evidence = [{"document": c.filename, "document_id": c.document_id, "page": c.page, "score": c.score, "snippet": c.snippet} for c in ans.citations]
    labels = {"evidence": "Retrieved passages are verbatim extracts from your documents."}
    labels["answer"] = "AI-generated interpretation (quote-validated)." if ans.mode == "llm" else ("Extractive: the sentences below are copied from the evidence." if ans.grounded else "No grounded answer.")
    secs = [{"type": "text", "title": "Answer", "text": ans.answer}]
    if evidence:
        secs.append(table("Evidence", ["Document", "Page", "Score", "Excerpt"], [[e["document"], e["page"], e["score"], e["snippet"][:240]] for e in evidence]))
    return Result(ans.answer, secs, evidence, llm_calls=1 if ans.mode == "llm" else 0, labels=labels, data={"mode": ans.mode, "grounded": ans.grounded})


# ---------------------------------------------------------------- Research agent
def research_agent(ctx: AgentContext) -> Result:
    q = str(ctx.params.get("question", "")).strip()
    if not q:
        return need("Provide a research 'question' (separate sub-questions with ';' or 'and').")
    subs = [s.strip(" ?.") for s in re.split(r";|\?|\band\b", q) if len(s.strip(" ?.")) > 3] or [q]
    rows, missing, evidence = [], [], []
    for s in subs[:8]:
        ps = ctx.tool("retrieve")(s, 3)
        if ps:
            rows.append([s, "Evidence found", f"{ps[0].filename} p.{ps[0].page}", ps[0].text[:160].replace("\n", " ")])
            evidence += [{"document": p.filename, "document_id": p.document_id, "page": p.page, "score": p.score, "snippet": p.text[:300]} for p in ps[:2]]
        else:
            rows.append([s, "NO EVIDENCE", "-", ""])
            missing.append(s)
    kw = Counter()
    for d in ctx.tool("project_documents")():
        text = " ".join(t for _, t in ctx.tool("document_pages")(d))
        kw.update(dict(tu.keywords(text, 15)))
    secs = [table("Findings per question", ["Question", "Result", "Best source", "Excerpt"], rows), bullets("Missing evidence", [f"No supporting passage found for: {m}" for m in missing] or ["None: every sub-question has at least one supporting passage."]), bullets("Recurring terms across project documents", [f"{w} ({n})" for w, n in kw.most_common(10)])]
    return Result(f"{len(subs) - len(missing)} of {len(subs)} sub-question(s) have supporting evidence; {len(missing)} lack evidence.", secs, evidence[:10], labels={"findings": "Passages are verbatim; coverage is lexical (BM25 + vector), not semantic proof."})


# ---------------------------------------------------------------- Document intelligence
EXPECTED = {
    "contract": ["parties", "term", "payment", "terminat", "liabilit", "governing law", "confidential"],
    "tender": ["scope", "eligib", "technical", "delivery", "warranty"],
    "policy": ["approval", "threshold", "procedure"],
    "quotation": ["unit price", "delivery", "warranty", "valid"],
}


def document_agent(ctx: AgentContext) -> Result:
    docs = ctx.tool("project_documents")()
    if ctx.params.get("document_id"):
        docs = [d for d in docs if d.id == ctx.params["document_id"]]
    if not docs:
        return need("Upload and process at least one document (PDF, DOCX, XLSX, CSV, TXT).")
    rows, secs, texts = [], [], {}
    for d in docs[:12]:
        text = "\n".join(t for _, t in ctx.tool("document_pages")(d))
        texts[d.id] = text
        low = text.lower()
        miss = [k for k in EXPECTED.get(d.document_type, []) if k not in low]
        dates = [x[0].isoformat() for x in tu.parse_dates(text)[:3]]
        amounts = [m.group(0) for m in tu.AMOUNT.finditer(text)][:3]
        rows.append([d.original_filename, d.document_type, d.page_count, f"{d.classification_confidence:.2f}", ", ".join(dates) or "-", ", ".join(amounts) or "-", ", ".join(miss) or "none"])
        summ = tu.summarize(text, 3)
        if summ:
            secs.append({"type": "text", "title": f"Summary: {d.original_filename} (extractive)", "text": " ".join(summ)})
    secs.insert(0, table("Documents", ["File", "Type", "Pages", "Classification confidence", "Dates found", "Amounts found", "Expected sections not found"], rows))
    cmp_id = ctx.params.get("compare_with")
    if cmp_id and ctx.params.get("document_id"):
        other = [d for d in ctx.tool("project_documents")() if d.id == cmp_id]
        if other:
            a, b = texts[ctx.params["document_id"]], "\n".join(t for _, t in ctx.tool("document_pages")(other[0]))
            sim = float((lambda m: (m[0] @ m[1].T).toarray()[0][0])(TfidfVectorizer().fit_transform([a, b]))) if a.strip() and b.strip() else 0.0
            la, lb = [x.strip() for x in a.splitlines() if x.strip()], [x.strip() for x in b.splitlines() if x.strip()]
            diff = [x for x in difflib.unified_diff(la, lb, lineterm="", n=0) if x[:1] in "+-" and x[:3] not in ("+++", "---")]
            secs.append(kv("Comparison", [["Cosine (TF-IDF) similarity", round(sim, 3)], ["Lines only in first", sum(1 for x in diff if x[0] == "-")], ["Lines only in second", sum(1 for x in diff if x[0] == "+")]]))
            secs.append(bullets("Sample differences", [x[:200] for x in diff[:12]]))
    flagged = sum(1 for r in rows if r[-1] != "none")
    return Result(f"Processed {len(rows)} document(s); {flagged} appear to lack expected sections.", secs, labels={"summary": "Extractive summaries copy the most informative sentences; nothing is generated."})


# ---------------------------------------------------------------- Data analyst
def _pick_dataset(ctx: AgentContext):
    docs = ctx.tool("project_documents")(mimes=("text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    if ctx.params.get("document_id"):
        docs = [d for d in docs if d.id == ctx.params["document_id"]]
    docs = sorted(docs, key=lambda d: (d.document_type != "dataset", d.document_type == "historical"))
    return docs[0] if docs else None


def data_agent(ctx: AgentContext) -> Result:
    doc = _pick_dataset(ctx)
    if doc is None:
        return need("Upload a CSV or Excel dataset to analyse (set its type to 'dataset').")
    df = ctx.tool("load_dataframe")(doc)
    if df.empty:
        return need("The dataset has no rows.")
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    cat = [c for c in df.columns if c not in num and df[c].nunique() <= 20 and df[c].nunique() > 1]
    datecol = None
    for c in df.columns:
        if c in num:
            continue
        if re.search(r"date|month|period|time", str(c), re.I):
            parsed = pd.to_datetime(df[c], errors="coerce")
            if parsed.notna().mean() > 0.8:
                df[c], datecol = parsed, c
                break
    secs, insights = [], []
    miss = df.isna().sum()
    secs.append(kv("Dataset", [["File", doc.original_filename], ["Rows", len(df)], ["Columns", len(df.columns)], ["Missing cells", int(miss.sum())], ["Duplicate rows", int(df.duplicated().sum())]]))
    if miss.sum():
        worst = miss.sort_values(ascending=False).index[0]
        insights.append(f"{int(miss.sum())} cells are missing; column '{worst}' has the most ({int(miss[worst])}).")
    if num:
        d = df[num[:8]].describe().T
        secs.append(table("Numeric summary", ["Column", "Mean", "Std", "Min", "Median", "Max"], [[c, round(r["mean"], 2), round(r["std"], 2) if pd.notna(r["std"]) else 0, round(r["min"], 2), round(r["50%"], 2), round(r["max"], 2)] for c, r in d.iterrows()]))
    anomalies = []
    for c in num[:8]:
        s = df[c].dropna()
        if len(s) < 8:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        out = s[(s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)]
        for idx, v in out.head(3).items():
            anomalies.append([c, int(idx) + 2, round(float(v), 2), f"outside [{q1 - 1.5 * iqr:.2f}, {q3 + 1.5 * iqr:.2f}]"])
        if len(out):
            insights.append(f"'{c}' has {len(out)} outlier(s) by the 1.5×IQR rule.")
    if anomalies:
        secs.append(table("Anomalies (IQR rule; row = spreadsheet row)", ["Column", "Row", "Value", "Normal range"], anomalies[:15]))
    if datecol and num:
        g = df.dropna(subset=[datecol]).set_index(datecol)[num[0]].resample("MS").sum()
        if len(g) >= 3:
            slope = np.polyfit(range(len(g)), g.values, 1)[0]
            change = tu.pct(float(g.iloc[-1]), float(g.iloc[0]))
            insights.append(f"'{num[0]}' trends {'up' if slope > 0 else 'down'} across {len(g)} months (first→last change {change}%).")
            secs.append(chart(f"{num[0]} by month", "line", [t.strftime("%Y-%m") for t in g.index], [{"name": num[0], "values": [round(float(v), 2) for v in g.values]}]))
    if cat and num:
        g = df.groupby(cat[0])[num[0]].sum().sort_values(ascending=False).head(12)
        secs.append(chart(f"{num[0]} by {cat[0]}", "bar", [str(i) for i in g.index], [{"name": num[0], "values": [round(float(v), 2) for v in g.values]}]))
        insights.append(f"'{g.index[0]}' contributes the most to '{num[0]}' ({g.iloc[0] / g.sum() * 100:.0f}% of the total).")
    if len(num) >= 2:
        corr = df[num].corr().abs().unstack().sort_values(ascending=False)
        pairs = [(a, b, round(float(df[a].corr(df[b])), 2)) for (a, b), v in corr.items() if a < b and v > 0.6][:3]
        if pairs:
            secs.append(table("Strong correlations (|r| > 0.6)", ["A", "B", "r"], [list(p) for p in pairs]))
            insights.append(f"Strongest relationship: {pairs[0][0]} vs {pairs[0][1]} (r = {pairs[0][2]}).")
    secs.append(bullets("Automated insights (rule-based, computed from the data above)", insights or ["No notable patterns detected."]))
    return Result(f"Analysed {len(df)} rows × {len(df.columns)} columns of {doc.original_filename}; {len(insights)} insight(s).", secs, labels={"insights": "Computed with pandas/NumPy rules, not generated text."})


# ---------------------------------------------------------------- Financial analysis
def _find_col(cols: list[str], words: tuple[str, ...], exclude: set[str] = frozenset()) -> str | None:
    for c in cols:
        if c not in exclude and any(w in str(c).lower() for w in words):
            return c
    return None


def financial_agent(ctx: AgentContext) -> Result:
    secs, summary_parts = [], []
    for doc in ctx.tool("project_documents")(mimes=("text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")):
        if ctx.params.get("document_id") and doc.id != ctx.params["document_id"]:
            continue
        df = ctx.tool("load_dataframe")(doc)
        cols = list(df.columns)
        b = _find_col(cols, ("budget", "planned", "plan", "estimate", "forecast"))
        a = _find_col(cols, ("actual", "spent", "spend", "expense", "incurred"), {b} if b else set())
        if not (a and b and pd.api.types.is_numeric_dtype(df[a]) and pd.api.types.is_numeric_dtype(df[b])):
            continue
        cat = next((c for c in cols if c not in (a, b) and not pd.api.types.is_numeric_dtype(df[c])), None)
        g = df.groupby(cat)[[b, a]].sum() if cat else df[[b, a]].sum().to_frame().T
        g["variance"] = g[a] - g[b]
        g["var_pct"] = [tu.pct(x, y) for x, y in zip(g[a], g[b])]
        rows = [[str(i), round(r[b], 2), round(r[a], 2), round(r["variance"], 2), r["var_pct"], "OVER budget" if r["variance"] > 0 else "under/at budget"] for i, r in g.iterrows()]
        secs.append(table(f"Budget vs actual: {doc.original_filename}", ["Category", "Budget", "Actual", "Variance", "Variance %", "Status"], rows))
        if cat:
            secs.append(chart("Budget vs actual by category", "bar", [str(i) for i in g.index], [{"name": "Budget", "values": [round(float(v), 2) for v in g[b]]}, {"name": "Actual", "values": [round(float(v), 2) for v in g[a]]}]))
        tb, ta = float(g[b].sum()), float(g[a].sum())
        unusual = [f"{i}: {r['var_pct']}% vs budget" for i, r in g.iterrows() if r["var_pct"] is not None and abs(r["var_pct"]) >= 20]
        secs.append(bullets("Unusual spending (|variance| ≥ 20% of budget)", unusual or ["No category deviates by 20% or more."]))
        summary_parts.append(f"{doc.original_filename}: budget {tb:,.0f}, actual {ta:,.0f} ({tu.pct(ta, tb)}% vs budget); {len(unusual)} unusual categor{'y' if len(unusual) == 1 else 'ies'}")
    run = ctx.tool("latest_run")()
    if run is not None:
        peer = [p for p in ctx.tool("price_rows")(run) if p.baseline_source == "peer" and p.normalized_unit_price]
        if peer:
            secs.append(table("Quotation cost comparison (all-in unit price)", ["Vendor", "Unit price", "Currency", "Deviation vs peers", "Flag"], [[p.vendor_name, round(p.normalized_unit_price, 2), p.base_currency, f"{p.deviation_pct}%" if p.deviation_pct is not None else "-", "review" if p.anomaly_flag else "-"] for p in peer]))
            summary_parts.append(f"{len(peer)} vendor quotation(s) compared on all-in unit price")
    if not secs:
        return need("Upload a CSV/XLSX with a budget column (budget/planned) and an actual column (actual/spent/expense), plus a category column; or run a procurement analysis for cost comparison.")
    return Result("; ".join(summary_parts) + ".", secs, labels={"figures": "All figures are computed from your files; no estimates were generated."})


# ---------------------------------------------------------------- Contract intelligence
CLAUSES = {
    "Termination": r"terminat", "Payment": r"payment|invoice|net \d+", "Liability": r"liabilit", "Confidentiality": r"confidential|non-disclosure",
    "Indemnity": r"indemnif", "Renewal": r"renew", "Governing law": r"governing law|jurisdiction", "Warranty": r"warrant",
    "Service levels": r"service level|\bsla\b|uptime", "Intellectual property": r"intellectual property|copyright|ownership of", "Force majeure": r"force majeure",
}
RISKS = [
    ("Auto-renewal", r"automatic(ally)? renew|auto-?renew|evergreen", "medium", "The contract may renew without action; diarise the notice deadline."),
    ("Unlimited liability", r"unlimited liability|without (any )?limit(ation)?|no (cap|limit) on liabilit", "high", "Liability appears uncapped."),
    ("Unilateral termination", r"terminate[^.]{0,60}(at any time|sole discretion)|sole discretion[^.]{0,60}terminat", "high", "One party may terminate at will."),
    ("Penalties", r"penalt(y|ies)|liquidated damages", "medium", "Financial penalties apply; check amounts and triggers."),
    ("Exclusivity", r"exclusive(ly)?\b|sole supplier|sole provider", "medium", "Exclusivity limits alternative suppliers."),
    ("Long notice period", r"(\b(9\d|1\d\d|\d{3,})\s*\(?\d*\)?\s*days?[’']?\s*(prior )?(written )?notice)", "low", "Notice period of 90+ days."),
]


def _contract_docs(ctx: AgentContext):
    docs = ctx.tool("project_documents")()
    if ctx.params.get("document_id"):
        return [d for d in docs if d.id == ctx.params["document_id"]]
    c = [d for d in docs if d.document_type == "contract"]
    return c


def contract_agent(ctx: AgentContext) -> Result:
    docs = _contract_docs(ctx)
    if not docs:
        return need("Upload a contract (set its type to 'contract' or let auto-classification detect it), or pass a document_id.")
    horizon = int(ctx.params.get("expiring_days", 60))
    secs, evidence, expiring, presence = [], [], [], {}
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    total_risks = 0
    for d in docs[:6]:
        pages = ctx.tool("document_pages")(d)
        clause_rows, dates_rows, risk_rows, found = [], [], [], set()
        for pno, text in pages:
            sents = tu.sentences(text)
            for name, pat in CLAUSES.items():
                hit = next((s for s in sents if re.search(pat, s, re.I)), None)
                if hit and name not in found:
                    found.add(name)
                    clause_rows.append([name, pno, hit[:220]])
            for dt, s, e in tu.parse_dates(text):
                ctxt = tu.context(text, s, e)
                low = ctxt.lower()
                label = "Renewal" if "renew" in low else "Expiry" if re.search(r"expir|end date|terminat|until|ends? on", low) else "Effective" if re.search(r"effective|commenc|start|begin", low) else "Date"
                dates_rows.append([dt.isoformat(), label, pno, ctxt[:200]])
                days = (dt - tu.today_utc()).days
                if label in ("Expiry", "Renewal") and 0 <= days <= horizon:
                    expiring.append([d.original_filename, label, dt.isoformat(), days])
            for name, pat, sev, why in RISKS:
                m = re.search(pat, text, re.I)
                if m:
                    risk_rows.append([sev.upper(), name, pno, why, tu.context(text, m.start(), m.end(), 80)])
        for name in ("Termination", "Liability", "Governing law", "Payment"):
            if name not in found:
                risk_rows.append(["MEDIUM", f"Missing clause: {name}", "-", f"No {name.lower()} language was detected.", ""])
        presence[d.original_filename] = found
        risk_rows.sort(key=lambda r: sev_rank[r[0].lower()])
        total_risks += len(risk_rows)
        secs.append(table(f"Clauses found: {d.original_filename}", ["Clause", "Page", "Text"], clause_rows))
        secs.append(table(f"Important dates: {d.original_filename}", ["Date", "Role", "Page", "Context"], dates_rows[:15]))
        secs.append(table(f"Risk indicators: {d.original_filename}", ["Severity", "Indicator", "Page", "Why it matters", "Evidence"], risk_rows))
        evidence += [{"document": d.original_filename, "document_id": d.id, "page": r[1], "snippet": r[2]} for r in clause_rows[:3]]
    if expiring:
        secs.insert(0, table(f"Expiring or renewing within {horizon} days", ["Document", "Event", "Date", "Days left"], expiring))
        for row in expiring:
            ctx.tool("notify")(f"Contract {row[1].lower()} in {row[3]} days", f"{row[0]}: {row[1]} on {row[2]}", "contract", None)
    if len(docs) >= 2:
        names = list(presence)
        allc = sorted(set().union(*presence.values()))
        secs.append(table("Clause comparison", ["Clause"] + names, [[c] + ["yes" if c in presence[n] else "NO" for n in names] for c in allc]))
    return Result(f"Reviewed {len(docs)} contract(s): {total_risks} risk indicator(s), {len(expiring)} expiring/renewing within {horizon} days.", secs, evidence, labels={"risks": "Risk indicators are keyword rules to focus a lawyer's review. They are not legal advice."})


# ---------------------------------------------------------------- Procurement / compliance / vendor
def procurement_agent(ctx: AgentContext) -> Result:
    out = ctx.tool("run_procurement")(bool(ctx.params.get("auto_confirm", False)))
    if out["needs_input"]:
        return need(out["needs_input"])
    run = out["run"]
    s = run.summary or {}
    secs = [kv("Analysis run", [["Run id", run.id], ["Status", run.status], ["Open review items", s.get("open_review_items", "-")], ["Vendors", s.get("vendors", "-")]])]
    msg = {"awaiting_human_review": "Analysis finished and is awaiting human review before approval.", "completed": "Analysis finished.", "failed": f"Analysis failed: {run.error}"}.get(run.status, f"Run status: {run.status}")
    return Result(msg, secs, status="completed" if run.status != "failed" else "completed", data={"run_id": run.id, "run_status": run.status})


def compliance_agent(ctx: AgentContext) -> Result:
    run = ctx.tool("latest_run")()
    if run is None:
        return need("Run the procurement analysis first (no finished run exists).")
    rows = ctx.tool("compliance_rows")(run)
    from collections import Counter

    counts = Counter(r.effective_status for r in rows)
    issues = [r for r in rows if r.effective_status != "Meets Requirement"]
    secs = [kv("Status counts", [[k, v] for k, v in counts.most_common()]), table("Non-compliant, missing or uncertain", ["Vendor", "Requirement", "Criticality", "Status", "Explanation"], [[r.vendor_name, r.requirement_label, r.criticality, r.effective_status, r.explanation[:200]] for r in issues])]
    evidence = [{"document": (r.evidence or {}).get("filename", ""), "page": (r.evidence or {}).get("page"), "snippet": str((r.evidence or {}).get("source_text", ""))[:240]} for r in issues if r.evidence][:10]
    open_items = len(ctx.tool("open_review_items")(run))
    return Result(f"{len(rows)} checks: {counts.get('Meets Requirement', 0)} met, {len(issues)} need attention; {open_items} open review item(s).", secs, evidence, labels={"verdicts": "Verdicts come from the deterministic rule engine, not a language model."})


def vendor_agent(ctx: AgentContext) -> Result:
    run = ctx.tool("latest_run")()
    if run is None:
        return need("Run the procurement analysis first so vendors can be evaluated.")
    comp, price = ctx.tool("compliance_rows")(run), ctx.tool("price_rows")(run)
    vendors = sorted({r.vendor_name for r in comp})
    rows, charts_v, charts_r = [], [], []
    for v in vendors:
        c = [r for r in comp if r.vendor_name == v]
        n = len(c) or 1
        meets = sum(r.effective_status == "Meets Requirement" for r in c)
        fails = sum(r.effective_status == "Does Not Meet Requirement" for r in c)
        mand_fail = sum(r.effective_status == "Does Not Meet Requirement" and r.criticality == "mandatory" for r in c)
        miss = sum(r.effective_status == "Missing Information" for r in c)
        rev = sum(r.effective_status == "Requires Human Review" for r in c)
        pr = [p for p in price if p.vendor_name == v]
        flagged = any(p.anomaly_flag for p in pr)
        dev = next((p.deviation_pct for p in pr if p.baseline_source == "peer" and p.deviation_pct is not None), None)
        risk = round(min(100, 45 * mand_fail / n + 15 * (fails - mand_fail) / n + 15 * miss / n + 10 * rev / n + (20 if flagged else 0)), 1)
        label = "HIGH" if risk >= 40 else "MEDIUM" if risk >= 20 else "LOW"
        flags = [t for t, on in (("mandatory requirement(s) failed", mand_fail), ("information missing", miss), ("needs human review", rev), ("price outlier vs baseline", flagged)) if on]
        rows.append([v, f"{meets}/{n}", mand_fail, miss, f"{dev}%" if dev is not None else "-", risk, label, "; ".join(flags) or "none"])
        charts_v.append(v)
        charts_r.append(risk)
    rows.sort(key=lambda r: r[5])
    secs = [table("Vendor evaluation (lowest risk first)", ["Vendor", "Requirements met", "Mandatory fails", "Missing", "Price vs peers", "Risk score (0-100)", "Risk", "Indicators"], rows), chart("Risk score by vendor", "bar", [r[0] for r in rows], [{"name": "Risk score", "values": [r[5] for r in rows]}]), bullets("How the risk score is computed", ["45 × mandatory-fail share + 15 × other-fail share + 15 × missing share + 10 × review share, plus 20 if the price is flagged (capped at 100). Transparent heuristic, not a calibrated model."])]
    best = rows[0]
    return Result(f"{len(rows)} vendor(s) evaluated. Lowest risk: {best[0]} (score {best[5]}). This is decision support; a person must select the vendor.", secs, labels={"risk": "Heuristic score from stored compliance and price results."})


# ---------------------------------------------------------------- Report
def report_agent(ctx: AgentContext) -> Result:
    kind = str(ctx.params.get("kind", "summary")).lower()
    if kind in ("pdf", "excel"):
        run = ctx.tool("latest_run")()
        if run is None:
            return need("A finished procurement analysis is required for PDF/Excel reports.")
        rep = ctx.tool("make_report")(kind)
        return Result(f"Generated {kind.upper()} report '{rep.filename}'. Download it from the Reports page.", [kv("Report", [["File", rep.filename], ["Report id", rep.id]])], data={"report_id": rep.id})
    tasks = ctx.tool("recent_tasks")(15)
    if not tasks:
        return need("Run at least one agent in this project first; the executive summary consolidates their results.")
    items = [f"{t.agent.replace('_', ' ').title()}: {(t.output or {}).get('summary', '')}" for t in tasks]
    return Result("Executive summary compiled from the latest agent results.", [bullets(f"Executive summary: {ctx.project.title}", items), {"type": "text", "title": "Note", "text": "This summary only repeats findings already produced and stored by the agents above; it adds no new claims."}], labels={"summary": "Consolidation of stored agent summaries."})


# ---------------------------------------------------------------- Communication (draft-only)
def communication_agent(ctx: AgentContext) -> Result:
    kind = str(ctx.params.get("kind", "task_update"))
    drafts = []
    if kind == "vendor_followup":
        run = ctx.tool("latest_run")()
        if run is None:
            return need("Run the procurement analysis first; follow-ups are drafted from missing/uncertain items.")
        rows = [r for r in ctx.tool("compliance_rows")(run) if r.effective_status in ("Missing Information", "Requires Human Review")]
        for v in sorted({r.vendor_name for r in rows}):
            items = [f"- {r.requirement_label} ({r.effective_status.lower()})" for r in rows if r.vendor_name == v]
            drafts.append({"type": "draft", "title": f"Email to {v}", "subject": f"Clarification needed on your quotation - {ctx.project.title}", "body": f"Dear {v} team,\n\nThank you for your quotation. To complete our evaluation we need clarification on:\n" + "\n".join(items) + "\n\nPlease reply with the missing details.\n\nKind regards,\n" + ctx.user.full_name})
        if not drafts:
            return Result("No vendor needs follow-up: no missing or uncertain items.", [])
    elif kind == "meeting_summary":
        tasks = ctx.tool("recent_tasks")(10)
        audit = ctx.tool("recent_audit")(10)
        body = f"Project: {ctx.project.title}\n\nAgent results:\n" + "\n".join(f"- {t.agent}: {(t.output or {}).get('summary', '')}" for t in tasks) + "\n\nRecent activity:\n" + "\n".join(f"- {a.timestamp:%Y-%m-%d %H:%M} {a.action}" for a in audit)
        drafts.append({"type": "draft", "title": "Meeting summary", "subject": f"Summary: {ctx.project.title}", "body": body})
    else:
        run = ctx.tool("latest_run")()
        status = f"Latest analysis run: {run.status}." if run else "No analysis has been run yet."
        drafts.append({"type": "draft", "title": "Task update", "subject": f"Status update: {ctx.project.title}", "body": f"Hello,\n\n{status}\nOpen tasks and approvals are visible in ProcuraMind.\n\n{ctx.user.full_name}"})
    return Result(f"Prepared {len(drafts)} draft(s) for your approval. Nothing is sent: copy approved drafts into your own mail client.", drafts, status="awaiting_approval", labels={"drafts": "Templated from stored results. ProcuraMind never sends external communications."})


# ---------------------------------------------------------------- Supervisor / workflow (delegating)
def supervisor_agent(ctx: AgentContext) -> Result:
    from procureai.agents.suite.orchestrator import supervise

    return supervise(ctx)


def workflow_agent(ctx: AgentContext) -> Result:
    from procureai.agents.suite.orchestrator import run_workflow_agent

    return run_workflow_agent(ctx)
