"""Tests for the retrieval-evaluation scorer and the context-dependent behaviours."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.rag.embedding as embedding_module
from src.evaluation.retrieval_eval import score_retrieval, summarise, wilson_interval
from src.ingestion.preprocess import clean_text
from src.rag.context import query_context


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _chunks(*ids):
    return [{"chunk_id": i, "content": "x" * 10} for i in ids]


class TestScoreRetrieval:
    def test_hit_at_rank_two(self):
        r = score_retrieval("b", "Article 21", _chunks("a", "b", "c", "d"), [])
        assert r["hit"] and r["mrr"] == 0.5 and r["precision"] == 0.25

    def test_miss_scores_zero(self):
        r = score_retrieval("z", "Article 21", _chunks("a", "b"), [])
        assert not r["hit"] and r["mrr"] == 0.0 and r["precision"] == 0.0

    def test_empty_retrieval_is_a_miss_not_a_perfect_score(self):
        r = score_retrieval("a", "X", [], [])
        assert not r["hit"] and r["context_chunks"] == 0

    def test_dumping_everything_has_full_recall_but_tiny_precision(self):
        r = score_retrieval("c5", "X", _chunks(*[f"c{i}" for i in range(200)]), [])
        assert r["hit"] and r["precision"] == 1 / 200

    def test_entity_match_is_case_and_whitespace_insensitive(self):
        r = score_retrieval("a", "Article 21", _chunks("a"), [{"entity_name": "ARTICLE   21"}])
        assert r["entity_hit"]

    def test_entity_miss(self):
        r = score_retrieval("a", "Article 21", _chunks("a"), [{"entity_name": "Section 302"}])
        assert not r["entity_hit"]


class TestSummary:
    def test_wilson_small_n_is_wide(self):
        lo, hi = wilson_interval(10, 10)
        assert lo < 0.75 and hi == 1.0  # 10/10 does NOT mean "certainly ~100%"

    def test_summarise_reports_n(self):
        rows = [score_retrieval("a", "X", _chunks("a"), []), score_retrieval("q", "X", _chunks("a"), [])]
        s = summarise(rows)
        assert s["n"] == 2 and s["hit_rate"] == 0.5


class TestEmbeddingPrefix:
    def _capture(self):
        seen: list[str] = []

        async def fake(texts):
            seen.extend(texts)
            return np.zeros((len(texts), 768), dtype=np.float32)

        return seen, fake

    def test_default_is_document_prefix(self):
        seen, fake = self._capture()
        with patch.object(embedding_module, "_encode", fake):
            _run(embedding_module.embedding_func(["hello"]))
        assert seen == ["search_document: hello"]

    def test_query_context_switches_to_query_prefix(self):
        seen, fake = self._capture()

        async def go():
            with query_context(answer=False):
                await embedding_module.embedding_func(["hello"])

        with patch.object(embedding_module, "_encode", fake):
            _run(go())
        assert seen == ["search_query: hello"]

    def test_empty_input_has_correct_2d_shape(self):
        assert _run(embedding_module.embedding_func([])).shape == (0, 768)


class TestPreprocessIdempotent:
    def test_clean_text_twice_equals_once(self):
        once = clean_text("HELD\nfoo\n1\nJUDGMENT\nbar")
        assert clean_text(once) == once


from src.evaluation.multichunk_eval import bootstrap_ci, score_multi, sign_test, summarise as summarise_multi
from src.evaluation.multichunk_generator import _is_junk as multi_is_junk


class TestMultiChunkScoring:
    def test_partial_recall_and_all_hit(self):
        r = score_multi(["a", "b", "c"], [], _chunks("x", "a", "b", "y"))
        assert abs(r["recall@5"] - 2 / 3) < 1e-9 and r["all_hit@5"] is False

    def test_all_hit_when_every_gold_chunk_retrieved(self):
        r = score_multi(["a", "b"], [], _chunks("b", "z", "a"))
        assert r["all_hit@5"] and r["recall@5"] == 1.0

    def test_recall_respects_rank_cutoff(self):
        ids = [f"c{i}" for i in range(15)] + ["gold"]
        r = score_multi(["gold"], [], _chunks(*ids))
        assert r["recall@5"] == 0.0 and r["recall@10"] == 0.0 and r["recall@20"] == 1.0

    def test_empty_retrieval_scores_zero(self):
        r = score_multi(["a"], [], [])
        assert r["recall@20"] == 0.0 and not r["all_hit@20"]


class TestPairedStats:
    def test_sign_test_clear_winner(self):
        pos, neg, p = sign_test([0.5] * 20)
        assert (pos, neg) == (20, 0) and p < 0.001

    def test_sign_test_drops_ties(self):
        pos, neg, p = sign_test([0, 0, 0])
        assert (pos, neg, p) == (0, 0, 1.0)

    def test_bootstrap_ci_contains_mean_and_is_ordered(self):
        vals = [0.0, 1.0] * 50
        lo, hi = bootstrap_ci(vals)
        assert lo <= 0.5 <= hi and lo < hi

    def test_summarise_multi_shape(self):
        rows = [score_multi(["a"], [], _chunks("a"))] * 3
        for r in rows:
            r["k"] = 2
        s = summarise_multi(rows)
        assert s["n"] == 3 and s["recall@20"] == 1.0


class TestMultiGeneratorFilters:
    def test_junk_entities_rejected(self):
        for bad in ["(3)", "[Sanjiv Khanna]x"[:3], "Supreme Court of India", "data", "x" * 90]:
            assert multi_is_junk(bad)

    def test_specific_entity_accepted(self):
        assert not multi_is_junk("Mineral Concession Rules, 1960")


from src.evaluation.rank_metrics import (average_precision_at_k, doc_coverage_at_k, first_hit_reciprocal_rank,
                                         ndcg_at_k, precision_at_k, recall_at_k)


class TestRankMetrics:
    def test_precision_counts_empty_slots_as_misses(self):
        assert precision_at_k(["a"], {"a"}, 5) == 0.2

    def test_ndcg_perfect_and_worst(self):
        assert abs(ndcg_at_k(["a", "b"], {"a", "b"}, 2) - 1.0) < 1e-9
        assert ndcg_at_k(["x", "y"], {"a"}, 2) == 0.0

    def test_ndcg_rewards_earlier_hits(self):
        assert ndcg_at_k(["a", "x", "y"], {"a"}, 3) > ndcg_at_k(["x", "y", "a"], {"a"}, 3)

    def test_average_precision(self):
        assert abs(average_precision_at_k(["a", "x", "b"], {"a", "b"}, 3) - (1 + 2 / 3) / 2) < 1e-9

    def test_mrr_first_hit(self):
        assert first_hit_reciprocal_rank(["x", "y", "a"], {"a"}) == 1 / 3
        assert first_hit_reciprocal_rank(["x"], {"a"}) == 0.0

    def test_doc_coverage(self):
        c2d = {"c1": "d1", "c2": "d2", "c3": "d1"}
        assert doc_coverage_at_k(["c1", "c3"], ["d1", "d2"], c2d, 20) == 0.5

    def test_recall_empty_gold_is_zero_not_error(self):
        assert recall_at_k(["a"], set(), 5) == 0.0

    def test_score_multi_includes_extended_metrics(self):
        r = score_multi(["a", "b"], ["d1", "d2"], _chunks("a", "x", "b"), {"a": "d1", "b": "d2", "x": "d3"})
        assert r["doc_coverage@20"] == 1.0 and r["mrr"] == 1.0 and 0 < r["ndcg@10"] <= 1.0


from src.evaluation.multichunk_judge import parse_scores, parse_yes_no


class TestJudgeParsing:
    def test_scores(self):
        assert parse_scores("accuracy: 4\ncompleteness: 2") == (4, 2)

    def test_scores_tolerant_of_markdown(self):
        assert parse_scores("**accuracy**: 5\n**completeness**: 3") == (5, 3)

    def test_scores_missing_is_none_not_zero(self):
        assert parse_scores("I cannot rate this") == (None, None)

    def test_yes_no(self):
        assert parse_yes_no("YES.") is True and parse_yes_no(" no") is False and parse_yes_no("maybe") is None
