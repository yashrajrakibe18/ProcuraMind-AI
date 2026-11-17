"""Reproducible retrieval evaluation on the SYNTHETIC policy document.

Usage: python scripts/evaluate_retrieval.py [--k 3]
Reports Precision@K, Recall@K and MRR for several chunk sizes. These numbers describe ONLY this small synthetic set;
they are not a claim about accuracy on real procurement documents.
"""

import argparse
import json
import tempfile
from pathlib import Path

from procureai.document_processing.loaders.loader import load_pages
from procureai.infrastructure.vector_store.chroma_store import ChromaVectorStore
from procureai.rag.embeddings.hashing import HashingEmbedder
from procureai.rag.evaluation import summarize
from procureai.rag.ingestion.indexer import DocumentIndexer
from procureai.rag.retrieval.retriever import Retriever
from procureai.samples.generate import policy_pdf

ROOT = Path(__file__).resolve().parent.parent


def evaluate(target_tokens: int, overlap: int, k: int, cases: list[dict], mode: str = "vector") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "policy.pdf"
        pdf.write_bytes(policy_pdf())
        pages = [(p.page_number, p.text) for p in load_pages(pdf, "application/pdf")]
        store, emb = ChromaVectorStore(str(Path(tmp) / "chroma")), HashingEmbedder(512)
        DocumentIndexer(store, emb, target_tokens, overlap).index(
            project_id="eval", document_id="policy", document_type="policy", filename="policy.pdf", pages=pages
        )
        retriever = Retriever(store, emb, min_score=0.0, mode=mode)
        results = []
        for case in cases:
            passages = retriever.retrieve("eval", case["query"], top_k=k)
            results.append(([p.section for p in passages], frozenset(case["relevant"])))
        return summarize(results, k)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    k = ap.parse_args().k
    cases = json.loads((ROOT / "tests/fixtures/retrieval_gold.json").read_text())["cases"]
    for mode in ("vector", "bm25", "hybrid"):
        print(f"\nmode = {mode}")
        print(f"{'chunk_tokens/overlap':<22}", "  ".join(f"{m:>12}" for m in (f"precision@{k}", f"recall@{k}", "mrr")))
        for tokens, overlap in ((60, 10), (220, 40), (500, 80), (900, 120)):
            r = evaluate(tokens, overlap, k, cases, mode)
            print(f"{tokens}/{overlap:<17}", "  ".join(f"{r[m]:>12.3f}" for m in (f"precision@{k}", f"recall@{k}", "mrr")))
