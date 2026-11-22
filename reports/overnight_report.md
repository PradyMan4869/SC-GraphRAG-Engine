# GraphRAG evaluation report

_Generated 2026-11-22 00:26. Everything below is computed from result files in `storage/` and `reports/`; anything missing is marked n/a._

## 0. Summary

- **graph-independent set** (n=106): best mode `mix` recall@20 58.9% (53-65) vs naive 53.3% (47-60); all gold chunks found 28.3% vs 23.6%.
- **graph-map set** (n=207): best mode `mix` recall@20 70.5% (66-75) vs naive 54.4% (50-59); all gold chunks found 46.4% vs 24.2%.
- **Answer evidence coverage** (judged): `naive` 39.8%, `mix` 28.9%, `hybrid` 27.5%.
- **Graph health:** 0.245 edges/node, 74.1% isolated nodes, largest connected component 14.6% of nodes (built under a truncating extraction config; see section 7).

## 1. Multi-chunk retrieval (graph-independent gold)

_n = 106 questions._ Gold chunks found by plain text search; no knowledge-graph input, so graph modes get no built-in advantage.

| mode | recall@5 | recall@10 | recall@20 (95% CI) | all gold found@20 | precision@20 | nDCG@10 | MAP@20 | MRR | doc coverage@20 | ctx chunks | latency p50/p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| naive | 43.6% | 49.0% | **53.3%** (47-60) | 23.6% | 0.062 | 0.444 | 0.351 | 0.582 | 82.4% | 20.0 | 133/147 |
| mix | 46.6% | 52.1% | **58.9%** (53-65) | 28.3% | 0.069 | 0.462 | 0.372 | 0.584 | 84.4% | 20.0 | 3262/4062 |
| hybrid | 23.9% | 26.8% | **27.8%** (22-34) | 5.7% | 0.033 | 0.248 | 0.187 | 0.348 | 74.8% | 20.0 | 3231/4064 |
| local | 16.7% | 18.5% | **19.6%** (15-25) | 2.8% | 0.023 | 0.181 | 0.14 | 0.261 | 64.9% | 20.0 | 2795/3453 |
| global | 18.6% | 21.3% | **22.2%** (18-28) | 2.8% | 0.026 | 0.202 | 0.148 | 0.304 | 68.2% | 20.0 | 2942/3478 |

Paired comparison on recall@20 (same questions):

| comparison (A vs B) | mean diff (A-B) | 95% CI | A better / B better | sign-test p |
|---|---|---|---|---|
| naive vs mix | -0.056 | [-0.094, -0.019] | 5 / 19 | 0.0066 |
| naive vs hybrid | +0.256 | [+0.180, +0.326] | 57 / 10 | 0.0 |
| naive vs local | +0.337 | [+0.267, +0.403] | 69 / 4 | 0.0 |
| naive vs global | +0.311 | [+0.233, +0.387] | 65 / 10 | 0.0 |
| mix vs hybrid | +0.311 | [+0.254, +0.371] | 64 / 1 | 0.0 |
| mix vs local | +0.393 | [+0.333, +0.454] | 74 / 0 | 0.0 |
| mix vs global | +0.366 | [+0.300, +0.431] | 68 / 1 | 0.0 |
| hybrid vs local | +0.082 | [+0.036, +0.128] | 24 / 4 | 0.0002 |
| hybrid vs global | +0.055 | [+0.022, +0.088] | 15 / 1 | 0.0005 |
| local vs global | -0.027 | [-0.080, +0.026] | 15 / 21 | 0.405 |

By number of gold chunks per question:

| mode | gold chunks | n | recall@20 | all found@20 |
|---|---|---|---|---|
| naive | 2 chunks | 77 | 53.9% | 28.6% |
| naive | 3 chunks | 20 | 55.0% | 15.0% |
| naive | 4 chunks | 9 | 44.4% | 0.0% |
| mix | 2 chunks | 77 | 59.1% | 33.8% |
| mix | 3 chunks | 20 | 63.3% | 20.0% |
| mix | 4 chunks | 9 | 47.2% | 0.0% |
| hybrid | 2 chunks | 77 | 27.3% | 7.8% |
| hybrid | 3 chunks | 20 | 33.3% | 0.0% |
| hybrid | 4 chunks | 9 | 19.4% | 0.0% |
| local | 2 chunks | 77 | 20.1% | 3.9% |
| local | 3 chunks | 20 | 20.0% | 0.0% |
| local | 4 chunks | 9 | 13.9% | 0.0% |
| global | 2 chunks | 77 | 22.1% | 2.6% |
| global | 3 chunks | 20 | 26.7% | 5.0% |
| global | 4 chunks | 9 | 13.9% | 0.0% |

## 2. Multi-chunk retrieval (graph-map gold; biased toward graph)

_n = 207 questions._ Gold chunks chosen via the graph's entity->chunk map, so this set **favours graph modes by construction**.

