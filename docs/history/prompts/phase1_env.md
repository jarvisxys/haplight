# Phase 1 — SUMO environment + classical controllers

Paste into Claude Code from the repo root.

---

Read `PLAN.md`, `configs/default.yaml`, `src/hap.py` and `src/sensing.py`
first. Those two src files are finished and tested — import from them, do not
rewrite them. If you think one is wrong, tell me and stop.

Build Phase 1: `scripts/build_nets.py`, `src/env.py`, `src/controllers.py`,
`src/metrics.py`, and `tests/test_env.py`. Follow the interface signatures in
PLAN.md exactly; later phases depend on them.

**scripts/build_nets.py** — generate Scenario 1 (5-intersection arterial,
400 m spacing) and Scenario 2 (4×4 grid, 300 m spacing) from
`configs/default.yaml`. Left-hand traffic (`--lefthand true`). Four approaches
per intersection, 3 lanes each, lane width 3.5 m. Emit `.net.xml`, `.rou.xml`
and `.sumocfg` into `nets/arterial5/` and `nets/grid4x4/`. Demand follows the
two-peak diurnal profile and the fleet shares in the config. Leave Scenario 3
alone — that is Phase 6.

**src/env.py** — the `HAPLightEnv` class from PLAN.md. Four things matter more
than the rest:

1. **Two queue channels.** `info["true_queues"]` is noise-free and feeds
   metrics and the greedy-HAP ground truth. Observations go through
   `SensingModel` and are corrupted. Never let a corrupted value reach
   `metrics.py` — that would invalidate every robustness result. Add an
   assertion that catches it.
2. **Truncation, not termination.** `step` returns `truncated=True` at episode
   end so the trainer can bootstrap `V(s_T)`. Do not return `done` in a way
   that makes the return look terminal.
3. **Clearance is internal.** When the phase changes, `step` runs the yellow
   and all-red inside the interval. The agent never sees a clearance as a
   decision point.
4. **Observation is exactly Eq. (7)** — the eight features in that order,
   normalised by the *fixed* constants `x_ref`/`mu_ref` from the config, then
   clipped to ±10. Not running statistics: the policy must be deterministic at
   deployment.

Prefer `libsumo`; fall back to `traci` if the import fails. Movement and phase
extraction should come from `traci.trafficlight.getControlledLinks` rather
than parsing the net XML — it is more robust to whatever netconvert produces.

**src/controllers.py** — `FixedTime` (Webster from Indo-HCM saturation flows),
`SOTL`, `MaxPressure` (count-based, i.e. `rho ≡ 1`), `EfficientMP`,
`AdvancedMP`, `GreedyHAP`. `GreedyHAP` must call `src.hap.greedy_phase`;
do not reimplement the argmax. All of them respect `g_min`, `g_max` and the
action mask.

**src/metrics.py** — the exact key list in PLAN.md. `aql` in active weight
units from `fleet.rho`, not vehicles. `pwd` from `fleet.occupancy`. Gini per
class and overall.

**tests/test_env.py** — the four Phase 1 acceptance tests in PLAN.md:
`test_mp_beats_fixed_time`, `test_min_green_respected`,
`test_mask_never_empty`, `test_true_queues_noise_free`. Keep them fast
(short episodes, one seed).

Work incrementally: get Scenario 1 running with FixedTime end to end and
print ATT before you touch the other controllers. Run
`pytest tests/ -q` after each step and keep all 20 existing tests green.

When you are done, run a 600 s episode of FT, MP and GreedyHAP on Scenario 1
and print the ATT/AWT/AQL table so I can sanity-check the magnitudes.
