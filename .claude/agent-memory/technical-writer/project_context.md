---
name: Project Context — GraphRAG Supreme Court
description: Core facts about the project scope, architecture, data, and technology choices
type: project
---

Fully local GraphRAG pipeline over ~35,000 Indian Supreme Court judgments (1950–2025). Public GitHub portfolio/resume project.

**Why:** Demonstrates graph-augmented retrieval for legal research; shows multi-hop reasoning across documents that plain vector search cannot do.

**Key technology decisions:**
- LightRAG (`lightrag-hku`) 1.4.x as the RAG orchestration layer — handles chunking, entity extraction, vector + graph storage internally
- LM Studio (OpenAI-compatible local server) hosts Qwen3-VL-8B-Instruct-Q4_K_M.gguf at `http://localhost:1234/v1` — no external API calls
- nomic-embed-text-v1.5 (768-dim, 8192-token context) for embeddings via sentence-transformers + CUDA; requires task prefixes (`search_document:` / `search_query:`)
- NetworkX is the graph backend (native to LightRAG, no adapter needed)
- nanoVectorDB is the vector backend (managed by LightRAG automatically)
- PyTorch 2.11.0+cu128 — CUDA 12.8 wheel, installed separately before requirements.txt

**Data pipeline:**
1. `src/ingestion/download.py` — boto3 unsigned S3 download from `indian-supreme-court-judgments` (ap-south-1), CC-BY-4.0
2. `src/ingestion/extract.py` — pymupdf (fitz) PDF-to-text, reads from tar in-memory
3. `src/ingestion/preprocess.py` — noise removal, section labeling ([FACTS], [ISSUES], [JUDGMENT], [ORDER], [HELD]), in-place overwrite
4. `scripts/index_documents.py` — async batch insert to LightRAG; `storage/indexed.json` tracks already-indexed docs; default 3 workers (VRAM constraint)

**Query modes (LightRAG 1.4.x):** naive, local, global, hybrid (recommended default)

**Incremental indexing:** `storage/indexed.json` persists doc IDs → timestamps; re-runs skip already-indexed files.

**How to apply:** Use these facts when writing any documentation about the project — architecture, setup, data, or API references.
