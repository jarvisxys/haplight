"""
Task-metrics evaluation (PLAN.md Phase 4 deliverable, PAPER_CHANGELOG P4-6).

The reward curve is a training diagnostic, not the paper's result -- this is
the actual deliverable table. Runs a trained checkpoint (HAPLight-RL, i.e.
the policy composed with the Corollary-1 SafetyFilter, exactly as deployed)
against FixedTime, MaxPressure and GreedyHAP on ATT/AWT/AQL/TP/PWD, 5 seeds,
at eta=0 and eta=0.6 (fixed conditions, not the training-time eta~U[0,0.6]
randomisation), with every controller sharing the same (seed, eta) demand
realisation per seed -- paired evidence, same methodology as P1c-3/P1c-4 --
so the reported HAPLight-RL vs GreedyHAP delta is a paired difference with
its own confidence interval, not a difference of independently-noisy means.

EPISODE ISOLATION (PAPER_CHANGELOG P4c-14/P4c-15): every episode runs in its
own freshly-spawned process (`multiprocessing.Pool(..., maxtasksperchild=1)`)
-- confirmed directly that running multiple episodes sequentially in one
process lets an earlier episode's libsumo/RNG state change a later episode's
outcome, even with an explicit seed on the later one (this is the THIRD
confirmed instance of the same defect: Phase-1 subscriptions-across-resets,
the P4c sweep's Pool worker reuse, and this script's old plain sequential
loop). See tests/test_episode_isolation.py for the standing automated gate.

Usage
-----
    python -m scripts.evaluate_policy --scenario s1 --checkpoint results/<run>/checkpoint.pt
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import torch
import yaml
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import metrics  # noqa: E402
from src.controllers import Controller, FixedTime, GreedyHAP, MaxPressure  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402
from src.policy import HAPLightPolicy, movement_index_phases  # noqa: E402
from src.ppo import select_action  # noqa: E402
from src.safety_filter import SafetyFilter, calibrate_threshold  # noqa: E402

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}
METRIC_KEYS = ["att", "awt", "aql", "tp", "pwd"]
GRIDLOCK_KEY = "gridlock"  # binary per-episode: env.pending_count() > 0 at truncation

# Phase 5 (PAPER_CHANGELOG P5-1): display name -> src.rl_baselines key.
# "colight" is ALWAYS displayed as the precise variant name -- this port is
# single-hop attention over raw sensed neighbour features, not multi-hop
# attention over neighbours' hidden embeddings, and must never be presented
# in a table as bare "CoLight".
BASELINE_DISPLAY = {
    "Advanced-MPLight": "advanced_mplight",
    "MPLight": "mplight",
    "CoLight-variant (single-hop attn)": "colight",
}
# HAPLight-RL appears TWICE on purpose (author instruction, Phase 5): the
# filtered entry is the deployed method; the unfiltered entry is the SAME
# trained policy with the Corollary-1 filter removed, which separates "our
# learned policy is good" from "our filter prevents deadlock" -- two
# distinct claims a reviewer will want disentangled, and free to report
# since only one policy was trained.
CONTROLLER_NAMES = [
    "FixedTime", "MaxPressure", "GreedyHAP",
    "HAPLight-RL", "HAPLight-RL (unfiltered)",
]
# Direction each metric is "better" in -- used only to sign the paired delta
# consistently (positive delta = HAPLight-RL better) in the printed table.
LOWER_IS_BETTER = {"att": True, "awt": True, "aql": True, "tp": False, "pwd": True}


def wilson_ci(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial rate k/n (z=1.96 default). Same
    formula used throughout the P4c deadlock-rate work -- no new dependency,
    honest at small n/rare-event counts where a normal-approximation CI can
    go negative or above 1."""
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z / denom) * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, center - half), min(1.0, center + half))


