"""
Spillback-deadlock diagnostic (PLAN.md Phase 4c, PAPER_CHANGELOG P4c-1/P4c-2).

Runs ONE deterministic episode and logs, every `--log-every` decision steps:
true total queue, in-network vehicle count, pending (insertion-backlog)
count, and the WORST per-movement storage occupancy fraction (x_m /
env.storage[i][mv]) network-wide, plus which movement it is. This is what
makes the deadlock mechanism visible: a movement pinned near 100% of its
OWN physical storage while total queue explodes is a structural spillback
deadlock, not merely heavy congestion (which would show high queues but no
single movement saturating its own storage).

Built to reproduce two known cases exactly:
  - P4-6's S1 GreedyHAP outlier: seed 119691546, eta=0.0 (ep=3 of the
    original n=16 greedy-HAP reference check).
  - P4-7's S2 trained-policy outlier: seed 779452647, eta=0.0, iteration-39
    checkpoint of results/s2_seed0_1787236381.

Usage
-----
    python -m scripts.diagnose_gridlock --scenario s1 --seed 119691546 --eta 0.0 --controller greedy
    python -m scripts.diagnose_gridlock --scenario s1 --seed 119691546 --eta 0.0 --controller greedy-storage-aware
    python -m scripts.diagnose_gridlock --scenario s2 --seed 779452647 --eta 0.0 --controller policy --checkpoint results/s2_seed0_1787236381/checkpoint.pt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402
from src.policy import HAPLightPolicy, movement_index_phases  # noqa: E402
from src.ppo import select_action  # noqa: E402
from src.safety_filter import SafetyFilter, calibrate_threshold  # noqa: E402

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}


class _PolicyController:
    """Deterministic trained-policy+filter controller, matching exactly how
    scripts/train.py's eta=0 clean eval drives the env."""

    def __init__(self, env, policy, filt):
        self.env = env
        self.policy = policy
        self.filt = filt
        self.phase_idx = {i: movement_index_phases(env.movements[i], env.phases[i]) for i in env.intersections}
        self.n_active = 0
        self.n_total = 0

    def reset(self) -> None:
        pass

    def act(self, obs, info):
        proposed = {}
        for i in self.env.intersections:
            a, _, _ = select_action(self.policy, obs[i], self.phase_idx[i], info["action_masks"][i], deterministic=True)
            proposed[i] = a
        actions, filter_active = self.filt.apply(obs, info, proposed)
        self.n_total += len(self.env.intersections)
        self.n_active += sum(filter_active.values())
        return actions


