#!/usr/bin/env bash
# Phase 5 training chain (PAPER_CHANGELOG P5-1). Strict priority order,
# equal 40-iteration budget for EVERY learned method, 1 training seed,
# both scenarios. Sequential on purpose -- concurrent runs recreate the
# CPU-contention problem this project has already diagnosed twice.
#
# BATCHED WITH COOLDOWNS (author instruction): each run is 5-9h of
# sustained 8-worker load on a laptop. Running eight of those back to
# back invites thermal throttling -- which would not only stress the
# hardware but silently distort the very per-iteration timings this
# phase depends on. A cooldown after each run, and a longer one after
# each completed method, keeps the machine out of sustained-throttle
# territory. Rests are logged to the manifest so the wall-clock record
# stays honest about what was compute and what was idle.
#
# --early-check-iterations 0 disables train.py's >25%-filter-activation
# early abort: at iteration 4 the production filter config sits at
# 0.255 (S1) / 0.257 (S2), marginally over that threshold, and the
# 100-iteration production runs that produced the paper's accepted
# results ran at exactly this operating point (mean 0.250 S1 / 0.213 S2).
# Aborting a 40-iteration run on it would be a false positive.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest.txt
mkdir -p results_phase5
: > "$MANIFEST"

ITERS=40
SEED=0
REST_RUN=1800     # 30 min after every run
REST_METHOD=1800  # +30 min more after a method's last scenario (60 total)

rest () {  # seconds label
  local s=$1 label=$2
  echo "REST ${s}s ($label) start $(date -Is)" >> "$MANIFEST"
  sleep "$s"
  echo "REST ${s}s ($label) end   $(date -Is)" >> "$MANIFEST"
}

run_hap () {   # scenario
  local sc=$1
  echo "=== START haplight_rl $sc $(date -Is)" >> "$MANIFEST"
  python -m scripts.train --scenario "$sc" --seed $SEED --iterations $ITERS \
      --early-check-iterations 0 \
      > "results_phase5/log_haplight_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results/${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE haplight_rl $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

run_base () { # baseline scenario
  local b=$1 sc=$2
  echo "=== START $b $sc $(date -Is)" >> "$MANIFEST"
  python -m scripts.train_baseline --baseline "$b" --scenario "$sc" --seed $SEED \
      --iterations $ITERS --skip-eval \
      > "results_phase5/log_${b}_${sc}.txt" 2>&1
  local rc=$?
  local d=$(ls -td results_baselines/${b}_${sc}_seed${SEED}_*/ 2>/dev/null | head -1)
  echo "DONE $b $sc rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
}

# --- Priority 1: HAPLight-RL (sets the equal budget; required) ---
run_hap s1
rest $REST_RUN "after haplight_rl s1"
run_hap s2
rest $((REST_RUN + REST_METHOD)) "after haplight_rl (method complete)"

# --- Priority 2: Advanced-MPLight (SOTA comparison; required) ---
run_base advanced_mplight s1
rest $REST_RUN "after advanced_mplight s1"
run_base advanced_mplight s2
rest $((REST_RUN + REST_METHOD)) "after advanced_mplight (method complete)"

# --- Priority 3: MPLight ---
run_base mplight s1
rest $REST_RUN "after mplight s1"
run_base mplight s2
rest $((REST_RUN + REST_METHOD)) "after mplight (method complete)"

# --- Priority 4: CoLight-variant ---
run_base colight s1
rest $REST_RUN "after colight s1"
run_base colight s2

echo "ALL_DONE $(date -Is)" >> "$MANIFEST"
