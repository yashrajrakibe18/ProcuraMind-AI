"""Keyword-based document classification (transparent, deterministic)."""

from __future__ import annotations

import re

from procureai.shared.enums import DocumentType

_KEYWORDS: dict[DocumentType, list[tuple[str, float]]] = {
    DocumentType.TENDER: [
        (r"\btender\b", 2.0),
        (r"\brfp\b|request for proposal", 2.0),
        (r"\brfq\b", 1.5),
        (r"technical (requirements|specifications)", 2.5),
        (r"\bbidders?\b", 1.5),
        (r"eligibility", 1.0),
        (r"scope of (work|supply)", 1.5),
        (r"mandatory", 0.8),
        (r"invitation to bid", 2.0),
    ],
    DocumentType.QUOTATION: [
        (r"\bquotation\b|\bquote\b", 2.5),
        (r"unit price", 2.0),
        (r"\bvendor\b|\bsupplier\b", 1.2),
        (r"valid(ity)? (until|for)", 1.0),
        (r"offered specifications?", 2.0),
        (r"payment terms", 0.8),
        (r"\bgst\b|\bvat\b", 0.6),
    ],
    DocumentType.POLICY: [
        (r"\bpolic(y|ies)\b", 2.5),
        (r"\bprocedure\b", 1.2),
        (r"\bguidelines?\b", 1.2),
        (r"approval (threshold|authority|limit)", 2.0),
        (r"\bshall\b", 0.7),
        (r"procurement (manual|rules)", 2.0),
        (r"conflict of interest", 1.5),
        (r"competitive bidding", 1.5),
    ],
    DocumentType.CONTRACT: [
        (r"\bcontract\b|\bagreement\b", 2.0),
        (r"\bparties\b|the (client|supplier|licensor|licensee)", 1.5),
        (r"terminat(e|ion)", 1.5),
        (r"governing law|jurisdiction", 2.0),
        (r"indemnif", 1.5),
        (r"effective date|term of this", 1.5),
        (r"confidential(ity)?", 1.0),
    ],
    DocumentType.FINANCIAL: [
        (r"\bbudget\b", 2.5),
        (r"\bactuals?\b", 1.5),
        (r"\bvariance\b", 2.0),
        (r"expenses?|expenditure", 1.5),
        (r"balance sheet|income statement|cash flow", 2.0),
        (r"forecast", 1.0),
    ],
    DocumentType.RESUME: [
        (r"curriculum vitae|\bresume\b|\bcv\b", 2.5),
        (r"work experience|professional experience|employment history", 2.0),
        (r"\beducation\b", 1.0),
        (r"\bskills\b", 1.0),
        (r"\bb\.?tech\b|\bm\.?sc\b|bachelor|master of", 0.8),
    ],
    DocumentType.JOB_DESCRIPTION: [
        (r"job description|job title|position:", 2.5),
        (r"we are (hiring|looking for)", 2.0),
        (r"responsibilities", 1.5),
        (r"(required )?qualifications|must[- ]have|nice[- ]to[- ]have", 1.5),
        (r"years of experience", 1.0),
    ],
    DocumentType.MEETING_NOTES: [
        (r"meeting (notes|minutes)|minutes of", 2.5),
        (r"attendees|agenda", 1.5),
        (r"action items?", 2.0),
        (r"\bdecisions?\b", 1.0),
    ],
    DocumentType.KNOWLEDGE_BASE: [
        (r"knowledge base|help (center|centre)|faq", 2.5),
        (r"how (do|to) i|troubleshoot", 1.5),
        (r"refund policy|return policy|support hours", 1.5),
    ],
    DocumentType.HISTORICAL: [
        (r"purchase (history|records?)", 2.5),
        (r"historical", 2.0),
        (r"previous (orders?|purchases?)", 1.5),
    ],
}


def classify_text(text: str, filename: str = "") -> tuple[DocumentType, float]:
    """Return (type, confidence in [0,1]). Falls back to OTHER with low confidence."""
    haystack = f"{filename}\n{text}".lower()
    scores: dict[DocumentType, float] = {}
    for dtype, patterns in _KEYWORDS.items():
        scores[dtype] = sum(w * min(len(re.findall(p, haystack)), 3) for p, w in patterns)
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    if scores[best] < 2.0 or total == 0:
        return DocumentType.OTHER, 0.2
    return best, round(min(0.99, scores[best] / total * min(1.0, scores[best] / 8.0 + 0.4)), 2)
