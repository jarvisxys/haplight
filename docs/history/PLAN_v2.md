# HAPLight — Implementation Plan

Companion to `HAPLight_journal_v2.tex`. This is the spec Claude Code works
from. Read this file plus the relevant `prompts/phaseN_*.md` before writing
code for a phase.

---

## Non-negotiable rules

0. **Never edit `paper/*.tex` during implementation.** Every paper-affecting
   decision or measurement goes in `PAPER_CHANGELOG.md` instead. The paper is
   rewritten once, at the end, from that file plus `results/`.

1. **`configs/default.yaml` is the only place numbers live.** Never hard-code
   a paper value in a `.py` file. If a number changes, it changes in the YAML
   and `scripts/report.py` regenerates the LaTeX table.
2. **`src/hap.py` and `src/sensing.py` are written and tested. Do not rewrite
   them.** Import from them. If you believe one is wrong, say so and stop —
   do not silently change it. `tests/test_hap.py` pins them to the paper.
3. **Every phase has an acceptance test.** A phase is not done until its test
   passes. Write the test first if it does not exist.
4. **`pytest tests/ -q` must stay green after every phase.**
5. **No result number is ever typed by hand.** Everything in Section VII of
   the paper comes out of `scripts/report.py`, which reads `results/*.parquet`
   and emits `.tex` fragments.
6. **Use `libsumo`, not `traci`, for training.** ~2–3× faster. Fall back to
   traci only if libsumo is unavailable. On Windows use `multiprocessing`
   with a `if __name__ == "__main__":` guard (spawn start method).

---

## Repository layout

```
haplight/
├─ PLAN.md                    ← this file
├─ requirements.txt
├─ configs/default.yaml       ← ALL parameters. Single source of truth.
├─ src/
│  ├─ hap.py                  ✅ DONE — HAP measure, Lemma 1, pressure
│  ├─ sensing.py              ✅ DONE — composite noise model
│  ├─ env.py                  ⬜ Phase 1 — SUMO wrapper
│  ├─ controllers.py          ⬜ Phase 1 — FT, SOTL, MP, Eff-MP, Adv-MP, GreedyHAP
│  ├─ policy.py               ⬜ Phase 4 — shared FRAP net (23,650 params)
│  ├─ ppo.py                  ⬜ Phase 4 — PPO + parallel workers
│  ├─ safety_filter.py        ⬜ Phase 4 — stability filter
│  ├─ rl_baselines.py         ⬜ Phase 5 — IPPO/PressLight/MPLight/CoLight/Adv-MPLight
│  ├─ metrics.py              ⬜ Phase 1 — ATT/AWT/AQL/TP/PWD/CO2/Gini
│  └─ stats.py                ⬜ Phase 8 — Wilcoxon + Holm + effect size + BCa
├─ scripts/
│  ├─ calibrate.py            ✅ DONE — C1/C2 (the gate)
│  ├─ build_nets.py           ⬜ Phase 1/6 — S1, S2, S3 generation
│  ├─ train.py                ⬜ Phase 4
│  ├─ evaluate.py             ⬜ Phase 7
│  └─ report.py               ⬜ Phase 8 — emits LaTeX tables + figures
├─ tests/test_hap.py          ✅ DONE — 20 tests, all passing
├─ nets/{arterial5,grid4x4,bengaluru}/
└─ results/                   ← one parquet row per episode
```

---

## Phase table

| # | What | Owner | Days | Gate |
|---|---|---|---|---|
| 0 | SUMO install, `SUMO_HOME`, repo, `pytest` green | you (15 min) | 0.5 | 20 tests pass |
| 1 | `env.py`, `controllers.py`, `metrics.py`, `build_nets.py` (S1/S2) | **Claude Code** | 2–3 | MP beats FT on S1 |
| 1b | **Demand calibration + heterogeneous composition** | **Claude Code** | 1–2 | v/c ≈ 0.85, HAP ≠ MP |
| 1c | **Per-movement ā, fleet realism, paired H1** | **Claude Code** | 1–2 | area ≈ count estimator |
| 2 | Run `calibrate.py` full (C1 + C2) | you (runs itself) | 0.5 | A5 verdict |
| 2b | Rewrite Sec. VII-A + `mu` calibration into paper | **me** | 0.5 | — |
| 3 | Two-wheeler behaviour tuning in SUMO | **Claude Code** | 1–2 | 2W filter to front |
| 4 | `policy.py`, `ppo.py`, `safety_filter.py`, `train.py` | **Claude Code** | 3–4 | beats greedy HAP on S1 |
| 5 | `rl_baselines.py` | **Claude Code** | 3–5 | Adv-MPLight ≈ published |
| 6 | Bengaluru OSM extraction ⚠️ highest risk | **Claude Code** | 2–4 | net loads, TLS sane |
| 7 | Full sweep | Claude Code launches | 5–7 wall | all parquet present |
| 8 | `report.py`, `stats.py`, tables, figures | **Claude Code** | 1–2 | paper compiles |
| 9 | Read results, decide narrative, rewrite Sec. VII | **me** | 3–4 | submittable |

