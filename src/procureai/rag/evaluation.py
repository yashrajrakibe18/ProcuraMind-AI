"""Retrieval metrics: Precision@K, Recall@K and MRR over a labelled query set."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    relevant: frozenset[str]  # identifiers, e.g. "policy.pdf#2" (filename#page) or section titles


def precision_at_k(ranked: list[str], relevant: frozenset[str], k: int) -> float:
    top = ranked[:k]
    return sum(1 for r in top if r in relevant) / k if k else 0.0


def recall_at_k(ranked: list[str], relevant: frozenset[str], k: int) -> float:
    return len({r for r in ranked[:k] if r in relevant}) / len(relevant) if relevant else 0.0


def reciprocal_rank(ranked: list[str], relevant: frozenset[str]) -> float:
    for i, r in enumerate(ranked, 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def summarize(results: list[tuple[list[str], frozenset[str]]], k: int) -> dict[str, float]:
    n = len(results) or 1
    return {
        f"precision@{k}": round(sum(precision_at_k(r, rel, k) for r, rel in results) / n, 4),
        f"recall@{k}": round(sum(recall_at_k(r, rel, k) for r, rel in results) / n, 4),
        "mrr": round(sum(reciprocal_rank(r, rel) for r, rel in results) / n, 4),
        "queries": float(len(results)),
    }
