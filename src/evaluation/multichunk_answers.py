"""
Answer phase for multi-chunk questions: run the *system under test* (the model in
LM_STUDIO_MODEL, e.g. the 1.5B) in several retrieval modes and save answer +
retrieved ids. Judging happens in a separate phase (multichunk_judge.py) with a
stronger model. Resumable: rows already present are skipped; saved every 5 rows.

    python -m src.evaluation.multichunk_answers --modes naive mix hybrid --n-regex 70 --n-legal 30
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
OUT_PATH = STORAGE_DIR / "multichunk_answers.json"
SETS = {"regex": "ground_truth_multi_regex.json", "legal": "ground_truth_multi.json"}


def _load_rows() -> list[dict]:
    return json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else []


def _save_rows(rows: list[dict]) -> None:
    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    tmp.replace(OUT_PATH)


async def run(modes: list[str], n_regex: int, n_legal: int) -> None:
    from src.rag.query import query

    items = []
    for set_name, n in (("regex", n_regex), ("legal", n_legal)):
        path = STORAGE_DIR / SETS[set_name]
        if path.exists() and n > 0:
            for it in json.loads(path.read_text(encoding="utf-8"))[:n]:
                items.append({**it, "set": set_name})
    rows = _load_rows()
    done = {(r["mode"], r["question"]) for r in rows}
    todo = [(m, it) for it in items for m in modes if (m, it["question"]) not in done]
    print(f"Answer phase: {len(items)} questions x {modes}; {len(done)} done, {len(todo)} to do", flush=True)

    for i, (mode, it) in enumerate(todo, 1):
        t0 = time.perf_counter()
        try:
            resp = await query(it["question"], mode=mode)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {mode}: {exc}", flush=True)
            continue
        rows.append({
            "set": it["set"], "mode": mode, "question": it["question"], "entity": it["entity"], "k": it["k"],
            "gold_chunk_ids": it["gold_chunk_ids"], "gold_doc_ids": it["gold_doc_ids"],
            "answer": resp.get("answer", "") or "",
            "retrieved_ids": [c.get("chunk_id") for c in resp.get("chunks", [])],
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "judge": None,
        })
        if i % 5 == 0:
            _save_rows(rows)
            print(f"  {i}/{len(todo)} answered", flush=True)
    _save_rows(rows)
    print("saved", OUT_PATH, len(rows), "rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["naive", "mix", "hybrid"])
    ap.add_argument("--n-regex", type=int, default=70)
    ap.add_argument("--n-legal", type=int, default=30)
    a = ap.parse_args()
    asyncio.run(run(a.modes, a.n_regex, a.n_legal))
