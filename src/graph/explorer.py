"""
Phase 4 — Indexing Pipeline
Owner: ml-pipeline-engineer

NetworkX graph inspection utilities for the LightRAG knowledge graph.

LightRAG writes a GraphML file at:
    <STORAGE_DIR>/graph_chunk_entity_relation.graphml

This module provides:
    load_graph(storage_dir)          — load the GraphML into a NetworkX graph
    print_stats(G)                   — print node/edge counts and top entities
    get_ego_graph(G, entity, radius) — return the subgraph around a named entity

CLI usage:
    # Print graph statistics
    python src/graph/explorer.py

    # Print ego-graph info around a specific entity
    python src/graph/explorer.py --entity "Article 21"

    # Use a non-default storage directory
    python src/graph/explorer.py --storage-dir path/to/storage
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_DIR = PROJECT_ROOT / "storage"
GRAPHML_FILENAME = "graph_chunk_entity_relation.graphml"

# Edge attribute that LightRAG uses to store relationship keywords/type
_EDGE_KEYWORD_ATTR = "keywords"


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def load_graph(storage_dir: Path | str) -> nx.Graph:
    """Load the LightRAG GraphML file into a NetworkX graph.

    Args:
        storage_dir: Path to the LightRAG working/storage directory.
                     The GraphML file is expected at
                     ``<storage_dir>/graph_chunk_entity_relation.graphml``.

    Returns:
        Loaded NetworkX graph (undirected or directed, as LightRAG wrote it).

    Raises:
        FileNotFoundError: If the GraphML file does not exist yet.
    """
    storage_dir = Path(storage_dir)
    # If the user passed the full file path instead of just the directory
    if storage_dir.suffix == ".graphml":
        graphml_path = storage_dir
    else:
        graphml_path = storage_dir / GRAPHML_FILENAME

    if not graphml_path.exists():
        raise FileNotFoundError(
            f"GraphML file not found: {graphml_path}\n"
            "Run index_documents.py first to populate the graph."
        )

    G = nx.read_graphml(graphml_path)
    return G


def print_stats(G: nx.Graph) -> None:
    """Print a summary of the graph structure to stdout.

    Outputs:
        - Node count and edge count
        - Top 10 entities by degree (most connected nodes)
        - Top 5 most common relationship types (from edge keyword attributes)

    Args:
        G: NetworkX graph loaded via :func:`load_graph`.
    """
    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()

    print(f"\nGraph Statistics")
    print("=" * 50)
    print(f"  Nodes : {node_count:,}")
    print(f"  Edges : {edge_count:,}")

    # Top 10 entities by degree
    print("\nTop 10 Entities by Degree (most connected):")
    print("-" * 50)
    degree_sorted = sorted(G.degree(), key=lambda kv: kv[1], reverse=True)
    for rank, (entity, degree) in enumerate(degree_sorted[:10], start=1):
        print(f"  {rank:2}. {entity!r}  (degree {degree})")

    # Top 5 relationship types from edge keyword attributes
    print("\nTop 5 Relationship Types (by edge keyword frequency):")
    print("-" * 50)
    keyword_counter: Counter[str] = Counter()
    for _u, _v, data in G.edges(data=True):
        raw = data.get(_EDGE_KEYWORD_ATTR, "")
        if raw:
            # LightRAG may store multiple keywords comma-separated
            for kw in str(raw).split(","):
                kw = kw.strip()
                if kw:
                    keyword_counter[kw] += 1

    if keyword_counter:
        for rank, (kw, count) in enumerate(keyword_counter.most_common(5), start=1):
            print(f"  {rank}. {kw!r}  ({count} edges)")
    else:
        print(f"  No '{_EDGE_KEYWORD_ATTR}' edge attribute found in graph.")
        print("  Available edge attributes:", _sample_edge_attrs(G))

    print()


def _sample_edge_attrs(G: nx.Graph) -> list[str]:
    """Return the attribute keys from the first edge, for diagnostics.

    Args:
        G: NetworkX graph.

    Returns:
        List of attribute key names from the first edge, or empty list.
    """
    for _u, _v, data in G.edges(data=True):
        return list(data.keys())
    return []


def get_ego_graph(
    G: nx.Graph,
    entity_name: str,
    radius: int = 2,
) -> nx.Graph:
    """Return the subgraph (ego graph) centered on *entity_name*.

    The ego graph contains *entity_name* and all nodes within *radius* hops,
    plus the edges between them.

    Args:
        G:           Full NetworkX graph.
        entity_name: Node ID / entity name to center on.
        radius:      Number of hops to expand from the center node.

    Returns:
        NetworkX subgraph (view) for the ego neighborhood.

    Raises:
        KeyError: If *entity_name* is not found in the graph.
    """
    if entity_name not in G:
        # Try case-insensitive lookup
        matches = [n for n in G.nodes() if str(n).lower() == entity_name.lower()]
        if matches:
            entity_name = matches[0]
        else:
            raise KeyError(
                f"Entity {entity_name!r} not found in graph. "
                f"Graph has {G.number_of_nodes():,} nodes."
            )

    ego = nx.ego_graph(G, entity_name, radius=radius)
    return ego


def print_ego_stats(ego: nx.Graph, entity_name: str, radius: int) -> None:
    """Print a summary of an ego graph to stdout.

    Args:
        ego:         Ego subgraph returned by :func:`get_ego_graph`.
        entity_name: The central entity name.
        radius:      The hop radius used.
    """
    center_degree = ego.degree(entity_name)
    neighbor_nodes = [n for n in ego.nodes() if n != entity_name]

    print(f"\nEgo Graph: {entity_name!r}  (radius={radius})")
    print("=" * 50)
    print(f"  Center node degree (in full graph context): shown below")
    print(f"  Subgraph nodes     : {ego.number_of_nodes():,}")
    print(f"  Subgraph edges     : {ego.number_of_edges():,}")
    print(f"  Direct neighbors   : {center_degree}")

    # List immediate neighbors (radius=1 nodes)
    direct = sorted(ego.neighbors(entity_name), key=lambda n: ego.degree(n), reverse=True)
    print(f"\n  Direct neighbors (sorted by subgraph degree):")
    for n in direct[:20]:
        print(f"    - {n!r}  (degree {ego.degree(n)})")
    if len(direct) > 20:
        print(f"    ... and {len(direct) - 20} more")

    # Edge keywords within the ego graph
    keyword_counter: Counter[str] = Counter()
    for _u, _v, data in ego.edges(data=True):
        raw = data.get(_EDGE_KEYWORD_ATTR, "")
        if raw:
            for kw in str(raw).split(","):
                kw = kw.strip()
                if kw:
                    keyword_counter[kw] += 1

    if keyword_counter:
        print(f"\n  Top relationship types within subgraph:")
        for kw, count in keyword_counter.most_common(5):
            print(f"    {kw!r}  ({count} edges)")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect the LightRAG knowledge graph.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/graph/explorer.py\n"
            "  python src/graph/explorer.py --entity \"Article 21\"\n"
            "  python src/graph/explorer.py --entity \"Article 21\" --radius 1\n"
        ),
    )
    parser.add_argument(
        "--storage-dir",
        type=Path,
        default=DEFAULT_STORAGE_DIR,
        metavar="DIR",
        help=f"LightRAG storage directory. Default: {DEFAULT_STORAGE_DIR}",
    )
    parser.add_argument(
        "--entity",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "Entity name to inspect as ego graph. "
            "When omitted, only global stats are printed."
        ),
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=2,
        metavar="N",
        help="Hop radius for ego graph expansion. Default: 2.",
    )
    return parser


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    storage_dir: Path = args.storage_dir.resolve()

    try:
        G = load_graph(storage_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print_stats(G)

    if args.entity is not None:
        try:
            ego = get_ego_graph(G, args.entity, radius=args.radius)
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print_ego_stats(ego, args.entity, radius=args.radius)


if __name__ == "__main__":
    main()
