"""
Phase 7 — Testing
Owner: code-tester

Shared pytest fixtures used across all test modules.
"""
from __future__ import annotations

import sys
import tarfile
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make the project root importable regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Minimal valid PDF bytes
# ---------------------------------------------------------------------------

def _make_minimal_pdf(text: str = "Supreme Court Judgment") -> bytes:
    """Return minimal, self-contained PDF bytes that fitz (PyMuPDF) can parse.

    The PDF is hand-crafted to the spec minimum so the test suite has no
    compile-time dependency on fpdf2 / reportlab.  The text stream embeds
    *text* as a visible string on page 1.
    """
    safe = text.replace("(", r"\(").replace(")", r"\)")

    # Build the objects first so we can compute byte offsets for the xref table.
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"

    stream_content = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode()
    obj4 = (
        b"4 0 obj\n<< /Length " + str(len(stream_content)).encode() + b" >>\nstream\n"
        + stream_content + b"\nendstream\nendobj\n"
    )
    obj5 = b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

    header = b"%PDF-1.4\n"
    body = obj1 + obj2 + obj3 + obj4 + obj5

    # Cross-reference table
    xref_offset = len(header) + len(body)
    offsets = []
    pos = len(header)
    for obj in (obj1, obj2, obj3, obj4, obj5):
        offsets.append(pos)
        pos += len(obj)

    xref_lines = [b"xref\n", f"0 6\n".encode(), b"0000000000 65535 f \n"]
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n \n".encode())

    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    )

    return header + body + b"".join(xref_lines) + trailer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_processed_dir(tmp_path: Path) -> Path:
    """Return a data/processed/year=2024/ directory containing 3 small .txt files."""
    year_dir = tmp_path / "data" / "processed" / "year=2024"
    year_dir.mkdir(parents=True)

    judgments = [
        (
            "2024_1_001_EN.txt",
            "IN THE SUPREME COURT OF INDIA\n\n"
            "CIVIL APPELLATE JURISDICTION\n\n"
            "FACTS\n\nThe petitioner challenged the order of the High Court.\n\n"
            "HELD\n\nThe appeal is allowed.\n",
        ),
        (
            "2024_1_002_EN.txt",
            "IN THE SUPREME COURT OF INDIA\n\n"
            "CRIMINAL APPELLATE JURISDICTION\n\n"
            "ISSUES\n\nWhether the conviction is sustainable in law.\n\n"
            "JUDGMENT\n\nAppeal dismissed.\n",
        ),
        (
            "2024_1_003_EN.txt",
            "IN THE SUPREME COURT OF INDIA\n\n"
            "WRIT JURISDICTION\n\n"
            "ORDER\n\nNotice issued to respondents.\n",
        ),
    ]

    for filename, content in judgments:
        (year_dir / filename).write_text(content, encoding="utf-8")

    return tmp_path


@pytest.fixture()
def tmp_raw_dir(tmp_path: Path) -> Path:
    """Return a data/raw/year=2024/ directory containing an english.tar with 2 fake PDFs."""
    year_dir = tmp_path / "data" / "raw" / "year=2024"
    year_dir.mkdir(parents=True)

    pdf_a = _make_minimal_pdf("Judgment A: Article 21 upheld.")
    pdf_b = _make_minimal_pdf("Judgment B: Bail application dismissed.")

    tar_path = year_dir / "english.tar"
    with tarfile.open(tar_path, "w") as tf:
        for name, data in (
            ("2024_1_001_EN.pdf", pdf_a),
            ("2024_1_002_EN.pdf", pdf_b),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    return tmp_path


@pytest.fixture()
def sample_judgment_text() -> str:
    """Return a multi-paragraph fake judgment string with section headings."""
    return (
        "IN THE SUPREME COURT OF INDIA\n"
        "\n"
        "CIVIL APPELLATE JURISDICTION\n"
        "\n"
        "CIVIL APPEAL NO. 1234 OF 2024\n"
        "\n"
        "Ram Prasad                         ... Appellant\n"
        "           versus\n"
        "State of Maharashtra               ... Respondent\n"
        "\n"
        "JUDGMENT\n"
        "\n"
        "The Court delivered the following judgment:\n"
        "\n"
        "FACTS\n"
        "\n"
        "The appellant was aggrieved by the order of the High Court of Bombay "
        "dated 15th March 2023 by which his writ petition was dismissed.\n"
        "\n"
        "The dispute relates to the acquisition of agricultural land under "
        "the Land Acquisition Act, 1894.\n"
        "\n"
        "ISSUES\n"
        "\n"
        "1. Whether the acquisition proceedings were conducted in accordance "
        "with the procedure prescribed by law.\n"
        "2. Whether the compensation awarded is adequate.\n"
        "\n"
        "HELD\n"
        "\n"
        "1. The acquisition proceedings are hereby quashed for non-compliance "
        "with Section 4 of the Act.\n"
        "2. Fresh proceedings shall be initiated within six months.\n"
        "\n"
        "ORDER\n"
        "\n"
        "The appeal is allowed. No order as to costs.\n"
    )


@pytest.fixture()
def mock_rag() -> MagicMock:
    """Return a MagicMock that mimics the return value of get_rag().

    ``aquery`` is an AsyncMock so it can be awaited in async test code.
    """
    rag = MagicMock()
    rag.aquery = AsyncMock(return_value="The fundamental right to life is protected.")
    return rag
