"""
Phase 1c Parts C/D (PAPER_CHANGELOG P1c-2/3/4/6): paired HAP-MP evidence with
spillback metrics, and a proper MP-vs-FT re-test at higher v/c and surge.

Two independent deliverables sharing plumbing (net reuse, route generation,
episode running), same pattern as scripts/calibrate_demand.py:

  --mode paired (default, Part C)
      The Phase 1b composition-dispersion sweep couldn't support H1 as
      reported, for three reasons this fixes:
        1. Disagreement at d=0 is a ~3% SAMPLING-NOISE FLOOR, not zero
           (the theorem's equality holds in expectation, not for any single
           finite realised queue) -- measured here across 5 seeds and
           reported explicitly, separate from any systematic effect.
        2. The old table was CONFOUNDED: raising dispersion changes the
           demand itself (more buses/trucks on the arterial), so ATT/AQL/
           PWD levels worsening with d says nothing about the controller.
           The real evidence is the PAIRED HAP-MP difference on IDENTICAL
           demand and seeds -- that's what this reports.
        3. WRONG METRIC: HAP optimises road-space occupancy, so its
           advantage should show as spillback prevention (metrics.
           spillback_stats), not vehicle travel time. Reported alongside
           ATT/AQL/PWD on both S1 and S2 (S2's 300m links are more
           spillback-prone) at v/c in {0.85, 0.95}, 3 seeds.

  --mode mp_vs_ft (Part D)
      P1b-8 (MP 232.6s vs FT 230.5s, v/c 0.85, single seed) isn't
      alarming on its own -- max-pressure is throughput-optimal, not
      delay-optimal, so a well-tuned Webster plan can be competitive at
      moderate stationary demand. Re-tested at v/c 0.95 and under
      demand.scale_surge, 5 seeds, both scenarios. Reported as measured,
      win or lose -- not adjusted toward a target.

Usage
-----
    python -m scripts.h1_evidence --mode paired
    python -m scripts.h1_evidence --mode mp_vs_ft
    python -m scripts.h1_evidence --mode both
    python -m scripts.h1_evidence --mode paired --hap-estimator count
"""
from __future__ import annotations

import argparse
import copy
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.calibrate_demand import (  # noqa: E402
    SCENARIOS,
    _mp_shadow_action,
    _od_setup,
    _prepare_net,
    _write_run,
    run_hap_vs_mp,
    scale_for_vc,
)
from src import metrics  # noqa: E402
from src.controllers import FixedTime, GreedyHAP, MaxPressure  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

PAIRED_SCENARIOS = ("s1_arterial", "s2_grid")
PAIRED_VC = (0.85, 0.95)
PAIRED_SEEDS = (0, 1, 2)
NOISE_FLOOR_SEEDS = (0, 1, 2, 3, 4)
MP_VS_FT_SEEDS = (0, 1, 2, 3, 4)


def _make_controller(cls, env, cfg, fleet):
    if cls is FixedTime:
        return cls(env, cfg, fleet)
    return cls(env)


def _run_controller_episode(
    rundir: Path, cfg: dict, fleet: Fleet, seed: int, controller_cls,
    estimator: str = "area", track_disagreement: bool = False,
) -> dict:
    """Drives one episode with `controller_cls`, collecting ATT/AQL/PWD/TP,
    mean 2W wait, and metrics.spillback_stats() from the per-step
    per-movement true_queues history against env.storage. If
    track_disagreement, also computes the MaxPressure shadow action at
    every decision (no second simulation) and reports the fraction of
    decisions where `controller_cls`'s own choice disagreed with it."""
    env = HAPLightEnv(str(rundir), cfg, fleet, seed=seed, eta=0.0, estimator=estimator)
    try:
        obs = env.reset()
        ctrl = _make_controller(controller_cls, env, cfg, fleet)
        ctrl.reset()
        info = env.info
        queue_history: List[dict] = []
        n_decisions = disagreements = 0
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            if track_disagreement:
                mp_actions = _mp_shadow_action(env, info)
                for i in env.intersections:
                    n_decisions += 1
                    if actions[i] != mp_actions[i]:
                        disagreements += 1
            queue_history.append(copy.deepcopy(info["true_queues"]))
            obs, reward, truncated, info = env.step(actions)

        trips = env.completed_trips()
        m = metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        two_w_wait = [t["waiting"] for t in trips if t["vclass"] == "twowheeler"]
        threshold = cfg["hap"].get("spillback_threshold", 0.9)
        sb = metrics.spillback_stats(queue_history, env.storage, env.dt, threshold=threshold)

        out = {
            "att": m["att"], "aql": m["aql"], "pwd": m["pwd"], "tp": m["tp"],
            "two_w_wait": float(np.mean(two_w_wait)) if two_w_wait else float("nan"),
            **sb,
        }
        if track_disagreement:
            out["disagreement_rate"] = disagreements / n_decisions if n_decisions else float("nan")
        return out
    finally:
        env.close()