| mode | recall@5 | recall@10 | recall@20 (95% CI) | all gold found@20 | precision@20 | nDCG@10 | MAP@20 | MRR | doc coverage@20 | ctx chunks | latency p50/p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| naive | 41.8% | 50.6% | **54.4%** (50-59) | 24.2% | 0.063 | 0.441 | 0.335 | 0.595 | 76.9% | 20.0 | 133/145 |
| mix | 46.7% | 61.0% | **70.5%** (66-75) | 46.4% | 0.082 | 0.501 | 0.392 | 0.624 | 83.5% | 20.0 | 1450/2015 |
| hybrid | 45.9% | 54.3% | **59.1%** (54-64) | 38.6% | 0.07 | 0.479 | 0.39 | 0.595 | 81.4% | 20.0 | 1377/1959 |

Paired comparison on recall@20 (same questions):

| comparison (A vs B) | mean diff (A-B) | 95% CI | A better / B better | sign-test p |
|---|---|---|---|---|
| naive vs mix | -0.161 | [-0.200, -0.125] | 10 / 78 | 0.0 |
| naive vs hybrid | -0.047 | [-0.102, +0.008] | 52 / 73 | 0.0732 |
| mix vs hybrid | +0.114 | [+0.079, +0.151] | 54 / 9 | 0.0 |

By number of gold chunks per question:

| mode | gold chunks | n | recall@20 | all found@20 |
|---|---|---|---|---|
| naive | 2 chunks | 137 | 62.4% | 35.8% |
| naive | 3 chunks | 46 | 42.8% | 2.2% |
| naive | 4 chunks | 24 | 31.2% | 0.0% |
| mix | 2 chunks | 137 | 78.8% | 62.0% |
| mix | 3 chunks | 46 | 58.0% | 21.7% |
| mix | 4 chunks | 24 | 46.9% | 4.2% |
| hybrid | 2 chunks | 137 | 63.9% | 49.6% |
| hybrid | 3 chunks | 46 | 52.9% | 21.7% |
| hybrid | 4 chunks | 24 | 43.8% | 8.3% |

Earlier run of this same set (before extended metrics): naive recall@20 54.4%, mix recall@20 70.5%, hybrid recall@20 59.1%.

## 3. Single-chunk retrieval (for reference; favours vector search)

| mode | n | gold chunk in context (95% CI) | MRR | precision (1/N) | ctx chunks |
|---|---|---|---|---|---|
| naive | 300 | 87.7% (84-91) | 0.765 | 0.044 | 20.0 |
| hybrid | 300 | 63.7% (58-69) | 0.574 | 0.032 | 20.0 |
| mix | 300 | 92.7% (89-95) | 0.792 | 0.046 | 20.0 |

## 4. Retrieval parameter sweep (mix mode)

Same questions (graph-independent set); only the listed parameter differs.

| config | params | recall over whole context | all gold found (whole ctx) | nDCG@10 | ctx chunks | p50 ms |
|---|---|---|---|---|---|---|
| mix (default) | {} | 58.9% | 28.3% | 0.462 | 20.0 | 3262 |
| mix [ctk10] | {"chunk_top_k": 10} | 46.9% | 17.9% | 0.43 | 10.0 | 1377 |
| mix [ctk40] | {"chunk_top_k": 40} | 64.5% | 35.8% | 0.486 | 33.3 | 1482 |
| mix [norerank] | {"enable_rerank": false} | 45.0% | 17.9% | 0.312 | 20.0 | 330 |
| mix [topk20] | {"top_k": 20} | 58.9% | 28.3% | 0.462 | 20.0 | 1126 |
| mix [topk80] | {"top_k": 80} | 59.2% | 28.3% | 0.463 | 20.0 | 1576 |

## 5. Answer quality on multi-chunk questions

Answers by the system under test; judged by **qwen3-vl-8b-instruct** against the gold excerpts.

| mode | n | answered (not refusal/empty) | evidence coverage (95% CI) | accuracy /5 | completeness /5 | gold recall@20 (retrieval) | avg answer chars | median e2e latency |
|---|---|---|---|---|---|---|---|---|
| naive | 100 | 100.0% | **39.8%** (32-47) | 2.54 | 2.06 | 53.4% | 3656 | 7.6s |
| mix | 100 | 100.0% | **28.9%** (22-36) | 2.30 | 1.94 | 65.8% | 2944 | 11.9s |
| hybrid | 100 | 100.0% | **27.5%** (21-34) | 2.17 | 1.82 | 42.4% | 2772 | 9.4s |

Paired comparison on evidence coverage:

| A vs B | n pairs | mean diff | 95% CI | A better / B better | sign-test p |
|---|---|---|---|---|---|
| naive vs mix | 100 | +0.109 | [+0.027, +0.189] | 35/12 | 0.0011 |
| naive vs hybrid | 100 | +0.123 | [+0.038, +0.202] | 39/17 | 0.0046 |
| mix vs hybrid | 100 | +0.014 | [-0.063, +0.092] | 22/22 | 1.0 |

_Caveat: accuracy/completeness are scored against the gold excerpts only; coverage is the more robust signal._

