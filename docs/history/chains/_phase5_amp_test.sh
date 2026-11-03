#!/usr/bin/env bash
# P5-3: decisive test of the ONE remaining controlled hypothesis for
# Advanced-MPLight's late-onset divergence -- network capacity.
#
# Established so far: the running-demand feature is numerically EXACT
# (matches the classical AdvancedMP controller's live reference
# 1500/1500), MPLight's single feature is byte-identical to AMP's
# pressure channel, and MPLight trains cleanly on the SAME reward and
# hyperparameters. The remaining difference I control is net width:
# I gave AMP 32/32/16 (5,542 params) vs MPLight's 16/16/8 (1,478) --
# my own inferred choice, NOT taken from the source paper.
#
# Must run the FULL 40 iterations: the divergence is a late-training
# phenomenon (the full-width run's first 10 iterations are flat/positive
# at Theil-Sen +12.6; the decline only appears after ~iteration 16), so
# any short probe is inconclusive by construction.
#
# 30-min cooldown first (author instruction).
cd "C:/Users/Aditya kumar/OneDrive/Desktop/HAPLIGHT" || exit 1

MANIFEST=results_phase5/manifest_amp_test.txt
mkdir -p results_phase5
: > "$MANIFEST"

rest () {
  echo "REST $1s ($2) start $(date -Is)" >> "$MANIFEST"; sleep "$1"
  echo "REST $1s ($2) end   $(date -Is)" >> "$MANIFEST"
}

echo "=== AMP WIDTH TEST BEGIN $(date -Is)" >> "$MANIFEST"
rest 1800 "pre-test cooldown"

echo "=== START advanced_mplight s1 @ narrow width (16/16/8) $(date -Is)" >> "$MANIFEST"
python -m scripts.train_baseline --baseline advanced_mplight --scenario s1 --seed 0 \
    --iterations 40 --skip-eval --config configs/_probe_amp_narrow.yaml \
    --worker-timeout-s 1800 --worker-max-retries 3 \
    --out results_phase5/amp_narrow \
    > results_phase5/log_amp_narrow_s1.txt 2>&1
rc=$?
d=$(ls -td results_phase5/amp_narrow/advanced_mplight_s1_seed0_*/ 2>/dev/null | head -1)
echo "DONE advanced_mplight s1 narrow rc=$rc dir=$d $(date -Is)" >> "$MANIFEST"
echo "ALL_DONE_AMP_TEST $(date -Is)" >> "$MANIFEST"