# --------------------------------------------------------------------------
# Part C: paired HAP-MP evidence with spillback metrics
# --------------------------------------------------------------------------

_PAIRED_KEYS = ["att", "aql", "pwd", "two_w_wait", "frac_steps_any_over_threshold",
                "spillback_events", "upstream_blocked_s"]


def paired_hap_mp(
    cfg: dict, fleet: Fleet, nets_dir: Path, workdir: Path,
    hap_estimator: str = "area", episode_s: float = 1800.0,
) -> dict:
    dispersion = cfg["demand"].get("composition_dispersion", 0.5)
    cfg_run = copy.deepcopy(cfg)
    cfg_run["demand"]["episode_length_s"] = episode_s

    print(f"\nPaired HAP-MP evidence (dispersion={dispersion:.2f}, "
          f"hap_estimator={hap_estimator!r}, episode={episode_s:.0f}s, "
          f"{len(PAIRED_SEEDS)} seeds)")

    cells = {}
    for scenario_key in PAIRED_SCENARIOS:
        name = SCENARIOS[scenario_key]
        nodes, edges, entry_edges, exit_edges, net_path = _prepare_net(scenario_key, cfg, nets_dir, workdir)
        od_pairs, _, _, _, od_shares = _od_setup(cfg, fleet, nodes, edges, entry_edges, exit_edges, dispersion)
        n_od = len(od_pairs)
        capacity = cfg["demand"]["capacity_veh_per_h"].get(scenario_key)
        if capacity is None:
            print(f"  (no calibrated capacity for {scenario_key} -- skipping)")
            continue

        for vc in PAIRED_VC:
            scale = scale_for_vc(vc, capacity, n_od)
            hap_runs, mp_runs = [], []
            for seed in PAIRED_SEEDS:
                rundir = workdir / f"paired_{scenario_key}_vc{vc}_seed{seed}"
                _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, rundir)
                hap_runs.append(_run_controller_episode(
                    rundir, cfg_run, fleet, seed, GreedyHAP, estimator=hap_estimator,
                ))
                mp_runs.append(_run_controller_episode(
                    rundir, cfg_run, fleet, seed, MaxPressure, estimator="area",
                ))

            def _mean(runs, key):
                return float(np.mean([r[key] for r in runs]))

            def _std(runs, key):
                return float(np.std([r[key] for r in runs]))

            diffs = {k: _mean(hap_runs, k) - _mean(mp_runs, k) for k in _PAIRED_KEYS}
            diff_std = {k: float(np.std([h[k] - m[k] for h, m in zip(hap_runs, mp_runs)])) for k in _PAIRED_KEYS}
            cells[(scenario_key, vc)] = {
                "hap_mean": {k: _mean(hap_runs, k) for k in _PAIRED_KEYS},
                "mp_mean": {k: _mean(mp_runs, k) for k in _PAIRED_KEYS},
                "diff_mean": diffs,
                "diff_std": diff_std,
            }
            print(f"\n  {scenario_key}  v/c={vc:.2f}  (scale={scale:.3f}, n={len(PAIRED_SEEDS)} seeds)")
            print(f"    {'metric':>28s} {'HAP':>10s} {'MP':>10s} {'HAP-MP':>10s} {'+-':>8s}")
            for k in _PAIRED_KEYS:
                print(f"    {k:>28s} {cells[(scenario_key, vc)]['hap_mean'][k]:10.2f} "
                      f"{cells[(scenario_key, vc)]['mp_mean'][k]:10.2f} "
                      f"{diffs[k]:10.2f} {diff_std[k]:8.2f}")

    # d=0 noise floor: how much of ANY measured HAP-MP difference could be
    # sampling noise rather than a systematic composition effect.
    print(f"\n  d=0 disagreement-rate noise floor (S1, v/c=0.85, "
          f"{len(NOISE_FLOOR_SEEDS)} seeds) -- the systematic component "
          f"above must clear this to mean anything:")
    name = SCENARIOS["s1_arterial"]
    nodes, edges, entry_edges, exit_edges, net_path = _prepare_net("s1_arterial", cfg, nets_dir, workdir)
    od_pairs, _, _, _, od_shares = _od_setup(cfg, fleet, nodes, edges, entry_edges, exit_edges, 0.0)
    capacity = cfg["demand"]["capacity_veh_per_h"].get("s1_arterial")
    n_od = len(od_pairs)
    scale = scale_for_vc(0.85, capacity, n_od) if capacity else 1.0
    rates = []
    for seed in NOISE_FLOOR_SEEDS:
        rundir = workdir / f"noisefloor_seed{seed}"
        _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, rundir)
        r = run_hap_vs_mp(rundir, cfg_run, fleet, seed=seed)
        rates.append(r["disagreement_rate"])
    noise_floor = {"mean": float(np.mean(rates)), "std": float(np.std(rates)), "rates": rates}
    print(f"    disagreement_rate = {noise_floor['mean']:.1%} +- {noise_floor['std']:.1%} "
          f"(per-seed: {[f'{x:.1%}' for x in rates]})")

    return {"cells": cells, "noise_floor": noise_floor}


