#!/usr/bin/env bash
# Phase 5 RETRAIN on corrected measurements (PAPER_CHANGELOG P5-2).
#
# Every pre-fix checkpoint was trained against 8x-inflated observations
# and rewards and is discarded from the main table (kept on disk, marked
# invalid-8x). This chain retrains the full equal-budget set on corrected
# measurements: 40 iterations for EVERY learned method, seed 0, both
# scenarios, strict priority order, sequential.
#
# HAPLight-RL trains at the RE-SWEPT storage threshold (0.15 engage /
# 0.10 release, configs/default.yaml) -- the old 0.80 was selected
# against inflated occupancies and could never fire post-fix.
#
# Batched with cooldowns (author instruction): 30 min after each run,
# 60 min after each method completes both scenarios. Rests are logged so
# the wall-clock record stays honest about compute vs idle.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest_retrain.txt
mkdir -p results_phase5
: > "$MANIFEST"

ITERS=40
SEED=0
REST_RUN=1800
REST_METHOD=1800
WD="--worker-timeout-s 1800 --worker-max-retries 3"

rest () {
  local s=$1 label=$2
  echo "REST ${s}s ($label) start $(date -Is)" >> "$MANIFEST"
  sleep "$s"
  echo "REST ${s}s ($label) end   $(date -Is)" >> "$MANIFEST"
}

run_hap () {
  local sc=$1
  echo "=== START haplight_rl $sc $(date -Is)" >> "$MANIFEST"
  python -m scripts.train --scenario "$sc" --seed $SEED --iterations $ITERS \
      --early-check-iterations 0 $WD \
      > "results_phase5/rt_log_haplight_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results/${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE haplight_rl $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

run_base () {
  local b=$1 sc=$2
  echo "=== START $b $sc $(date -Is)" >> "$MANIFEST"
  python -m scripts.train_baseline --baseline "$b" --scenario "$sc" --seed $SEED \
      --iterations $ITERS --skip-eval $WD \
      > "results_phase5/rt_log_${b}_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results_baselines/${b}_${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE $b $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

echo "=== RETRAIN CHAIN BEGIN $(date -Is)" >> "$MANIFEST"

run_hap s1
rest $REST_RUN "after haplight_rl s1"
run_hap s2
rest $((REST_RUN + REST_METHOD)) "after haplight_rl (method complete)"

run_base advanced_mplight s1
rest $REST_RUN "after advanced_mplight s1"
run_base advanced_mplight s2
rest $((REST_RUN + REST_METHOD)) "after advanced_mplight (method complete)"

run_base mplight s1
rest $REST_RUN "after mplight s1"
run_base mplight s2
rest $((REST_RUN + REST_METHOD)) "after mplight (method complete)"

run_base colight s1
rest $REST_RUN "after colight s1"
run_base colight s2

echo "ALL_DONE_RETRAIN $(date -Is)" >> "$MANIFEST"
