"""
Per-movement estimator calibration (Phase 1c Part A, PAPER_CHANGELOG P1c-1).

P1b-7 found Greedy HAP collapses under estimator="area" once composition
varies by movement: a SINGLE GLOBAL a_bar divided into queues whose
composition differs by movement produces a fixed, per-movement,
non-cancelling bias (a 75%-2W side street looks ~21% smaller than it is; a
bus/truck-heavy arterial looks ~12% larger) -- Remark 3's uniform-error-is-
free argument does not apply because the error is NOT uniform across
movements. The fix Remark 3 itself prescribes: calibrate a_bar PER MOVEMENT
instead of once globally.

This script:
  1. Calibrates a_bar_m per movement from one classified-count episode
     (estimator="count", the clean channel) -- the simulated stand-in for a
     one-hour count at camera commissioning. `Fleet.a_bar_for(composition)`
     does the math (src/hap.py); this script does the counting and I/O.
  2. Re-runs the P1b-7 comparison with per-movement calibration on: a
     three-way table (global a_bar / per-movement a_bar / count estimator)
     at composition_dispersion in {0, 0.5, 1.0} on S1 at nominal demand.
  3. Reports a staleness row: a_bar_m calibrated at d=0.5 but evaluated at
     d=1.0, bounding how stale a commissioning calibration can get as
     composition drifts before it needs recommissioning.
  4. Writes the PRODUCTION a_bar_per_movement.json into nets/<scenario>/ for
     BOTH S1 and S2 (at each scenario's own scale_nominal, the config's
     default composition_dispersion) -- this is what makes src/env.py's
     file-presence-based auto-load actually take effect for every
     subsequent default estimator="area" run.

Usage
-----
    python -m scripts.calibrate_estimator                # full three-way sweep + install
    python -m scripts.calibrate_estimator --quick          # fast smoke test
    python -m scripts.calibrate_estimator --no-install      # sweep only, don't touch nets/
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.calibrate_demand import (  # noqa: E402
    SCENARIOS,
    _od_setup,
    _prepare_net,
    _write_run,
)
from src import metrics  # noqa: E402
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

THREE_WAY_DISPERSIONS = (0.0, 0.5, 1.0)
STALE_CALIBRATED_AT = 0.5
STALE_EVALUATED_AT = 1.0


# --------------------------------------------------------------------------
# Calibration: one count-estimator episode -> per-movement a_bar_m
# --------------------------------------------------------------------------


def run_count_episode_and_calibrate(
    rundir: Path, cfg: dict, fleet: Fleet, seed: int = 0,
) -> Tuple[dict, Dict[str, float]]:
    """Drives ONE GreedyHAP episode with estimator="count" (the clean,
    non-circular channel -- mirrors a classified count at commissioning),
    both computing ATT/AQL/TP/PWD for that episode AND accumulating each
    movement's true_counts to fit a_bar_m = fleet.a_bar_for(shares).
    Movements never observed during the episode are simply absent from the
    returned dict; src/env.py falls back to the global fleet.a_bar for
    those. Returns (metrics_dict, a_bar_per_movement)."""
    env = HAPLightEnv(str(rundir), cfg, fleet, seed=seed, eta=0.0, estimator="count")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        totals: Dict[str, Dict[str, float]] = {}
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                for mv, counts in info["true_counts"][i].items():
                    bucket = totals.setdefault(mv, {})
                    for cls, n in counts.items():
                        bucket[cls] = bucket.get(cls, 0.0) + n

        trips = env.completed_trips()
        m = metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        metrics_out = {"trips": len(trips), "att": m["att"], "aql": m["aql"], "tp": m["tp"], "pwd": m["pwd"]}

        a_bar_m: Dict[str, float] = {}
        for mv, counts in totals.items():
            mass = sum(counts.values())
            if mass > 0:
                a_bar_m[mv] = fleet.a_bar_for(counts)
        return metrics_out, a_bar_m
    finally:
        env.close()


def run_area_episode(rundir: Path, cfg: dict, fleet: Fleet, seed: int = 0) -> dict:
    """Same as above but estimator="area" and no calibration bookkeeping --
    used for the "global" row (no a_bar_per_movement.json present in
    rundir) and the "per-movement" / "stale" rows (json written first)."""
    env = HAPLightEnv(str(rundir), cfg, fleet, seed=seed, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
        trips = env.completed_trips()
        m = metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        return {"trips": len(trips), "att": m["att"], "aql": m["aql"], "tp": m["tp"], "pwd": m["pwd"]}
    finally:
        env.close()


# --------------------------------------------------------------------------
# Part A deliverable: three-way table + staleness row
# --------------------------------------------------------------------------


def three_way_sweep(
    cfg: dict, fleet: Fleet, nets_dir: Path, workdir: Path,
    dispersions=THREE_WAY_DISPERSIONS, episode_s: float = 1800.0, seed: int = 0,
) -> dict:
    scenario_key = "s1_arterial"
    name = SCENARIOS[scenario_key]
    nodes, edges, entry_edges, exit_edges, net_path = _prepare_net(scenario_key, cfg, nets_dir, workdir)

    nominal = (cfg.get("demand", {}) or {}).get("scale_nominal") or {}
    scale = nominal.get(scenario_key)
    if scale is None:
        print("  (no calibrated demand.scale_nominal.s1_arterial -- using 1.0; "
              "run scripts/calibrate_demand.py first for a meaningful result)")
        scale = 1.0

    cfg_run = copy.deepcopy(cfg)
    cfg_run["demand"]["episode_length_s"] = episode_s

    print(f"\nPer-movement estimator calibration -- three-way sweep on S1 "
          f"(scale={scale:.3f}, episode={episode_s:.0f}s)")
    print(f"  {'d':>5s} {'estimator':>13s} {'ATT':>8s} {'AQL':>8s} {'TP':>8s} {'PWD':>8s}")

    calibrations: Dict[float, Dict[str, float]] = {}
    rows = []
    for d in dispersions:
        od_pairs, _, _, fractions, od_shares = _od_setup(cfg, fleet, nodes, edges, entry_edges, exit_edges, d)
        rundir = workdir / f"d{d}"
        _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, rundir)

        global_m = run_area_episode(rundir, cfg_run, fleet, seed=seed)
        print(f"  {d:5.2f} {'global':>13s} {global_m['att']:8.1f} {global_m['aql']:8.2f} "
              f"{global_m['tp']:8.1f} {global_m['pwd']:8.2f}")

        count_m, a_bar_m = run_count_episode_and_calibrate(rundir, cfg_run, fleet, seed=seed)
        print(f"  {d:5.2f} {'count':>13s} {count_m['att']:8.1f} {count_m['aql']:8.2f} "
              f"{count_m['tp']:8.1f} {count_m['pwd']:8.2f}")
        calibrations[d] = a_bar_m

        (rundir / "a_bar_per_movement.json").write_text(json.dumps(a_bar_m, indent=2))
        permv_m = run_area_episode(rundir, cfg_run, fleet, seed=seed)
        print(f"  {d:5.2f} {'per-movement':>13s} {permv_m['att']:8.1f} {permv_m['aql']:8.2f} "
              f"{permv_m['tp']:8.1f} {permv_m['pwd']:8.2f}")

        area_gap = abs(permv_m["tp"] - count_m["tp"]) / count_m["tp"] if count_m["tp"] else float("nan")
        rows.append({
            "dispersion": d, "global": global_m, "count": count_m, "per_movement": permv_m,
            "n_calibrated_movements": len(a_bar_m),
            "per_movement_tp_gap_vs_count": area_gap,
        })

    # Staleness row: reuse the calibration fitted at STALE_CALIBRATED_AT,
    # apply it to a rundir built at STALE_EVALUATED_AT.
    stale_cal = calibrations.get(STALE_CALIBRATED_AT)
    stale_row = None
    if stale_cal is not None:
        od_pairs, _, _, fractions, od_shares = _od_setup(
            cfg, fleet, nodes, edges, entry_edges, exit_edges, STALE_EVALUATED_AT
        )
        stale_rundir = workdir / f"stale_cal{STALE_CALIBRATED_AT}_eval{STALE_EVALUATED_AT}"
        _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, stale_rundir)
        (stale_rundir / "a_bar_per_movement.json").write_text(json.dumps(stale_cal, indent=2))
        stale_row = run_area_episode(stale_rundir, cfg_run, fleet, seed=seed)
        print(
            f"\nStaleness check: a_bar_m calibrated at d={STALE_CALIBRATED_AT}, "
            f"evaluated at d={STALE_EVALUATED_AT} (composition has drifted since "
            f"commissioning):\n"
            f"  {'':5s} {'estimator':>13s} {'ATT':>8s} {'AQL':>8s} {'TP':>8s} {'PWD':>8s}"
        )
        print(f"  {'':5s} {'stale-permv':>13s} {stale_row['att']:8.1f} {stale_row['aql']:8.2f} "
              f"{stale_row['tp']:8.1f} {stale_row['pwd']:8.2f}")
        fresh = next(r for r in rows if r["dispersion"] == STALE_EVALUATED_AT)
        print(
            f"  (fresh per-movement calibration AT d={STALE_EVALUATED_AT} for comparison: "
            f"ATT={fresh['per_movement']['att']:.1f} AQL={fresh['per_movement']['aql']:.2f} "
            f"TP={fresh['per_movement']['tp']:.1f} PWD={fresh['per_movement']['pwd']:.2f})"
        )

    return {"rows": rows, "stale_row": stale_row, "calibrations": calibrations}


# --------------------------------------------------------------------------
# Production install: write a_bar_per_movement.json into nets/<scenario>/
# --------------------------------------------------------------------------


def calibrate_and_install(
    scenario_key: str, cfg: dict, fleet: Fleet, nets_dir: Path, seed: int = 0,
) -> Dict[str, float]:
    """The "deployed" calibration: one full-length (cfg's actual
    episode_length_s, not a shortened sweep episode -- genuinely mirroring
    a one-hour classified count) estimator="count" episode at the
    scenario's own scale_nominal and the config's default
    composition_dispersion, written directly into nets/<scenario>/
    alongside the persistent net -- this is what src/env.py auto-loads by
    default from here on for any run pointed at that net_dir."""
    name = SCENARIOS[scenario_key]
    net_dir = nets_dir / name
    nodes, edges, entry_edges, exit_edges, net_path = _prepare_net(scenario_key, cfg, nets_dir, net_dir)

    nominal = (cfg.get("demand", {}) or {}).get("scale_nominal") or {}
    scale = nominal.get(scenario_key, 1.0)
    dispersion = cfg["demand"].get("composition_dispersion", 0.5)
    od_pairs, _, _, _, od_shares = _od_setup(cfg, fleet, nodes, edges, entry_edges, exit_edges, dispersion)

    with tempfile.TemporaryDirectory(prefix=f"haplight_install_{name}_") as td:
        rundir = Path(td)
        _write_run(name, net_path, fleet, cfg, od_pairs, od_shares, scale, rundir)
        _, a_bar_m = run_count_episode_and_calibrate(rundir, cfg, fleet, seed=seed)

    out_path = net_dir / "a_bar_per_movement.json"
    out_path.write_text(json.dumps(a_bar_m, indent=2))
    print(
        f"Installed {out_path} -- {len(a_bar_m)} movements calibrated "
        f"(scale={scale:.3f}, dispersion={dispersion:.2f})"
    )
    return a_bar_m


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--nets", default="nets")
    ap.add_argument("--episode-s", type=float, default=1800.0, help="diagnostic three-way sweep episode length")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quick", action="store_true", help="short episode -- smoke test only")
    ap.add_argument("--no-install", action="store_true", help="run the sweep only; don't write nets/<scenario>/a_bar_per_movement.json")
    args = ap.parse_args()

    config_path = Path(args.config)
    cfg = yaml.safe_load(config_path.read_text())
    nets_dir = Path(args.nets)
    fleet = Fleet.from_config(cfg)
    episode_s = 300.0 if args.quick else args.episode_s

    with tempfile.TemporaryDirectory(prefix="haplight_estcal_") as td:
        workdir = Path(td)
        three_way_sweep(cfg, fleet, nets_dir, workdir, episode_s=episode_s, seed=args.seed)

    if not args.no_install:
        print()
        for sk in ("s1_arterial", "s2_grid"):
            calibrate_and_install(sk, cfg, fleet, nets_dir, seed=args.seed)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
