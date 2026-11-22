"""
Retrieval evaluation on multi-chunk, cross-judgment questions.

Each question's gold set is 2-4 chunks from different judgments. Per mode we report
(means with 95% bootstrap intervals over questions):

  recall@5/10/20     mean fraction of gold chunks within the first K retrieved
  all_hit@K          fraction of questions where EVERY gold chunk is within the first K
  precision@K        relevant chunks in the top K / K
  ndcg@K, map@20     rank-aware quality (assumes returned order = system ranking)
  mrr                reciprocal rank of the first gold chunk
  doc_coverage@20    fraction of gold judgments represented in the context
  latency            retrieval latency (mean / p50 / p95 ms)
  avg_context_*      how much context was used (recall means little without it)

Modes are compared with a paired sign test and a paired bootstrap interval on
per-question recall@20. Per-question retrieved id lists are saved so any further
metric can be computed offline.

    python -m src.evaluation.multichunk_eval --modes naive mix hybrid --gt ground_truth_multi.json
    python -m src.evaluation.multichunk_eval --modes mix --params '{"chunk_top_k": 40}' --tag ctk40

Needs LM Studio running (query embeddings; keyword extraction for graph modes).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.rank_metrics import all_metrics  # noqa: E402

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
KS = (5, 10, 20)
EXTRA_METRICS = ("recall@ctx", "all_hit@ctx", "precision@5", "precision@10", "precision@20", "ndcg@10", "ndcg@20", "map@20", "mrr", "doc_coverage@20")


def score_multi(gold_chunks: list[str], gold_docs: list[str], chunks: list[dict],
                chunk_to_doc: dict[str, str] | None = None) -> dict:
    """Pure function: score one retrieval result against a multi-chunk gold set."""
    ids = [c.get("chunk_id") for c in chunks]
    out = all_metrics(ids, gold_chunks, gold_docs, chunk_to_doc)
    gold = set(gold_chunks)
    out["recall@ctx"] = len(gold & set(ids)) / len(gold) if gold else 0.0   # over the WHOLE returned context
    out["all_hit@ctx"] = gold <= set(ids)
    out["context_chunks"] = len(ids)
    out["context_chars"] = sum(len(c.get("content", "")) for c in chunks)
    return out


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


def sign_test(diffs: list[float]) -> tuple[int, int, float]:
    """Exact two-sided sign test on paired differences (ties dropped)."""
    pos, neg = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    n = pos + neg
    if n == 0:
        return pos, neg, 1.0
    tail = sum(math.comb(n, i) for i in range(min(pos, neg) + 1)) / 2 ** n
    return pos, neg, min(1.0, 2 * tail)


def _percentile(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))] if sorted_vals else 0.0


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    out: dict = {"n": n}
    for k in KS:
        vals = [r[f"recall@{k}"] for r in rows]
        lo, hi = bootstrap_ci(vals)
        out[f"recall@{k}"] = round(sum(vals) / n, 3)
        out[f"recall@{k}_ci95"] = [round(lo, 3), round(hi, 3)]
        out[f"all_hit@{k}"] = round(sum(r[f"all_hit@{k}"] for r in rows) / n, 3)
    for m in EXTRA_METRICS:
        if all(m in r for r in rows):
            out[m] = round(sum(r[m] for r in rows) / n, 3)
    out["avg_context_chunks"] = round(sum(r["context_chunks"] for r in rows) / n, 1)
    out["avg_context_chars"] = round(sum(r["context_chars"] for r in rows) / n)
    lat = sorted(r["latency_ms"] for r in rows if "latency_ms" in r)
    if lat:
        out["latency_ms_mean"] = round(sum(lat) / len(lat))
        out["latency_ms_p50"] = round(_percentile(lat, 0.5))
        out["latency_ms_p95"] = round(_percentile(lat, 0.95))
    return out


def _chunk_to_doc() -> dict[str, str]:
    chunks = json.loads((STORAGE_DIR / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    return {cid: c.get("full_doc_id") for cid, c in chunks.items()}


async def run(modes: list[str], limit: int | None, gt_name: str = "ground_truth_multi.json",
              out_name: str = "multichunk_eval.json", params: dict | None = None, tag: str = "") -> dict:
    from src.rag.query import retrieve

    params = params or {}
    gt = json.loads((STORAGE_DIR / gt_name).read_text(encoding="utf-8"))
    if limit:
        gt = gt[:limit]
    c2d = _chunk_to_doc()
    per_mode: dict[str, list[dict]] = {}
    for mode in modes:
        rows = []
        for i, item in enumerate(gt, 1):
            t0 = time.perf_counter()
            try:
                data = await retrieve(item["question"], mode=mode, **params)
            except Exception as exc:  # noqa: BLE001  (one bad query must not kill an overnight run)
                print(f"  ! {mode} q{i}: {exc}", flush=True)
                data = {"chunks": []}
            latency = (time.perf_counter() - t0) * 1000
            row = score_multi(item["gold_chunk_ids"], item["gold_doc_ids"], data["chunks"], c2d)
            row.update(k=item["k"], question=item["question"], entity=item["entity"],
                       latency_ms=round(latency), retrieved_ids=[c.get("chunk_id") for c in data["chunks"]])
            rows.append(row)
            if i % 25 == 0:
                print(f"  {mode}: {i}/{len(gt)}", flush=True)
        per_mode[mode] = rows

    result: dict = {"tag": tag, "params": params, "gt": gt_name, "n_questions": len(gt),
                    "modes": {m: summarise(r) for m, r in per_mode.items()}, "paired": {}}
    names = list(per_mode)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            diffs = [x["recall@20"] - y["recall@20"] for x, y in zip(per_mode[a], per_mode[b])]
            pos, neg, p = sign_test(diffs)
            lo, hi = bootstrap_ci(diffs)
            result["paired"][f"{a}_vs_{b}"] = {
                "mean_recall@20_diff": round(sum(diffs) / len(diffs), 3), "ci95": [round(lo, 3), round(hi, 3)],
                f"{a}_better": pos, f"{b}_better": neg, "sign_test_p": round(p, 4)}
    result["by_k"] = {m: {str(k): summarise([r for r in rows if r["k"] == k]) for k in sorted({r["k"] for r in rows})}
                      for m, rows in per_mode.items()}
    result["caveats"] = [
        "Questions are LLM-generated from 2-4 chunks and verified so no single chunk suffices; gold may omit other valid chunks.",
        "Rank-based metrics assume the returned chunk order reflects system ranking.",
    ]
    result["per_question"] = per_mode
    (STORAGE_DIR / out_name).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["naive", "mix", "hybrid"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--gt", default="ground_truth_multi.json")
    ap.add_argument("--out", default="multichunk_eval.json")
    ap.add_argument("--params", default="{}", help='JSON of extra QueryParam fields, e.g. \'{"chunk_top_k": 40}\'')
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    res = asyncio.run(run(args.modes, args.limit, args.gt, args.out, json.loads(args.params), args.tag))
    print(json.dumps({k: res[k] for k in ("n_questions", "modes", "paired")}, indent=2))
