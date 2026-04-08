"""
Phase 2 — Extraction
Owner: ml-pipeline-engineer

Opens english.tar archives for each year, extracts judgment PDFs in-memory,
converts them to plain text via pymupdf (fitz), and writes one .txt file per
judgment to data/processed/year=YYYY/.

Output file naming mirrors the PDF stem, e.g.:
    2024_9_770_773_EN.pdf  →  data/processed/year=2024/2024_9_770_773_EN.txt

Usage:
    python src/ingestion/extract.py --years 2023 2024 2025
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import tarfile
from pathlib import Path

import fitz  # pymupdf
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core extraction helpers
# ---------------------------------------------------------------------------

def _pdf_bytes_to_text(pdf_bytes: bytes) -> str:
    """
    Extract all text from a PDF given its raw bytes.

    Pages are joined with a single newline; paragraphs within a page are
    separated by the whitespace pymupdf preserves.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        Full plain-text string for the document.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_year(
    year: int,
    raw_dir: Path,
    processed_dir: Path,
) -> None:
    """
    Extract all PDFs from the english.tar for *year* and save as .txt files.

    For each member in the tar archive that ends with .pdf:
      1. Read its bytes from the tar without extracting to disk.
      2. Parse with pymupdf to get plain text.
      3. Write to processed_dir/year=YYYY/{stem}.txt.

    Skips files that have already been extracted (output .txt exists).

    Args:
        year:          Four-digit year, e.g. 2024.
        raw_dir:       Root of raw downloads, e.g. Path("data/raw").
        processed_dir: Root for processed output, e.g. Path("data/processed").
    """
    year_str = str(year)
    tar_path = raw_dir / f"year={year_str}" / "english.tar"
    out_dir = processed_dir / f"year={year_str}"

    if not tar_path.exists():
        log.warning("Tar archive not found — skipping year %d: %s", year, tar_path)
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Opening archive: %s", tar_path)

    with tarfile.open(tar_path, "r") as tf:
        # Collect all PDF members first so we can show a total count in tqdm
        pdf_members = [m for m in tf.getmembers() if m.name.lower().endswith(".pdf")]

        if not pdf_members:
            log.warning("No PDF files found in archive for year %d", year)
            return

        log.info("Found %d PDFs for year %d", len(pdf_members), year)

        skipped = 0
        failed = 0

        for member in tqdm(pdf_members, desc=f"{year_str}", unit="pdf"):
            # Derive output path from the PDF filename (basename only)
            pdf_name = Path(member.name).name
            stem = Path(pdf_name).stem
            out_path = out_dir / f"{stem}.txt"

            if out_path.exists():
                skipped += 1
                continue

            try:
                fobj = tf.extractfile(member)
                if fobj is None:
                    log.debug("Skipping non-file tar member: %s", member.name)
                    continue

                pdf_bytes = fobj.read()
                text = _pdf_bytes_to_text(pdf_bytes)
                out_path.write_text(text, encoding="utf-8")

            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to extract %s: %s", member.name, exc)
                failed += 1

    log.info(
        "Year %d done — extracted: %d, skipped: %d, failed: %d",
        year,
        len(pdf_members) - skipped - failed,
        skipped,
        failed,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_years(raw: list[str]) -> list[int]:
    """Resolve --years tokens to a sorted list of ints."""
    years: list[int] = []
    for token in raw:
        try:
            years.append(int(token))
        except ValueError:
            log.error("Invalid year token: %r — must be an integer", token)
            sys.exit(1)
    return sorted(set(years))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract judgment PDFs from tar archives and convert to .txt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/ingestion/extract.py --years 2023 2024 2025\n"
        ),
    )
    parser.add_argument(
        "--years",
        nargs="+",
        required=True,
        metavar="YEAR",
        help="One or more four-digit years to extract.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        metavar="DIR",
        help=f"Root directory of raw downloads. Default: {DEFAULT_RAW_DIR}",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        metavar="DIR",
        help=f"Root directory for extracted text. Default: {DEFAULT_PROCESSED_DIR}",
    )
    args = parser.parse_args()

    years = _parse_years(args.years)
    raw_dir: Path = args.raw_dir.resolve()
    processed_dir: Path = args.processed_dir.resolve()

    log.info("Raw dir:       %s", raw_dir)
    log.info("Processed dir: %s", processed_dir)
    log.info("Years:         %s", years)

    for year in years:
        log.info("=== Year %d ===", year)
        extract_year(year, raw_dir, processed_dir)

    log.info("Extraction complete.")


if __name__ == "__main__":
    main()
