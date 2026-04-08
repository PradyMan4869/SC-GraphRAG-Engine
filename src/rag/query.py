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
  hybrid  — local + global graph context combined  (recommended default)
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

from src.rag.indexer import get_rag

VALID_MODES = {"naive", "local", "global", "hybrid"}


async def query(question: str, mode: str = "hybrid") -> dict:
    """Query the knowledge graph and return a structured result with context.

    Returns:
        {"answer": str, "mode": str, "question": str, "entities": list, "chunks": list}
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid mode '{mode}'. Choose from: {', '.join(sorted(VALID_MODES))}"
        )

    rag = await get_rag()
    # aquery_llm returns raw_data dict containing 'entities', 'relationships', 'chunks', 'llm_response'
    result = await rag.aquery_llm(question, param=QueryParam(mode=mode))

    return {
        "answer": result.get("llm_response", {}).get("content", ""),
        "mode": mode,
        "question": question,
        "entities": result.get("entities", []),
        "chunks": result.get("chunks", [])
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
