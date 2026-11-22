"""
Multi-chunk, cross-judgment question generator.

Single-chunk questions (see generator.py) are a bad test for a graph: the
question is a paraphrase of one chunk, so plain vector search trivially finds it.
Here every question *needs 2-3 chunks from different judgments*.

Procedure
  1. Pick a specific entity that appears in 2-4 distinct judgments (specific enough
     that the gold chunks cover most of its footprint; not a hub like "Supreme
     Court of India"; not junk like "(3)").
  2. From each judgment take the entity's best chunk (most mentions of it).
  3. Ask the generator model for a question that requires ALL excerpts.
  4. Verify: for each excerpt alone, ask the model whether it can fully answer the
     question. Keep the question only if NO single excerpt suffices.

Gold = the set of chunk ids (no gold answer: retrieval eval does not need one, and
generating it roughly triples the time per question). Output: storage/ground_truth_multi.json

Run with a capable model loaded (e.g. the 8B):
    LM_STUDIO_MODEL=qwen3-vl-8b-instruct python -m src.evaluation.multichunk_generator
Env: EVAL_MULTI_N (default 250), EVAL_SEED, EVAL_CONCURRENCY (default 1; prompts are
~2k tokens, so keep LM Studio's per-slot context large enough).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()
STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
client = AsyncOpenAI(base_url=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"), api_key="lm-studio")
MODEL = os.getenv("LM_STUDIO_MODEL", "default")
SEED = int(os.getenv("EVAL_SEED", "1234"))
N_TARGET = int(os.getenv("EVAL_MULTI_N", "250"))
CONCURRENCY = int(os.getenv("EVAL_CONCURRENCY", "1"))
MIN_DOCS, MAX_DOCS = 2, 4
MAX_EXCERPT_CHARS = 1800

GENERIC = {"supreme court of india", "high court", "appellant", "respondent", "state", "court", "judgment",
           "order", "union of india", "petitioner", "section", "act", "data", "location", "date", "event",
           "person", "organization", "concept", "india", "government"}


def _is_junk(name: str) -> bool:
    n = name.strip()
    return (len(n) < 4 or len(n) > 80 or n.lower() in GENERIC
            or bool(re.fullmatch(r"[\[\(\)\]\d\s\.\-,;:]+", n)))


LEGAL_ANCHOR = re.compile(
    r"\b(Act|Code|Article|Section|Rule|Rules|Constitution|Schedule|Regulations?|Doctrine|Order [IVXLC]+|"
    r"Convention|Ordinance|Amendment|Clause|Proviso)\b|\bs\.\s?\d+|\d{3,4}\)?$", re.I)
ENTITY_FILTER = os.getenv("EVAL_ENTITY_FILTER", "legal")  # "legal" = statutes/sections/articles only; "any"
OUT_NAME = os.getenv("EVAL_MULTI_OUT", "ground_truth_multi.json")


def _chat_json(text: str) -> dict:
    if "```" in text:
        text = text.split("```json")[-1].split("```")[1] if "```json" in text else text.split("```")[1]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


async def _ask(prompt: str, max_tokens: int) -> str:
    r = await client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0, max_tokens=max_tokens)
    return r.choices[0].message.content or ""


GEN_PROMPT = """You are helping build a legal-research benchmark. Below are {k} excerpts from {k} DIFFERENT Supreme Court of India judgments. All of them involve "{entity}".

{excerpts}

TASK: Write ONE standalone question a legal researcher might ask about this provision or concept that can only be answered by COMBINING information from EVERY excerpt (for example comparing how the Court treated the matter in different cases, or tracing a rule across them). It must NOT be answerable from any single excerpt alone. Do not mention "excerpt", "text" or "passage".

Respond as JSON with a single key: {{"question": "..."}}"""

CHECK_PROMPT = """QUESTION: {question}

EXCERPT:
{excerpt}

