---
name: GraphRAG Supreme Court — project overview and stack
description: Core stack, architectural decisions, and phase status for the Indian Supreme Court GraphRAG project
type: project
---

GraphRAG system for indexing and querying Indian Supreme Court judgments.

**Stack:**
- LLM backend: LM Studio OpenAI-compatible server at http://localhost:1234/v1, model qwen3-vl-8b-instruct-q4_k_m
- Embedding: nomic-ai/nomic-embed-text-v1.5 via sentence-transformers on CUDA, dim=768
- Graph/vector store: LightRAG 1.4.13 (lightrag-hku) with default NanoVectorDB + NetworkX
- Storage dir: controlled by STORAGE_DIR env var (default storage/)

**LightRAG 1.4.13 API facts (verified from source):**
- LightRAG is a @dataclass — all config is flat constructor kwargs, no nested config objects
- embedding_func field accepts EmbeddingFunc(embedding_dim, func, max_token_size)
- chunk_token_size and chunk_overlap_token_size are direct fields
- Must call `await rag.initialize_storages()` before first insert or query
- Insert: `await rag.ainsert(input: str | list[str], ids=..., file_paths=...)` returns track_id str
- Query: `await rag.aquery(query, param=QueryParam(mode=...))` returns str
- QueryParam modes: naive, local, global, hybrid, mix, bypass

**nomic-embed-text-v1.5 prefix requirement:**
- Documents (indexing): prefix "search_document: "
- Queries: prefix "search_query: "
- embedding_func (default, used by LightRAG) uses document prefix
- embed_for_query() uses query prefix for runtime question embedding

**Phase status:**
- Phase 3 complete: src/rag/embedding.py, src/rag/indexer.py, src/rag/query.py
- Phase 6 complete: ui/app.py — single-file Streamlit UI with Ask tab, Graph Explorer tab, sidebar stats
- src/rag/llm_backend.py was pre-existing (do not modify)

**Why:** Legal document Q&A system requiring entity/relation extraction from court judgments to answer constitutional and case-law questions.

**How to apply:** Any additions to the RAG pipeline should follow the singleton pattern established in indexer.py (get_rag()) and respect the task-prefix convention for embeddings.
