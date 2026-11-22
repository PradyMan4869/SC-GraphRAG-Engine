# GraphRAG — Indian Supreme Court Judgments

A fully local GraphRAG pipeline for Indian Supreme Court judgments (the public corpus has ~35,000 judgments, 1950–2025), built as a portfolio project demonstrating graph-augmented retrieval for legal research. **Currently indexed: 630 judgments (9 failed)**, as recorded in `reports/system_stats.json` (the `storage/` index itself is gitignored and not in this repo); the full corpus is not indexed, and the in-memory NetworkX / nano-vector-db storage would need replacing (e.g. Neo4j + a real vector DB) to reach that scale.

---

> **Screenshot / Demo**
> 
> _Add a screenshot or screen recording of the Streamlit UI here._
> <img width="1900" height="1076" alt="image" src="https://github.com/user-attachments/assets/aa5b37f9-068c-402c-88da-065d3f2c25f5" />

---

## What It Does

- **Graph-augmented retrieval.** Plain RAG retrieves text chunks by vector similarity. GraphRAG additionally extracts named entities (cases, articles, parties, doctrines) and their relationships into a knowledge graph, enabling multi-hop reasoning across documents that vector search alone cannot traverse.
- **Five query modes.** `naive` (dense vector only), `local` (entity-centric graph neighbourhood), `global` (relation-centric graph paths), `hybrid` (local + global, graph only: no chunk-level vector search) and `mix` (graph + vector search). `mix` scored best on retrieval in the evaluation below, so use it for multi-document questions.
- **Fully local inference.** The LLM and the embedding model (nomic-embed-text-v1.5) are both served by LM Studio on a local GPU; the cross-encoder reranker (bge-reranker-base) runs in-process on PyTorch. No external API calls, no data leaves the machine.
- **Incremental indexing.** Already-indexed documents are tracked in `storage/indexed.json` and skipped on re-runs, so you can index year-by-year without reprocessing the entire corpus.

---

## Architecture

```
AWS S3 (indian-supreme-court-judgments)
    │  download.py (boto3, no auth)
    ▼
data/raw/year=YYYY/english.tar    ← ZIP of PDFs
    │  extract.py (pymupdf)
    ▼
data/processed/year=YYYY/*.txt   ← plain text
    │  preprocess.py
    ▼
LightRAG.insert()                ← index_documents.py
    ├── Embedding: nomic-embed-text-v1.5 via LM Studio → nanoVectorDB
    └── Entity extraction: LLM via LM Studio (LM_STUDIO_MODEL) → NetworkX graph
    Query-time: vector/graph retrieval → bge-reranker-base → LLM answer
    ▼
LightRAG.query(mode="mix")
    ▼
Streamlit UI  (ui/app.py)
```

---

## Tech Stack

| Component | Package / Version |
|---|---|
| Language | Python 3.13 |
| RAG framework | LightRAG (`lightrag-hku`) 1.4.x |
| Embedding model | `nomic-embed-text-v1.5` (768-dim) served by LM Studio; `search_document:` / `search_query:` prefixes applied per call |
| Reranker | `BAAI/bge-reranker-base` (sentence-transformers, fp16 on CUDA) |
| LLM | Any LM Studio chat model, set via `LM_STUDIO_MODEL`. Graph extraction was first run on Qwen3-VL-8B (Q4\_K\_M) and later moved to a smaller Qwen2.5 model for speed; see *Evaluation* below. |
| Graph store | NetworkX 3.4+ |
| Vector store | nanoVectorDB (managed by LightRAG) |
| UI | Streamlit 1.43+ |
| Deep learning | PyTorch 2.11.0+cu128 |
| PDF extraction | PyMuPDF 1.25+ |
| S3 downloads | boto3 1.37+ |

---

## Setup

### Prerequisites