def worst_storage_occupancy(env, info):
    """(intersection, movement, x_m/storage_m) for whichever movement is
    closest to (or over) its OWN physical storage capacity right now."""
    worst = (None, None, -1.0)
    for i in env.intersections:
        for mv in env.movements[i]:
            cap = env.storage[i].get(mv, 0.0)
            if cap <= 0:
                continue
            frac = info["true_queues"][i][mv] / cap
            if frac > worst[2]:
                worst = (i, mv, frac)
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--eta", type=float, default=0.0)
    ap.add_argument("--controller", choices=["greedy", "greedy-storage-aware", "policy"], required=True)
    ap.add_argument("--checkpoint", default=None, help="required for --controller policy")
    ap.add_argument("--theta", type=float, default=None, help="override hap.storage_aware_theta")
    ap.add_argument("--storage-triggered-filter", action="store_true",
                     help="--controller policy only: OR a storage-occupancy trigger into the SafetyFilter (P4c-4)")
    ap.add_argument("--storage-threshold", type=float, default=None, help="override rl.filter.storage_trigger_threshold")
    ap.add_argument("--fallback-storage-aware", action="store_true",
                     help="--controller policy only: SafetyFilter's fallback GreedyHAP uses storage-aware pressure (P4c-7/P4c-9)")
    ap.add_argument("--hysteresis", action="store_true", help="engage-and-commit: release gap + minimum dwell (P4c-11)")
    ap.add_argument("--gap", type=float, default=0.10, help="release threshold = engage threshold - gap")
    ap.add_argument("--min-dwell", type=int, default=3)
    ap.add_argument("--B", type=float, default=None,
                     help="PAPER_CHANGELOG P4c-12: pre-computed filter threshold B. If omitted, this script "
                          "calibrates B itself via a GreedyHAP episode run in THIS process immediately before "
                          "the main test episode -- confirmed to perturb the main episode's outcome (two "
                          "sequential libsumo simulation loads in one process do not fully reset some internal "
                          "state, even with an explicit --seed on the second). scripts/train.py/evaluate_policy.py/"
                          "sweep_storage_threshold.py all calibrate B once, decoupled from every test episode, "
                          "and are NOT affected -- pass --B explicitly here to match that and get a trustworthy "
                          "single-episode reproduction of a sweep result.")
    ap.add_argument("--log-every", type=int, default=120, help="decision steps between log rows (120 * dt=5s = 600s)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    net_dir = Path("nets") / SCENARIO_NET[args.scenario]
    fleet = Fleet.from_config(cfg)

    # calibrate_threshold() opens and closes its OWN libsumo instance -- it
    # must run before the main env below is constructed/reset, since libsumo
    # is a single in-process simulation engine and does not support two
    # overlapping open instances (confirmed: doing this the other way round
    # crashes the main env's first step() with "network was not yet
    # constructed", since calibrate_threshold's own env.close() tears down
    # the process-wide libsumo state the main env had already built).
    policy = None
    B = None
    if args.controller == "policy":
        assert args.checkpoint, "--controller policy requires --checkpoint"
        policy = HAPLightPolicy(cfg)
        ckpt = torch.load(args.checkpoint, map_location="cpu")
        policy.load_state_dict(ckpt["policy"])
        policy.eval()
        B = args.B if args.B is not None else calibrate_threshold(str(net_dir), cfg, fleet, seed=0)

    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=args.seed, eta=args.eta, estimator="area")
    try:
        obs = env.reset()
        info = env.info

        if args.controller == "greedy":
            controller = GreedyHAP(env, storage_aware=False)
        elif args.controller == "greedy-storage-aware":
            controller = GreedyHAP(env, storage_aware=True, theta=args.theta)
        else:
            storage_threshold = args.storage_threshold if args.storage_threshold is not None else cfg["rl"]["filter"].get("storage_trigger_threshold", 0.85)
            filt = SafetyFilter(
                env, B, storage_aware=args.storage_triggered_filter,
                storage_threshold=storage_threshold,
                fallback_storage_aware=args.fallback_storage_aware,
                hysteresis=args.hysteresis,
                storage_threshold_low=max(0.0, storage_threshold - args.gap),
                min_dwell=args.min_dwell,
            )
            controller = _PolicyController(env, policy, filt)
        controller.reset()

        print(f"scenario={args.scenario} seed={args.seed} eta={args.eta} controller={args.controller}"
              + (f" storage_triggered_filter=True threshold={filt.storage_threshold}" if args.controller == "policy" and args.storage_triggered_filter else "")
              + (f" fallback_storage_aware={args.fallback_storage_aware}" if args.controller == "policy" else "")
              + (f" theta={args.theta}" if args.theta is not None else ""))
        header = f"{'sim_time':>8}{'pending':>8}{'in_net':>8}{'compl_tp':>9}{'true_q':>10}{'worst_occ':>11}  worst_movement"
        print(header)

        step = 0
        truncated = False
        max_true_q = 0.0
        max_worst_occ = 0.0
        while not truncated:
            actions = controller.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            if step % args.log_every == 0 or truncated:
                tq = sum(sum(info["true_queues"][i].values()) for i in env.intersections)
                wi, wmv, wfrac = worst_storage_occupancy(env, info)
                max_true_q = max(max_true_q, tq)
                max_worst_occ = max(max_worst_occ, wfrac)
                print(f"{step * env.dt:8.0f}{env.pending_count():8d}{env.in_network_count():8d}"
                      f"{len(env.completed_trips()):9d}{tq:10.1f}{wfrac:11.1%}  {wi}/{wmv}")
            step += 1

        final_tq = sum(sum(info["true_queues"][i].values()) for i in env.intersections)
        activation = f"  filter_activation={controller.n_active / max(1, controller.n_total):.1%}" if args.controller == "policy" else ""
        print(f"\nfinal true_total_queue={final_tq:.1f}  max true_total_queue={max_true_q:.1f}  "
              f"max worst-movement storage occupancy={max_worst_occ:.1%}  "
              f"completed_tp={len(env.completed_trips())}  final_pending={env.pending_count()}{activation}")
    finally:
        env.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
