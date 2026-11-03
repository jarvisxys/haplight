"""
Effective decision-rate diagnostic (PAPER_CHANGELOG P4-6).

With decision_interval_s=5 and min_green_s=10, a phase switch forces the
next ceil(g_min/dt)=2 decisions to a single legal action (the mask has only
the just-selected phase available until g_min elapses) -- the learner
cannot influence those steps at all. How much this caps what the policy can
contribute depends on how often the controller switches, which is
behaviour-dependent, not fixed by g_min/dt alone -- measured empirically
here, not computed analytically, for both a representative classical
controller (GreedyHAP) and a trained checkpoint if one is given.

Usage
-----
    python -m scripts.measure_decision_rate --scenario s1
    python -m scripts.measure_decision_rate --scenario s1 --checkpoint results/<run>/checkpoint.pt
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


def _measure(env, controller, safety_filter=None) -> dict:
    obs = env.reset()
    controller.reset()
    info = env.info
    n_free = n_total = n_switches = 0
    truncated = False
    while not truncated:
        for i in env.intersections:
            n_total += 1
            if int(info["action_masks"][i].sum()) > 1:
                n_free += 1
        proposed = controller.act(obs, info)
        if safety_filter is not None:
            actions, _ = safety_filter.apply(obs, info, proposed)
        else:
            actions = proposed
        for i in env.intersections:
            if actions[i] != info["current_phase"][i]:
                n_switches += 1
        obs, reward, truncated, info = env.step(actions)
    return {"n_free": n_free, "n_total": n_total, "n_switches": n_switches}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], default="s1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eta", type=float, default=0.0)
    ap.add_argument("--checkpoint", default=None, help="if given, also measures the trained policy (+filter)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    net_dir = Path("nets") / SCENARIO_NET[args.scenario]
    fleet = Fleet.from_config(cfg)

    print(f"decision_interval_s={cfg['signal']['decision_interval_s']}  min_green_s={cfg['signal']['min_green_s']}")

    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=args.seed, eta=args.eta, estimator="area")
    try:
        stats = _measure(env, GreedyHAP(env))
    finally:
        env.close()
    frac = stats["n_free"] / stats["n_total"]
    print(f"GreedyHAP: {stats['n_free']}/{stats['n_total']} decisions had >1 valid action "
          f"({frac:.1%} free, {1 - frac:.1%} forced) -- {stats['n_switches']} switches")

    if args.checkpoint:
        policy = HAPLightPolicy(cfg)
        ckpt = torch.load(args.checkpoint, map_location="cpu")
        policy.load_state_dict(ckpt["policy"])
        policy.eval()
        B = calibrate_threshold(str(net_dir), cfg, fleet, seed=args.seed)

        class _PolicyController:
            def __init__(self, env):
                self.env = env
                self.phase_idx = None

            def reset(self):
                # env.movements/env.phases are only populated after env's
                # own reset() (topology discovery happens there) -- build
                # lazily here, not in __init__.
                self.phase_idx = {i: movement_index_phases(env.movements[i], env.phases[i]) for i in env.intersections}

            def act(self, obs, info):
                actions = {}
                for i in self.env.intersections:
                    a, _, _ = select_action(policy, obs[i], self.phase_idx[i], info["action_masks"][i], deterministic=True)
                    actions[i] = a
                return actions

        env = HAPLightEnv(str(net_dir), cfg, fleet, seed=args.seed, eta=args.eta, estimator="area")
        try:
            ctrl = _PolicyController(env)
            filt = SafetyFilter(env, B)
            stats = _measure(env, ctrl, filt)
        finally:
            env.close()
        frac = stats["n_free"] / stats["n_total"]
        print(f"Trained policy (iter {ckpt['iteration']}) + filter: {stats['n_free']}/{stats['n_total']} "
              f"decisions had >1 valid action ({frac:.1%} free, {1 - frac:.1%} forced) -- {stats['n_switches']} switches")

    return 0


if __name__ == "__main__":
    sys.exit(main())
