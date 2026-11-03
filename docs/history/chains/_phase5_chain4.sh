#!/usr/bin/env bash
# Phase 5 training chain, part 4 (PAPER_CHANGELOG P5-1): CoLight-variant,
# the last of the three reviewer-required baselines (the graph-attention
# comparison). Same equal 40-iteration budget, seed 0, both scenarios.
#
# Labelled "CoLight-variant (single-hop attn)" everywhere it is reported:
# this port is single-hop attention over raw sensed neighbour features,
# NOT multi-hop attention over neighbours' hidden embeddings. Never
# presented as bare "CoLight".
#
# Opens with a cooldown -- the n=10 evaluation just put the machine under
# ~2h of 15-worker load. Widened watchdog carried over from chain 3
# (1800s / 3 retries) after the transient SUMO "Socket reset by peer"
# that aborted MPLight S2: infrastructure robustness only, it touches no
# hyperparameter and no budget.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest.txt
mkdir -p results_phase5

ITERS=40
SEED=0
REST_RUN=1800
WD="--worker-timeout-s 1800 --worker-max-retries 3"

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
      --iterations $ITERS --skip-eval $WD \
      > "results_phase5/log_${b}_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results_baselines/${b}_${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE $b $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

echo "=== CHAIN4 BEGIN $(date -Is)" >> "$MANIFEST"
rest $REST_RUN "pre-chain4 cooldown (post-evaluation)"

run_base colight s1
rest $REST_RUN "after colight s1"
run_base colight s2

echo "ALL_DONE_CHAIN4 $(date -Is)" >> "$MANIFEST"
