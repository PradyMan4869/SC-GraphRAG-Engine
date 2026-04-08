---
name: Testing Conventions for GraphRAG Project
description: Explicit testing rules established for the GraphRAG Supreme Court project
type: feedback
---

Use `unittest.mock` only — do NOT use `pytest-mock` (not installed).

**Why:** The user's constraints document explicitly prohibits pytest-mock. unittest.mock covers all the same use cases.

**How to apply:** All patches use `from unittest.mock import patch, MagicMock, AsyncMock`. No `mocker` fixture.

---

Stub `lightrag`, `lightrag.utils`, `openai`, and `src.rag.indexer` via `sys.modules` at module level in `test_rag_query.py` before importing `src.rag.query`.

**Why:** `query.py` imports `from lightrag import QueryParam` and `from src.rag.indexer import get_rag` at module level. `indexer.py` in turn imports LightRAG, `lightrag.utils.EmbeddingFunc`, `openai.AsyncOpenAI`, and tries to load a SentenceTransformer model. None of these are available or allowed in the test environment.

**How to apply:** Define stub insertion functions (e.g. `_install_lightrag_stubs()`, `_install_openai_stub()`, `_install_src_rag_stubs()`) and call them before any project import at the top of the test module.

---

Use `from __future__ import annotations` in every test file.

**Why:** Stated constraint in the test specification. Keeps forward-reference typing consistent with the source modules.

---

Do not load real SentenceTransformer models. Patch `src.rag.embedding._encode` at the module level.

**Why:** No GPU available in test environment; model weights are not present. Patching `_encode` (the sync entry point called via `asyncio.to_thread`) is the correct isolation point — it prevents `_get_model()` from ever being called.

**How to apply:** `with patch.object(embedding_module, "_encode", fake_encode_func):` inside each test or test class that exercises `embedding_func` or `embed_for_query`.

---

Fake PDFs for tar fixtures: hand-craft minimal valid PDF-1.4 bytes instead of using fpdf2/reportlab.

**Why:** Neither fpdf2 nor reportlab is guaranteed to be installed. PyMuPDF (fitz) is installed and can parse the minimal hand-crafted PDF. This avoids an optional dependency.

**How to apply:** Use the `_make_minimal_pdf(text)` helper in `conftest.py` which builds a 5-object PDF-1.4 structure with a single text stream.
