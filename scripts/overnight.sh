#!/usr/bin/env bash
# Overnight evaluation orchestrator. Sequential, resumable phases; model swaps via `lms`.
# A failing phase is logged and the run continues. Optional phases are skipped after
# 03:30; the final report is always generated. Writes Logs/overnight/DONE when finished.
cd "D:/Projects/Resume/GraphRag-Supreme Court" || exit 1

RUN_DIR="Logs/overnight"
mkdir -p "$RUN_DIR" reports
rm -f "$RUN_DIR/DONE"
PY="venv/Scripts/python.exe"
SMALL="qwen2.5-1.5b-instruct"
BIG="qwen3-vl-8b-instruct"
EMBED="text-embedding-nomic-embed-text-v1.5"

if [ "$(date +%H)" -lt 12 ]; then DL_DAY="today"; else DL_DAY="tomorrow"; fi
DEADLINE_OPT=$(date -d "$DL_DAY 03:30" +%s)

log() { echo "$(date '+%F %T') $*" | tee -a "$RUN_DIR/orchestrator.log"; }

run_phase() {  # name optional(0|1) timeout_minutes cmd...
  local name=$1 opt=$2 tmo=$3; shift 3
  if [ "$opt" = "1" ] && [ "$(date +%s)" -ge "$DEADLINE_OPT" ]; then
    log "SKIP  $name (past 03:30 deadline for optional phases)"; echo "$name SKIPPED" >> "$RUN_DIR/state.txt"; return 0
  fi
  log "START $name (timeout ${tmo}m)"
  local t0; t0=$(date +%s)
  timeout "${tmo}m" "$@" > "$RUN_DIR/$name.log" 2>&1
  local rc=$?
  log "END   $name rc=$rc elapsed=$(( $(date +%s) - t0 ))s"
  echo "$name rc=$rc" >> "$RUN_DIR/state.txt"
  return 0
}

health() {  # model -> 0 if chat + embeddings respond
  local m=$1
  curl -s -m 120 http://localhost:1234/v1/chat/completions -H "Content-Type: application/json" \
    -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":3}" | grep -q '"choices"' || return 1
  curl -s -m 60 http://localhost:1234/v1/embeddings -H "Content-Type: application/json" \
    -d "{\"model\":\"$EMBED\",\"input\":\"hi\"}" | grep -q '"embedding"' || return 1
  return 0
}

ensure_llm() {  # model ctx parallel
  local m=$1 ctx=$2 par=$3
  log "LOAD  $m ctx=$ctx parallel=$par"
  lms unload --all >> "$RUN_DIR/lms.log" 2>&1
  sleep 3
  for attempt in 1 2 3; do
    lms load "$m" --context-length "$ctx" --parallel "$par" --gpu max --identifier "$m" -y >> "$RUN_DIR/lms.log" 2>&1 && break
    log "WARN  load $m failed (attempt $attempt)"; sleep 15
  done
  lms load "$EMBED" -y >> "$RUN_DIR/lms.log" 2>&1
  for attempt in 1 2 3 4 5 6; do
    if health "$m"; then log "READY $m"; return 0; fi
    sleep 20
  done
  log "ERROR $m not healthy after load; continuing anyway"; return 1
}

# Settings for the system under test (1.5B): the answer prompt can reach ~25k tokens.
export RERANK_DEVICE=cuda
export LM_STUDIO_MODEL=$SMALL
export QUERY_MAX_TOTAL_TOKENS=26000
export EVAL_BENCH_N=60

log "=== overnight run started; optional-phase deadline $(date -d @$DEADLINE_OPT '+%F %T') ==="
run_phase sysstats 0 15 $PY -m src.evaluation.system_stats
run_phase pytest   0 10 $PY -m pytest tests -q

# ---------------- Stage A: system under test (1.5B, 32k context) ----------------
ensure_llm $SMALL 32768 1
run_phase eval_regex 0 150 $PY -m src.evaluation.multichunk_eval --modes naive mix hybrid local global \
    --gt ground_truth_multi_regex.json --out multichunk_eval_regex.json --tag regex
run_phase answers_multi 0 180 $PY -m src.evaluation.multichunk_answers --modes naive mix hybrid --n-regex 70 --n-legal 30

# ---------------- Stage B: judge (8B) ----------------
ensure_llm $BIG 8192 1
run_phase judge_multi 0 150 env JUDGE_MODEL=$BIG LM_STUDIO_MODEL=$BIG $PY -m src.evaluation.multichunk_judge
run_phase report_interim 0 5 $PY -m src.evaluation.report

# ---------------- Stage C: more retrieval evals + single-chunk answers (1.5B) ----------------
ensure_llm $SMALL 32768 1
run_phase eval_legal 1 120 $PY -m src.evaluation.multichunk_eval --modes naive mix hybrid \
    --gt ground_truth_multi.json --out multichunk_eval_legal.json --tag legal
run_phase sweep_ctk10   1 40 $PY -m src.evaluation.multichunk_eval --modes mix --gt ground_truth_multi_regex.json --params '{"chunk_top_k": 10}' --out sweep_ctk10.json --tag ctk10
run_phase sweep_ctk40   1 40 $PY -m src.evaluation.multichunk_eval --modes mix --gt ground_truth_multi_regex.json --params '{"chunk_top_k": 40}' --out sweep_ctk40.json --tag ctk40
run_phase sweep_topk80  1 40 $PY -m src.evaluation.multichunk_eval --modes mix --gt ground_truth_multi_regex.json --params '{"top_k": 80}' --out sweep_topk80.json --tag topk80
run_phase sweep_topk20  1 40 $PY -m src.evaluation.multichunk_eval --modes mix --gt ground_truth_multi_regex.json --params '{"top_k": 20}' --out sweep_topk20.json --tag topk20
run_phase sweep_norerank 1 40 $PY -m src.evaluation.multichunk_eval --modes mix --gt ground_truth_multi_regex.json --params '{"enable_rerank": false}' --out sweep_norerank.json --tag norerank
run_phase answers_single 1 120 $PY -m src.evaluation.benchmark --phase answer --modes naive mix hybrid --n 60

# ---------------- Stage D: judge single-chunk answers (8B) ----------------
if [ "$(date +%s)" -lt "$DEADLINE_OPT" ]; then
  ensure_llm $BIG 8192 1
  run_phase judge_single 1 60 env JUDGE_MODEL=$BIG LM_STUDIO_MODEL=$BIG $PY -m src.evaluation.benchmark --phase judge
fi

run_phase system_stats_final 0 15 $PY -m src.evaluation.system_stats
run_phase report_final 0 5 $PY -m src.evaluation.report
log "=== overnight run finished ==="
date '+%F %T' > "$RUN_DIR/DONE"
