"""
Phase 7 — Testing
Owner: code-tester

Unit tests for src/graph/explorer.py.

All tests use in-memory NetworkX graphs — no GraphML files are written to disk
except in the load_graph tests, which use pytest's tmp_path fixture.
"""
from __future__ import annotations

import sys
import io
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.graph.explorer import (
    GRAPHML_FILENAME,
    get_ego_graph,
    load_graph,
    print_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_graphml(directory: Path, G: nx.Graph) -> Path:
    """Serialise *G* as GraphML into *directory* and return the file path."""
    path = directory / GRAPHML_FILENAME
    nx.write_graphml(G, str(path))
    return path


def _small_graph() -> nx.Graph:
    """Return a small undirected graph for general testing."""
    G = nx.Graph()
    G.add_node("Article 21", entity_type="constitutional_provision")
    G.add_node("Supreme Court", entity_type="institution")
    G.add_node("Habeas Corpus", entity_type="legal_concept")
    G.add_node("Right to Life", entity_type="fundamental_right")
    G.add_edge("Article 21", "Supreme Court", keywords="constitutional, fundamental")
    G.add_edge("Article 21", "Habeas Corpus", keywords="remedy, writ")
    G.add_edge("Article 21", "Right to Life", keywords="life, liberty")
    G.add_edge("Supreme Court", "Habeas Corpus", keywords="jurisdiction")
    return G


# ===========================================================================
# load_graph
# ===========================================================================


class TestLoadGraph:
    """load_graph must raise FileNotFoundError when the GraphML file is absent."""

    def test_load_graph_file_not_found_raises(self, tmp_path: Path) -> None:
        # Arrange: storage_dir exists but contains no GraphML file
        storage_dir = tmp_path / "empty_storage"
        storage_dir.mkdir()

        # Act + Assert
        with pytest.raises(FileNotFoundError):
            load_graph(storage_dir)

    def test_load_graph_error_message_contains_path(self, tmp_path: Path) -> None:
        storage_dir = tmp_path / "no_graph"
        storage_dir.mkdir()

        with pytest.raises(FileNotFoundError, match=GRAPHML_FILENAME):
            load_graph(storage_dir)

    def test_load_graph_accepts_string_path(self, tmp_path: Path) -> None:
        """load_graph should coerce a str to Path without raising."""
        G = _small_graph()
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        _write_graphml(storage_dir, G)

        loaded = load_graph(str(storage_dir))
        assert loaded.number_of_nodes() == G.number_of_nodes()

    def test_load_graph_returns_networkx_graph(self, tmp_path: Path) -> None:
        G = _small_graph()
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        _write_graphml(storage_dir, G)

        loaded = load_graph(storage_dir)
        assert isinstance(loaded, nx.Graph)

    def test_load_graph_preserves_node_count(self, tmp_path: Path) -> None:
        G = _small_graph()
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        _write_graphml(storage_dir, G)

        loaded = load_graph(storage_dir)
        assert loaded.number_of_nodes() == G.number_of_nodes()

    def test_load_graph_preserves_edge_count(self, tmp_path: Path) -> None:
        G = _small_graph()
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()
        _write_graphml(storage_dir, G)

        loaded = load_graph(storage_dir)
        assert loaded.number_of_edges() == G.number_of_edges()


# ===========================================================================
# print_stats
# ===========================================================================


class TestPrintStats:
    """print_stats must not crash regardless of graph content."""

    def test_print_stats_empty_graph_does_not_raise(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        G = nx.Graph()
        print_stats(G)  # must not raise

    def test_print_stats_empty_graph_reports_zero_nodes(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        G = nx.Graph()
        print_stats(G)
        out = capsys.readouterr().out
        assert "0" in out

    def test_print_stats_with_nodes_reports_correct_count(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        G = _small_graph()
        print_stats(G)
        out = capsys.readouterr().out
        # 4 nodes in _small_graph
        assert "4" in out

    def test_print_stats_with_nodes_reports_edge_count(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        G = _small_graph()
        print_stats(G)
        out = capsys.readouterr().out
        # 4 edges in _small_graph
        assert "4" in out

    def test_print_stats_outputs_section_headers(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        G = _small_graph()
        print_stats(G)
        out = capsys.readouterr().out
        assert "Graph Statistics" in out

    def test_print_stats_graph_with_no_keyword_attr_does_not_raise(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Edges without 'keywords' attribute must be handled gracefully."""
        G = nx.Graph()
        G.add_node("A")
        G.add_node("B")
        G.add_edge("A", "B")  # no 'keywords' attribute
        print_stats(G)  # must not raise

    def test_print_stats_single_node_no_edges_does_not_raise(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        G = nx.Graph()
        G.add_node("Lonely Node")
        print_stats(G)  # must not raise


# ===========================================================================
# get_ego_graph
# ===========================================================================


class TestGetEgoGraph:
    """get_ego_graph must return the correct subgraph or raise KeyError."""

    def test_get_ego_graph_entity_found_contains_center(self) -> None:
        G = _small_graph()
        ego = get_ego_graph(G, "Article 21", radius=1)
        assert "Article 21" in ego.nodes()

    def test_get_ego_graph_entity_found_returns_nx_graph(self) -> None:
        G = _small_graph()
        ego = get_ego_graph(G, "Article 21", radius=1)
        assert isinstance(ego, nx.Graph)

    def test_get_ego_graph_includes_direct_neighbours(self) -> None:
        G = _small_graph()
        ego = get_ego_graph(G, "Article 21", radius=1)
        # All three neighbours of "Article 21" must appear in radius=1 ego graph.
        assert "Supreme Court" in ego.nodes()
        assert "Habeas Corpus" in ego.nodes()
        assert "Right to Life" in ego.nodes()

    def test_get_ego_graph_radius_0_contains_only_center(self) -> None:
        G = _small_graph()
        ego = get_ego_graph(G, "Article 21", radius=0)
        assert set(ego.nodes()) == {"Article 21"}

    def test_get_ego_graph_radius_2_includes_second_hop(self) -> None:
        # Build a linear chain: A -- B -- C -- D
        G = nx.Graph()
        G.add_edge("A", "B")
        G.add_edge("B", "C")
        G.add_edge("C", "D")

        ego = get_ego_graph(G, "A", radius=2)
        # Radius=2 should include A, B, C but not D
        assert "A" in ego.nodes()
        assert "B" in ego.nodes()
        assert "C" in ego.nodes()
        assert "D" not in ego.nodes()

    def test_get_ego_graph_case_insensitive_lookup(self) -> None:
        G = _small_graph()
        # "article 21" (all lower) should resolve to "Article 21"
        ego = get_ego_graph(G, "article 21", radius=1)
        # The returned subgraph should contain the canonical node name
        node_names_lower = [str(n).lower() for n in ego.nodes()]
        assert "article 21" in node_names_lower

    def test_get_ego_graph_case_insensitive_returns_subgraph(self) -> None:
        G = _small_graph()
        ego = get_ego_graph(G, "SUPREME COURT", radius=1)
        assert isinstance(ego, nx.Graph)

    def test_get_ego_graph_case_insensitive_mixed_case(self) -> None:
        G = _small_graph()
        # "hAbEaS cOrPuS" should still match "Habeas Corpus"
        ego = get_ego_graph(G, "hAbEaS cOrPuS", radius=1)
        node_names_lower = [str(n).lower() for n in ego.nodes()]
        assert "habeas corpus" in node_names_lower

    def test_get_ego_graph_entity_not_found_raises_key_error(self) -> None:
        G = _small_graph()
        with pytest.raises(KeyError):
            get_ego_graph(G, "Nonexistent Entity XYZ", radius=1)

    def test_get_ego_graph_not_found_error_message_contains_entity_name(
        self,
    ) -> None:
        G = _small_graph()
        with pytest.raises(KeyError, match="Missing Entity"):
            get_ego_graph(G, "Missing Entity", radius=1)

    def test_get_ego_graph_empty_graph_raises_key_error(self) -> None:
        G = nx.Graph()
        with pytest.raises(KeyError):
            get_ego_graph(G, "Article 21", radius=1)

    def test_get_ego_graph_subgraph_node_count_is_bounded_by_full_graph(
        self,
    ) -> None:
        G = _small_graph()
        ego = get_ego_graph(G, "Article 21", radius=2)
        assert ego.number_of_nodes() <= G.number_of_nodes()
