"""
Collect index / graph / extraction statistics into reports/system_stats.json.

Covers metrics that earlier evaluations ignored: graph structure (density,
connectivity, junk entity rate), per-document indexing status, storage sizes and
the extraction A/B results. Pure local file reads; no LLM needed.

    python -m src.evaluation.system_stats
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
REPORT_DIR = PROJECT_ROOT / "reports"


def _junk(name: str) -> bool:
    n = str(name).strip()
    return len(n) > 100 or len(n) <= 2 or bool(re.fullmatch(r"[\[\(\)\]\d\s\.\-,;:]+", n))


def graph_stats() -> dict:
    import networkx as nx

    path = STORAGE_DIR / "graph_chunk_entity_relation.graphml"
    if not path.exists():
        return {"available": False}
    g = nx.read_graphml(path)
    n, m = g.number_of_nodes(), g.number_of_edges()
    deg = dict(g.degree())
    comps = [len(c) for c in nx.connected_components(g)]
    types = collections.Counter((a.get("entity_type") or "unknown").strip().lower() for _, a in g.nodes(data=True))
    top = sorted(deg.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "available": True, "nodes": n, "edges": m,
        "edges_per_node": round(m / n, 3) if n else 0,
        "avg_degree": round(2 * m / n, 2) if n else 0,
        "isolated_nodes": sum(1 for d in deg.values() if d == 0),
        "isolated_pct": round(100 * sum(1 for d in deg.values() if d == 0) / n, 1) if n else 0,
        "degree_le1_pct": round(100 * sum(1 for d in deg.values() if d <= 1) / n, 1) if n else 0,
        "connected_components": len(comps),
        "largest_component_nodes": max(comps) if comps else 0,
        "largest_component_pct": round(100 * max(comps) / n, 1) if comps and n else 0,
        "junk_entity_pct": round(100 * sum(_junk(x) for x in g.nodes()) / n, 2) if n else 0,
        "top_entity_types": types.most_common(8),
        "top_hubs": [(str(k)[:60], v) for k, v in top],
    }


def index_stats() -> dict:
    out: dict = {}
    ds_path = STORAGE_DIR / "kv_store_doc_status.json"
    if ds_path.exists():
        ds = json.loads(ds_path.read_text(encoding="utf-8"))
        out["docs_by_status"] = dict(collections.Counter(v.get("status") for v in ds.values()))
    ch_path = STORAGE_DIR / "kv_store_text_chunks.json"
    if ch_path.exists():
        ch = json.loads(ch_path.read_text(encoding="utf-8"))
        out["chunks"] = len(ch)
        toks = [c.get("tokens", 0) for c in ch.values()]
        out["avg_chunk_tokens"] = round(sum(toks) / max(1, len(toks)), 1)
        out["docs_with_chunks"] = len({c.get("full_doc_id") for c in ch.values()})
    out["storage_mb"] = {p.name: round(p.stat().st_size / 1e6, 1) for p in sorted(STORAGE_DIR.glob("*.json")) if p.stat().st_size > 5e6}
    out["storage_graphml_mb"] = round((STORAGE_DIR / "graph_chunk_entity_relation.graphml").stat().st_size / 1e6, 1) \
        if (STORAGE_DIR / "graph_chunk_entity_relation.graphml").exists() else None
    return out


def extraction_ab() -> dict:
    from src.evaluation.extraction_ab import _stats

    def load(name):
        p = STORAGE_DIR / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    configs = {
        "8B | original cap400 ctx4k": "ab_large.json",
        "1.5B | original cap400 ctx4k": "ab_small.json",
        "8B | cap2500 ctx4k": "ab_large_cap2500.json",
        "8B | cap2500 ctx8k": "ab_large_ctx8k.json",
        "1.5B | cap2500 ctx8k": "ab_small_ctx8k.json",
        "1.5B | ctx8k + lean prompt": "ab_small_lean.json",
        "1.5B | ctx8k temp0.3": "ab_small_T0.3_F0.json",
        "1.5B | ctx8k temp0.2 freq0.3": "ab_small_T0.2_F0.3.json",
        "1.5B | ctx8k freq0.5": "ab_small_T0.0_F0.5.json",
    }
    out = {}
    for label, fname in configs.items():
        d = load(fname)
        if d:
            s = _stats(d["rows"])
            s["looping_outputs"] = sum(1 for r in d["rows"] if r["raw_chars"] > 6000)
            s["chunks_with_relations"] = sum(1 for r in d["rows"] if r["relations"])
            out[label] = s
    return out


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    result = {"graph": graph_stats(), "index": index_stats(), "extraction_ab": extraction_ab()}
    (REPORT_DIR / "system_stats.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"graph": {k: v for k, v in result["graph"].items() if k not in ("top_hubs", "top_entity_types")},
                      "index": result["index"].get("docs_by_status")}, indent=1))


if __name__ == "__main__":
    main()
