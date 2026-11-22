"""
Public query interface for the Supreme Court GraphRAG system.

Usage (programmatic):
    from src.rag.query import query
    result = await query("What is Article 21?", mode="hybrid")
    # result == {"answer": "...", "mode": "hybrid", "question": "..."}

Usage (CLI):
    python src/rag/query.py "What is Article 21?"
    python src/rag/query.py "What is Article 21?" --mode local

Valid modes (LightRAG 1.4.x):
  naive   — dense vector search over raw chunks, no graph traversal
  local   — entity-centric graph context (local neighbourhood)
  global  — relation-centric graph context (global paths)
  hybrid  — local + global graph context combined (graph only: NO chunk-level vector search)
  mix     — graph context + chunk vector search (LightRAG default for KG+vector)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure the project root is in sys.path so 'src' can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lightrag import QueryParam

from src.rag.context import query_context
from src.rag.indexer import get_rag

VALID_MODES = {"naive", "local", "global", "hybrid", "mix"}


def _check_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Choose from: {', '.join(sorted(VALID_MODES))}"
        )


async def query(question: str, mode: str = "hybrid") -> dict:
    """Query the knowledge graph and return the answer plus the retrieved context.

    Returns:
        {"answer": str, "mode": str, "question": str, "entities": list, "chunks": list}
    """
    _check_mode(mode)
    rag = await get_rag()
    # The answer prompt can reach ~25k tokens (20 chunks + entities + relations). Cap it
    # to fit the model's context window via QUERY_MAX_TOTAL_TOKENS (LightRAG default: 30000).
    extra = {}
    if os.getenv("QUERY_MAX_TOTAL_TOKENS"):
        extra["max_total_tokens"] = int(os.getenv("QUERY_MAX_TOTAL_TOKENS"))
    with query_context(answer=True):
        result = await rag.aquery_llm(question, param=QueryParam(mode=mode, **extra))

    # LightRAG nests retrieval output under "data"; "llm_response" is top-level.
    data = result.get("data") or {}
    answer = (result.get("llm_response") or {}).get("content") or ""
    if not answer.strip():
        # LightRAG swallows LLM errors (e.g. prompt larger than the model's context) and
        # returns an empty answer; surface that instead of reporting it as a result.
        raise RuntimeError(f"Empty answer from LLM (status={result.get('status')}); the prompt may exceed "
                           "the model's context window - increase it in LM Studio or lower QUERY_MAX_TOTAL_TOKENS.")
    return {
        "answer": answer,
        "mode": mode,
        "question": question,
        "entities": data.get("entities", []),
        "chunks": data.get("chunks", []),
    }


async def retrieve(question: str, mode: str = "hybrid", **params) -> dict:
    """Retrieval only (no answer generation). Used by the evaluation harness.

    `params` are extra QueryParam fields (e.g. top_k, chunk_top_k, enable_rerank) for tuning sweeps.
    Returns {"entities": [...], "chunks": [...], "relationships": [...]}.
    """
    _check_mode(mode)
    rag = await get_rag()
    with query_context(answer=False):
        result = await rag.aquery_data(question, param=QueryParam(mode=mode, **params))
    data = result.get("data") or {}
    return {
        "entities": data.get("entities", []),
        "relationships": data.get("relationships", []),
        "chunks": data.get("chunks", []),
    }


# ---------------------------------------------------------------------------
# Simple CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Query the Supreme Court GraphRAG system."
    )
    parser.add_argument("question", help="Question to ask")
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=sorted(VALID_MODES),
        help="Retrieval mode (default: hybrid)",
    )
    args = parser.parse_args()

    result = asyncio.run(query(args.question, mode=args.mode))
    print(result["answer"])
