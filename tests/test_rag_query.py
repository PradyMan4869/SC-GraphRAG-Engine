"""
Phase 7 — Testing
Owner: code-tester

Unit tests for src/rag/query.py.

LightRAG is never loaded: we patch 'src.rag.query.get_rag' to return the
mock_rag fixture, and pre-populate sys.modules with stub lightrag entries so
that the module-level imports in query.py and indexer.py do not trigger real
LightRAG initialisation.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Stub lightrag before any project import can pull the real package.
# ---------------------------------------------------------------------------

def _install_lightrag_stubs() -> None:
    """Insert minimal stub modules for lightrag so imports don't fail."""
    if "lightrag" in sys.modules:
        return  # already stubbed or available

    lightrag_mod = types.ModuleType("lightrag")

    class _QueryParam:  # noqa: D401
        """Minimal stub for lightrag.QueryParam."""
        def __init__(self, mode: str = "hybrid", **kwargs):
            self.mode = mode

    class _LightRAG:
        """Minimal stub for lightrag.LightRAG."""
        def __init__(self, **kwargs):
            pass

        async def initialize_storages(self):
            pass

        async def aquery(self, question: str, param=None):
            return ""

        async def ainsert(self, text, ids=None):
            return "stub-id"

    lightrag_mod.QueryParam = _QueryParam
    lightrag_mod.LightRAG = _LightRAG

    lightrag_utils = types.ModuleType("lightrag.utils")

    class _EmbeddingFunc:
        def __init__(self, **kwargs):
            pass

    lightrag_utils.EmbeddingFunc = _EmbeddingFunc

    sys.modules["lightrag"] = lightrag_mod
    sys.modules["lightrag.utils"] = lightrag_utils


def _install_openai_stub() -> None:
    """Insert a minimal stub for the openai package so llm_backend.py can be imported."""
    if "openai" in sys.modules:
        return

    openai_mod = types.ModuleType("openai")

    class _AsyncOpenAI:
        def __init__(self, **kwargs):
            pass

    openai_mod.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai_mod


def _install_src_rag_stubs() -> None:
    """Pre-populate src.rag.indexer in sys.modules with a lightweight stub.

    query.py does ``from src.rag.indexer import get_rag`` at import time.
    The real indexer pulls in LightRAG, the LLM backend, and the embedding
    model.  By registering a stub *before* the first import of src.rag.query
    we prevent all of that from loading.
    """
    if "src.rag.indexer" in sys.modules:
        return

    indexer_stub = types.ModuleType("src.rag.indexer")

    async def _stub_get_rag():
        return MagicMock()

    indexer_stub.get_rag = _stub_get_rag
    sys.modules["src.rag.indexer"] = indexer_stub


_install_lightrag_stubs()
_install_openai_stub()
_install_src_rag_stubs()

# Now it is safe to import the project modules.
from src.rag.query import query, VALID_MODES  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# query() — return shape
# ===========================================================================


class TestQueryReturnShape:
    """query() must return a dict with exactly the keys: answer, mode, question."""

    def test_query_returns_dict_with_answer_key(self, mock_rag: MagicMock) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?"))
        assert "answer" in result

    def test_query_returns_dict_with_mode_key(self, mock_rag: MagicMock) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?"))
        assert "mode" in result

    def test_query_returns_dict_with_question_key(self, mock_rag: MagicMock) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?"))
        assert "question" in result

    def test_query_result_has_exactly_three_keys(self, mock_rag: MagicMock) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?"))
        assert set(result.keys()) == {"answer", "mode", "question"}

    def test_query_question_field_echoes_input(self, mock_rag: MagicMock) -> None:
        question = "Define habeas corpus."
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query(question))
        assert result["question"] == question

    def test_query_answer_field_is_rag_response(self, mock_rag: MagicMock) -> None:
        mock_rag.aquery = AsyncMock(return_value="Life and liberty are protected.")
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?"))
        assert result["answer"] == "Life and liberty are protected."


# ===========================================================================
# query() — mode validation
# ===========================================================================


