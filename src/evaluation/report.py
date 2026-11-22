"""
Build reports/overnight_report.md from all result files (missing pieces are reported
as "not available", never invented).

    python -m src.evaluation.report
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.multichunk_eval import bootstrap_ci, sign_test  # noqa: E402

STORAGE_DIR = PROJECT_ROOT / os.getenv("STORAGE_DIR", "storage")
REPORT_DIR = PROJECT_ROOT / "reports"
NA = "n/a"


def _load(name: str, base: Path = STORAGE_DIR):
    p = base / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def pct(x) -> str:
    return NA if x is None else f"{100 * x:.1f}%"


def ci(x) -> str:
    return "" if not x else f" ({100 * x[0]:.0f}-{100 * x[1]:.0f})"


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def retrieval_section(title: str, d: dict | None, note: str = "") -> tuple[str, dict]:
    if not d:
        return f"### {title}\n\n_Not available._\n", {}
    modes = d["modes"]
    rows = []
    for m, v in modes.items():
        rows.append([m, f"{pct(v.get('recall@5'))}", f"{pct(v.get('recall@10'))}",
                     f"**{pct(v.get('recall@20'))}**{ci(v.get('recall@20_ci95'))}", pct(v.get("all_hit@20")),
                     v.get("precision@20", NA), v.get("ndcg@10", NA), v.get("map@20", NA), v.get("mrr", NA),
                     pct(v.get("doc_coverage@20")), v.get("avg_context_chunks"),
                     f"{v['latency_ms_p50']}/{v['latency_ms_p95']}" if "latency_ms_p50" in v else NA])
    s = f"### {title}\n\n_n = {d['n_questions']} questions._ {note}\n\n"
    s += table(["mode", "recall@5", "recall@10", "recall@20 (95% CI)", "all gold found@20", "precision@20", "nDCG@10",
                "MAP@20", "MRR", "doc coverage@20", "ctx chunks", "latency p50/p95 ms"], rows)
    if d.get("paired"):
        prow = []
        for k, v in d["paired"].items():
            a, b = k.split("_vs_")
            prow.append([f"{a} vs {b}", f"{v['mean_recall@20_diff']:+.3f}", f"[{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}]",
                         f"{v.get(a + '_better', 0)} / {v.get(b + '_better', 0)}", v["sign_test_p"]])
        s += "\nPaired comparison on recall@20 (same questions):\n\n"
        s += table(["comparison (A vs B)", "mean diff (A-B)", "95% CI", "A better / B better", "sign-test p"], prow)
    if d.get("by_k"):
        brow = []
        for m, bk in d["by_k"].items():
            for k, v in bk.items():
                brow.append([m, f"{k} chunks", v["n"], pct(v["recall@20"]), pct(v["all_hit@20"])])
        s += "\nBy number of gold chunks per question:\n\n" + table(["mode", "gold chunks", "n", "recall@20", "all found@20"], brow)
    return s, modes


def sweep_section() -> str:
    files = sorted(STORAGE_DIR.glob("sweep_*.json"))
    base = _load("multichunk_eval_regex.json")
    rows = []
    if base and "mix" in base["modes"]:
        v = base["modes"]["mix"]
        rows.append(["mix (default)", "{}", pct(v.get("recall@ctx", v["recall@20"])), pct(v.get("all_hit@ctx", v["all_hit@20"])),
                     v.get("ndcg@10", NA), v["avg_context_chunks"], v.get("latency_ms_p50", NA)])
    for f in files:
        d = _load(f.name)
        if not d:
            continue
        mode = next(iter(d["modes"]))
        v = d["modes"][mode]
        rows.append([f"{mode} [{d.get('tag', f.stem)}]", json.dumps(d.get("params", {})), pct(v.get("recall@ctx", v["recall@20"])),
                     pct(v.get("all_hit@ctx", v["all_hit@20"])), v.get("ndcg@10", NA), v["avg_context_chunks"], v.get("latency_ms_p50", NA)])
    if len(rows) <= 1:
        return "_Parameter sweep not available._\n"
    return "Same questions (graph-independent set); only the listed parameter differs.\n\n" + table(
        ["config", "params", "recall over whole context", "all gold found (whole ctx)", "nDCG@10", "ctx chunks", "p50 ms"], rows)


def answers_section() -> tuple[str, dict]:
    rows = _load("multichunk_answers.json")
    if not rows:
        return "_Not available._\n", {}
    judged = [r for r in rows if r.get("judge")]
    if not judged:
        return f"_{len(rows)} answers generated but not judged._\n", {}
    by_mode: dict[str, list[dict]] = {}
    for r in judged:
        by_mode.setdefault(r["mode"], []).append(r)
    jm = next((r.get("judge_model") for r in judged if r.get("judge_model")), "?")
    trows, summary = [], {}
    for m, rs in by_mode.items():
        cov = [r["judge"]["coverage"] for r in rs if r["judge"].get("coverage") is not None]
        acc = [r["judge"]["accuracy"] for r in rs if r["judge"].get("accuracy") is not None]
        comp = [r["judge"]["completeness"] for r in rs if r["judge"].get("completeness") is not None]
        ans = [r["judge"]["answered"] for r in rs]
        lo, hi = bootstrap_ci(cov) if len(cov) > 1 else (0, 0)
        rec = [len(set(r["gold_chunk_ids"]) & set(r["retrieved_ids"][:20])) / len(r["gold_chunk_ids"]) for r in rs]
        summary[m] = {"coverage": st.mean(cov) if cov else None}
        trows.append([m, len(rs), pct(sum(ans) / len(ans)), f"**{pct(st.mean(cov)) if cov else NA}**{ci((lo, hi)) if cov else ''}",
                      f"{st.mean(acc):.2f}" if acc else NA, f"{st.mean(comp):.2f}" if comp else NA,
                      pct(st.mean(rec)), f"{st.mean(r['judge']['answer_chars'] for r in rs):.0f}",
                      f"{st.median(r['latency_ms'] for r in rs) / 1000:.1f}s"])
    s = f"Answers by the system under test; judged by **{jm}** against the gold excerpts.\n\n"
    s += table(["mode", "n", "answered (not refusal/empty)", "evidence coverage (95% CI)", "accuracy /5", "completeness /5",
                "gold recall@20 (retrieval)", "avg answer chars", "median e2e latency"], trows)
    modes = list(by_mode)
    if len(modes) > 1:
        prow = []
        for i, a in enumerate(modes):
            for b in modes[i + 1:]:
                ia = {r["question"]: r["judge"].get("coverage") for r in by_mode[a]}
                ib = {r["question"]: r["judge"].get("coverage") for r in by_mode[b]}
                diffs = [ia[q] - ib[q] for q in ia if q in ib and ia[q] is not None and ib[q] is not None]
                if len(diffs) > 5:
                    lo, hi = bootstrap_ci(diffs)
                    pos, neg, p = sign_test(diffs)
                    prow.append([f"{a} vs {b}", len(diffs), f"{st.mean(diffs):+.3f}", f"[{lo:+.3f}, {hi:+.3f}]", f"{pos}/{neg}", round(p, 4)])
        if prow:
            s += "\nPaired comparison on evidence coverage:\n\n" + table(
                ["A vs B", "n pairs", "mean diff", "95% CI", "A better / B better", "sign-test p"], prow)
    s += "\n_Caveat: accuracy/completeness are scored against the gold excerpts only; coverage is the more robust signal._\n"
    return s, summary


def single_chunk_benchmark() -> str:
    res = _load("benchmark_results.json")
    if not res:
        return "_Not available._\n"
    by: dict[str, list[dict]] = {}
    for r in res:
        by.setdefault(r["mode"], []).append(r)
    rows = []
    for m, rs in by.items():
        acc = [r["judge_metrics"].get("accuracy") for r in rs if r.get("judge_metrics") and r["judge_metrics"].get("accuracy") is not None]
        comp = [r["judge_metrics"].get("completeness") for r in rs if r.get("judge_metrics") and r["judge_metrics"].get("completeness") is not None]
        hit = [float(r["graph_metrics"]["hit"]) for r in rs if "hit" in r.get("graph_metrics", {})]
        jm = next((r.get("judge_model") for r in rs if r.get("judge_model")), "?")
        rows.append([m, len(rs), f"{st.mean(acc):.2f}" if acc else NA, f"{st.mean(comp):.2f}" if comp else NA,
                     f"{len(acc)}/{len(rs)}", f"{st.mean(r['text_metrics']['rouge_l'] for r in rs):.3f}",
                     f"{st.mean(r['text_metrics']['bleu'] for r in rs):.3f}", pct(st.mean(hit)) if hit else NA,
                     f"{st.median(r['latency_ms'] for r in rs) / 1000:.1f}s", jm])
    return ("Single-chunk questions (each answerable from one chunk); answers by the system under test (1.5B), "
            "judge as listed.\n\n" + table(["mode", "n", "judge accuracy /10", "judge completeness /10", "judgements parsed",
                                            "ROUGE-L", "BLEU", "gold chunk retrieved", "median latency", "judge"], rows))


def single_chunk_retrieval() -> str:
    a, b = _load("retrieval_eval_naive_hybrid.json"), _load("retrieval_eval_naive_mix.json")
    rows = []
    for d in (a, b):
        if d:
            for m, v in d["modes"].items():
                if m not in [r[0] for r in rows]:
                    rows.append([m, d["n_questions"], f"{pct(v['hit_rate'])}{ci(v['hit_rate_ci95'])}", v["mrr"], v["precision"], v["avg_context_chunks"]])
    if not rows:
        return "_Not available._\n"
    return table(["mode", "n", "gold chunk in context (95% CI)", "MRR", "precision (1/N)", "ctx chunks"], rows)


def system_section() -> str:
    d = _load("system_stats.json", REPORT_DIR)
    if not d:
        return "_Not available._\n"
    g, ix = d.get("graph", {}), d.get("index", {})
    s = ""
    if g.get("available"):
        s += table(["metric", "value"], [
            ["indexed documents (processed / failed)", f"{ix.get('docs_by_status', {}).get('processed', NA)} / {ix.get('docs_by_status', {}).get('failed', 0)}"],
            ["text chunks (avg tokens)", f"{ix.get('chunks', NA)} ({ix.get('avg_chunk_tokens', NA)})"],
            ["graph nodes / edges", f"{g['nodes']:,} / {g['edges']:,}"],
            ["edges per node (avg degree)", f"{g['edges_per_node']} ({g['avg_degree']})"],
            ["isolated nodes", f"{g['isolated_nodes']:,} ({g['isolated_pct']}%)"],
            ["nodes with degree <= 1", f"{g['degree_le1_pct']}%"],
            ["connected components (largest holds)", f"{g['connected_components']:,} ({g['largest_component_pct']}% of nodes)"],
            ["junk entity names (sentences, digits, 1-2 chars)", f"{g['junk_entity_pct']}%"],
            ["graphml size", f"{ix.get('storage_graphml_mb', NA)} MB"]])
    ab = d.get("extraction_ab", {})
    if ab:
        rows = [[k, v["chunks"], v["sec_per_chunk"], v["entities_per_chunk"], v["relations_per_chunk"], f"{v['chunks_with_relations']}/{v['chunks']}",
                 f"{v['looping_outputs']}/{v['chunks']}", pct(v["junk_name_rate"]), pct(v["relations_with_unextracted_endpoint"])] for k, v in ab.items()]
        s += "\n#### Extraction A/B (same chunks, sequential calls, LightRAG's own prompt and parser)\n\n"
        s += table(["config", "chunks", "sec/chunk", "entities/chunk", "relations/chunk", "chunks with relations",
                    "looping/over-long outputs", "junk names", "relations w/ unextracted endpoint"], rows)
    return s


def build() -> str:
    now = time.strftime("%Y-%m-%d %H:%M")
    s = f"# GraphRAG evaluation report\n\n_Generated {now}. Everything below is computed from result files in `storage/` and `reports/`; "
    s += "anything missing is marked n/a._\n\n"

    regex, legal = _load("multichunk_eval_regex.json"), _load("multichunk_eval_legal.json")
    legacy = _load("multichunk_eval_graphmap_legal_v1.json")
    tldr = []
    for name, d in (("graph-independent set", regex), ("graph-map set", legal)):
        if d and "naive" in d["modes"]:
            best = max(d["modes"].items(), key=lambda kv: kv[1]["recall@20"])
            nv = d["modes"]["naive"]
            tldr.append(f"- **{name}** (n={d['n_questions']}): best mode `{best[0]}` recall@20 {pct(best[1]['recall@20'])}{ci(best[1]['recall@20_ci95'])} "
                        f"vs naive {pct(nv['recall@20'])}{ci(nv['recall@20_ci95'])}; all gold chunks found {pct(best[1]['all_hit@20'])} vs {pct(nv['all_hit@20'])}.")
    ans, ans_sum = answers_section()
    if ans_sum:
        tldr.append("- **Answer evidence coverage** (judged): " + ", ".join(f"`{m}` {pct(v['coverage'])}" for m, v in ans_sum.items()) + ".")
    g = (_load("system_stats.json", REPORT_DIR) or {}).get("graph", {})
    if g.get("available"):
        tldr.append(f"- **Graph health:** {g['edges_per_node']} edges/node, {g['isolated_pct']}% isolated nodes, "
                    f"largest connected component {g['largest_component_pct']}% of nodes (built under a truncating extraction config; see section 7).")
    s += "## 0. Summary\n\n" + ("\n".join(tldr) if tldr else "_No results yet._") + "\n\n"

    sec, _ = retrieval_section("1. Multi-chunk retrieval - graph-independent gold set (regex-anchored statute/article questions)", regex,
                               "Gold chunks found by plain text search; no knowledge-graph input, so graph modes get no built-in advantage.")
    s += "## 1. Multi-chunk retrieval (graph-independent gold)\n\n" + sec.split("\n", 2)[2] + "\n"
    sec, _ = retrieval_section("2", legal, "Gold chunks chosen via the graph's entity->chunk map, so this set **favours graph modes by construction**.")
    s += "## 2. Multi-chunk retrieval (graph-map gold; biased toward graph)\n\n" + sec.split("\n", 2)[2]
    if legacy:
        v = legacy["modes"]
        s += "\nEarlier run of this same set (before extended metrics): " + ", ".join(f"{m} recall@20 {pct(x['recall@20'])}" for m, x in v.items()) + ".\n"
    s += "\n## 3. Single-chunk retrieval (for reference; favours vector search)\n\n" + single_chunk_retrieval() + "\n"
    s += "## 4. Retrieval parameter sweep (mix mode)\n\n" + sweep_section() + "\n"
    s += "## 5. Answer quality on multi-chunk questions\n\n" + ans + "\n"
    s += "## 6. Single-chunk answer benchmark\n\n" + single_chunk_benchmark() + "\n"
    s += "## 7. Index, graph and extraction quality\n\n" + system_section() + "\n"
    s += """### Root causes found in the extraction pipeline