def matched_pairs_rank_biserial(diff: np.ndarray) -> float:
    """Matched-pairs rank-biserial correlation (Kerby 2014's "simple
    difference formula"): r = (W+ - W-) / (W+ + W-), the effect size that
    accompanies a Wilcoxon signed-rank test -- appropriate for PAIRED,
    non-parametric data (same seed/demand realisation for both
    controllers), unlike Cliff's delta which assumes independent samples.
    r in [-1, +1]; positive = the majority of rank-weight favours the first
    argument. Zero differences are dropped (matches scipy.stats.wilcoxon's
    default `zero_method='wilcox'`); returns 0.0 if nothing remains."""
    diff = diff[diff != 0]
    if len(diff) == 0:
        return 0.0
    ranks = sstats.rankdata(np.abs(diff))
    w_pos = float(ranks[diff > 0].sum())
    w_neg = float(ranks[diff < 0].sum())
    total = w_pos + w_neg
    return (w_pos - w_neg) / total if total > 0 else 0.0


def bca_ci(diff: np.ndarray, confidence: float = 0.95, n_resamples: int = 9999) -> tuple[float, float] | None:
    """BCa (bias-corrected and accelerated) bootstrap CI for the mean of
    paired differences -- more reliable than the normal-theory paired-t CI
    when the underlying distribution is skewed/heavy-tailed, which is
    exactly the shape a rare deadlock episode produces (P4c-15: GreedyHAP
    eta=0.6 seed=4 aql=7714 against a healthy-seed mean in the hundreds).
    Returns None if BCa is degenerate for this sample (e.g. zero variance,
    or scipy's acceleration estimate fails) rather than raising -- callers
    must handle None and report it as such, not silently fall back to a
    different method."""
    if len(diff) < 2 or np.allclose(diff, diff[0]):
        return None
    try:
        res = sstats.bootstrap(
            (diff,), np.mean, confidence_level=confidence, method="BCa",
            n_resamples=n_resamples, random_state=0,
        )
        return (float(res.confidence_interval.low), float(res.confidence_interval.high))
    except Exception:
        return None


class HAPLightRLController(Controller):
    """The trained policy composed with the Corollary-1 safety filter --
    this IS "HAPLight-RL" as deployed, not the bare policy network."""

    def __init__(
        self, env, policy: HAPLightPolicy, B: float, storage_aware: bool = False,
        fallback_storage_aware: bool = False, hysteresis: bool = False,
        storage_threshold: float | None = None, storage_threshold_low: float | None = None,
        min_dwell: int = 3, use_filter: bool = True,
    ):
        self.env = env
        self.policy = policy
        self.B = B
        # use_filter=False -> the SAME trained policy, filter removed
        # (PAPER_CHANGELOG P5-1). Not a separate training run: it isolates
        # the filter's own contribution to the deadlock-rate result.
        self.use_filter = use_filter
        self.storage_aware = storage_aware
        self.fallback_storage_aware = fallback_storage_aware
        self.hysteresis = hysteresis
        self.storage_threshold = storage_threshold
        self.storage_threshold_low = storage_threshold_low
        self.min_dwell = min_dwell
        self.filt = None
        self.phase_idx = None
        self._last_activation = 0.0

    def reset(self) -> None:
        # env.movements/env.phases are only populated after env's own
        # reset() (topology discovery happens there, not at construction) --
        # build lazily here, not in __init__.
        self.filt = SafetyFilter(
            self.env, self.B, storage_aware=self.storage_aware,
            storage_threshold=self.storage_threshold,
            fallback_storage_aware=self.fallback_storage_aware,
            hysteresis=self.hysteresis, storage_threshold_low=self.storage_threshold_low,
            min_dwell=self.min_dwell,
        ) if self.use_filter else None
        self.phase_idx = {i: movement_index_phases(self.env.movements[i], self.env.phases[i]) for i in self.env.intersections}

    def act(self, obs, info) -> Dict[str, int]:
        proposed = {}
        for i in self.env.intersections:
            a, _, _ = select_action(self.policy, obs[i], self.phase_idx[i], info["action_masks"][i], deterministic=True)
            proposed[i] = a
        if not self.use_filter:
            self._last_activation = 0.0
            return proposed
        final_actions, filter_active = self.filt.apply(obs, info, proposed)
        self._last_activation = float(np.mean(list(filter_active.values())))
        return final_actions


