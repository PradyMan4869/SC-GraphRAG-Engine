"""
Cross-encoder reranker for LightRAG (BAAI/bge-reranker-base).

Notes on resources: the reranker shares the GPU with LM Studio. It is loaded
lazily once, in fp16 on CUDA (~0.6 GB instead of ~1.1 GB), and inference runs
in a worker thread so it never blocks the event loop. Set RERANK_DEVICE=cpu to
keep it off the GPU entirely.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Dict, List

log = logging.getLogger(__name__)

RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-base")
RERANK_MAX_LENGTH = 512  # bge-reranker-base's trained limit; longer pairs are truncated
RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "16"))

_model = None
_model_lock = threading.Lock()


def _resolve_device() -> str:
    import torch  # imported lazily: keeps `import src.rag.reranker` cheap

    requested = os.getenv("RERANK_DEVICE")
    if requested:
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_reranker():
    """Load the model once (thread-safe)."""
    global _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import CrossEncoder
            import torch

            device = _resolve_device()
            log.info("Loading reranker %s on %s", RERANK_MODEL, device)
            kwargs = {"torch_dtype": torch.float16} if device.startswith("cuda") else {}
            _model = CrossEncoder(
                RERANK_MODEL, device=device, max_length=RERANK_MAX_LENGTH, model_kwargs=kwargs
            )
    return _model


def _score(query: str, documents: List[str]) -> List[float]:
    model = get_reranker()  # first call loads the model here, off the event loop
    pairs = [(query, doc) for doc in documents]
    return [float(x) for x in model.predict(pairs, batch_size=RERANK_BATCH_SIZE, show_progress_bar=False)]


async def rerank_handler(query: str, documents: List[str], top_n: int = 5, **_: object) -> List[Dict]:
    """LightRAG rerank hook: returns [{"index": int, "relevance_score": float}, ...] best-first."""
    if not documents:
        return []
    scores = await asyncio.get_running_loop().run_in_executor(None, _score, query, documents)
    ranked = sorted(
        ({"index": i, "relevance_score": sc} for i, sc in enumerate(scores)),
        key=lambda r: r["relevance_score"],
        reverse=True,
    )
    return ranked[:top_n]
