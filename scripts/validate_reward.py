"""
Reward validity test (PLAN.md Phase 4, PAPER_CHANGELOG P4-3).

A training reward is only useful if it ranks controllers the same way the
metrics the paper actually cares about (AQL, throughput) do -- otherwise the
RL objective is not aligned with the paper's own evaluation protocol, and no
amount of training budget fixes that (a well-trained policy under a
misaligned reward is a well-trained wrong thing). This is a NO-TRAINING,
~1-2 minute check: one paired episode each for FixedTime, MaxPressure,
GreedyHAP, a uniform-random policy, and random+SafetyFilter, all at the same
eta~U[0,0.6] draw and the same demand/seed realisation (P1c-3 paired
methodology) -- reward-return is reported alongside ATT/AQL/throughput, and
the Spearman rank correlation between reward-return and each of (-AQL,
throughput) is the pass/fail signal.

PERMANENT GATE: every rl.reward.form candidate must be run through this
script and reported before any training run uses it (author instruction,
2026-08-10). A reward that fails here (rank correlation well short of 1.0,
or the wrong sign) is not a training problem to fix with more iterations --
it is a reward-design problem to fix before spending any training budget.

Usage
-----
    python -m scripts.validate_reward --scenario s1 --reward-form pressure_all
    python -m scripts.validate_reward --scenario s1 --all-forms
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import metrics  # noqa: E402
from src.controllers import Controller, FixedTime, GreedyHAP, MaxPressure  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402
from src.safety_filter import SafetyFilter, calibrate_threshold  # noqa: E402

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}
REWARD_FORMS = ["pressure_all", "total_queue", "served_pressure", "pressure_raw"]


class RandomPolicy(Controller):
    """Uniform-random legal action every step. Deliberately non-adaptive --
    the sharpest available probe of how much of a controller's reward-return
    is the safety filter's certified floor (Remark 6) rather than anything
    resembling good control, and a control arm for the rank-correlation test
    itself (a valid reward should rank Random well below every classical
    controller, not merely below GreedyHAP)."""

    def __init__(self, env, seed: int):
        self.env = env
        self._seed = seed
        self.rng: Optional[np.random.Generator] = None

    def reset(self) -> None:
        self.rng = np.random.default_rng(self._seed)

    def act(self, obs, info) -> Dict[str, int]:
        actions = {}
        for i in self.env.intersections:
            allowed = np.flatnonzero(info["action_masks"][i])
            actions[i] = int(self.rng.choice(allowed))
        return actions


def _run_episode(env, controller, safety_filter=None) -> Tuple[float, float]:
    """Drives one full episode. Returns (reward_return, filter_activation):
    reward_return is env.step()'s own reward summed per intersection over
    the episode, then averaged across intersections -- the IDENTICAL
    convention scripts/train.py::_episode_return uses, so numbers here are
    directly comparable to a training run's logged returns."""
    obs = env.reset()
    controller.reset()
    info = env.info
    total = {i: 0.0 for i in env.intersections}
    n_active = n_total = 0
    truncated = False
    while not truncated:
        proposed = controller.act(obs, info)
        if safety_filter is not None:
            actions, filter_active = safety_filter.apply(obs, info, proposed)
            n_total += len(env.intersections)
            n_active += sum(filter_active.values())
        else:
            actions = proposed
        obs, reward, truncated, info = env.step(actions)
        for i in env.intersections:
            total[i] += reward[i]
    reward_return = float(np.mean(list(total.values())))
    activation = (n_active / n_total) if n_total else float("nan")
    return reward_return, activation