def run_episode(
    controller_name: str, cfg: dict, net_dir: str, seed: int, eta: float,
    policy_state_dict: dict | None, B: float | None, filter_kwargs: dict | None,
) -> dict:
    """One episode, one controller. Module-level and picklable so
    multiprocessing (spawn) can call it directly -- matches
    scripts/train.py's and scripts/sweep_storage_threshold.py's own worker
    convention. Run under maxtasksperchild=1 (see main()) so every episode
    gets a genuinely fresh process; do not remove that without re-running
    tests/test_episode_isolation.py."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    fleet = Fleet.from_config(cfg)
    baseline_key = BASELINE_DISPLAY.get(controller_name)
    env = HAPLightEnv(
        net_dir, cfg, fleet, seed=seed, eta=eta, estimator="area",
        # Advanced-MPLight's state-builder reads the cached running-demand
        # channel, which is only populated when this is on (P5-1).
        advanced_mp_running_demand=(baseline_key == "advanced_mplight"),
    )
    try:
        if controller_name == "FixedTime":
            controller = FixedTime(env, cfg, fleet, net_dir=net_dir)
        elif controller_name == "MaxPressure":
            controller = MaxPressure(env)
        elif controller_name == "GreedyHAP":
            controller = GreedyHAP(env)
        elif controller_name in ("HAPLight-RL", "HAPLight-RL (unfiltered)"):
            policy = HAPLightPolicy(cfg)
            policy.load_state_dict(policy_state_dict)
            policy.eval()
            kwargs = dict(filter_kwargs or {})
            kwargs["use_filter"] = controller_name == "HAPLight-RL"
            controller = HAPLightRLController(env, policy, B, **kwargs)
        elif baseline_key is not None:
            from src.rl_baselines import BaselineRLController, make_policy  # noqa: E402

            policy = make_policy(cfg, baseline_key)
            policy.load_state_dict(policy_state_dict)
            policy.eval()
            controller = BaselineRLController(env, baseline_key, policy)
        else:
            raise ValueError(f"unknown controller {controller_name!r}")

        obs = env.reset()
        controller.reset()
        info = env.info
        truncated = False
        while not truncated:
            actions = controller.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
        activation = getattr(controller, "_last_activation", 0.0)
        m = metrics.compute(
            env.completed_trips(), env.true_queue_history(), fleet, cfg,
            env.gmax_activation_rate(), filter_activation_rate=activation,
        )
        # First-class deadlock signal (pre-registered classification, see
        # PAPER_CHANGELOG P4c thread): the insertion backlog never clears by
        # episode end. Computed before env.close() -- pending_count() reads
        # live SUMO state.
        m[GRIDLOCK_KEY] = 1.0 if env.pending_count() > 0 else 0.0
    finally:
        env.close()
    return {"controller": controller_name, "seed": seed, "eta": eta, **m}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], default="s1")
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)),
                     help="n>=10 is now the standard (P4c-15): almost every "
                          "'not significant, favourable point estimate, high "
                          "variance' result at n=5 was a sample-size problem "
                          "-- characterizing a ~4%% deadlock event needs "
                          "enough draws to see it repeatedly")
    ap.add_argument("--etas", type=float, nargs="+", default=[0.0, 0.6])
    ap.add_argument("--out", default=None)
    ap.add_argument("--n-workers", type=int, default=None)
    ap.add_argument("--storage-triggered-filter", action="store_true",
                     help="OR a storage-occupancy trigger into the SafetyFilter (P4c-5/P4c-7)")
    ap.add_argument("--production-filter", action="store_true",
                     help="use the exact scripts/train.py default (storage, storage, hysteresis) "
                          "filter config: storage_aware=True, fallback_storage_aware=True, "
                          "hysteresis=True, threshold=0.80/0.70, min_dwell=3 (P4c-14)")
    ap.add_argument("--baseline-checkpoint", action="append", default=[], metavar="KEY=PATH",
                     help="Phase 5 RL baseline to include, repeatable, e.g. "
                          "--baseline-checkpoint advanced_mplight=results_baselines/<run>/checkpoint.pt "
                          "(keys: " + ", ".join(sorted(BASELINE_DISPLAY.values())) + ")")
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
    print(f"Loaded {args.checkpoint} (iteration {ckpt['iteration']})")

    B = calibrate_threshold(str(net_dir), cfg, fleet, seed=0)
    print(f"Safety filter B = {B:.3f}")

    filter_kwargs = {
        "storage_aware": args.storage_triggered_filter or args.production_filter,
        "fallback_storage_aware": args.production_filter,
        "hysteresis": args.production_filter,
        "storage_threshold": 0.80 if args.production_filter else None,
        "storage_threshold_low": 0.70 if args.production_filter else None,
        "min_dwell": 3,
    }

    # Phase 5 baselines (PAPER_CHANGELOG P5-1): each contributes one extra
    # controller column, loaded from its own trained checkpoint.
    key_to_display = {v: k for k, v in BASELINE_DISPLAY.items()}
    baseline_states: Dict[str, dict] = {}
    controller_names = list(CONTROLLER_NAMES)
    for spec in args.baseline_checkpoint:
        if "=" not in spec:
            raise SystemExit(f"--baseline-checkpoint expects KEY=PATH, got {spec!r}")
        key, path = spec.split("=", 1)
        if key not in key_to_display:
            raise SystemExit(f"unknown baseline key {key!r}; expected one of {sorted(key_to_display)}")
        from src.rl_baselines import make_policy  # noqa: E402

        bpolicy = make_policy(cfg, key)
        bckpt = torch.load(path, map_location="cpu")
        bpolicy.load_state_dict(bckpt["policy"])
        bpolicy.eval()
        display = key_to_display[key]
        baseline_states[display] = {k: v.detach().cpu().clone() for k, v in bpolicy.state_dict().items()}
        controller_names.append(display)
        print(f"Loaded baseline {display} from {path} (iteration {bckpt['iteration']})")

    jobs = []
    for eta in args.etas:
        for seed in args.seeds:
            for name in controller_names:
                if name in ("HAPLight-RL", "HAPLight-RL (unfiltered)"):
                    jobs.append((name, cfg, str(net_dir), seed, eta, state_dict, B, filter_kwargs))
                elif name in baseline_states:
                    jobs.append((name, cfg, str(net_dir), seed, eta, baseline_states[name], None, None))
                else:
                    jobs.append((name, cfg, str(net_dir), seed, eta, None, None, None))

    print(f"{len(jobs)} episodes, {n_workers} parallel workers, "
          f"maxtasksperchild=1 (fresh process per episode -- P4c-14/P4c-15)\n")
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=n_workers, maxtasksperchild=1) as pool:
        raw_results = pool.starmap(run_episode, jobs)

    # results[eta][controller][metric] -> list over seeds, in --seeds order
    all_keys = METRIC_KEYS + [GRIDLOCK_KEY]
    results: Dict[float, Dict[str, Dict[str, List[float]]]] = {
        eta: {name: {k: [] for k in all_keys} for name in controller_names} for eta in args.etas
    }
    by_key = {(r["eta"], r["controller"], r["seed"]): r for r in raw_results}
    for eta in args.etas:
        for seed in args.seeds:
            for name in controller_names:
                m = by_key[(eta, name, seed)]
                for k in all_keys:
                    results[eta][name][k].append(m[k])
                print(f"eta={eta:.1f} seed={seed} {name:<12} " +
                      " ".join(f"{k}={m[k]:.2f}" for k in METRIC_KEYS) +
                      (f"  GRIDLOCK" if m[GRIDLOCK_KEY] else ""))

    def paired_block(eta: float, reference: str, label: str) -> dict:
        """Paired stats of every OTHER controller against `reference`, on the
        same (seed, eta) demand realisation. Heavy-tail-correct reporting
        (P4c-15 convention): the deadlock rate above is the primary result;
        MEDIAN is the central-tendency figure here, with BCa on the paired
        difference and rank-biserial as the effect size -- the mean and the
        normal-theory t-CI are kept only as secondary context, because one
        rare gridlocked episode (aql in the thousands against a healthy-seed
        mean in the hundreds) moves a mean far more than it moves a median."""
        block: dict = {}
        if reference not in results[eta]:
            return block
        print(f"\nPaired vs {label}, positive = the row's method better, n={n}:")
        for name in controller_names:
            if name == reference:
                continue
            block[name] = {}
            parts = []
            for k in METRIC_KEYS:
                mine = np.array(results[eta][name][k], dtype=float)
                ref = np.array(results[eta][reference][k], dtype=float)
                sign = 1.0 if LOWER_IS_BETTER[k] else -1.0
                diff = sign * (ref - mine)  # positive = `name` better
                sem = diff.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
                tcrit = sstats.t.ppf(0.975, df=n - 1) if n > 1 else float("nan")
                lo, hi = diff.mean() - tcrit * sem, diff.mean() + tcrit * sem
                try:
                    res = sstats.ttest_rel(mine, ref)
                    t_stat, p_val = float(res.statistic), float(res.pvalue)
                except Exception:
                    t_stat, p_val = float("nan"), float("nan")
                r_rb = matched_pairs_rank_biserial(diff)
                bca = bca_ci(diff)
                block[name][k] = {
                    "median_self": float(np.median(mine)),
                    "median_reference": float(np.median(ref)),
                    "median_delta": float(np.median(diff)),
                    "delta_mean": float(diff.mean()),
                    "ci_lo": float(lo), "ci_hi": float(hi),
                    "t": t_stat, "p": p_val,
                    "rank_biserial_r": float(r_rb),
                    "bca_ci_lo": bca[0] if bca is not None else None,
                    "bca_ci_hi": bca[1] if bca is not None else None,
                }
                bca_str = f"[{bca[0]:+.1f},{bca[1]:+.1f}]" if bca is not None else "n/a"
                parts.append(f"{k}: med_d={np.median(diff):+.1f} BCa={bca_str} r={r_rb:+.2f}")
            print(f"  {name:<34} " + "  ".join(parts))
        return block

    summary_vs_greedy = {}
    summary_vs_amp = {}
    gridlock_summary = {}
    median_summary = {}
    n = len(args.seeds)
    AMP = "Advanced-MPLight"
    for eta in args.etas:
        print(f"\n=== eta = {eta} ===")
        name_w = max(len(x) for x in controller_names) + 2
        header = f"{'controller':<{name_w}}" + "".join(f"{k:>16}" for k in METRIC_KEYS) + f"{'gridlock':>18}"
        print(header)
        print("-" * len(header))
        gridlock_summary[eta] = {}
        median_summary[eta] = {}
        for name in controller_names:
            row = []
            median_summary[eta][name] = {}
            for k in METRIC_KEYS:
                arr = np.array(results[eta][name][k], dtype=float)
                median_summary[eta][name][k] = float(np.median(arr))
                # median (primary) with the mean kept alongside as context
                row.append(f"{np.median(arr):.1f}/{arr.mean():.1f}")
            k_gridlock = int(sum(results[eta][name][GRIDLOCK_KEY]))
            lo_g, hi_g = wilson_ci(k_gridlock, n)
            gridlock_summary[eta][name] = {"k": k_gridlock, "n": n, "rate": k_gridlock / n, "ci_lo": lo_g, "ci_hi": hi_g}
            row.append(f"{k_gridlock}/{n}=[{lo_g:.0%},{hi_g:.0%}]")
            print(f"{name:<{name_w}}" + "".join(f"{v:>16}" for v in row[:-1]) + f"{row[-1]:>18}")
        print("(metric cells are median/mean; gridlock is k/n with a Wilson 95% CI)")

        summary_vs_greedy[eta] = paired_block(eta, "GreedyHAP", "GreedyHAP")
        if AMP in results[eta]:
            summary_vs_amp[eta] = paired_block(eta, AMP, f"{AMP} (SOTA baseline)")

    out_path = Path(args.out) if args.out else Path(args.checkpoint).parent / "evaluation.json"
    payload = {
        "checkpoint": args.checkpoint, "iteration": ckpt["iteration"], "seeds": args.seeds,
        "etas": args.etas, "B": B,
        "controllers": controller_names,
        "raw": {str(eta): {name: results[eta][name] for name in controller_names} for eta in args.etas},
        "median": {str(eta): median_summary[eta] for eta in args.etas},
        "paired_delta_vs_greedy_hap": {str(eta): summary_vs_greedy[eta] for eta in args.etas},
        "paired_delta_vs_advanced_mplight": {str(eta): summary_vs_amp.get(eta, {}) for eta in args.etas},
        "gridlock_rate": {str(eta): gridlock_summary[eta] for eta in args.etas},
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
