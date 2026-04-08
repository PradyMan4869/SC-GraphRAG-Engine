---
name: Project GraphRAG Supreme Court
description: Testing environment, framework, source layout, and run command for the GraphRAG Indian Supreme Court project
type: project
---

Python 3.13 venv at `D:\Projects\GraphRag-Supreme Court\venv\`.

**Source layout:**
- `src/ingestion/download.py` — S3 download with boto3 (unsigned); `_parse_years`, `download_year`, `make_s3_client`
- `src/ingestion/extract.py` — tar → PDF → text via fitz/pymupdf; `extract_year`, `_pdf_bytes_to_text`
- `src/ingestion/preprocess.py` — `clean_text`, `preprocess_year`; labels FACTS/ISSUES/JUDGMENT/ORDER/HELD all-caps headings; removes lone page numbers and "Page N" footers
- `src/graph/explorer.py` — NetworkX GraphML utils; `load_graph`, `print_stats`, `get_ego_graph` (case-insensitive lookup)
- `src/rag/embedding.py` — nomic-embed-text-v1.5 via SentenceTransformer; `embedding_func` (document prefix), `embed_for_query` (query prefix), `EMBEDDING_DIM=768`
- `src/rag/query.py` — `query(question, mode)` async; VALID_MODES = {naive, local, global, hybrid}; calls `get_rag()` from `src.rag.indexer`
- `src/rag/indexer.py` — LightRAG singleton; imports lightrag, lightrag.utils, openai (via llm_backend)
- `src/rag/llm_backend.py` — LM Studio OpenAI-compatible backend; imports openai.AsyncOpenAI

**Test run command:**
```
venv\Scripts\python -m pytest tests/ -v
```

**Installed packages:** pytest, networkx, pymupdf (fitz), tqdm, python-dotenv, boto3, botocore

**Why:** pipeline for downloading, extracting, preprocessing Indian SC judgments and indexing into LightRAG knowledge graph for hybrid RAG queries.

**How to apply:** When adding tests, remember that lightrag and openai are NOT installed in the test environment — they must be stubbed via sys.modules before any src.rag.* import.
