#!/usr/bin/env bash
# Phase 5 training chain, part 3 (PAPER_CHANGELOG P5-1).
#
# Why this exists: MPLight S2 aborted at iteration 9 with rc=1 when a
# rollout worker hung -- SUMO reported "tcpip::Socket::recvAndCheck @
# recv: Socket reset by peer" and the P4-6 watchdog correctly refused to
# wait forever (900s x2 retries, then raise). Iterations 0-8 had run
# cleanly at 563-646s each, so this was a transient infrastructure
# failure, not divergence or a code defect. The run is RESUMED from its
# iteration-8 checkpoint rather than restarted: per-iteration eta draws
# come from SeedSequence([seed, iteration]), so a resumed run sees
# exactly the demand realisations it would have seen anyway, and the
# optimizer state is checkpointed too. The completed run is therefore
# still a genuine 40-iteration, equal-budget run.
#
# Watchdog widened for the resumed runs: --worker-timeout-s 1800 (from
# 900) and --worker-max-retries 3 (from 2). Purely an infrastructure
# robustness setting -- it changes nothing about the training protocol,
# the budget, or any hyperparameter, and so does not touch the
# equal-budget fairness property. With iterations legitimately taking
# 563-646s, a 900s per-worker ceiling left little headroom for a single
# slow episode.
#
# Priority order is preserved: MPLight (priority 3) is completed BEFORE
# CoLight-variant (priority 4) gets any compute.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest.txt
mkdir -p results_phase5

ITERS=40
SEED=0
REST_RUN=1800
REST_METHOD=1800
WD="--worker-timeout-s 1800 --worker-max-retries 3"

MPLIGHT_S2_CKPT="results_baselines/mplight_s2_seed0_1788638147/checkpoint.pt"

rest () {
  local s=$1 label=$2
  echo "REST ${s}s ($label) start $(date -Is)" >> "$MANIFEST"
  sleep "$s"
  echo "REST ${s}s ($label) end   $(date -Is)" >> "$MANIFEST"
}

run_base () {   # baseline scenario [extra args...]
  local b=$1 sc=$2; shift 2
  echo "=== START $b $sc $* $(date -Is)" >> "$MANIFEST"
  python -m scripts.train_baseline --baseline "$b" --scenario "$sc" --seed $SEED \
      --iterations $ITERS --skip-eval $WD "$@" \
      >> "results_phase5/log_${b}_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results_baselines/${b}_${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE $b $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

echo "=== CHAIN3 BEGIN $(date -Is)" >> "$MANIFEST"
rest $REST_RUN "pre-chain3 cooldown"

# --- Priority 3 (completion): resume MPLight S2 from iteration 8 ---
run_base mplight s2 --resume "$MPLIGHT_S2_CKPT"
rest $((REST_RUN + REST_METHOD)) "after mplight s2 resume (method complete)"

# --- Priority 4: CoLight-variant ---
run_base colight s1
rest $REST_RUN "after colight s1"
run_base colight s2

echo "ALL_DONE_CHAIN3 $(date -Is)" >> "$MANIFEST"
