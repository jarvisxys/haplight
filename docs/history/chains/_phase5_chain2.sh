#!/usr/bin/env bash
# Phase 5 training chain, part 2 (PAPER_CHANGELOG P5-1). Priorities 1-2
# (HAPLight-RL, Advanced-MPLight) already completed at 40 iterations,
# seed 0, both scenarios. This continues with priority 3 (MPLight) and
# priority 4 (CoLight-variant), same equal 40-iteration budget.
#
# Opens with a 30-minute cooldown before any compute (author
# instruction): the previous chain ran ~37h of training and the machine
# should not go straight back under sustained 8-worker load.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest.txt
mkdir -p results_phase5

ITERS=40
SEED=0
REST_RUN=1800
REST_METHOD=1800

rest () {
  local s=$1 label=$2
  echo "REST ${s}s ($label) start $(date -Is)" >> "$MANIFEST"
  sleep "$s"
  echo "REST ${s}s ($label) end   $(date -Is)" >> "$MANIFEST"
}

run_base () {
  local b=$1 sc=$2
  echo "=== START $b $sc $(date -Is)" >> "$MANIFEST"
  python -m scripts.train_baseline --baseline "$b" --scenario "$sc" --seed $SEED \
      --iterations $ITERS --skip-eval \
      > "results_phase5/log_${b}_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results_baselines/${b}_${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE $b $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

echo "=== CHAIN2 BEGIN $(date -Is)" >> "$MANIFEST"
rest $REST_RUN "pre-chain2 cooldown"

# --- Priority 3: MPLight ---
run_base mplight s1
rest $REST_RUN "after mplight s1"
run_base mplight s2
rest $((REST_RUN + REST_METHOD)) "after mplight (method complete)"

# --- Priority 4: CoLight-variant ---
run_base colight s1
rest $REST_RUN "after colight s1"
run_base colight s2

echo "ALL_DONE_CHAIN2 $(date -Is)" >> "$MANIFEST"
