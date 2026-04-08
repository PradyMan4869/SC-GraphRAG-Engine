---
name: Indexing Pipeline — Phase 4 Implementation
description: Documents what was built for LightRAG indexing and graph inspection, key design decisions, and paths to all files.
type: project
---

Phase 4 (Indexing Pipeline) of the GraphRAG system for Indian Supreme Court judgments is implemented and complete.

**Why:** These are the indexing and graph-inspection components. They batch-insert preprocessed .txt files into LightRAG's vector/graph store and provide utilities to inspect the resulting NetworkX knowledge graph.

**How to apply:** When extending or debugging these modules, reference the design decisions below rather than re-deriving them.

---

## Files written

- `scripts/index_documents.py` — async CLI for batch-inserting .txt files into LightRAG
- `src/graph/explorer.py` — NetworkX graph inspection utilities

---

## Key design decisions

### scripts/index_documents.py

- `storage/indexed.json` tracks `{doc_id: ISO-8601 timestamp}` so re-runs skip already-indexed docs. Writes atomically via tmp file + rename to avoid corruption.
- `asyncio.Semaphore(--workers)` bounds concurrency. Default is 3 workers. LightRAG calls LLM + embedding per doc, so >4 workers risks VRAM exhaustion.
- `insert_document` is imported inside the async `_index_one` coroutine (not at module top level) so the LightRAG singleton is constructed after the event loop is running.
- `doc_id` = txt file stem, e.g. `"2024_9_770_773_EN"`.
- `_collect_files()` applies `--sample` per year (not globally) so testing 5 docs from 2024 gives exactly 5 docs regardless of year count.
- `asyncio.gather()` collects all results; the indexed.json is saved once after all tasks complete.
- `asyncio.run(main())` is the entry point — `main()` is the async function.

### src/graph/explorer.py

- GraphML path: `<STORAGE_DIR>/graph_chunk_entity_relation.graphml` (LightRAG default).
- `_EDGE_KEYWORD_ATTR = "keywords"` is the expected LightRAG edge attribute; if missing, `print_stats` falls back to listing whatever attrs exist.
- `get_ego_graph` does case-insensitive fallback lookup if the exact entity name is not found — important because LightRAG may normalize entity casing.
- `print_ego_stats` caps direct-neighbor listing at 20 to keep output readable.
- `load_graph` raises `FileNotFoundError` with a helpful message if the graph hasn't been created yet (i.e., indexing hasn't run).