## 6. Single-chunk answer benchmark

Single-chunk questions (each answerable from one chunk); answers by the system under test (1.5B), judge as listed.

| mode | n | judge accuracy /10 | judge completeness /10 | judgements parsed | ROUGE-L | BLEU | gold chunk retrieved | median latency | judge |
|---|---|---|---|---|---|---|---|---|---|
| naive | 60 | 6.27 | 5.62 | 60/60 | 0.298 | 0.145 | 81.7% | 4.1s | qwen3-vl-8b-instruct |
| mix | 60 | 6.10 | 5.60 | 60/60 | 0.274 | 0.118 | 90.0% | 8.8s | qwen3-vl-8b-instruct |
| hybrid | 60 | 5.35 | 4.68 | 60/60 | 0.272 | 0.114 | 63.3% | 8.4s | qwen3-vl-8b-instruct |

## 7. Index, graph and extraction quality

| metric | value |
|---|---|
| indexed documents (processed / failed) | 630 / 9 |
| text chunks (avg tokens) | 20035 (399.2) |
| graph nodes / edges | 42,790 / 10,490 |
| edges per node (avg degree) | 0.245 (0.49) |
| isolated nodes | 31,718 (74.1%) |
| nodes with degree <= 1 | 93.3% |
| connected components (largest holds) | 33,620 (14.6% of nodes) |
| junk entity names (sentences, digits, 1-2 chars) | 6.34% |
| graphml size | 26.6 MB |

#### Extraction A/B (same chunks, sequential calls, LightRAG's own prompt and parser)

| config | chunks | sec/chunk | entities/chunk | relations/chunk | chunks with relations | looping/over-long outputs | junk names | relations w/ unextracted endpoint |
|---|---|---|---|---|---|---|---|---|
| 8B | original cap400 ctx4k | 40 | 15.2 | 8.12 | 0.65 | 12/40 | 0/40 | 0.3% | 0.0% |
| 1.5B | original cap400 ctx4k | 40 | 8.63 | 8.43 | 0.12 | 4/40 | 0/40 | 5.0% | 0.0% |
| 8B | cap2500 ctx4k | 20 | 17.46 | 9.4 | 2.0 | 12/20 | 0/20 | 1.1% | 0.0% |
| 8B | cap2500 ctx8k | 20 | 50.87 | 12.2 | 10.1 | 20/20 | 2/20 | 0.4% | 12.9% |
| 1.5B | cap2500 ctx8k | 20 | 16.4 | 13.55 | 3.4 | 10/20 | 14/20 | 5.9% | 16.2% |
| 1.5B | ctx8k + lean prompt | 12 | 14.26 | 4.08 | 1.75 | 6/12 | 8/12 | 2.0% | 38.1% |
| 1.5B | ctx8k temp0.3 | 12 | 17.43 | 13.42 | 2.08 | 6/12 | 9/12 | 0.6% | 36.0% |
| 1.5B | ctx8k temp0.2 freq0.3 | 12 | 16.09 | 10.5 | 1.67 | 5/12 | 8/12 | 4.8% | 55.0% |
| 1.5B | ctx8k freq0.5 | 12 | 16.25 | 10.0 | 1.5 | 4/12 | 8/12 | 6.7% | 16.7% |

### Root causes found in the extraction pipeline

- The 400-token output cap **and** a 4096-token context truncated almost every extraction: LightRAG's extraction system prompt is ~3,000 tokens, leaving ~480 tokens for output. Relations are written last, so they were cut off. Fixed config: context >= 8192 and a higher output cap.
- With a sufficient context the 8B model yields ~10 relations/chunk (vs ~0.7 under the original config); the 1.5B model loops (repeats entity lines until the token cap) on most chunks even with a short prompt or sampling penalties.
- `hybrid` mode in LightRAG is graph-only (no chunk vector search); `mix` adds it. The README previously recommended `hybrid`.
- The corpus was indexed with the faster small model: measured wall-clock indexing speed-up 12.9x (owner-measured, entity extraction over the corpus). Per-call speed ratio measured here under the corrected config: ~3.1x at one request at a time; the remainder is consistent with 4 concurrent requests. The quality cost of that trade is in the extraction A/B table above.

## 8. Method and caveats

- Gold sets are LLM-generated (Qwen3-VL-8B) from 2-4 chunks in different judgments; a verifier removes questions answerable from one chunk. They are not human-labelled.
- Gold chunk sets can omit other valid chunks, so recall is a conservative estimate for all modes.
- Rank-based metrics (nDCG, MAP, MRR, @5, @10) assume returned order reflects ranking; recall@20 does not.
- Judge: Qwen3-VL-8B (stronger than the 1.5B answerer, but still a small local model); failed judge calls are excluded, not scored as zero.
- Confidence intervals: 95% bootstrap over questions. Mode comparisons: paired sign test on per-question recall@20.
- Retrieval ran with the cross-encoder reranker (bge-reranker-base) enabled for every mode.
