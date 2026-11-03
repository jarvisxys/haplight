#!/usr/bin/env bash
# Phase 5 chain 4 (PAPER_CHANGELOG P5-8). Finishes the laptop table:
#   1. RESUME CoLight-variant (single-hop attn) S1 from iteration 23. It
#      crashed there on a transient SUMO port collision under the
#      TraCI-over-TCP backend, which the pre-P5-8 watchdog did not retry.
#   2. CoLight-variant S2, 40 iterations.
#   3. The FINAL n=10 evaluation -- HAPLight-RL (filtered + unfiltered) +
#      CoLight-variant + FixedTime/MaxPressure/GreedyHAP, both scenarios,
#      eta in {0, 0.6}. Runs ONLY if both CoLight runs return rc=0, so a
#      partial or missing checkpoint can never reach the table.
#
# Uses the P5-8 watchdog fix: a worker that raises is retried on the SAME
# episode (same seed/iteration/worker), not allowed to end the run. The
# resume continues at iteration 24; per-iteration eta draws come from
# SeedSequence([seed, iteration]), so it sees exactly the demand
# realisations an uninterrupted run would have.
#
# Backend deliberately UNCHANGED (TraCI over TCP, system Python), matching
# every other corrected-measurement run in this table. Switching one
# method to libsumo mid-comparison would break consistency (P5-8).
#
# Cooldowns between every heavy stage (author instruction).
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1
M=results_phase5/manifest_retrain4.txt; mkdir -p results_phase5; : > "$M"
WD="--worker-timeout-s 1800 --worker-max-retries 3"
rest(){ echo "REST $1s ($2) start $(date -Is)" >> "$M"; sleep "$1"; echo "REST $1s ($2) end   $(date -Is)" >> "$M"; }

S1DIR=results_baselines/colight_s1_seed0_1789238385

echo "=== CHAIN4 BEGIN $(date -Is)" >> "$M"
rest 1800 "pre-chain cooldown"

echo "=== START colight s1 RESUME from iter 23 $(date -Is)" >> "$M"
python -m scripts.train_baseline --baseline colight --scenario s1 --seed 0 --iterations 40 \
    --skip-eval $WD --resume "$S1DIR/checkpoint.pt" > results_phase5/rt4_log_colight_s1.txt 2>&1
RC1=$?
echo "DONE colight s1 rc=$RC1 dir=$S1DIR iters=$(( $(wc -l < "$S1DIR/train_log.csv") - 1 )) $(date -Is)" >> "$M"

rest 1800 "after colight s1"

echo "=== START colight s2 $(date -Is)" >> "$M"
python -m scripts.train_baseline --baseline colight --scenario s2 --seed 0 --iterations 40 \
    --skip-eval $WD > results_phase5/rt4_log_colight_s2.txt 2>&1
RC2=$?
S2DIR=""
for d in $(ls -td results_baselines/colight_s2_seed0_*/ 2>/dev/null); do
  [ -f "$d/INVALID_8X.txt" ] && continue
  S2DIR="${d%/}"; break
done
echo "DONE colight s2 rc=$RC2 dir=$S2DIR $(date -Is)" >> "$M"

if [ "$RC1" -ne 0 ] || [ "$RC2" -ne 0 ] || [ -z "$S2DIR" ]; then
  echo "SKIP final-eval: a CoLight run did not complete (rc1=$RC1 rc2=$RC2 s2dir='$S2DIR') $(date -Is)" >> "$M"
  echo "ALL_DONE_CHAIN4 (eval skipped) $(date -Is)" >> "$M"
  exit 1
fi

rest 1800 "before final evaluation"

ev(){ local sc=$1 hap=$2 col=$3
  echo "=== START final-eval $sc $(date -Is)" >> "$M"
  python -m scripts.evaluate_policy --scenario "$sc" --checkpoint "$hap" --production-filter \
    --seeds 0 1 2 3 4 5 6 7 8 9 --etas 0.0 0.6 \
    --baseline-checkpoint "colight=$col" \
    --out "results_phase5/eval_final_${sc}.json" > "results_phase5/eval_final_${sc}_stdout.txt" 2>&1
  echo "DONE final-eval $sc rc=$? $(date -Is)" >> "$M"; }

ev s1 results/s1_seed0_1788963312/checkpoint.pt "$S1DIR/checkpoint.pt"
rest 1800 "between final evals"
ev s2 results/s2_seed0_1788987398/checkpoint.pt "$S2DIR/checkpoint.pt"

echo "ALL_DONE_CHAIN4 $(date -Is)" >> "$M"
