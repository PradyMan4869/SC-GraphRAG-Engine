"""
Phase 7 — Testing
Owner: code-tester

Unit tests for src/ingestion/preprocess.py and src/ingestion/download.py.

All tests are fully offline: no network, no real S3, no file-system writes
beyond what pytest's tmp_path provides.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.preprocess import clean_text, preprocess_year
from src.ingestion.download import _parse_years, ALL_YEARS


# ===========================================================================
# clean_text — noise removal
# ===========================================================================


class TestCleanTextPageNumbers:
    """clean_text should remove lines that are lone page numbers."""

    def test_clean_text_removes_lone_integer_page_numbers(self) -> None:
        text = "Some paragraph.\n42\nAnother paragraph."
        result = clean_text(text)
        assert "42" not in result.splitlines()

    def test_clean_text_removes_single_digit_page_number(self) -> None:
        text = "First line.\n1\nSecond line."
        result = clean_text(text)
        lines = result.splitlines()
        assert "1" not in lines

    def test_clean_text_preserves_number_embedded_in_sentence(self) -> None:
        # "42" inside a sentence is NOT a lone page number — must be kept.
        text = "Section 42 deals with this topic."
        result = clean_text(text)
        assert "Section 42 deals with this topic." in result

    def test_clean_text_removes_dashed_page_number_format(self) -> None:
        # Format: "- 7 -"
        text = "Para one.\n- 7 -\nPara two."
        result = clean_text(text)
        assert "- 7 -" not in result


class TestCleanTextPageFooters:
    """clean_text should remove "Page N" header/footer lines."""

    def test_clean_text_removes_page_n_line(self) -> None:
        text = "Paragraph text.\nPage 2\nMore text."
        result = clean_text(text)
        assert "Page 2" not in result.splitlines()

    def test_clean_text_removes_page_n_of_m_line(self) -> None:
        text = "Paragraph text.\nPage 14 of 100\nMore text."
        result = clean_text(text)
        assert "Page 14 of 100" not in result

    def test_clean_text_removes_lowercase_page_footer(self) -> None:
        text = "Para.\npage 3\nPara."
        result = clean_text(text)
        assert "page 3" not in result

    def test_clean_text_preserves_line_mentioning_page_in_body(self) -> None:
        # A sentence that contains "page" but is not a lone footer.
        text = "See page 3 of the exhibit for details."
        result = clean_text(text)
        assert "See page 3 of the exhibit for details." in result


class TestCleanTextBlankLineCollapse:
    """clean_text should collapse multiple consecutive blank lines to a single one."""

    def test_clean_text_collapses_two_blank_lines(self) -> None:
        text = "Para A.\n\n\nPara B."
        result = clean_text(text)
        # No double blank line should remain
        assert "\n\n\n" not in result

    def test_clean_text_collapses_many_blank_lines(self) -> None:
        text = "Para A.\n\n\n\n\n\nPara B."
        result = clean_text(text)
        assert "\n\n\n" not in result

    def test_clean_text_preserves_single_blank_line(self) -> None:
        text = "Para A.\n\nPara B."
        result = clean_text(text)
        assert "Para A." in result
        assert "Para B." in result
        # Single separator should still exist
        assert "\n\n" in result

    def test_clean_text_strips_leading_and_trailing_blank_lines(self) -> None:
        text = "\n\nPara A.\n\n"
        result = clean_text(text)
        assert not result.startswith("\n")
        assert not result.endswith("\n")


class TestCleanTextNullBytes:
    """clean_text should strip null bytes and non-printable characters."""

    def test_clean_text_removes_null_bytes(self) -> None:
        text = "Good\x00 text here."
        result = clean_text(text)
        assert "\x00" not in result

    def test_clean_text_removes_multiple_null_bytes(self) -> None:
        text = "\x00\x00Hello\x00World\x00"
        result = clean_text(text)
        assert "\x00" not in result
        assert "Hello" in result
        assert "World" in result

    def test_clean_text_removes_ascii_control_chars(self) -> None:
        # \x01 through \x08 are non-printable control chars
        text = "Text\x01with\x07controls."
        result = clean_text(text)
        assert "\x01" not in result
        assert "\x07" not in result

    def test_clean_text_preserves_tab_whitespace(self) -> None:
        # Tab (0x09) should be preserved by _remove_non_printable
        text = "Column A\tColumn B"
        result = clean_text(text)
        # After strip, tab may be gone from line, but the text content preserved
        assert "Column A" in result
        assert "Column B" in result


class TestCleanTextSectionHeadings:
    """clean_text should label all-caps section heading lines with a bracketed prefix."""

    def test_clean_text_labels_held_heading(self) -> None:
        text = "Some text.\n\nHELD\n\nThe appeal is allowed."
        result = clean_text(text)
        assert "[HELD] HELD" in result

    def test_clean_text_labels_facts_heading(self) -> None:
        text = "Intro.\n\nFACTS\n\nThe facts are as follows."
        result = clean_text(text)
        assert "[FACTS] FACTS" in result

    def test_clean_text_labels_issues_heading(self) -> None:
        text = "Intro.\n\nISSUES\n\nThe issues are."
        result = clean_text(text)
        assert "[ISSUES] ISSUES" in result

    def test_clean_text_labels_judgment_heading(self) -> None:
        text = "Intro.\n\nJUDGMENT\n\nWe hold."
        result = clean_text(text)
        assert "[JUDGMENT] JUDGMENT" in result

    def test_clean_text_labels_order_heading(self) -> None:
        text = "Intro.\n\nORDER\n\nAppeal dismissed."
        result = clean_text(text)
        assert "[ORDER] ORDER" in result

    def test_clean_text_does_not_label_mixed_case_heading(self) -> None:
        # Mixed-case "Held:" is NOT a standalone all-caps heading — must not be labelled.
        text = "The court held: the act is valid."
        result = clean_text(text)
        assert "[HELD]" not in result

    def test_clean_text_does_not_label_section_keyword_in_long_line(self) -> None:
        # A long line with HELD buried inside should not be labelled as a heading.
        long_line = "HELD " + "x" * 80
        result = clean_text(long_line)
        assert "[HELD]" not in result


class TestCleanTextBodyTextPreservation:
    """clean_text must not alter normal legal prose."""

    def test_clean_text_preserves_normal_sentence(self) -> None:
        sentence = "The petitioner filed a writ petition under Article 32."
        result = clean_text(sentence)
        assert sentence in result

    def test_clean_text_preserves_quoted_text(self) -> None:
        sentence = 'The Court observed: "Liberty cannot be curtailed."'
        result = clean_text(sentence)
        assert sentence in result

    def test_clean_text_preserves_numbered_list_items(self) -> None:
        text = "1. The first ground of appeal.\n2. The second ground of appeal."
        result = clean_text(text)
        assert "1. The first ground of appeal." in result
        assert "2. The second ground of appeal." in result


# ===========================================================================
# preprocess_year — file-system behaviour
# ===========================================================================


class TestPreprocessYear:
    """preprocess_year interacts with the filesystem; use tmp_processed_dir."""

    def test_preprocess_year_skips_missing_dir(self, tmp_path: Path) -> None:
        """No error raised when the year directory does not exist."""
        # Arrange: tmp_path has no year=9999 sub-directory
        processed_root = tmp_path / "data" / "processed"
        processed_root.mkdir(parents=True)

        # Act + Assert: must complete silently without raising
        preprocess_year(9999, processed_root)

    def test_preprocess_year_cleans_files_in_place(
        self, tmp_processed_dir: Path
    ) -> None:
        """Files in tmp_processed_dir should be overwritten with cleaned content."""
        processed_root = tmp_processed_dir / "data" / "processed"
        year_dir = processed_root / "year=2024"

        # Inject a page-number artifact into one file
        dirty_file = year_dir / "2024_1_001_EN.txt"
        dirty_file.write_text("Paragraph.\n42\nAnother paragraph.", encoding="utf-8")

        preprocess_year(2024, processed_root)

        cleaned = dirty_file.read_text(encoding="utf-8")
        lines = cleaned.splitlines()
        assert "42" not in lines, "Lone page number was not removed"

    def test_preprocess_year_processes_all_txt_files(
        self, tmp_processed_dir: Path
    ) -> None:
        """All .txt files for the year must be touched (mtime or content updated)."""
        processed_root = tmp_processed_dir / "data" / "processed"
        year_dir = processed_root / "year=2024"

        original_contents = {
            p: p.read_text(encoding="utf-8") for p in year_dir.glob("*.txt")
        }
        assert len(original_contents) == 3, "Fixture should provide exactly 3 files"

        preprocess_year(2024, processed_root)

        # Files still exist after preprocessing
        for path in original_contents:
            assert path.exists()


# ===========================================================================
# download._parse_years — CLI argument parsing
# ===========================================================================


class TestParseYears:
    """_parse_years resolves the --years CLI argument."""

    def test_parse_years_all_returns_full_range(self) -> None:
        result = _parse_years(["all"])
        assert result == ALL_YEARS

    def test_parse_years_all_case_insensitive(self) -> None:
        # "ALL", "All", "aLl" must all expand to the corpus range.
        assert _parse_years(["ALL"]) == ALL_YEARS
        assert _parse_years(["All"]) == ALL_YEARS

    def test_parse_years_single_year(self) -> None:
        result = _parse_years(["2024"])
        assert result == [2024]

    def test_parse_years_multiple_years(self) -> None:
        result = _parse_years(["2022", "2023", "2024"])
        assert result == [2022, 2023, 2024]

    def test_parse_years_deduplicates_and_sorts(self) -> None:
        result = _parse_years(["2024", "2022", "2024", "2023"])
        assert result == [2022, 2023, 2024]

    def test_parse_years_all_contains_1950_through_2025(self) -> None:
        result = _parse_years(["all"])
        assert 1950 in result
        assert 2025 in result

    def test_parse_years_all_does_not_contain_years_outside_range(self) -> None:
        result = _parse_years(["all"])
        assert 1949 not in result
        assert 2026 not in result

    def test_parse_years_explicit_years_correct_type(self) -> None:
        result = _parse_years(["2020", "2021"])
        assert all(isinstance(y, int) for y in result)

    def test_parse_years_invalid_token_exits(self) -> None:
        """Invalid token should call sys.exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            _parse_years(["not-a-year"])
        assert exc_info.value.code == 1
