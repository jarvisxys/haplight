"""
Multi-seed threshold sweep for the (storage, storage) filter configuration
(PLAN.md Phase 4c, PAPER_CHANGELOG P4c-10).

P4c-9 found (storage, storage) -- storage-aware pressure AND a storage-
triggered filter with a storage-aware fallback -- is the unique
combination healthy on BOTH known deadlock seeds. But "healthy on the two
seeds that found the mechanism" is not "safe to deploy": P4c-8's
regression was caused by exactly this mistake (an unmeasured 0.85
threshold). This sweeps the trigger threshold across MULTIPLE seeds per
scenario, most of them fresh (not selected for being known-bad), to find
the threshold that holds across every tested seed.

Measured at eta=0 (deterministic) deliberately: this is the tie-locking,
worst-case sensing condition (P4-6/P1-1) -- ANY sensing noise (P4-6 showed
even eta=0.01 breaks these ties) gives strictly more margin, so this
sweep is a LOWER BOUND on the real operational threshold, not the
operational value itself.

"Deadlock" classification (pre-registered before running, not fit to the
results after): final_pending > 0 -- the insertion backlog never clears
by episode end. Zero in every healthy trace examined across P4c-2 through
P4c-9; strictly positive in every confirmed deadlock trace. No borderline
case has been observed where this disagreed with a qualitative read of
the trace.

Usage
-----
    python -m scripts.sweep_storage_threshold --scenario s1 --checkpoint results/s1_seed0_1786387277/checkpoint.pt --seeds 0 1 2 3 4 5 6 7 8 9
    python -m scripts.sweep_storage_threshold --scenario s2 --checkpoint results/s2_seed0_1787236381/checkpoint.pt --seeds 779452647 0 1 2 3 4 5 6 7 8
"""
from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import os
import sys
from pathlib import Path
from typing import Dict, List

import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402
from src.policy import HAPLightPolicy, movement_index_phases  # noqa: E402
from src.ppo import select_action  # noqa: E402
from src.safety_filter import SafetyFilter, calibrate_threshold  # noqa: E402

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}


def is_deadlock(final_pending: int) -> bool:
    return final_pending > 0