# --------------------------------------------------------------------------
# Part D: MP vs FT at v/c 0.95 and under surge
# --------------------------------------------------------------------------


def mp_vs_ft(cfg: dict, fleet: Fleet, nets_dir: Path, workdir: Path, episode_s: float = None) -> dict:
    dispersion = cfg["demand"].get("composition_dispersion", 0.5)
    cfg_run = copy.deepcopy(cfg)
    if episode_s is not None:
        cfg_run["demand"]["episode_length_s"] = episode_s

    print(f"\nMP vs FT re-test (dispersion={dispersion:.2f}, "
          f"{len(MP_VS_FT_SEEDS)} seeds, episode={cfg_run['demand']['episode_length_s']:.0f}s)")

    results = {}
    for scenario_key in PAIRED_SCENARIOS:
        name = SCENARIOS[scenario_key]
        nodes, edges, entry_edges, exit_edges, net_path = _prepare_net(scenario_key, cfg, nets_dir, workdir)
        od_pairs, _, _, _, od_shares = _od_setup(cfg, fleet, nodes, edges, entry_edges, exit_edges, dispersion)
        n_od = len(od_pairs)
        capacity = cfg["demand"]["capacity_veh_per_h"].get(scenario_key)
        scale_surge = cfg["demand"]["scale_surge"].get(scenario_key)
        if capacity is None or scale_surge is None:
            print(f"  (no calibrated demand for {scenario_key} -- skipping)")
            continue
        levels = {"vc0.95": scale_for_vc(0.95, capacity, n_od), "surge": scale_surge}

        for level_name, scale in levels.items():
            ft_atts, mp_atts = [], []
            for seed in MP_VS_FT_SEEDS:
                rundir = workdir / f"mpft_{scenario_key}_{level_name}_seed{seed}"
                _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, rundir)
                ft = _run_controller_episode(rundir, cfg_run, fleet, seed, FixedTime, estimator="area")
                mp = _run_controller_episode(rundir, cfg_run, fleet, seed, MaxPressure, estimator="area")
                ft_atts.append(ft["att"])
                mp_atts.append(mp["att"])
            ft_mean, ft_std = float(np.mean(ft_atts)), float(np.std(ft_atts))
            mp_mean, mp_std = float(np.mean(mp_atts)), float(np.std(mp_atts))
            mp_wins = mp_mean < ft_mean
            results[(scenario_key, level_name)] = {
                "scale": scale, "ft_att_mean": ft_mean, "ft_att_std": ft_std,
                "mp_att_mean": mp_mean, "mp_att_std": mp_std, "mp_wins": mp_wins,
            }
            verdict = "MP wins" if mp_wins else "FT wins (MP loses)"
            print(f"  {scenario_key:>12s} {level_name:>8s} (scale={scale:.3f})  "
                  f"FT={ft_mean:7.2f}+-{ft_std:5.2f}  MP={mp_mean:7.2f}+-{mp_std:5.2f}  {verdict}")

    return results


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--nets", default="nets")
    ap.add_argument("--mode", choices=["paired", "mp_vs_ft", "both"], default="both")
    ap.add_argument("--hap-estimator", choices=["area", "count"], default="area",
                     help="which estimator drives GreedyHAP in --mode paired -- 'area' is the "
                          "realistic deployed configuration once per-movement calibration "
                          "(scripts/calibrate_estimator.py) is installed; fall back to 'count' "
                          "if that hasn't recovered close to it")
    ap.add_argument("--episode-s", type=float, default=1800.0)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    config_path = Path(args.config)
    cfg = yaml.safe_load(config_path.read_text())
    nets_dir = Path(args.nets)
    fleet = Fleet.from_config(cfg)
    episode_s = 300.0 if args.quick else args.episode_s

    with tempfile.TemporaryDirectory(prefix="haplight_h1_") as td:
        workdir = Path(td)
        if args.mode in ("paired", "both"):
            paired_hap_mp(cfg, fleet, nets_dir, workdir, hap_estimator=args.hap_estimator, episode_s=episode_s)
        if args.mode in ("mp_vs_ft", "both"):
            mp_vs_ft(cfg, fleet, nets_dir, workdir, episode_s=episode_s if args.quick else None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