class TestQueryModeValidation:
    """query() must validate the mode argument before touching the RAG."""

    def test_query_invalid_mode_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _run(query("Some question", mode="turbo"))

    def test_query_invalid_mode_error_message_mentions_mode(self) -> None:
        with pytest.raises(ValueError, match="turbo"):
            _run(query("Some question", mode="turbo"))

    def test_query_invalid_mode_error_message_mentions_valid_choices(self) -> None:
        with pytest.raises(ValueError, match="hybrid"):
            _run(query("Some question", mode="bad"))

    def test_query_empty_string_mode_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _run(query("Some question", mode=""))

    def test_query_mode_uppercase_raises_value_error(self) -> None:
        # Modes are case-sensitive — "HYBRID" is not valid.
        with pytest.raises(ValueError):
            _run(query("Some question", mode="HYBRID"))

    def test_query_does_not_call_rag_when_mode_invalid(self) -> None:
        rag_mock = MagicMock()
        rag_mock.aquery = AsyncMock()
        with (
            patch("src.rag.query.get_rag", new=AsyncMock(return_value=rag_mock)),
            pytest.raises(ValueError),
        ):
            _run(query("Some question", mode="invalid"))
        rag_mock.aquery.assert_not_called()


# ===========================================================================
# query() — default mode
# ===========================================================================


class TestQueryDefaultMode:
    """query() must default to 'hybrid' when no mode is supplied."""

    def test_query_default_mode_is_hybrid(self, mock_rag: MagicMock) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?"))
        assert result["mode"] == "hybrid"

    def test_query_mode_field_reflects_explicit_local(
        self, mock_rag: MagicMock
    ) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?", mode="local"))
        assert result["mode"] == "local"

    def test_query_mode_field_reflects_explicit_global(
        self, mock_rag: MagicMock
    ) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?", mode="global"))
        assert result["mode"] == "global"

    def test_query_mode_field_reflects_explicit_naive(
        self, mock_rag: MagicMock
    ) -> None:
        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            result = _run(query("What is Article 21?", mode="naive"))
        assert result["mode"] == "naive"


# ===========================================================================
# query() — QueryParam forwarding
# ===========================================================================


class TestQueryParamForwarding:
    """query() must pass the correct mode to rag.aquery via QueryParam."""

    def test_query_passes_mode_to_aquery_param(self, mock_rag: MagicMock) -> None:
        """The QueryParam object forwarded to aquery must carry the requested mode."""
        received_params: list = []

        async def capture_aquery(question: str, param=None):
            received_params.append(param)
            return "stub answer"

        mock_rag.aquery = capture_aquery

        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            _run(query("What is Article 21?", mode="local"))

        assert len(received_params) == 1
        assert received_params[0].mode == "local"

    def test_query_passes_hybrid_mode_by_default(self, mock_rag: MagicMock) -> None:
        received_params: list = []

        async def capture_aquery(question: str, param=None):
            received_params.append(param)
            return "stub answer"

        mock_rag.aquery = capture_aquery

        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            _run(query("What is Article 21?"))

        assert received_params[0].mode == "hybrid"

    def test_query_passes_question_string_to_aquery(
        self, mock_rag: MagicMock
    ) -> None:
        received_questions: list[str] = []

        async def capture_aquery(question: str, param=None):
            received_questions.append(question)
            return "stub answer"

        mock_rag.aquery = capture_aquery
        question = "Is bail a right?"

        with patch("src.rag.query.get_rag", new=AsyncMock(return_value=mock_rag)):
            _run(query(question, mode="naive"))

        assert received_questions[0] == question


# ===========================================================================
# VALID_MODES constant
# ===========================================================================


class TestValidModes:
    """Sanity-check the VALID_MODES set exported by query.py."""

    def test_valid_modes_contains_hybrid(self) -> None:
        assert "hybrid" in VALID_MODES

    def test_valid_modes_contains_local(self) -> None:
        assert "local" in VALID_MODES

    def test_valid_modes_contains_global(self) -> None:
        assert "global" in VALID_MODES

    def test_valid_modes_contains_naive(self) -> None:
        assert "naive" in VALID_MODES

    def test_valid_modes_has_exactly_four_entries(self) -> None:
        assert len(VALID_MODES) == 4
