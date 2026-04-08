# GraphRAG — Indian Supreme Court Judgments

A fully local GraphRAG pipeline over ~35,000 Indian Supreme Court judgments (1950–2025), built as a portfolio project demonstrating graph-augmented retrieval for legal research.

---

> **Screenshot / Demo**
> 
> _Add a screenshot or screen recording of the Streamlit UI here._
> <img width="1900" height="1076" alt="image" src="https://github.com/user-attachments/assets/aa5b37f9-068c-402c-88da-065d3f2c25f5" />

---

## What It Does

- **Graph-augmented retrieval over 35,000 judgments.** Plain RAG retrieves text chunks by vector similarity. GraphRAG additionally extracts named entities (cases, articles, parties, doctrines) and their relationships into a knowledge graph, enabling multi-hop reasoning across documents that vector search alone cannot traverse.
- **Four query modes.** `naive` (dense vector only), `local` (entity-centric graph neighbourhood), `global` (relation-centric graph paths), and `hybrid` (local + global combined — recommended for legal research).
- **Fully local inference.** The LLM (Qwen3-VL-8B) and embedding model (nomic-embed-text-v1.5) run on a local GPU via LM Studio and PyTorch CUDA. No external API calls, no data leaves the machine.
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
    ├── Embedding: nomic-embed-text-v1.5 (CUDA)  → nanoVectorDB
    └── Entity extraction: Qwen3-VL-8B via LM Studio → NetworkX graph
    ▼
LightRAG.query(mode="hybrid")
    ▼
Streamlit UI  (ui/app.py)
```

---

## Tech Stack

| Component | Package / Version |
|---|---|
| Language | Python 3.13 |
| RAG framework | LightRAG (`lightrag-hku`) 1.4.x |
| Embedding model | `nomic-ai/nomic-embed-text-v1.5` (768-dim, 8192-token context) |
| LLM | Qwen3-VL-8B-Instruct-Q4\_K\_M (via LM Studio) |
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

**Index multiple years with custom concurrency:**

```bash
python scripts/index_documents.py --years 2023 2024 --workers 4
```

> **Note on `--workers`:** The default is 3 concurrent async insert tasks. Each task calls both the embedding model and the LLM. Increasing workers beyond 4 risks VRAM exhaustion on an 8B model.

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

Valid modes: `naive`, `local`, `global`, `hybrid` (default: `hybrid`).

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
