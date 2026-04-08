"""
Phase 4 — Indexing Pipeline

CLI entrypoint: walks data/processed/, reads .txt files, and inserts them
into LightRAG one document at a time.

indexed.json is updated after every document so progress survives interruption.
Run again after any crash — already-indexed docs are skipped automatically.

The primary speedup is /no_think in llm_backend.py which disables Qwen3's
chain-of-thought reasoning (was consuming the entire max_tokens budget,
leaving nothing for the actual entity extraction output).

Usage:
    python scripts/index_documents.py --years 2024
    python scripts/index_documents.py --years 2024 --sample 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tqdm import tqdm

DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_STORAGE_DIR = PROJECT_ROOT / "storage"
INDEXED_JSON = DEFAULT_STORAGE_DIR / "indexed.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# indexed.json helpers
# ---------------------------------------------------------------------------

def _load_index(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read %s (%s) — starting fresh.", path, exc)
        return {}


def _save_index(path: Path, index: dict[str, str]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _discover_years(processed_dir: Path) -> list[int]:
    years: list[int] = []
    for d in processed_dir.iterdir():
        if d.is_dir() and d.name.startswith("year="):
            try:
                years.append(int(d.name[5:]))
            except ValueError:
                pass
    return sorted(years)


def _collect_files(processed_dir: Path, years: list[int], sample: int | None) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for year in years:
        year_dir = processed_dir / f"year={year}"
        if not year_dir.exists():
            log.warning("Year directory not found, skipping: %s", year_dir)
            continue
        files = sorted(year_dir.glob("*.txt"))
        if sample is not None:
            files = files[:sample]
        for f in files:
            result.append((f.stem, f))
    return result


# ---------------------------------------------------------------------------
# Async indexing — one doc at a time, indexed.json updated after each
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Insert judgment .txt files into LightRAG one at a time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/index_documents.py --years 2024 --sample 10\n"
            "  python scripts/index_documents.py --years 2024\n"
        ),
    )
    parser.add_argument("--years", nargs="+", metavar="YEAR", default=None)
    parser.add_argument("--sample", type=int, default=None, metavar="N",
                        help="Index only the first N documents per year.")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    args = parser.parse_args()

    processed_dir: Path = args.processed_dir.resolve()
    if not processed_dir.exists():
        log.error("Processed directory does not exist: %s", processed_dir)
        sys.exit(1)

    if args.years is None:
        years = _discover_years(processed_dir)
        if not years:
            log.error("No year=YYYY subdirectories found in %s", processed_dir)
            sys.exit(1)
        log.info("Auto-discovered years: %s", years)
    else:
        try:
            years = sorted({int(y) for y in args.years})
        except ValueError:
            log.error("--years values must be integers")
            sys.exit(1)

    all_files = _collect_files(processed_dir, years, args.sample)
    if not all_files:
        log.warning("No .txt files found. Nothing to do.")
        return

    index = _load_index(INDEXED_JSON)
    pending = [(doc_id, path) for doc_id, path in all_files if doc_id not in index]
    skipped = len(all_files) - len(pending)

    log.info("Total: %d | Skipped (already indexed): %d | To insert: %d",
             len(all_files), skipped, len(pending))

    if not pending:
        log.info("Nothing new to index.")
        _print_summary(0, skipped, 0)
        return

    from src.rag.indexer import get_rag  # noqa: PLC0415

    rag = await get_rag()

    inserted = 0
    failed = 0

    with tqdm(total=len(pending), desc="Indexing", unit="doc") as pbar:
        for doc_id, path in pending:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                log.error("Cannot read %s: %s", path, exc)
                failed += 1
                pbar.update(1)
                continue

            try:
                await rag.ainsert(text, ids=[doc_id])
                ts = datetime.now(timezone.utc).isoformat()
                index[doc_id] = ts
                _save_index(INDEXED_JSON, index)
                inserted += 1
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to index %s: %s", doc_id, exc)
                failed += 1

            pbar.update(1)

    _print_summary(inserted, skipped, failed)


def _print_summary(inserted: int, skipped: int, failed: int) -> None:
    print("\n" + "=" * 50)
    print("  Indexing Summary")
    print("=" * 50)
    print(f"  Inserted : {inserted}")
    print(f"  Skipped  : {skipped}")
    print(f"  Failed   : {failed}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