**Bring back to me:** the C1/C2 numbers, the first main-comparison table, the
robustness curves, and anything that refutes a hypothesis. Those are
judgement calls, not coding.

---

## Interfaces Claude Code must implement

These signatures are fixed so phases can be built in parallel.

### `src/env.py`

```python
class HAPLightEnv:
    """SUMO wrapper. One instance = one network = one episode at a time."""

    def __init__(self, net_dir: str, cfg: dict, fleet: Fleet,
                 seed: int = 0, eta: float = 0.0,
                 estimator: str = "area",   # "area" | "count"
                 gui: bool = False, use_libsumo: bool = True): ...

    def reset(self) -> dict[str, np.ndarray]:
        """Returns {intersection_id: obs_vector}. Calls SensingModel.reset_episode()."""

    def step(self, actions: dict[str, int]) -> tuple[
        dict[str, np.ndarray],   # obs
        dict[str, float],        # reward, Eq. (12)
        bool,                    # truncated (episode end — NOT terminated)
        dict,                    # info: filter_active, gmax_active, queues, ...
    ]:
        """Advances Delta t seconds (cfg.signal.decision_interval_s)."""

    # required properties
    intersections: list[str]
    phases: dict[str, list[list[str]]]     # intersection -> phases -> movements
    action_masks: dict[str, np.ndarray]    # bool per phase, valid actions
    movements: dict[str, list[str]]
    mu: dict[str, float]                   # movement -> saturation flow
    true_queues: dict[str, float]          # NOISE-FREE, for metrics only
```

Hard requirements:
- **Two queue channels.** `info["true_queues"]` is noise-free and is used for
  metrics and for greedy-HAP ground truth in the filter certificate.
  Observations are corrupted. Never let the noisy value reach the metrics.
- Episode end is **truncation**, not termination. `step` returns
  `truncated=True`; the trainer bootstraps `V(s_T)`.
- Yellow/all-red is inserted inside `step` when the phase changes, so the
  agent never sees a clearance interval as a decision point.
- Action mask must always leave ≥1 valid phase.

### `src/controllers.py`

```python
class Controller:
    def act(self, obs, info) -> dict[str, int]: ...
    def reset(self): ...
```
Implement: `FixedTime`, `SOTL`, `MaxPressure`, `EfficientMP`, `AdvancedMP`,
`GreedyHAP`. `GreedyHAP` must call `src.hap.greedy_phase` — do not reimplement
the argmax.

### `src/metrics.py`

Per-episode dict with keys exactly:
`att, awt, aql, ad, tp, pwd, fuel, co2, gini_overall, gini_2w, gini_car,
gini_auto, gini_bus, gini_truck, filter_activation_rate, gmax_activation_rate`

`aql` is in **active weight units** (from `fleet.rho`), not vehicles.
`pwd` uses `fleet.occupancy`.

### `results/` schema

One parquet file per (scenario, method, seed), one row per episode:
```
scenario, method, seed, episode, eta, weight_scheme, estimator,
<all metric keys>, wall_clock_s
```

---

## Acceptance tests per phase

| Phase | Test | Passes if |
|---|---|---|
| 1 | `tests/test_env.py::test_mp_beats_fixed_time` | MP ATT < FT ATT on S1 |
| 1 | `tests/test_env.py::test_min_green_respected` | no phase shorter than `g_min` |
| 1 | `tests/test_env.py::test_mask_never_empty` | ≥1 valid action, every step |
| 1 | `tests/test_env.py::test_true_queues_noise_free` | `eta=1.0` leaves `true_queues` unchanged |
| 3 | `tests/test_sublane.py::test_2w_reach_front` | mean 2W stop-line position < mean car position in a mixed queue |
| 4 | `tests/test_policy.py::test_param_count` | **exactly 23,650** parameters |
| 4 | `tests/test_policy.py::test_mask_blocks_invalid` | masked logits → zero probability |
| 4 | `tests/test_ppo.py::test_filtered_steps_no_gradient` | policy grad is zero on overridden steps |
| 4 | `tests/test_ppo.py::test_truncation_bootstraps` | `V(s_T)` used at episode end |
| 5 | `tests/test_baselines.py::test_all_baselines_run` | every baseline completes an episode |
| 6 | `tests/test_nets.py::test_bengaluru_loads` | net loads, every TLS has ≥2 phases |
| 8 | `scripts/report.py` | emits `.tex`, paper compiles with 0 undefined refs |