Can the question be FULLY and correctly answered using only this excerpt? Reply with exactly one word: YES or NO."""


ANCHOR_SOURCE = os.getenv("EVAL_ANCHOR_SOURCE", "graph")  # "graph" = entity->chunk map; "regex" = plain text search

SECTION_RE = re.compile(
    r"Sections?\s+(\d+[A-Z]?(?:\(\d+\))?)\s+of\s+the\s+((?:[A-Z][A-Za-z&.]*\s+){1,6}Act)(?:,?\s*(\d{4}))?")
ARTICLE_RE = re.compile(r"Article\s+(\d+[A-Z]?)\s+of\s+the\s+(Constitution)")


def build_jobs_regex() -> list[dict]:
    """Graph-independent anchors: 'Section N of the X Act' / 'Article N of the Constitution'
    found by plain regex over the chunk text, grouped across judgments. Nothing here
    uses the knowledge graph, so graph retrieval gets no built-in advantage."""
    chunks = json.loads((STORAGE_DIR / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    groups: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    label: dict[str, str] = {}
    for cid, c in chunks.items():
        text = re.sub(r"\s+", " ", c.get("content", ""))
        if len(text) < 300:
            continue
        doc = c.get("full_doc_id", cid)
        for m in SECTION_RE.finditer(text):
            key = f"section {m.group(1)} of the {m.group(2).lower()}"
            label[key] = f"Section {m.group(1)} of the {m.group(2)}"
            groups[key][doc][cid] = groups[key][doc].get(cid, 0) + 1
        for m in ARTICLE_RE.finditer(text):
            key = f"article {m.group(1)} of the constitution"
            label[key] = f"Article {m.group(1)} of the Constitution"
            groups[key][doc][cid] = groups[key][doc].get(cid, 0) + 1
    rng = random.Random(SEED)
    keys = sorted(k for k, by_doc in groups.items() if MIN_DOCS <= len(by_doc) <= MAX_DOCS)
    rng.shuffle(keys)
    jobs, used_chunks = [], set()
    for key in keys:
        gold = [(doc, max(cids, key=cids.get)) for doc, cids in sorted(groups[key].items())]
        if any(cid in used_chunks for _, cid in gold):
            continue
        used_chunks.update(cid for _, cid in gold)
        jobs.append({"entity": label[key], "doc_ids": [d for d, _ in gold], "chunk_ids": [c for _, c in gold],
                     "texts": [chunks[c]["content"][:MAX_EXCERPT_CHARS] for _, c in gold]})
        if len(jobs) >= N_TARGET * 2:
            break
    print(f"{len(keys)} regex anchors in {MIN_DOCS}-{MAX_DOCS} judgments; {len(jobs)} candidate sets (target {N_TARGET})")
    return jobs


def build_jobs() -> list[dict]:
    if ANCHOR_SOURCE == "regex":
        return build_jobs_regex()
    mapping = json.loads((STORAGE_DIR / "kv_store_entity_chunks.json").read_text(encoding="utf-8"))
    chunks = json.loads((STORAGE_DIR / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    names = sorted(mapping)
    rng.shuffle(names)
    jobs, used_chunks = [], set()
    for ent in names:
        if _is_junk(ent):
            continue
        if ENTITY_FILTER == "legal" and not LEGAL_ANCHOR.search(ent):
            continue
        by_doc: dict[str, list[str]] = defaultdict(list)
        for cid in mapping[ent].get("chunk_ids", []):
            c = chunks.get(cid)
            if c and len(c.get("content", "")) >= 300 and ent.lower() in c["content"].lower():
                by_doc[c.get("full_doc_id", cid)].append(cid)
        if not (MIN_DOCS <= len(by_doc) <= MAX_DOCS):
            continue
        gold = []
        for doc, cids in sorted(by_doc.items()):
            best = max(cids, key=lambda i: chunks[i]["content"].lower().count(ent.lower()))
            gold.append((doc, best))
        if any(cid in used_chunks for _, cid in gold):
            continue  # keep questions independent: no chunk reused
        used_chunks.update(cid for _, cid in gold)
        jobs.append({"entity": ent, "doc_ids": [d for d, _ in gold], "chunk_ids": [c for _, c in gold],
                     "texts": [chunks[c]["content"][:MAX_EXCERPT_CHARS] for _, c in gold]})
        if len(jobs) >= N_TARGET * 2:  # headroom for generation / verification rejects
            break
    print(f"{len(jobs)} candidate entity/chunk sets (target {N_TARGET})")
    return jobs


async def make_question(job: dict) -> dict | None:
    k = len(job["texts"])
    excerpts = "\n\n".join(f"[Excerpt {i + 1}]\n{t}" for i, t in enumerate(job["texts"]))
    try:
        qa = _chat_json(await _ask(GEN_PROMPT.format(k=k, entity=job["entity"], excerpts=excerpts), 150))
        question = qa["question"].strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  gen failed for {job['entity']!r}: {exc}")
        return None
    # Verification: reject if any single excerpt can answer it alone.
    for t in job["texts"]:
        verdict = (await _ask(CHECK_PROMPT.format(question=question, excerpt=t), 5)).strip().upper()
        if verdict.startswith("YES"):
            return None
    return {"entity": job["entity"], "question": question, "gold_chunk_ids": job["chunk_ids"], "gold_doc_ids": job["doc_ids"], "k": k}


async def main() -> None:
    jobs = build_jobs()
    print(f"generator/verifier model: {MODEL}")
    sem = asyncio.Semaphore(CONCURRENCY)
    out: list[dict] = []
    rejected = 0
    done_jobs = [0]

    async def work(j):
        nonlocal rejected
        if len(out) >= N_TARGET:
            return
        async with sem:
            if len(out) >= N_TARGET:  # re-check: target may have been reached while queued
                return
            r = await make_question(j)
        done_jobs[0] += 1
        if done_jobs[0] % 5 == 0:
            print(f"  jobs {done_jobs[0]}: {len(out)} accepted, {rejected} rejected", flush=True)
        if r is None:
            rejected += 1
        elif len(out) < N_TARGET:
            out.append(r)
            if len(out) % 10 == 0:
                print(f"  {len(out)} accepted, {rejected} rejected", flush=True)
                (STORAGE_DIR / OUT_NAME).write_text(json.dumps(out, indent=2), encoding="utf-8")

    await asyncio.gather(*(work(j) for j in jobs))
    (STORAGE_DIR / OUT_NAME).write_text(json.dumps(out, indent=2), encoding="utf-8")
    ks = [o["k"] for o in out]
    print(f"\nDone: {len(out)} multi-chunk questions ({ks.count(2)} with 2 chunks, {ks.count(3)} with 3, "
          f"{ks.count(4)} with 4); {rejected} rejected (single excerpt sufficed or generation failed)")


if __name__ == "__main__":
    asyncio.run(main())