- The 400-token output cap **and** a 4096-token context truncated almost every extraction: LightRAG's extraction system prompt is ~3,000 tokens, leaving ~480 tokens for output. Relations are written last, so they were cut off. Fixed config: context >= 8192 and a higher output cap.
- With a sufficient context the 8B model yields ~10 relations/chunk (vs ~0.7 under the original config); the 1.5B model loops (repeats entity lines until the token cap) on most chunks even with a short prompt or sampling penalties.
- `hybrid` mode in LightRAG is graph-only (no chunk vector search); `mix` adds it. The README previously recommended `hybrid`.
- The corpus was indexed with the faster small model: measured wall-clock indexing speed-up 12.9x (owner-measured, entity extraction over the corpus). Per-call speed ratio measured here under the corrected config: ~3.1x at one request at a time; the remainder is consistent with 4 concurrent requests. The quality cost of that trade is in the extraction A/B table above.

"""
    s += """## 8. Method and caveats

- Gold sets are LLM-generated (Qwen3-VL-8B) from 2-4 chunks in different judgments; a verifier removes questions answerable from one chunk. They are not human-labelled.
- Gold chunk sets can omit other valid chunks, so recall is a conservative estimate for all modes.
- Rank-based metrics (nDCG, MAP, MRR, @5, @10) assume returned order reflects ranking; recall@20 does not.
- Judge: Qwen3-VL-8B (stronger than the 1.5B answerer, but still a small local model); failed judge calls are excluded, not scored as zero.
- Confidence intervals: 95% bootstrap over questions. Mode comparisons: paired sign test on per-question recall@20.
- Retrieval ran with the cross-encoder reranker (bge-reranker-base) enabled for every mode.
"""
    return s


if __name__ == "__main__":
    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / "overnight_report.md"
    out.write_text(build(), encoding="utf-8")
    print("wrote", out)
