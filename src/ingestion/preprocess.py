"""
Phase 2 — Preprocessing
Owner: ml-pipeline-engineer

Cleans extracted judgment .txt files in-place:
  - Removes lone page numbers and "Page N" header/footer lines
  - Collapses runs of blank lines to a single blank line
  - Strips leading/trailing whitespace per line
  - Removes null bytes and non-printable characters
  - Detects and labels section headings: FACTS, ISSUES, JUDGMENT, ORDER, HELD

Files are overwritten in place; the directory layout is unchanged.

Usage:
    python src/ingestion/preprocess.py --years 2023 2024 2025
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Lines matching any of these patterns are considered header/footer noise
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\d+$"),               # lone page numbers: "1", "42"
    re.compile(r"^Page\s+\d+(\s+of\s+\d+)?$", re.IGNORECASE),  # "Page 1", "Page 42 of 100"
    re.compile(r"^-\s*\d+\s*-$"),       # "- 1 -", "- 42 -"
]

# Section heading patterns — captured group is the canonical label
_SECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bFACTS?\b", re.IGNORECASE), "FACTS"),
    (re.compile(r"\bISSUE[SD]?\b", re.IGNORECASE), "ISSUES"),
    (re.compile(r"\bJUDGMENT\b", re.IGNORECASE), "JUDGMENT"),
    (re.compile(r"\bORDER\b", re.IGNORECASE), "ORDER"),
    (re.compile(r"\bHELD\b", re.IGNORECASE), "HELD"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text cleaning helpers
# ---------------------------------------------------------------------------

def _is_noise_line(line: str) -> bool:
    """Return True if the line is a header/footer that should be removed."""
    stripped = line.strip()
    return any(pat.fullmatch(stripped) for pat in _NOISE_PATTERNS)


def _remove_non_printable(text: str) -> str:
    """Strip null bytes and non-printable ASCII control characters.

    Preserves standard whitespace: space (0x20), tab (0x09), newline (0x0A),
    carriage return (0x0D).
    """
    # Remove null bytes first
    text = text.replace("\x00", "")
    # Remove ASCII control characters except tab, newline, carriage return
    return re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def _detect_section(line: str) -> str | None:
    """
    Return a canonical section label if the line is a section heading,
    otherwise return None.

    A heading is identified as a short line (≤ 80 chars) consisting primarily
    of the section keyword, possibly with trailing punctuation or numbering.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return None
    for pattern, label in _SECTION_PATTERNS:
        if pattern.search(stripped):
            return label
    return None


def clean_text(text: str) -> str:
    """
    Apply all cleaning operations to *text* and return the cleaned string.

    Operations (in order):
      1. Remove null bytes / non-printable characters.
      2. Strip leading/trailing whitespace from each line.
      3. Remove noise lines (lone page numbers, "Page N" footers).
      4. Label detected section headings with a normalised prefix.
      5. Collapse consecutive blank lines into a single blank line.

    Args:
        text: Raw extracted judgment text.

    Returns:
        Cleaned text string.
    """
    text = _remove_non_printable(text)

    lines = text.splitlines()
    cleaned: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Drop noise lines entirely
        if _is_noise_line(stripped):
            continue

        # Label section headings.
        # Only annotate when the line is short, matches a keyword, AND is
        # written in ALL CAPS (typical for Indian SC judgment headings).
        section = _detect_section(stripped)
        if section is not None and stripped == stripped.upper() and stripped:
            # Prepend a bracketed marker so downstream code can split on sections
            stripped = f"[{section}] {stripped}"

        cleaned.append(stripped)

    # Collapse multiple consecutive blank lines into one
    collapsed: list[str] = []
    prev_blank = False
    for line in cleaned:
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank

    # Remove leading/trailing blank lines from the document
    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()

    return "\n".join(collapsed)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preprocess_year(year: int, processed_dir: Path) -> None:
    """
    Clean all .txt files for *year* in-place.

    Reads each file, applies clean_text(), and overwrites the original.
    Skips files that cannot be read.

    Args:
        year:          Four-digit year, e.g. 2024.
        processed_dir: Root of processed text files, e.g. Path("data/processed").
    """
    year_str = str(year)
    year_dir = processed_dir / f"year={year_str}"

    if not year_dir.exists():
        log.warning("Processed directory not found — skipping year %d: %s", year, year_dir)
        return

    txt_files = sorted(year_dir.glob("*.txt"))

    if not txt_files:
        log.warning("No .txt files found for year %d in %s", year, year_dir)
        return

    log.info("Preprocessing %d files for year %d", len(txt_files), year)

    failed = 0

    for txt_path in tqdm(txt_files, desc=f"{year_str}", unit="file"):
        try:
            raw = txt_path.read_text(encoding="utf-8", errors="replace")
            cleaned = clean_text(raw)
            txt_path.write_text(cleaned, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to preprocess %s: %s", txt_path.name, exc)
            failed += 1

    log.info(
        "Year %d done — processed: %d, failed: %d",
        year,
        len(txt_files) - failed,
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
        description="Clean extracted judgment text files in-place.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/ingestion/preprocess.py --years 2023 2024 2025\n"
        ),
    )
    parser.add_argument(
        "--years",
        nargs="+",
        required=True,
        metavar="YEAR",
        help="One or more four-digit years to preprocess.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        metavar="DIR",
        help=f"Root directory of extracted text files. Default: {DEFAULT_PROCESSED_DIR}",
    )
    args = parser.parse_args()

    years = _parse_years(args.years)
    processed_dir: Path = args.processed_dir.resolve()

    log.info("Processed dir: %s", processed_dir)
    log.info("Years:         %s", years)

    for year in years:
        log.info("=== Year %d ===", year)
        preprocess_year(year, processed_dir)

    log.info("Preprocessing complete.")


if __name__ == "__main__":
    main()
