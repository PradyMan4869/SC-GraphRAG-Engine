"""
Phase 7 — Testing
Owner: code-tester

Unit tests for src/rag/embedding.py.

The SentenceTransformer model is never loaded — _encode is patched at the
module level so no CUDA device or model weights are required.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.rag.embedding as embedding_module
from src.rag.embedding import (
    EMBEDDING_DIM,
    embedding_func,
    embed_for_query,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously (compatible with Python 3.10+)."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fake_encode(texts: list[str]) -> np.ndarray:
    """Return a deterministic dummy embedding for each text (dim=768)."""
    return np.array([[float(i) / 768] * 768 for i, _ in enumerate(texts)], dtype=np.float32)


# ===========================================================================
# EMBEDDING_DIM constant
# ===========================================================================


class TestEmbeddingDimConstant:
    def test_embedding_dim_is_768(self) -> None:
        assert EMBEDDING_DIM == 768

    def test_embedding_dim_is_int(self) -> None:
        assert isinstance(EMBEDDING_DIM, int)


# ===========================================================================
# embedding_func — document prefix
# ===========================================================================


class TestEmbeddingFunc:
    """embedding_func should prepend 'search_document: ' and return nested lists."""

    def test_embedding_func_adds_document_prefix_to_each_text(self) -> None:
        captured: list[list[str]] = []

        async def capturing_encode(texts: list[str]) -> np.ndarray:
            captured.append(list(texts))
            return await _fake_encode(texts)

        with patch.object(embedding_module, "_encode", capturing_encode):
            _run(embedding_func(["Article 21", "Article 32"]))

        assert len(captured) == 1
        assert captured[0][0] == "search_document: Article 21"
        assert captured[0][1] == "search_document: Article 32"

    def test_embedding_func_adds_prefix_to_single_text(self) -> None:
        captured: list[list[str]] = []

        def capturing_encode(texts: list[str]) -> list[list[float]]:
            captured.append(list(texts))
            return _fake_encode(texts)

        with patch.object(embedding_module, "_encode", capturing_encode):
            _run(embedding_func(["Due process of law"]))

        assert captured[0][0] == "search_document: Due process of law"

    def test_embedding_func_returns_nested_list(self) -> None:
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embedding_func(["test"]))

        assert isinstance(result, np.ndarray)
        assert result.ndim == 2
        assert isinstance(result[0][0], np.float32)

    def test_embedding_func_output_length_matches_input_length(self) -> None:
        texts = ["text one", "text two", "text three"]
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embedding_func(texts))

        assert len(result) == len(texts)

    def test_embedding_func_each_vector_has_correct_dimension(self) -> None:
        texts = ["some judgment text"]
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embedding_func(texts))

        assert len(result[0]) == 768

    def test_embedding_func_empty_list_returns_empty_list(self) -> None:
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embedding_func([]))

        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_embedding_func_does_not_double_prefix_if_called_twice(self) -> None:
        """Calling embedding_func twice on the same text should not stack prefixes."""
        captured: list[list[str]] = []

        async def capturing_encode(texts: list[str]) -> np.ndarray:
            captured.append(list(texts))
            return await _fake_encode(texts)

        with patch.object(embedding_module, "_encode", capturing_encode):
            _run(embedding_func(["Article 21"]))
            _run(embedding_func(["Article 21"]))

        for call_args in captured:
            assert call_args[0].count("search_document:") == 1


# ===========================================================================
# embed_for_query — query prefix
# ===========================================================================


class TestEmbedForQuery:
    """embed_for_query should prepend 'search_query: ' and return nested lists."""

    def test_embed_for_query_adds_query_prefix_to_each_text(self) -> None:
        captured: list[list[str]] = []

        async def capturing_encode(texts: list[str]) -> np.ndarray:
            captured.append(list(texts))
            return await _fake_encode(texts)

        with patch.object(embedding_module, "_encode", capturing_encode):
            _run(embed_for_query(["What is habeas corpus?"]))

        assert captured[0][0] == "search_query: What is habeas corpus?"

    def test_embed_for_query_prefix_differs_from_document_prefix(self) -> None:
        doc_captured: list[str] = []
        query_captured: list[str] = []

        async def doc_encode(texts: list[str]) -> np.ndarray:
            doc_captured.extend(texts)
            return await _fake_encode(texts)

        async def query_encode(texts: list[str]) -> np.ndarray:
            query_captured.extend(texts)
            return await _fake_encode(texts)

        with patch.object(embedding_module, "_encode", doc_encode):
            _run(embedding_func(["test text"]))

        with patch.object(embedding_module, "_encode", query_encode):
            _run(embed_for_query(["test text"]))

        assert doc_captured[0].startswith("search_document: ")
        assert query_captured[0].startswith("search_query: ")
        assert doc_captured[0] != query_captured[0]

    def test_embed_for_query_returns_nested_list(self) -> None:
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embed_for_query(["test query"]))

        assert isinstance(result, np.ndarray)
        assert result.ndim == 2
        assert isinstance(result[0][0], np.float32)

    def test_embed_for_query_output_length_matches_input_length(self) -> None:
        texts = ["query one", "query two"]
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embed_for_query(texts))

        assert len(result) == len(texts)

    def test_embed_for_query_each_vector_has_correct_dimension(self) -> None:
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embed_for_query(["fundamental rights"]))

        assert len(result[0]) == 768

    def test_embed_for_query_empty_list_returns_empty_list(self) -> None:
        with patch.object(embedding_module, "_encode", _fake_encode):
            result = _run(embed_for_query([]))

        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_embed_for_query_multiple_texts_all_prefixed(self) -> None:
        captured: list[list[str]] = []

        async def capturing_encode(texts: list[str]) -> np.ndarray:
            captured.append(list(texts))
            return await _fake_encode(texts)

        questions = ["What is Article 21?", "Define habeas corpus.", "Who may file PIL?"]
        with patch.object(embedding_module, "_encode", capturing_encode):
            _run(embed_for_query(questions))

        for sent_text in captured[0]:
            assert sent_text.startswith("search_query: ")
