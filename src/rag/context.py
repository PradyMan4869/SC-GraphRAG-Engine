"""
Per-call flags carried via contextvars.

LightRAG calls the same `embedding_func` for documents and for queries, and the
same `llm_model_func` for entity extraction and for answer generation. Those
need different behaviour (nomic prefixes; output-length budget), and LightRAG
gives us no hook to tell them apart. A ContextVar set around a query is
inherited by every asyncio task LightRAG spawns inside that call, and is
isolated between concurrent queries.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

# True while embedding a user query (use nomic's "search_query:" prefix).
QUERY_EMBEDDING: ContextVar[bool] = ContextVar("QUERY_EMBEDDING", default=False)
# True while generating a user-facing answer (use the larger token budget).
ANSWER_GENERATION: ContextVar[bool] = ContextVar("ANSWER_GENERATION", default=False)


@contextmanager
def query_context(answer: bool = True):
    t1 = QUERY_EMBEDDING.set(True)
    t2 = ANSWER_GENERATION.set(answer)
    try:
        yield
    finally:
        ANSWER_GENERATION.reset(t2)
        QUERY_EMBEDDING.reset(t1)