- Python 3.13 (from [python.org](https://www.python.org/downloads/))
- Git
- CUDA 12.8+ (RTX GPU required for local inference)
- [LM Studio](https://lmstudio.ai/) with `Qwen3-VL-8B-Instruct-Q4_K_M.gguf` loaded

### 1. Clone and create the virtual environment

```bash
git clone https://github.com/<your-username>/graphrag-supreme-court.git
cd "graphrag-supreme-court"
scripts\setup_venv.bat
```

`setup_venv.bat` creates a `venv/`, installs PyTorch 2.11 with the CUDA 12.8 wheel, then installs all other dependencies from `requirements.txt`.

After it completes, activate the environment:

```bash
venv\Scripts\activate
```

Verify GPU access:

```bash
python -c "import torch; print(torch.cuda.get_device_name(0))"
```

### 2. Start the LM Studio server

1. Open LM Studio.
2. Load model: `Qwen3-VL-8B-Instruct-Q4_K_M.gguf`.
3. Open the **Developer** tab and click **Start Server**.
4. Confirm the server is running at `http://localhost:1234`.

### 3. Configure environment variables

```bash
copy .env.example .env
```

Edit `.env` if you need to override the default LM Studio URL, model name, or storage paths. The defaults work without modification for a standard LM Studio install.

---

## Data

**Source:** [AWS Open Data Registry — Indian Supreme Court Judgments](https://registry.opendata.aws/)  
**Bucket:** `s3://indian-supreme-court-judgments` (region: `ap-south-1`, public, no authentication required)  
**License:** CC-BY-4.0  
**Size:** ~52 GB for the full corpus (1950–2025)

### Download

Downloads the `.tar` archive of judgment PDFs, the index JSON, and the metadata Parquet file for the specified years. Files are skipped if already present with the correct size.

```bash
python src/ingestion/download.py --years 2024
```

To download multiple years:

```bash
python src/ingestion/download.py --years 2022 2023 2024
```

To download the entire corpus (1950–2025):

```bash
python src/ingestion/download.py --years all
```

### Extract

Reads each `.tar` archive in-memory, converts each PDF to plain text via PyMuPDF, and writes one `.txt` file per judgment to `data/processed/year=YYYY/`. Already-extracted files are skipped.

```bash
python src/ingestion/extract.py --years 2024
```

### Preprocess

Cleans extracted `.txt` files in-place: removes page-number noise lines, strips non-printable characters, collapses blank lines, and annotates section headings (`FACTS`, `ISSUES`, `JUDGMENT`, `ORDER`, `HELD`).

```bash
python src/ingestion/preprocess.py --years 2024
```

---

## Indexing

Indexing reads preprocessed `.txt` files and inserts them into LightRAG, which runs the embedding model and LLM in parallel to build the vector store and knowledge graph. Already-indexed document IDs are recorded in `storage/indexed.json` and skipped on re-runs.

**Test run — 10 documents from 2024:**

```bash
python scripts/index_documents.py --years 2024 --sample 10
```

**Index a full year:**

```bash
python scripts/index_documents.py --years 2024
```

**Index multiple years:**

```bash
python scripts/index_documents.py --years 2023 2024
```

> **Concurrency** is fixed in `src/rag/indexer.py` (`llm_model_max_async=4`, one document at a time). More than ~4 concurrent LLM calls risks VRAM exhaustion on an 8B model. Documents whose extraction fails are *not* recorded as indexed and are retried on the next run.

---

## Usage

### CLI query

```bash
python src/rag/query.py "What did the court hold on Article 21?"
```

Specify a retrieval mode:

```bash
python src/rag/query.py "What did the court hold on Article 21?" --mode local
```

Valid modes: `naive`, `local`, `global`, `hybrid`, `mix`. The CLI/UI default is still `hybrid`; pass `--mode mix` for the best-measured retrieval.

### Streamlit UI

```bash
streamlit run ui/app.py
```

Opens the interactive query interface in your browser at `http://localhost:8501`.

### Graph explorer

Inspect the knowledge graph structure after indexing:

```bash
# Print graph statistics (node/edge counts, top entities, top relationship types)
python src/graph/explorer.py

# Inspect the ego graph around a specific entity (2-hop neighbourhood)
python src/graph/explorer.py --entity "Article 21"

# Adjust the hop radius
python src/graph/explorer.py --entity "Article 21" --radius 1
```

---

## Evaluation

Run `python -m src.evaluation.generator` (builds a seeded synthetic question set from indexed chunks), then `python -m src.evaluation.retrieval_eval --modes naive hybrid` (retrieval only) and `python -m src.evaluation.benchmark` (adds answers, ROUGE/BLEU and an LLM judge). All of these need LM Studio running.

Retrieval is scored against the single chunk each question was generated from: **hit rate** (was the gold chunk in the context), **precision** (1/N when hit), **MRR**, and **context size**. Recall is always reported next to context size, since returning everything gives 100% recall. Results include n and a 95% Wilson interval.

Known limitations: questions are LLM-generated (not hand-labelled) from one chunk, which favours lexical/naive retrieval; the answer judge is the same local model that wrote the answers; ROUGE/BLEU against short gold answers mostly measure length.

### Results (overnight run, 2026-11-22)

Full tables, confidence intervals and caveats: `reports/overnight_report.md` (regenerate with `python -m src.evaluation.report`). Retrieval is scored on **multi-chunk questions** (2-4 gold chunks from different judgments; a verifier drops questions answerable from one chunk), reranker on, 20 chunks returned.

| Gold set | naive | mix | hybrid |
|---|---|---|---|
| Graph-independent (n=106), recall@20 | 53.3% | **58.9%** | 27.8% |
| Graph-map (n=207, biased toward graph), recall@20 | 54.4% | **70.5%** | 59.1% |
| Single-chunk (n=300), gold in context | 87.7% | **92.7%** | 63.7% |

- `mix` beats `naive` on every set; on the unbiased set the gain is modest (+5.6 pts, paired sign test p=0.007). `hybrid`/`local`/`global` are far worse because the graph is sparse (below).
- Graph modes cost ~1.4-3.3 s per retrieval vs ~0.13 s for `naive`. Graph retrieval is not faster.
- Reranker matters: disabling it drops `mix` recall@20 from 58.9% to 45.0%. Raising `chunk_top_k` to 40 gives 64.5% (about 33 chunks).
- **Answer quality does not favour the graph.** With the 1.5B answering model, an 8B judge scored evidence coverage on multi-chunk questions at 39.8% (`naive`), 28.9% (`mix`), 27.5% (`hybrid`); on single-chunk questions `naive` and `mix` are roughly tied (~6.2/10). Do not claim graph retrieval improves answers.

**Graph health.** 42,790 nodes, 10,490 edges (0.245 edges/node); 74% of nodes isolated; largest component holds 14.6% of nodes. The corpus was indexed with a 400-token output cap and 4096 context, which truncated extraction output (relations are written last) so most relations were lost.

**Extraction-model trade-off.** Moving graph extraction from Qwen3-8B to a Qwen2.5-1.5B model cut wall-clock indexing time by a measured **12.9x** over the corpus (owner-measured; hours instead of days). This is an indexing-time figure only, not a retrieval number. Under a corrected config (context >= 8192) the 8B yields ~10 relations/chunk while the 1.5B loops on about half of chunks and produces many junk entity names (extraction A/B table in the report). Re-indexing everything with the 8B would take roughly 11 days, so it has not been done. (Owner log: the 8B indexed 160 documents in ~30 h before the switch; the 1.5B processed the remaining ~620 in ~9 h.)

**Limitations.** Gold questions are LLM-generated (Qwen3-VL-8B), not human-labelled, and gold sets can miss other valid chunks. The judge is a small local model. Answer evals use 60-100 questions per mode. The "hand-labelled 98.5% entity recall" figure is not supported by any evaluation in this repo and should not be cited.

---

## Project Structure

```
├── src/
│   ├── ingestion/          # S3 download, PDF extraction, text cleaning
│   ├── rag/                # LightRAG init, LLM backend, embeddings, query
│   └── graph/              # NetworkX graph inspection
├── ui/                     # Streamlit app
├── scripts/                # CLI entrypoints (setup, download, index)
├── tests/                  # pytest test suite
├── data/                   # gitignored — downloaded judgments
└── storage/                # gitignored — LightRAG vector + graph storage
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## License

- **Data** (`data/`): [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) — Indian Supreme Court Judgments dataset via AWS Open Data Registry.
- **Code** (everything else): [MIT](LICENSE).
