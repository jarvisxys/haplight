#!/usr/bin/env bash
# Phase 5 chain 3 (PAPER_CHANGELOG P5-4). Runs ONLY work that does not
# depend on the author's pending decision about the pressure-lineage
# baselines (pressure_raw failed the corrected-measurement gate on S1):
#   1. early corrected evaluation of HAPLight-RL (filtered + unfiltered)
#      against FixedTime/MaxPressure/GreedyHAP -- none use pressure_raw --
#      answering the filter-behaviour question ahead of the final table;
#   2. CoLight-variant (single-hop attn) retrain, 40 iterations, both
#      scenarios -- a total_queue method (total_queue PASSES the gate), and
#      needed in the final table under every option on the table.
# Sequential with cooldowns (author instruction). Prelim eval seeds are
# deterministic, so its HAPLight-RL/classical cells will reproduce exactly
# in the final table.
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1
M=results_phase5/manifest_retrain3.txt; mkdir -p results_phase5; : > "$M"
rest(){ echo "REST $1s ($2) start $(date -Is)" >> "$M"; sleep "$1"; echo "REST $1s ($2) end   $(date -Is)" >> "$M"; }
ev(){ local sc=$1 ck=$2
  echo "=== START prelim-eval $sc $(date -Is)" >> "$M"
  python -m scripts.evaluate_policy --scenario "$sc" --checkpoint "$ck" --production-filter \
    --seeds 0 1 2 3 4 5 6 7 8 9 --etas 0.0 0.6 \
    --out "results_phase5/evalc_prelim_${sc}.json" > "results_phase5/evalc_prelim_${sc}_stdout.txt" 2>&1
  echo "DONE prelim-eval $sc rc=$? $(date -Is)" >> "$M"; }
tr(){ local sc=$1
  echo "=== START colight $sc $(date -Is)" >> "$M"
  python -m scripts.train_baseline --baseline colight --scenario "$sc" --seed 0 --iterations 40 \
    --skip-eval --worker-timeout-s 1800 --worker-max-retries 3 > "results_phase5/rt3_log_colight_${sc}.txt" 2>&1
  local rc=$?; local d=$(ls -td results_baselines/colight_${sc}_seed0_*/ 2>/dev/null | head -1)
  echo "DONE colight $sc rc=$rc dir=$d $(date -Is)" >> "$M"; }
echo "=== CHAIN3 BEGIN $(date -Is)" >> "$M"
rest 1800 "pre-chain cooldown"
ev s1 results/s1_seed0_1788963312/checkpoint.pt
rest 1800 "after prelim-eval s1"
ev s2 results/s2_seed0_1788987398/checkpoint.pt
rest 1800 "before colight training"
tr s1
rest 1800 "after colight s1"
tr s2
echo "ALL_DONE_CHAIN3 $(date -Is)" >> "$M"
