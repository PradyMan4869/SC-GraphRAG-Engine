"""
Judge phase for multi-chunk answers (run with a stronger model than the one that
answered; set JUDGE_MODEL). For every saved answer:

  evidence_coverage   fraction of the gold excerpts whose key information relevant
                      to the question appears in the answer (one YES/NO call per
                      excerpt). Robust: it asks only about gold evidence.
  accuracy (1-5)      is the answer consistent with the gold excerpts (no contradictions)?
  completeness (1-5)  does it cover what the question asks, drawing on ALL excerpts?
  answered            False if the answer is empty or a refusal ("not enough information")

Caveat: accuracy/completeness are measured against the gold excerpts only, so correct
extra information from other retrieved chunks can be penalised; coverage is the
cleaner signal. A failed judge call is recorded as missing (None), never as zero.
Resumable; saved every 5 answers.

    JUDGE_MODEL=qwen3-vl-8b-instruct python -m src.evaluation.multichunk_judge
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()
STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
ANSWERS_PATH = STORAGE_DIR / "multichunk_answers.json"
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("LM_STUDIO_MODEL", "default")
client = AsyncOpenAI(base_url=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"), api_key="lm-studio")
MAX_ANSWER_CHARS, MAX_EXCERPT_CHARS = 1800, 1800

COVERAGE_PROMPT = """QUESTION: {question}

ANSWER TO EVALUATE:
{answer}

SOURCE EXCERPT:
{excerpt}

Does the ANSWER contain the key information from the SOURCE EXCERPT that is relevant to the QUESTION (even if paraphrased)? Reply with exactly one word: YES or NO."""

QUALITY_PROMPT = """QUESTION: {question}

SOURCE EXCERPTS (ground truth):
{excerpts}

ANSWER TO EVALUATE:
{answer}

Rate the ANSWER against the SOURCE EXCERPTS on two 1-5 scales:
accuracy: 5 = fully consistent with the excerpts, 1 = contradicts them or invents facts.
completeness: 5 = fully addresses the question using information from ALL excerpts, 1 = misses almost everything.
Reply in exactly this format and nothing else:
accuracy: N
completeness: N"""

REFUSAL = re.compile(r"(not (enough|sufficient)|insufficient|cannot (be )?(answer|determin)|no (relevant )?information|unable to)", re.I)


def parse_scores(text: str) -> tuple[int | None, int | None]:
    a = re.search(r"accuracy\D{0,5}([1-5])", text, re.I)
    c = re.search(r"completeness\D{0,5}([1-5])", text, re.I)
    return (int(a.group(1)) if a else None, int(c.group(1)) if c else None)


def parse_yes_no(text: str) -> bool | None:
    t = text.strip().upper()
    if t.startswith("YES"):
        return True
    if t.startswith("NO"):
        return False
    return None


async def _ask(prompt: str, max_tokens: int) -> str:
    r = await client.chat.completions.create(
        model=JUDGE_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0, max_tokens=max_tokens)
    return r.choices[0].message.content or ""


async def judge_row(row: dict, chunks: dict[str, str]) -> dict:
    answer = (row["answer"] or "").strip()
    excerpts = [chunks.get(c, "")[:MAX_EXCERPT_CHARS] for c in row["gold_chunk_ids"]]
    answered = bool(answer) and not (len(answer) < 400 and REFUSAL.search(answer))
    if not answer:
        return {"answered": False, "coverage": 0.0, "coverage_flags": [False] * len(excerpts),
                "accuracy": 1, "completeness": 1, "answer_chars": 0}
    ans = answer[:MAX_ANSWER_CHARS]
    flags: list[bool | None] = []
    for ex in excerpts:
        try:
            flags.append(parse_yes_no(await _ask(COVERAGE_PROMPT.format(question=row["question"], answer=ans, excerpt=ex), 4)))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! coverage call failed: {exc}", flush=True)
            flags.append(None)
    valid = [f for f in flags if f is not None]
    acc = comp = None
    try:
        joined = "\n\n".join(f"[Excerpt {i + 1}]\n{e}" for i, e in enumerate(excerpts))
        acc, comp = parse_scores(await _ask(QUALITY_PROMPT.format(question=row["question"], excerpts=joined, answer=ans), 20))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! quality call failed: {exc}", flush=True)
    return {"answered": answered, "coverage": (sum(valid) / len(valid)) if valid else None,
            "coverage_flags": flags, "accuracy": acc, "completeness": comp, "answer_chars": len(answer)}


def _save(rows: list[dict]) -> None:
    tmp = ANSWERS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    tmp.replace(ANSWERS_PATH)


async def main() -> None:
    rows = json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
    chunks_raw = json.loads((STORAGE_DIR / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
    chunks = {cid: c.get("content", "") for cid, c in chunks_raw.items()}
    del chunks_raw
    todo = [r for r in rows if not r.get("judge")]
    print(f"Judge phase (judge model: {JUDGE_MODEL}): {len(todo)} of {len(rows)} to judge", flush=True)
    for i, r in enumerate(todo, 1):
        r["judge"] = await judge_row(r, chunks)
        r["judge_model"] = JUDGE_MODEL
        if i % 5 == 0:
            _save(rows)
            print(f"  judged {i}/{len(todo)}", flush=True)
    _save(rows)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
