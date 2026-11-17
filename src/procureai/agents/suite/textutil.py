"""Small deterministic text helpers shared by the agents (no model calls)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime

from procureai.rag.embeddings.hashing import _STOP, _WORD

_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})\b", re.I),
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I),
]
AMOUNT = re.compile(r"(?:USD|EUR|GBP|INR|Rs\.?|₹|\$|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|lakh|crore|k|m))?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|INR)\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def sentences(text: str, min_len: int = 20) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if len(s.strip()) >= min_len]


def summarize(text: str, n: int = 3) -> list[str]:
    """Extractive summary: sentences scored by normalised content-word frequency, returned in document order."""
    sents = sentences(text)
    if len(sents) <= n:
        return sents
    freq = Counter(w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2)
    top = max(freq.values()) if freq else 1
    scored = []
    for i, s in enumerate(sents):
        words = [w for w in _WORD.findall(s.lower()) if w not in _STOP and len(w) > 2]
        if not words:
            continue
        scored.append((sum(freq[w] / top for w in words) / (len(words) ** 0.6), i))
    best = sorted(scored, reverse=True)[:n]
    return [sents[i] for _, i in sorted(best, key=lambda x: x[1])]


def keywords(text: str, n: int = 10) -> list[tuple[str, int]]:
    c = Counter(w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 3 and not w.isdigit())
    return c.most_common(n)


def parse_dates(text: str) -> list[tuple[date, int, int]]:
    """Return (date, start, end) for every recognised date string."""
    found: list[tuple[date, int, int]] = []
    for idx, pat in enumerate(_DATE_PATTERNS):
        for m in pat.finditer(text):
            try:
                g = m.groups()
                if idx == 0:
                    d = date(int(g[0]), int(g[1]), int(g[2]))
                elif idx == 1:
                    d = date(int(g[2]), int(g[1]), int(g[0]))  # day/month/year
                elif idx == 2:
                    d = date(int(g[2]), MONTHS.index(g[1][:3].lower()) + 1, int(g[0]))
                else:
                    d = date(int(g[2]), MONTHS.index(g[0][:3].lower()) + 1, int(g[1]))
            except ValueError:
                continue
            found.append((d, m.start(), m.end()))
    return sorted(set(found), key=lambda x: x[1])


def context(text: str, start: int, end: int, width: int = 110) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - width) : end + width]).strip()


def pct(a: float, b: float) -> float | None:
    return None if not b else round((a - b) / abs(b) * 100, 1)


def today_utc() -> date:
    return datetime.utcnow().date()