---

## Compute budget (paper Table VII)

| | S1 | S2 | S3 |
|---|---|---|---|
| RL methods trained | 6 | 6 | 4 |
| Seeds | 5 | 5 | 5 |
| Episodes per run | 800 | 800 | 800 |
| Training episodes | 24,000 | 24,000 | 16,000 |
| Main eval | 1,800 | 1,800 | 1,500 |
| Robustness | — | 3,600 | 2,400 |

Roughly **5 days continuous on one 8-core box.** Levers if you overrun, in
this order: (1) robustness grid to S2 only; (2) training 800 → 500 episodes
with convergence curves shown; (3) drop MARDDPG entirely; (4) eval 30 → 20
episodes/seed. Never cut seeds below 5.

---

## Placeholders in the paper and what fills them

| Paper location | `\note{}` / `\pl` | Produced by |
|---|---|---|
| Sec. VI-C | N for Scenario 3 | `build_nets.py` |
| Fig. 2(c) | corridor screenshot | SUMO-GUI export |
| Sec. VII-A, Tab. VIII | realised ε | `calibrate.py` (C1) |
| Sec. VII-A, Tab. IX | A5 verdict | `calibrate.py` (C2) |
| Sec. VII-B, Tab. X | main comparison | `evaluate.py` → `report.py` |
| Sec. VII-B, Tab. XI | effect sizes | `stats.py` |
| Sec. VII-C | weight-vector comparison (H5) | `evaluate.py` |
| Fig. 4 | robustness curves | `evaluate.py` |
| Tab. XII | ablations | `evaluate.py` |
| Tab. XIII | fairness | `evaluate.py` |
| Sec. VII-G | surge + filter timeline | `evaluate.py` |
| Sec. VII-H | sensitivity sweeps | `evaluate.py` |
| Fig. 5 | training curves | `train.py` |
| Tab. VII | wall-clock | `train.py` timing |
| Sec. VIII-A | edge latency | manual, on a Pi/Jetson |
| Sec. VIII-C | repo URL | you |

---

## Known traps

- **`osmWebWizard` output for Indian arterials is always broken.** Missing
  TLS, unjoined junctions, phantom connections. Budget for hand-fixing in
  netedit and record every fix in `build_nets.py`.
- **Sublane (SL2015) costs 2–4× runtime.** Already in the budget.
- **Windows + libsumo:** one instance per process. Parallel envs need
  `multiprocessing`, not threads.
- **Pin the SUMO version** in `requirements.txt` — sublane behaviour has
  changed across releases.
- **Wilcoxon with n=150 flags 0.3 s differences.** Always report effect size
  and check against the pre-registered MPE (2% ATT / 5% AQL).
- **traci without subscriptions is ~10x too slow.** Per-vehicle
  `getSpeed`/`getTypeID` calls are one socket round-trip each; at ~2000
  vehicles x 3600 steps that is 7.2M round-trips per episode. Subscribe once
  per vehicle on departure and read `getAllSubscriptionResults()` once per
  step. Use `simulation.getArrivedIDList()` to finalise trips rather than
  diffing `getIDList()`.
- **A mistuned fixed-time baseline invalidates every reported gain.** Webster
  splits must come from the actual generated demand, never from a uniform
  assumption. If MP fails to beat FT, investigate — do not detune FT.
- **Greedy HAP == MaxPressure whenever composition is spatially uniform.**
  `x^HAP = c x^MP` for a scalar c, so the argmax is identical (Remark 3). The
  weight vector only does work when class mix varies across movements. If the
  two controllers ever tie exactly, check composition dispersion first.
- **Free-flow networks cannot discriminate between controllers.** Demand must
  be calibrated to a measured v/c, never left at a default.
- **Don't let the filter silently produce your gains.** Log activation rate on
  every run; under saturation HAPLight ≈ greedy HAP by design (Remark 6).