def validate_one_form(
    cfg: dict, net_dir: Path, fleet: Fleet, seed: int, reward_form: str,
) -> dict:
    cfg = dict(cfg)
    cfg["rl"] = dict(cfg["rl"])
    cfg["rl"]["reward"] = dict(cfg["rl"]["reward"])
    cfg["rl"]["reward"]["form"] = reward_form

    # eta ~ U[0, 0.6], drawn ONCE and shared by every controller below so the
    # comparison is paired -- same demand realisation, same sensing-noise
    # draw, only the controller (and what it does with the same information)
    # differs.
    rng = np.random.default_rng(seed)
    eta = float(rng.uniform(0.0, 0.6))

    # B is a property of the SENSED channel only (x_hat/w_hat), independent
    # of reward_form -- calibrated once per form for isolation, cheap (one
    # GreedyHAP episode).
    B = calibrate_threshold(str(net_dir), cfg, fleet, seed=seed)

    def _fixed_time(env):
        return FixedTime(env, cfg, fleet, net_dir=str(net_dir)), None

    def _max_pressure(env):
        return MaxPressure(env), None

    def _greedy_hap(env):
        return GreedyHAP(env), None

    def _random(env):
        return RandomPolicy(env, seed), None

    def _random_filter(env):
        return RandomPolicy(env, seed), SafetyFilter(env, B)

    builders = {
        "FixedTime": _fixed_time,
        "MaxPressure": _max_pressure,
        "GreedyHAP": _greedy_hap,
        "Random": _random,
        "Random+Filter": _random_filter,
    }

    rows: List[dict] = []
    for name, build in builders.items():
        env = HAPLightEnv(str(net_dir), cfg, fleet, seed=seed, eta=eta, estimator="area")
        try:
            controller, safety_filter = build(env)
            reward_return, activation = _run_episode(env, controller, safety_filter)
            m = metrics.compute(
                env.completed_trips(), env.true_queue_history(), fleet, cfg,
                env.gmax_activation_rate(),
                filter_activation_rate=activation if not np.isnan(activation) else 0.0,
            )
        finally:
            env.close()
        rows.append({
            "controller": name,
            "reward_return": reward_return,
            "att": m["att"],
            "aql": m["aql"],
            "tp": m["tp"],
            "filter_activation": activation,
        })

    returns = [r["reward_return"] for r in rows]
    aqls = [r["aql"] for r in rows]
    tps = [r["tp"] for r in rows]
    # AQL: lower is better -- correlate reward against -AQL so a healthy
    # reward gives POSITIVE correlation against both quantities.
    rho_aql = float(spearmanr(returns, [-a for a in aqls]).correlation)
    rho_tp = float(spearmanr(returns, tps).correlation)

    # PAPER_CHANGELOG P5-1: exact `== 1.0` rejected a genuinely-perfect
    # rank correlation (pressure_raw's first passing run measured
    # 0.9999999999999999 on both -- confirmed via direct JSON inspection
    # this is scipy.stats.spearmanr's own floating-point arithmetic on a
    # PERFECTLY monotonic 5-point ranking, not a real one-rank discrepancy;
    # a hand-check of the same 5 (return, -aql)/(return, tp) pairs confirms
    # identical rank order in both). Tolerance-based comparison instead --
    # this is a numerical-precision fix to the gate itself, not a loosening
    # of what counts as "rank-consistent": the docstring's own bar is
    # "well short of 1.0," and 1e-9 is far tighter than that.
    passes = bool(rho_aql > 1.0 - 1e-9 and rho_tp > 1.0 - 1e-9)

    return {
        "reward_form": reward_form,
        "B": B,
        "eta": eta,
        "seed": seed,
        "rows": rows,
        "rho_reward_vs_neg_aql": rho_aql,
        "rho_reward_vs_tp": rho_tp,
        "passes": passes,
    }


def _print_table(result: dict) -> None:
    print(f"\n=== reward_form = {result['reward_form']}  (eta={result['eta']:.3f}, B={result['B']:.2f}, seed={result['seed']}) ===")
    header = f"{'controller':<16}{'reward_return':>16}{'att':>10}{'aql':>10}{'tp':>10}{'filter%':>10}"
    print(header)
    print("-" * len(header))
    for r in result["rows"]:
        fa = "" if np.isnan(r["filter_activation"]) else f"{100*r['filter_activation']:.1f}"
        print(f"{r['controller']:<16}{r['reward_return']:>16.2f}{r['att']:>10.1f}{r['aql']:>10.1f}{r['tp']:>10.1f}{fa:>10}")
    print(f"Spearman rho(reward, -AQL)       = {result['rho_reward_vs_neg_aql']:+.3f}")
    print(f"Spearman rho(reward, throughput) = {result['rho_reward_vs_tp']:+.3f}")
    verdict = "PASS -- rank-consistent with AQL and throughput" if result["passes"] \
        else "FAIL -- reward ranks controllers differently from AQL/throughput"
    print(f"Verdict: {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], default="s1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--reward-form", choices=REWARD_FORMS, default="pressure_all")
    ap.add_argument("--all-forms", action="store_true", help="run all three reward forms, one comparison table each")
    ap.add_argument("--out", default="results/reward_validation.json")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    net_dir = Path("nets") / SCENARIO_NET[args.scenario]
    a_bar_path = net_dir / "a_bar_per_movement.json"
    assert a_bar_path.exists(), f"{a_bar_path} missing -- run scripts/calibrate_estimator.py first."
    fleet = Fleet.from_config(cfg)

    forms = REWARD_FORMS if args.all_forms else [args.reward_form]
    results = []
    for form in forms:
        result = validate_one_form(cfg, net_dir, fleet, args.seed, form)
        _print_table(result)
        results.append(result)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    return 0 if all(r["passes"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
