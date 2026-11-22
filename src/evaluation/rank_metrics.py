"""
Standard ranked-retrieval metrics (binary relevance), as pure functions.

`ranked` is the list of retrieved chunk ids in the order the system returned them;
`gold` is the set of relevant chunk ids. NOTE: rank-based metrics (nDCG, AP, MRR,
@5/@10) assume the returned order reflects the system's ranking. Set-based recall
at the full context size (@20) does not depend on order.
"""
from __future__ import annotations

import math


def recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    return len(gold & set(ranked[:k])) / len(gold) if gold else 0.0


def precision_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """Relevant chunks in the top-k divided by k (not by len(ranked): an empty slot counts as a miss)."""
    return len(gold & set(ranked[:k])) / k


def ndcg_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, c in enumerate(ranked[:k]) if c in gold)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), k)))
    return dcg / idcg if idcg else 0.0


def average_precision_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    hits, total = 0, 0.0
    for i, c in enumerate(ranked[:k], 1):
        if c in gold:
            hits += 1
            total += hits / i
    denom = min(len(gold), k)
    return total / denom if denom else 0.0


def first_hit_reciprocal_rank(ranked: list[str], gold: set[str]) -> float:
    for i, c in enumerate(ranked, 1):
        if c in gold:
            return 1.0 / i
    return 0.0


def doc_coverage_at_k(ranked: list[str], gold_docs: list[str], chunk_to_doc: dict[str, str], k: int) -> float:
    """Fraction of gold judgments that contribute at least one chunk to the top-k."""
    docs = {chunk_to_doc.get(c) for c in ranked[:k]}
    gd = set(gold_docs)
    return len(gd & docs) / len(gd) if gd else 0.0


def all_metrics(ranked: list[str], gold_chunks: list[str], gold_docs: list[str],
                chunk_to_doc: dict[str, str] | None = None, ks: tuple[int, ...] = (5, 10, 20)) -> dict:
    gold = set(gold_chunks)
    out: dict = {}
    for k in ks:
        out[f"recall@{k}"] = recall_at_k(ranked, gold, k)
        out[f"all_hit@{k}"] = gold <= set(ranked[:k])
        out[f"precision@{k}"] = precision_at_k(ranked, gold, k)
        out[f"ndcg@{k}"] = ndcg_at_k(ranked, gold, k)
    out["map@20"] = average_precision_at_k(ranked, gold, 20)
    out["mrr"] = first_hit_reciprocal_rank(ranked, gold)
    if chunk_to_doc is not None:
        out["doc_coverage@20"] = doc_coverage_at_k(ranked, gold_docs, chunk_to_doc, 20)
    return out
