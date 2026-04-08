"""
Phase 1 — Data Acquisition
Owner: ml-pipeline-engineer

Downloads Indian Supreme Court Judgments from the public AWS S3 bucket.
Bucket: s3://indian-supreme-court-judgments (ap-south-1, no-auth, CC-BY-4.0)

Bucket layout:
    data/tar/year=YYYY/english/english.index.json
    data/tar/year=YYYY/english/english.tar
    metadata/parquet/year=YYYY/metadata.parquet

Usage:
    python src/ingestion/download.py --years 2023 2024 2025
    python src/ingestion/download.py --years all
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUCKET_NAME = "indian-supreme-court-judgments"
BUCKET_REGION = "ap-south-1"

# S3 key templates (format with year=YYYY)
S3_TAR_KEY = "data/tar/year={year}/english/english.tar"
S3_INDEX_KEY = "data/tar/year={year}/english/english.index.json"
S3_PARQUET_KEY = "metadata/parquet/year={year}/metadata.parquet"

# Years available in the corpus
ALL_YEARS = list(range(1950, 2026))

# Project root is two levels above this file (src/ingestion/download.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB per streaming chunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S3 client factory
# ---------------------------------------------------------------------------

def make_s3_client() -> boto3.client:
    """Return a boto3 S3 client configured for unsigned (public) access."""
    return boto3.client(
        "s3",
        region_name=BUCKET_REGION,
        config=Config(signature_version=UNSIGNED),
    )


# ---------------------------------------------------------------------------
# Core download helpers
# ---------------------------------------------------------------------------

def _s3_object_size(s3_client: boto3.client, key: str) -> int | None:
    """Return the ContentLength of an S3 object, or None if it does not exist."""
    try:
        head = s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
        return head["ContentLength"]
    except s3_client.exceptions.ClientError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _download_file(
    s3_client: boto3.client,
    s3_key: str,
    dest_path: Path,
    desc: str = "",
) -> bool:
    """
    Stream an S3 object to *dest_path* with a tqdm progress bar.

    Skips the download if the local file already exists and its size matches
    the remote ContentLength header.

    Returns True if the file was (or already was) successfully downloaded,
    False if the S3 key does not exist.
    """
    remote_size = _s3_object_size(s3_client, s3_key)
    if remote_size is None:
        log.warning("S3 key not found — skipping: s3://%s/%s", BUCKET_NAME, s3_key)
        return False

    # Skip if already downloaded with correct size
    if dest_path.exists() and dest_path.stat().st_size == remote_size:
        log.info("Already downloaded (size match) — skipping: %s", dest_path.name)
        return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Downloading s3://%s/%s → %s", BUCKET_NAME, s3_key, dest_path)

    response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
    body = response["Body"]

    with (
        open(dest_path, "wb") as fh,
        tqdm(
            total=remote_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=desc or dest_path.name,
            leave=False,
        ) as bar,
    ):
        while True:
            chunk = body.read(CHUNK_SIZE)
            if not chunk:
                break
            fh.write(chunk)
            bar.update(len(chunk))

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download_year(
    year: int,
    dest_dir: Path,
    s3_client: boto3.client,
) -> None:
    """
    Download all three artifacts for *year* into *dest_dir/year=YYYY/*.

    Files downloaded:
        - english.tar         (tar archive of judgment PDFs)
        - english.index.json  (index listing PDF filenames inside the tar)
        - metadata.parquet    (structured case metadata)

    Args:
        year:       Four-digit year, e.g. 2024.
        dest_dir:   Local root directory, e.g. Path("data/raw").
        s3_client:  Unsigned boto3 S3 client (from make_s3_client()).
    """
    year_str = str(year)
    year_dir = dest_dir / f"year={year_str}"
    year_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[tuple[str, Path, str]] = [
        (
            S3_INDEX_KEY.format(year=year_str),
            year_dir / "english.index.json",
            f"{year_str}/index.json",
        ),
        (
            S3_TAR_KEY.format(year=year_str),
            year_dir / "english.tar",
            f"{year_str}/english.tar",
        ),
        (
            S3_PARQUET_KEY.format(year=year_str),
            year_dir / "metadata.parquet",
            f"{year_str}/metadata.parquet",
        ),
    ]

    for s3_key, local_path, desc in artifacts:
        _download_file(s3_client, s3_key, local_path, desc=desc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_years(raw: list[str]) -> list[int]:
    """Resolve the --years argument to a sorted list of ints."""
    if len(raw) == 1 and raw[0].lower() == "all":
        return ALL_YEARS
    years: list[int] = []
    for token in raw:
        try:
            years.append(int(token))
        except ValueError:
            log.error("Invalid year token: %r — must be an integer or 'all'", token)
            sys.exit(1)
    return sorted(set(years))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Indian Supreme Court judgment archives from S3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/ingestion/download.py --years 2023 2024 2025\n"
            "  python src/ingestion/download.py --years all\n"
        ),
    )
    parser.add_argument(
        "--years",
        nargs="+",
        required=True,
        metavar="YEAR",
        help="One or more four-digit years, or 'all' for the full corpus (1950–2025).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_RAW_DIR,
        metavar="DIR",
        help=f"Root directory for downloaded files. Default: {DEFAULT_RAW_DIR}",
    )
    args = parser.parse_args()

    years = _parse_years(args.years)
    dest_dir: Path = args.dest.resolve()

    log.info("Destination: %s", dest_dir)
    log.info("Years to download: %s", years)

    s3 = make_s3_client()

    for year in years:
        log.info("=== Year %d ===", year)
        download_year(year, dest_dir, s3)

    log.info("Download complete.")


if __name__ == "__main__":
    main()
