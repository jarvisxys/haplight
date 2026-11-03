#!/usr/bin/env bash
# Phase 5 RETRAIN part 2 on corrected measurements (PAPER_CHANGELOG P5-2/P5-3).
#
# HAPLight-RL S1+S2 already retrained on corrected measurements.
# Advanced-MPLight is DROPPED (P5-3): after three genuine, evidence-based
# fix attempts it still diverges -- see PAPER_CHANGELOG P5-3 for the
# stated reason. This chain retrains the two remaining learned baselines
# on corrected measurements: MPLight and CoLight-variant (single-hop
# attn). 40 iterations each (equal budget, absolute rule), seed 0, both
# scenarios, sequential.
#
# Batched with cooldowns (author instruction): 30 min before starting,
# 30 min between scenarios, 60 min between methods.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest_retrain2.txt
mkdir -p results_phase5
: > "$MANIFEST"

ITERS=40
SEED=0
WD="--worker-timeout-s 1800 --worker-max-retries 3"

rest () {
  echo "REST $1s ($2) start $(date -Is)" >> "$MANIFEST"; sleep "$1"
  echo "REST $1s ($2) end   $(date -Is)" >> "$MANIFEST"
}

run_base () {
  local b=$1 sc=$2
  echo "=== START $b $sc $(date -Is)" >> "$MANIFEST"
  python -m scripts.train_baseline --baseline "$b" --scenario "$sc" --seed $SEED \
      --iterations $ITERS --skip-eval $WD \
      > "results_phase5/rt2_log_${b}_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results_baselines/${b}_${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE $b $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

echo "=== RETRAIN2 BEGIN $(date -Is)" >> "$MANIFEST"
rest 1800 "pre-chain cooldown"

run_base mplight s1
rest 1800 "after mplight s1"
run_base mplight s2
rest 3600 "after mplight (method complete)"

run_base colight s1
rest 1800 "after colight s1"
run_base colight s2

echo "ALL_DONE_RETRAIN2 $(date -Is)" >> "$MANIFEST"
