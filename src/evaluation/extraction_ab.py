"""
A/B test of graph-extraction models on identical chunks, using LightRAG's own
extraction prompts and parser (so it measures the real indexing step, without
touching the stored graph).

Run once per model (set LM_STUDIO_MODEL to the model loaded in LM Studio):

    LM_STUDIO_MODEL=qwen2.5-1.5b-instruct python -m src.evaluation.extraction_ab run --out storage/ab_small.json
    LM_STUDIO_MODEL=qwen3-vl-8b-instruct  python -m src.evaluation.extraction_ab run --out storage/ab_large.json
    python -m src.evaluation.extraction_ab compare storage/ab_large.json storage/ab_small.json

`compare` treats the first file as the *reference* (the larger model). That is a
relative measure, NOT ground truth: the 8B model is also imperfect. Reported:

  - speed: seconds per chunk (sequential, so it is a per-call latency; real
    indexing used 4 concurrent requests) and the resulting speed ratio
  - yield: entities / relations per chunk, parse failures (empty output)
  - quality proxies: junk-name rate, entities not found verbatim in the chunk
    (hallucination proxy), relations whose endpoints are not extracted entities
  - agreement with the reference: entity precision / recall / F1 on normalised
    names, and relation recall on (source, target) pairs
  - dumps side-by-side samples to eyeball (the only real quality check)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
SEED = 1234


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).lower().strip())


def _is_junk(name: str) -> bool:
    n = name.strip()
    return len(n) > 100 or len(n) <= 2 or bool(re.fullmatch(r"[\[\(\)\]\d\s\.\-,;:]+", n))


def sample_chunks(n: int) -> list[tuple[str, str]]:
    chunks = json.loads((STORAGE_DIR / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    ids = sorted(k for k, v in chunks.items() if len(v.get("content", "")) >= 400)
    random.Random(SEED).shuffle(ids)
    return [(i, chunks[i]["content"]) for i in ids[:n]]


async def run(n: int, out: Path) -> None:
    from lightrag.operate import _process_extraction_result
    from lightrag.prompt import PROMPTS
    from lightrag.constants import DEFAULT_ENTITY_TYPES
    from src.rag.llm_backend import LM_STUDIO_MODEL, llm_model_func
    from src.rag.extraction_prompt import apply_if_enabled

    lean = apply_if_enabled()

    delim, done = PROMPTS["DEFAULT_TUPLE_DELIMITER"], PROMPTS["DEFAULT_COMPLETION_DELIMITER"]
    base = dict(tuple_delimiter=delim, completion_delimiter=done,
                entity_types=",".join(DEFAULT_ENTITY_TYPES), language="English")
    examples = "\n".join(PROMPTS["entity_extraction_examples"]).format(
        **{**base, "entity_types": ", ".join(DEFAULT_ENTITY_TYPES)})
    base["examples"] = examples
    system = PROMPTS["entity_extraction_system_prompt"].format(**base)

    print(f"Model: {LM_STUDIO_MODEL}; {n} chunks (sequential); lean prompt: {lean}")
    rows = []
    for i, (cid, text) in enumerate(sample_chunks(n), 1):
        user = PROMPTS["entity_extraction_user_prompt"].format(**{**base, "input_text": text})
        t0 = time.perf_counter()
        try:
            raw = await llm_model_func(user, system_prompt=system)
            err = None
        except Exception as exc:  # noqa: BLE001
            raw, err = "", str(exc)
        secs = time.perf_counter() - t0
        nodes, edges = await _process_extraction_result(
            raw, cid, int(time.time()), "ab", tuple_delimiter=delim, completion_delimiter=done)
        ents = sorted({k for k in nodes})
        rels = sorted({(a, b) for (a, b) in edges})
        rows.append({"chunk_id": cid, "text": text, "seconds": round(secs, 2), "error": err,
                     "raw_chars": len(raw), "entities": ents, "relations": [list(r) for r in rels]})
        print(f"  {i}/{n}  {secs:.1f}s  {len(ents)} ent / {len(rels)} rel", flush=True)
    out.write_text(json.dumps({"model": LM_STUDIO_MODEL, "rows": rows}, indent=1), encoding="utf-8")
    print("saved", out)


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    ents = [e for r in rows for e in r["entities"]]
    rels = [tuple(x) for r in rows for x in r["relations"]]
    text = {r["chunk_id"]: _norm(r["text"]) for r in rows}
    not_in_text = sum(1 for r in rows for e in r["entities"] if _norm(e) not in text[r["chunk_id"]])
    dangling = sum(1 for r in rows for a, b in r["relations"]
                   if a not in set(r["entities"]) or b not in set(r["entities"]))
    return {
        "chunks": n,
        "sec_per_chunk": round(sum(r["seconds"] for r in rows) / n, 2),
        "entities_per_chunk": round(len(ents) / n, 2),
        "relations_per_chunk": round(len(rels) / n, 2),
        "empty_extractions": sum(1 for r in rows if not r["entities"] and not r["relations"]),
        "errors": sum(1 for r in rows if r["error"]),
        "junk_name_rate": round(sum(map(_is_junk, ents)) / max(1, len(ents)), 3),
        "entities_not_verbatim_in_chunk": round(not_in_text / max(1, len(ents)), 3),
        "relations_with_unextracted_endpoint": round(dangling / max(1, len(rels)), 3),
    }


def compare(ref_path: Path, cand_path: Path) -> None:
    ref, cand = json.loads(ref_path.read_text("utf-8")), json.loads(cand_path.read_text("utf-8"))
    rr = {r["chunk_id"]: r for r in ref["rows"]}
    cc = {r["chunk_id"]: r for r in cand["rows"]}
    ids = [i for i in rr if i in cc]
    rrows, crows = [rr[i] for i in ids], [cc[i] for i in ids]
    sr, sc = _stats(rrows), _stats(crows)

    tp = fp = fn = rtp = rfn = 0
    for i in ids:
        a, b = {_norm(e) for e in rr[i]["entities"]}, {_norm(e) for e in cc[i]["entities"]}
        tp += len(a & b); fn += len(a - b); fp += len(b - a)
        ra = {frozenset((_norm(x), _norm(y))) for x, y in rr[i]["relations"]}
        rb = {frozenset((_norm(x), _norm(y))) for x, y in cc[i]["relations"]}
        rtp += len(ra & rb); rfn += len(ra - rb)
    p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
    summary = {
        "reference": ref["model"], "candidate": cand["model"], "n_chunks": len(ids),
        "reference_stats": sr, "candidate_stats": sc,
        "speed_ratio_candidate_vs_reference": round(sr["sec_per_chunk"] / max(1e-9, sc["sec_per_chunk"]), 2),
        "agreement_with_reference": {
            "entity_precision": round(p, 3), "entity_recall": round(r, 3),
            "entity_f1": round(2 * p * r / max(1e-9, p + r), 3),
            "relation_recall": round(rtp / max(1, rtp + rfn), 3)},
        "note": "Reference is the larger model, not ground truth; agreement is a relative measure.",
    }
    (STORAGE_DIR / "extraction_ab_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    print("\n=== Side-by-side samples (eyeball these) ===")
    for i in ids[:6]:
        print(f"\n--- {i} ---\n{rr[i]['text'][:350].strip()!r}")
        print(f"  {ref['model']}: {rr[i]['entities'][:12]}")
        print(f"  {cand['model']}: {cc[i]['entities'][:12]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--n", type=int, default=40); r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare"); c.add_argument("ref", type=Path); c.add_argument("cand", type=Path)
    a = ap.parse_args()
    if a.cmd == "run":
        asyncio.run(run(a.n, a.out))
    else:
        compare(a.ref, a.cand)
