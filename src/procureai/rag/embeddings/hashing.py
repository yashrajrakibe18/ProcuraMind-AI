"""Deterministic, offline embedder (hashed word 1-2 grams, L2-normalised). No model download required.

This is a lexical embedder: good for policy/clause retrieval on shared vocabulary, weaker on pure paraphrase.
Swap in a neural embedder behind the same ``embed`` interface when one is available.
"""

from __future__ import annotations

import re

from sklearn.feature_extraction.text import HashingVectorizer

_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with "
    "shall should must may can not no any all each per".split()
)
_WORD = re.compile(r"[a-z0-9]+")


def _stem(tok: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
            return tok[: -len(suffix)]
    return tok


def analyze(text: str) -> list[str]:
    toks = [_stem(t) for t in _WORD.findall(text.lower()) if t not in _STOP]
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]


class HashingEmbedder:
    name = "hashing-v1"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self._vec = HashingVectorizer(n_features=dim, analyzer=analyze, alternate_sign=False, norm="l2")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._vec.transform(texts).toarray().tolist()
