import asyncio
from typing import List, Dict
from sentence_transformers import CrossEncoder
import torch

# Configuration
RERANK_MODEL = "BAAI/bge-reranker-base"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Singleton instance
_model = None

def get_reranker():
    global _model
    if _model is None:
        print(f"Loading Reranker Model: {RERANK_MODEL} on {DEVICE}...")
        _model = CrossEncoder(RERANK_MODEL, device=DEVICE)
    return _model

async def rerank_handler(query: str, documents: List[str], top_n: int = 5) -> List[Dict]:
    """
    Reranks a list of document strings based on their relevance to the query.
    
    Signature matches LightRAG's internal expectations:
    async def rerank_func(query: str, documents: list[str], top_n: int) -> list[dict]
    
    Returns:
    List[Dict]: [{"index": int, "relevance_score": float}, ...]
    """
    if not documents:
        return []

    model = get_reranker()
    
    # Prepare pairs for CrossEncoder: (query, doc_text)
    pairs = [[query, doc] for doc in documents]

    # Perform reranking (synchronous call wrapped in run_in_executor)
    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(None, lambda: model.predict(pairs))

    # Create the index-based result format required by LightRAG
    results = []
    for i, score in enumerate(scores):
        results.append({
            "index": i,
            "relevance_score": float(score)
        })

    # Sort by score descending and take top_n
    sorted_results = sorted(results, key=lambda x: x["relevance_score"], reverse=True)
    return sorted_results[:top_n]
