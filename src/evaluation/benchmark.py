"""
End-to-end benchmark: answers + retrieval metrics + ROUGE/BLEU + LLM judge.

Two phases so the judge can be a *different, stronger* model than the one that
answers (a 1.5B model grading its own answers is close to meaningless):

  1. answer  (default model: LM_STUDIO_MODEL, i.e. the system under test)
       python -m src.evaluation.benchmark --phase answer --modes naive hybrid --n 100
  2. judge   (load a stronger model in LM Studio, then set JUDGE_MODEL)
       JUDGE_MODEL=qwen3-vl-8b-instruct python -m src.evaluation.benchmark --phase judge

State is saved incrementally to storage/benchmark_answers.json and the run is
resumable. The final file storage/benchmark_results.json is rebuilt after each
phase. Retrieval metrics come from src.evaluation.retrieval_eval.score_retrieval
(measured against the gold chunk, nothing derived from judge scores).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
ANSWERS_PATH = STORAGE_DIR / "benchmark_answers.json"
RESULTS_PATH = STORAGE_DIR / "benchmark_results.json"
SAVE_EVERY = 5


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    tmp.replace(path)


def _key(row: dict) -> tuple[str, str]:
    return (row["mode"], row["question"])


async def answer_phase(modes: list[str], n: int) -> list[dict]:
    from src.evaluation.metrics import calculate_text_metrics
    from src.evaluation.retrieval_eval import score_retrieval
    from src.rag.query import query as rag_query

    gt = [g for g in json.loads((STORAGE_DIR / "ground_truth.json").read_text(encoding="utf-8"))
          if g.get("reference_chunk_id")][:n]
    rows = _load(ANSWERS_PATH)
    done = {_key(r) for r in rows}
    print(f"Answer phase: {len(gt)} questions x {modes}; {len(done)} already done")

    new = 0
    for mode in modes:
        for item in gt:
            if (mode, item["question"]) in done:
                continue
            t0 = time.perf_counter()
            try:
                resp = await rag_query(item["question"], mode=mode)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {mode}: {exc}")
                continue
            latency = (time.perf_counter() - t0) * 1000
            answer = resp.get("answer", "") or ""
            rows.append({
                "question": item["question"],
                "mode": mode,
                "gold_answer": item["ground_truth"],
                "answer": answer,
                "latency_ms": round(latency, 1),
                "text_metrics": calculate_text_metrics(answer, item["ground_truth"]),
                "graph_metrics": score_retrieval(
                    item["reference_chunk_id"], item["entity"],
                    resp.get("chunks", []), resp.get("entities", [])),
                "target_entity": item["entity"],
                "judge_metrics": None,
            })
            new += 1
            if new % SAVE_EVERY == 0:
                _save(ANSWERS_PATH, rows)
                print(f"  {len(rows)} answers saved")
    _save(ANSWERS_PATH, rows)
    return rows


async def judge_phase() -> list[dict]:
    from src.evaluation.metrics import JUDGE_MODEL, llm_judge

    rows = _load(ANSWERS_PATH)
    todo = [r for r in rows if not r.get("judge_metrics") or r["judge_metrics"].get("accuracy") is None]
    print(f"Judge phase (judge model: {JUDGE_MODEL}): {len(todo)} of {len(rows)} to judge")
    for i, r in enumerate(todo, 1):
        r["judge_metrics"] = await llm_judge(r["question"], r["answer"], r["gold_answer"])
        r["judge_model"] = JUDGE_MODEL
        if i % SAVE_EVERY == 0:
            _save(ANSWERS_PATH, rows)
            print(f"  judged {i}/{len(todo)}")
    _save(ANSWERS_PATH, rows)
    return rows


def finalize(rows: list[dict]) -> None:
    results = [dict(r, judge_metrics=r["judge_metrics"] or {}) for r in rows]
    _save(RESULTS_PATH, results)
    print(f"Wrote {len(results)} rows to {RESULTS_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["answer", "judge", "all"], default="all")
    ap.add_argument("--modes", nargs="+", default=["naive", "hybrid"])
    ap.add_argument("--n", type=int, default=int(os.getenv("EVAL_BENCH_N", "100")))
    args = ap.parse_args()

    rows: list[dict] = []
    if args.phase in ("answer", "all"):
        rows = asyncio.run(answer_phase(args.modes, args.n))
    if args.phase in ("judge", "all"):
        rows = asyncio.run(judge_phase())
    finalize(rows or _load(ANSWERS_PATH))
