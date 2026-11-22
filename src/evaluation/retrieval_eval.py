"""
Retrieval-only evaluation (no answer generation, no LLM judge).

For every question in storage/ground_truth.json we know the chunk the question
was written from (`reference_chunk_id`). We run retrieval in each mode and
measure, against that gold chunk:

  - hit_rate (recall@context): was the gold chunk in the retrieved context?
  - precision: relevant chunks / chunks retrieved (1/N when hit, else 0)
  - mrr: reciprocal rank of the gold chunk in the retrieved list
  - context_chunks / context_chars: how much was put in the prompt. Recall
    must always be read next to this -- dumping everything gives 100% recall.
  - entity_hit_rate: was the target entity among the retrieved entities
    (case/whitespace-insensitive substring match)

Results are reported with n and a 95% Wilson interval, because n is small.

Caveats (also printed with the results):
  - Questions are LLM-generated from a single chunk, not hand-labelled.
  - One gold chunk per question; other chunks may also answer it.
  - Naive vector search is advantaged: a question written from a chunk's text
    is lexically close to that chunk.

Usage:
    python -m src.evaluation.retrieval_eval --modes naive hybrid
Note: query embedding goes through LM Studio (see src/rag/embedding.py), so LM Studio
must be running for every mode; local/global/hybrid also use the LLM for keyword extraction.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from discordant counts (A hit/B miss, A miss/B hit)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def score_retrieval(gold_chunk_id: str, target_entity: str, chunks: list[dict], entities: list[dict]) -> dict:
    """Score one retrieval result against the gold chunk. Pure function (unit-testable)."""
    ids = [c.get("chunk_id") for c in chunks]
    hit = gold_chunk_id in ids
    rank = ids.index(gold_chunk_id) + 1 if hit else None
    target = " ".join(target_entity.lower().split())
    names = [" ".join(str(e.get("entity_name", "")).lower().split()) for e in entities]
    return {
        "hit": hit,
        "precision": (1 / len(ids)) if hit and ids else 0.0,
        "mrr": (1 / rank) if rank else 0.0,
        "context_chunks": len(ids),
        "context_chars": sum(len(c.get("content", "")) for c in chunks),
        "entity_hit": any(target in n or n in target for n in names if n),
    }


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    hits = sum(r["hit"] for r in rows)
    ehits = sum(r["entity_hit"] for r in rows)
    lo, hi = wilson_interval(hits, n)
    elo, ehi = wilson_interval(ehits, n)
    mean = lambda k: sum(r[k] for r in rows) / n if n else 0.0
    return {
        "n": n,
        "hit_rate": round(hits / n, 3) if n else 0.0,
        "hit_rate_ci95": [round(lo, 3), round(hi, 3)],
        "precision": round(mean("precision"), 3),
        "mrr": round(mean("mrr"), 3),
        "entity_hit_rate": round(ehits / n, 3) if n else 0.0,
        "entity_hit_rate_ci95": [round(elo, 3), round(ehi, 3)],
        "avg_context_chunks": round(mean("context_chunks"), 1),
        "avg_context_chars": round(mean("context_chars")),
    }


async def run(modes: list[str]) -> dict:
    from src.rag.query import retrieve

    gt_path = STORAGE_DIR / "ground_truth.json"
    ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    ground_truth = [g for g in ground_truth if g.get("reference_chunk_id")]

    out: dict = {"n_questions": len(ground_truth), "modes": {}, "per_question": []}
    for mode in modes:
        rows = []
        for item in ground_truth:
            data = await retrieve(item["question"], mode=mode)
            row = score_retrieval(
                item["reference_chunk_id"], item["entity"],
                data["chunks"], data["entities"],
            )
            rows.append(row)
            out["per_question"].append({"mode": mode, "question": item["question"], **row})
        out["modes"][mode] = summarise(rows)

    # Paired comparison between every pair of modes on the same questions.
    by_mode: dict[str, list[bool]] = {}
    for r in out["per_question"]:
        by_mode.setdefault(r["mode"], []).append(r["hit"])
    out["paired"] = {}
    names = list(by_mode)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            only_a = sum(x and not y for x, y in zip(by_mode[a], by_mode[b]))
            only_b = sum(y and not x for x, y in zip(by_mode[a], by_mode[b]))
            out["paired"][f"{a}_vs_{b}"] = {
                f"only_{a}_hit": only_a, f"only_{b}_hit": only_b,
                "mcnemar_p": round(mcnemar_exact(only_a, only_b), 4),
            }

    out["caveats"] = [
        "Questions are LLM-generated from one chunk, not hand-labelled.",
        "Single gold chunk per question; other chunks may also be valid.",
        "Question text is lexically close to its source chunk, which favours naive vector search.",
    ]
    (STORAGE_DIR / "retrieval_eval.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["naive", "hybrid"])
    args = ap.parse_args()
    result = asyncio.run(run(args.modes))
    print(json.dumps({"n_questions": result["n_questions"], "modes": result["modes"], "paired": result["paired"]}, indent=2))
    print("\nCaveats:")
    for c in result["caveats"]:
        print(" -", c)
