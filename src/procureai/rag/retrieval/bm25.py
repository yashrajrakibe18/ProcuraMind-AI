"""Okapi BM25 over the chunks of one project (built on demand from the vector store's stored text)."""

from __future__ import annotations

import math
from collections import Counter

from procureai.rag.embeddings.hashing import _STOP, _WORD, _stem


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in _WORD.findall(text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs, self.k1, self.b = docs, k1, b
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in docs]
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: list[str], index: int) -> float:
        tf, dl, s = self.tf[index], len(self.docs[index]), 0.0
        for t in set(query):
            f = tf.get(t, 0)
            if f:
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return s

    def rank(self, query: list[str]) -> list[tuple[int, float]]:
        scored = [(i, self.score(query, i)) for i in range(self.n)]
        return sorted([x for x in scored if x[1] > 0], key=lambda x: -x[1])
