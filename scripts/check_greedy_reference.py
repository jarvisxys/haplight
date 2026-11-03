"""
Greedy-HAP reference sanity check (PAPER_CHANGELOG P4-6).

scripts/train.py's two greedy-HAP references (eta~U[0,0.6] and eta=0) use
the IDENTICAL ep_seed derivation (SeedSequence([seed, 0xC1EEDA, ep]),
independent of fixed_eta) for matching episode index -- so the two
reference computations are already PAIRED (same demand realisation per ep,
only the sensing-noise draw differs), not independent samples. This script
reuses that pairing directly and runs a paired t-test on eta=0 minus
eta~U[0,0.6] per-episode returns, at a larger n than the n_envs=8 used
inline during a training run's pre-flight check -- distinguishing "real,
reproducible effect" from "n=8 sampling noise" for the counter-intuitive
result that greedy HAP scored WORSE at eta=0 (perfect information) than
under sensing noise.

Usage
-----
    python -m scripts.check_greedy_reference --scenario s1 --n-episodes 16
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import ttest_rel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}


def _episode_return(cfg: dict, net_dir: str, ep_seed: int, eta: float) -> float:
    """Module-level and picklable so multiprocessing (spawn) can call it
    directly in a fresh process per episode (PAPER_CHANGELOG P4c-15) --
    this script previously ran every episode sequentially in one process,
    the same episode-isolation defect confirmed elsewhere in this
    codebase, which would have undermined the very statistical validation
    this script exists to perform."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(net_dir, cfg, fleet, seed=ep_seed, eta=eta, estimator="area")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        total = {i: 0.0 for i in env.intersections}
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                total[i] += reward[i]
        return float(np.mean(list(total.values())))
    finally:
        env.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], default="s1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-episodes", type=int, default=16)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    net_dir = Path("nets") / SCENARIO_NET[args.scenario]

    rng = np.random.default_rng(args.seed)  # matches compute_greedy_reference's own rng stream
    etas_drawn = [float(rng.uniform(0.0, 0.6)) for _ in range(args.n_episodes)]
    ep_seeds = [
        int(np.random.SeedSequence([args.seed, 0xC1EEDA, ep]).generate_state(1)[0] % (2**31 - 1))
        for ep in range(args.n_episodes)
    ]
    jobs = []
    for ep_seed, eta_u in zip(ep_seeds, etas_drawn):
        jobs.append((cfg, str(net_dir), ep_seed, 0.0))
        jobs.append((cfg, str(net_dir), ep_seed, eta_u))

    ctx = mp.get_context("spawn")
    n_workers = min(len(jobs), max(1, (os.cpu_count() or 2) - 1))
    with ctx.Pool(processes=n_workers, maxtasksperchild=1) as pool:
        flat_returns = pool.starmap(_episode_return, jobs)
    eta0_vals = flat_returns[0::2]
    etaU_vals = flat_returns[1::2]
    for ep, (eta_u, r_eta0, r_etaU) in enumerate(zip(etas_drawn, eta0_vals, etaU_vals)):
        print(f"ep {ep:2d}  eta_u={eta_u:.3f}  eta0_return={r_eta0:10.2f}  etaU_return={r_etaU:10.2f}  "
              f"diff(eta0-etaU)={r_eta0 - r_etaU:10.2f}")

    eta0_arr = np.array(eta0_vals)
    etaU_arr = np.array(etaU_vals)
    diff = eta0_arr - etaU_arr

    print(f"\nn={args.n_episodes}")
    print(f"eta=0     mean={eta0_arr.mean():.2f}  std={eta0_arr.std(ddof=1):.2f}")
    print(f"eta~U[0,0.6] mean={etaU_arr.mean():.2f}  std={etaU_arr.std(ddof=1):.2f}")
    print(f"paired diff (eta0 - etaU): mean={diff.mean():.2f}  std={diff.std(ddof=1):.2f}  "
          f"sem={diff.std(ddof=1)/np.sqrt(args.n_episodes):.2f}")

    res = ttest_rel(eta0_arr, etaU_arr)
    print(f"paired t-test: t={res.statistic:.3f}  p={res.pvalue:.4f}")
    if res.pvalue < 0.05:
        print("-> statistically significant difference (at n=%d): the eta=0 vs eta~U gap is NOT sampling noise." % args.n_episodes)
    else:
        print("-> NOT statistically significant at n=%d: consistent with n=8 sampling noise, not a real effect." % args.n_episodes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
