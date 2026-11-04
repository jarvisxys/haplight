"""
Per-episode speed benchmark: traci (TCP) vs libsumo (in-process), v3 plan
Sec. "Compute plan" ("the speed-up must be measured before the budget is
locked") and the week-1 gate ("speed-up measured").

Protocol (fixed before the first run, 2026-11-04):
- Workload: one full episode (demand.episode_length_s from the config,
  3600 s by default) under GreedyHAP, eta=0.6 (sensing pipeline on),
  estimator "area". GreedyHAP stands in for every controller: the policy
  forward pass is small next to the simulation, so this measures the
  environment cost that dominates training and evaluation.
- Grid: scenarios x backends x seeds. Jobs are interleaved by seed so both
  backends see the same machine conditions.
- Isolation: every episode runs in its own spawned process
  (Pool(maxtasksperchild=1)), as in production.
- Timing: wall-clock from env construction to env.close(); reset and
  stepping are also recorded separately.
- Memory: peak working set of the worker process, plus the sumo child
  process for traci, read just before close.
- Parity at full length: each episode records one rolling SHA-256 over
  every step's observation, reward, true queues, sensed queues and actions.
  Episodes with the same (scenario, seed) must have the same digest on both
  backends; the summary reports any mismatch.
- --workers 1 measures pure per-episode time. --workers N (laptop: at most
  6, see CLAUDE.md) measures throughput under parallel load.

Outputs (outside the repository, via the results/ junction):
  <out>/episodes.parquet  one row per episode
  <out>/manifest.json     git SHA, dirty flag, config hash, package versions,
                          host, CPU/RAM, arguments

Usage:
  uv run python -m scripts.benchmark_backend --workers 1 --seeds 0 1
  uv run python -m scripts.benchmark_backend --workers 6 --seeds 0 1 2 3 4 5
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import multiprocessing as mp
import pickle
import platform
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

import pandas as pd
import psutil
import pyarrow  # noqa: F401  # must be imported before libsumo on Windows (CLAUDE.md)
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.controllers import GreedyHAP
from src.env import HAPLightEnv
from src.hap import Fleet

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}
ETA = 0.6
PACKAGES = ["eclipse-sumo", "libsumo", "traci", "sumolib", "numpy", "torch", "pandas", "pyarrow"]


def _peak_mem_mb(proc: psutil.Process) -> float:
    mi = proc.memory_info()
    return getattr(mi, "peak_wset", mi.rss) / 2**20


def run_episode(scenario: str, backend: str, seed: int, cfg: dict) -> dict:
    """One timed episode. Module-level and picklable for spawn."""
    sys.path.insert(0, str(ROOT))
    t0 = time.perf_counter()
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(str(ROOT / "nets" / SCENARIO_NET[scenario]), cfg, fleet, seed=seed,
                      eta=ETA, estimator="area", use_libsumo=(backend == "libsumo"))
    try:
        obs = env.reset()
        t_reset = time.perf_counter()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        h = hashlib.sha256()
        h.update(pickle.dumps(({i: obs[i].tobytes() for i in sorted(obs)},
                               info["true_queues"], info["x_hat"])))
        n_steps = 0
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            h.update(pickle.dumps(({i: obs[i].tobytes() for i in sorted(obs)}, reward,
                                   info["true_queues"], info["x_hat"], actions)))
            n_steps += 1
        t_steps = time.perf_counter()
        me = psutil.Process()
        mem_worker = _peak_mem_mb(me)
        mem_sumo = sum(_peak_mem_mb(c) for c in me.children(recursive=True)
                       if c.name().lower().startswith("sumo"))
        n_trips = len(env.completed_trips())
        gridlock = env.pending_count() > 0
        backend_used = env.backend
    finally:
        env.close()
    t_end = time.perf_counter()
    return {
        "scenario": scenario, "backend": backend, "backend_used": backend_used, "seed": seed,
        "eta": ETA, "episode_length_s": float(cfg["demand"]["episode_length_s"]),
        "n_steps": n_steps, "n_trips": n_trips, "gridlock": gridlock,
        "wall_s": t_end - t0, "reset_s": t_reset - t0, "step_s": t_steps - t_reset,
        "peak_mem_worker_mb": mem_worker, "peak_mem_sumo_mb": mem_sumo,
        "trajectory_sha256": h.hexdigest(),
    }


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def _manifest(args: argparse.Namespace, cfg_path: Path) -> dict:
    vm = psutil.virtual_memory()
    return {
        "script": "scripts/benchmark_backend.py",
        "started_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "config": str(cfg_path),
        "config_sha256": hashlib.sha256(cfg_path.read_bytes()).hexdigest(),
        "args": vars(args),
        "python": sys.version.split()[0],
        "packages": {p: metadata.version(p) for p in PACKAGES},
        "host": platform.node(),
        "platform": platform.platform(),
        "cpu_logical": psutil.cpu_count(),
        "cpu_physical": psutil.cpu_count(logical=False),
        "ram_total_gb": round(vm.total / 2**30, 2),
        "ram_available_gb_at_start": round(vm.available / 2**30, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenarios", nargs="+", choices=sorted(SCENARIO_NET), default=["s1", "s2"])
    ap.add_argument("--backends", nargs="+", choices=["traci", "libsumo"], default=["traci", "libsumo"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--episode-length-s", type=float, default=None,
                    help="override demand.episode_length_s (for smoke runs only)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg_path = (ROOT / args.config).resolve()
    cfg = copy.deepcopy(yaml.safe_load(cfg_path.read_text()))
    if args.episode_length_s is not None:
        cfg["demand"]["episode_length_s"] = args.episode_length_s
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(args.out) if args.out else ROOT / "results" / "benchmarks" / f"backend_w{args.workers}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(args, cfg_path)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    jobs = [(sc, b, seed, cfg) for seed in args.seeds for sc in args.scenarios for b in args.backends]
    print(f"{len(jobs)} episodes, {args.workers} workers, maxtasksperchild=1 -> {out}", flush=True)
    t0 = time.perf_counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=args.workers, maxtasksperchild=1) as pool:
        rows = pool.starmap(run_episode, jobs)
    total = time.perf_counter() - t0

    df = pd.DataFrame(rows)
    df.to_parquet(out / "episodes.parquet", index=False)
    manifest["total_wall_s"] = total
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    bad = df[df["backend"] != df["backend_used"]]
    if len(bad):
        print(f"ERROR: {len(bad)} episodes ran on a different backend than requested")

    summary = df.groupby(["scenario", "backend"]).agg(
        n=("wall_s", "size"), wall_median_s=("wall_s", "median"), wall_mean_s=("wall_s", "mean"),
        wall_min_s=("wall_s", "min"), wall_max_s=("wall_s", "max"),
        mem_worker_mb=("peak_mem_worker_mb", "max"), mem_sumo_mb=("peak_mem_sumo_mb", "max"),
    )
    print(summary.round(1).to_string())
    if {"traci", "libsumo"} <= set(df["backend"]):
        for sc, g in df.groupby("scenario"):
            med = g.groupby("backend")["wall_s"].median()
            print(f"{sc}: speed-up traci/libsumo (median wall) = {med['traci'] / med['libsumo']:.2f}x")
        par = df.pivot_table(index=["scenario", "seed"], columns="backend",
                             values="trajectory_sha256", aggfunc="first")
        mismatch = par[par["traci"] != par["libsumo"]]
        print(f"full-length parity: {len(par) - len(mismatch)}/{len(par)} (scenario, seed) pairs identical")
        if len(mismatch):
            print(mismatch.to_string())
    print(f"total wall {total:.0f} s; outputs in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