def run_one(
    policy_state_dict: dict, cfg: dict, net_dir: str, B: float,
    seed: int, eta: float, threshold: float,
    hysteresis: bool = False, gap: float = 0.10, min_dwell: int = 3,
) -> dict:
    """One episode: trained policy + (storage, storage) filter at a given
    threshold. Module-level and picklable so multiprocessing (spawn) can
    call it directly (matches scripts/train.py's own worker convention).

    `hysteresis`/`gap`/`min_dwell` (PAPER_CHANGELOG P4c-11): `threshold` is
    swept as the ENGAGE (high) threshold; the release (low) threshold
    tracks it at a fixed gap below, so each swept point represents a
    fixed-width hysteresis band centred at a different point, not just a
    single moving boundary."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    fleet = Fleet.from_config(cfg)
    policy = HAPLightPolicy(cfg)
    policy.load_state_dict(policy_state_dict)
    policy.eval()

    env = HAPLightEnv(net_dir, cfg, fleet, seed=seed, eta=eta, estimator="area")
    try:
        obs = env.reset()
        info = env.info
        filt = SafetyFilter(
            env, B, storage_aware=True, storage_threshold=threshold,
            fallback_storage_aware=True,
            hysteresis=hysteresis, storage_threshold_low=max(0.0, threshold - gap),
            min_dwell=min_dwell,
        )
        phase_idx = {i: movement_index_phases(env.movements[i], env.phases[i]) for i in env.intersections}

        n_active = n_total = 0
        truncated = False
        while not truncated:
            proposed: Dict[str, int] = {}
            for i in env.intersections:
                a, _, _ = select_action(policy, obs[i], phase_idx[i], info["action_masks"][i], deterministic=True)
                proposed[i] = a
            actions, filter_active = filt.apply(obs, info, proposed)
            n_total += len(env.intersections)
            n_active += sum(filter_active.values())
            obs, reward, truncated, info = env.step(actions)

        final_tq = sum(sum(info["true_queues"][i].values()) for i in env.intersections)
        return {
            "seed": seed, "threshold": threshold,
            "final_queue": final_tq, "throughput": len(env.completed_trips()),
            "final_pending": env.pending_count(),
            "filter_activation": n_active / max(1, n_total),
        }
    finally:
        env.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--thresholds", type=float, nargs="+", default=[0.60, 0.70, 0.80, 0.85, 0.90, 0.95])
    ap.add_argument("--eta", type=float, default=0.0)
    ap.add_argument("--n-workers", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--hysteresis", action="store_true", help="engage-and-commit: fixed release gap below threshold + minimum dwell (P4c-11)")
    ap.add_argument("--gap", type=float, default=0.10, help="release threshold = engage threshold - gap")
    ap.add_argument("--min-dwell", type=int, default=3)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    net_dir = Path("nets") / SCENARIO_NET[args.scenario]
    fleet = Fleet.from_config(cfg)
    n_workers = args.n_workers or max(1, (os.cpu_count() or 2) - 1)

    policy = HAPLightPolicy(cfg)
    ckpt = torch.load(args.checkpoint, map_location="cpu")
    policy.load_state_dict(ckpt["policy"])
    policy.eval()
    state_dict = {k: v.detach().cpu().clone() for k, v in policy.state_dict().items()}

    # B depends only on scenario (calibrated once against GreedyHAP at
    # nominal demand, seed=0, fixed) -- NOT on the test seed/threshold, so
    # this happens once, not per (seed, threshold) pair.
    B = calibrate_threshold(str(net_dir), cfg, fleet, seed=0)
    print(f"scenario={args.scenario} checkpoint={args.checkpoint} B={B:.3f} eta={args.eta}")
    print(f"seeds={args.seeds}")
    print(f"thresholds={args.thresholds}")
    print(f"hysteresis={args.hysteresis} gap={args.gap} min_dwell={args.min_dwell}")
    print(f"{len(args.seeds) * len(args.thresholds)} runs, {n_workers} parallel workers\n")

    jobs = [
        (state_dict, cfg, str(net_dir), B, seed, args.eta, th, args.hysteresis, args.gap, args.min_dwell)
        for seed in args.seeds for th in args.thresholds
    ]
    ctx = mp.get_context("spawn")
    # PAPER_CHANGELOG P4c-14: CONFIRMED, not hypothesised -- a worker process
    # reused across multiple sequential trials (Pool's default behaviour)
    # contaminates later trials with state from earlier ones in the SAME
    # process (direct test: (seed=6, threshold=0.85) flips from FAIL to OK
    # when run as a worker's 2nd job vs its 1st, with nothing else changed).
    # `maxtasksperchild=1` forces a genuinely fresh process, and therefore a
    # fresh libsumo instance, for every single trial -- no process, and
    # therefore no state, is ever reused across trials. This is slower
    # (process startup cost per trial instead of per worker) but the
    # correctness fix is more important than the speed loss.
    with ctx.Pool(processes=n_workers, maxtasksperchild=1) as pool:
        results = pool.starmap(run_one, jobs)

    for r in results:
        r["deadlock"] = is_deadlock(r["final_pending"])

    out_path = Path(args.out) if args.out else Path(f"results/threshold_sweep_{args.scenario}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["seed", "threshold", "final_queue", "throughput", "final_pending", "filter_activation", "deadlock"],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    by_seed: Dict[int, List[dict]] = {}
    for r in results:
        by_seed.setdefault(r["seed"], []).append(r)

    print(f"{'seed':>14}   per-threshold outcome")
    for seed in args.seeds:
        rows = sorted(by_seed[seed], key=lambda r: r["threshold"])
        outcome_str = " ".join(f"{r['threshold']:.2f}:{'OK' if not r['deadlock'] else 'FAIL'}" for r in rows)
        print(f"{seed:>14}   {outcome_str}")

    # CORRECT aggregation: safety is NOT guaranteed monotonic in the
    # threshold (confirmed empirically -- some seeds fail at isolated
    # threshold values with SAFE values on both sides, e.g. FAIL at 0.80,
    # OK at 0.85, FAIL at 0.90). "Highest value that happened to be safe
    # for this seed" is misleading if a LOWER, untested-as-worse value
    # actually fails -- the only sound question is, per THRESHOLD VALUE,
    # does it hold across every seed simultaneously.
    by_threshold: Dict[float, List[dict]] = {}
    for r in results:
        by_threshold.setdefault(r["threshold"], []).append(r)

    print(f"\n{'threshold':>12}   status")
    safe_at: List[float] = []
    for th in sorted(by_threshold):
        rows = by_threshold[th]
        fails = [r["seed"] for r in rows if r["deadlock"]]
        if fails:
            print(f"{th:>12.2f}   FAILS on seed(s): {fails}")
        else:
            print(f"{th:>12.2f}   safe across all {len(rows)} seeds")
            safe_at.append(th)

    print()
    if not safe_at:
        print("NO tested threshold is safe across every seed -- do not deploy any value from this grid.")
    else:
        # a threshold with an unsafe neighbour on either side (in the
        # tested grid) has no confirmed margin, even though it itself
        # passed -- flag this explicitly rather than reporting it as if
        # it were robustly safe.
        all_th = sorted(by_threshold)
        for th in safe_at:
            idx = all_th.index(th)
            lo_ok = idx == 0 or all_th[idx - 1] in safe_at
            hi_ok = idx == len(all_th) - 1 or all_th[idx + 1] in safe_at
            margin_note = "" if (lo_ok and hi_ok) else "  <-- flanked by a failing threshold in this grid, no confirmed margin"
            print(f"Safe at all seeds: {th:.2f}{margin_note}")

    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
