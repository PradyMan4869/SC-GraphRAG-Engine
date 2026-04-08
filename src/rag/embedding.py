"""
Async embedding wrapper for LightRAG using LM Studio's nomic-embed-text-v1.5 API.

LM Studio exposes an OpenAI-compatible /v1/embeddings endpoint.
Load "nomic-embed-text-v1.5" in LM Studio alongside the LLM.

nomic-embed-text-v1.5 requires task-specific prefixes:
  - Indexing/documents: "search_document: <text>"
  - Querying:           "search_query: <text>"
"""

from __future__ import annotations

import os

import numpy as np
from openai import AsyncOpenAI

EMBEDDING_DIM = 768
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_EMBED_MODEL = os.getenv(
    "LM_STUDIO_EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5"
)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")
    return _client


async def _encode(texts: list[str]) -> np.ndarray:
    """Call LM Studio's /v1/embeddings endpoint; returns (n, 768) float32 array."""
    client = _get_client()
    response = await client.embeddings.create(
        model=LM_STUDIO_EMBED_MODEL,
        input=texts,
    )
    results = sorted(response.data, key=lambda d: d.index)
    return np.array([d.embedding for d in results], dtype=np.float32)


async def embedding_func(texts: list[str]) -> np.ndarray:
    """LightRAG-compatible async embedding function (document prefix)."""
    if not texts:
        return np.array([], dtype=np.float32)
    prefixed = [f"search_document: {t}" for t in texts]
    return await _encode(prefixed)


async def embed_for_query(texts: list[str]) -> np.ndarray:
    """Async embedding for user queries (query prefix)."""
    if not texts:
        return np.array([], dtype=np.float32)
    prefixed = [f"search_query: {t}" for t in texts]
    return await _encode(prefixed)
