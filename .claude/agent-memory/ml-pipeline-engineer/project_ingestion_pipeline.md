---
name: Ingestion Pipeline — Phase 1 & 2 Implementation
description: Documents what was built for data acquisition and preprocessing, key design decisions, and paths to all four files.
type: project
---

Phase 1 (download.py) and Phase 2 (extract.py, preprocess.py) of the ingestion pipeline are implemented and complete.

**Why:** These are the first two phases of the GraphRAG system for Indian Supreme Court judgments. They handle S3 data acquisition and text extraction before LightRAG indexing.

**How to apply:** When extending or debugging these modules, reference the design decisions below rather than re-deriving them.

---

## Files written

- `src/ingestion/download.py` — boto3 unsigned S3 download with tqdm, size-check skip logic
- `src/ingestion/extract.py` — in-memory tar extraction + pymupdf text conversion
- `src/ingestion/preprocess.py` — in-place text cleaning with section labeling
- `scripts/download_data.bat` — replaces old aws-cli placeholder with Python script calls

---

## Key design decisions

### download.py
- Uses `Config(signature_version=UNSIGNED)` from botocore for no-auth public bucket access.
- Skip logic: `head_object` to fetch ContentLength, compare to local `stat().st_size`.
- Downloads index.json first (smallest), then the tar, then the parquet — so partial runs leave useful artifacts.
- `--years all` expands to 1950–2025 (ALL_YEARS constant).
- S3 key templates: `data/tar/year={year}/english/english.tar`, `metadata/parquet/year={year}/metadata.parquet`.

### extract.py
- Uses `tarfile.open` + `tf.extractfile(member)` to read PDFs directly from the tar into memory — no temp disk extraction.
- `fitz.open(stream=bytes, filetype="pdf")` accepts raw bytes; no temp file needed.
- Output: `data/processed/year=YYYY/{stem}.txt` where stem matches the PDF filename stem.
- Skip logic: output .txt file already exists.

### preprocess.py
- Section detection only fires when the line is ALL CAPS and ≤ 80 chars — matches Indian SC heading style.
- Section marker format: `[FACTS] FACTS` — bracket prefix so LightRAG chunking or downstream code can split on `\[SECTION\]` regex.
- Noise removal: lone digits, "Page N", "- N -" patterns.
- Non-printable removal preserves tab, LF, CR; strips 0x01–0x08, 0x0B, 0x0C, 0x0E–0x1F, 0x7F.
