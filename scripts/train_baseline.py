"""
PPO training for a Phase 5 RL baseline (PLAN.md Phase 5, prompts/
phase5_baselines.md). Mirrors scripts/train.py's rollout/iteration-loop
shape (same watchdog/retry machinery, same checkpoint/CSV pattern) but:
  - no safety filter (approved Phase 5 plan, decision A -- baselines are
    bare, literature-faithful RL controllers);
  - no greedy-HAP reference (baselines are compared to MaxPressure after
    training, via src.rl_baselines.evaluate_vs_mp, not to greedy-HAP);
  - policy/state/reward are the baseline's own (src.rl_baselines), not
    HAPLight's.

Usage
-----
    python -m scripts.train_baseline --baseline advanced_mplight --scenario s2 --stage C
    python -m scripts.train_baseline --baseline advanced_mplight --scenario s2 --quick --sequential
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from typing import List

import numpy as np
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.hap import Fleet  # noqa: E402
from src.ppo import PPOTrainer, Trajectory  # noqa: E402
from src.policy import HAPLightPolicy  # noqa: E402
from src.rl_baselines import (  # noqa: E402
    STATE_FNS, baseline_policy_cfg, discover_intersections, evaluate_vs_mp,
    make_policy, run_baseline_episode, run_ippo_episode,
)
from scripts.train import check_iteration_contention, run_workers_with_watchdog  # noqa: E402

BASELINE_CHOICES = sorted(set(STATE_FNS.keys()) | {"ippo"})

SCENARIO_NET = {"s1": "arterial5", "s2": "grid4x4"}


def _cpu_state_dict(policy) -> dict:
    return {k: v.detach().cpu().clone() for k, v in policy.state_dict().items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--baseline", required=True, choices=BASELINE_CHOICES)
    ap.add_argument("--scenario", choices=["s1", "s2"], default="s2")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--iterations", type=int, default=None,
                     help="default: cfg['rl']['ppo']['iterations'] (100, full paper spec)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="results_baselines")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--n-envs", type=int, default=None)
    ap.add_argument("--sequential", action="store_true")
    ap.add_argument("--quick", action="store_true", help="short episodes -- smoke test only (Stage B)")
    ap.add_argument("--worker-timeout-s", type=float, default=900.0)
    ap.add_argument("--worker-max-retries", type=int, default=2)
    ap.add_argument("--eval-seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4],
                     help="MaxPressure-paired Stage-C sanity-gate seeds, run after training")
    ap.add_argument("--skip-eval", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    scenario_key = {"s1": "s1_arterial", "s2": "s2_grid"}[args.scenario]
    net_name = SCENARIO_NET[args.scenario]
    net_dir = Path("nets") / net_name

    a_bar_path = net_dir / "a_bar_per_movement.json"
    assert a_bar_path.exists(), (
        f"{a_bar_path} missing -- run scripts/calibrate_estimator.py first "
        f"(same requirement as scripts/train.py, PAPER_CHANGELOG P1c-1/P1c-9)."
    )

    if args.quick:
        cfg = dict(cfg)
        cfg["demand"] = dict(cfg["demand"])
        cfg["demand"]["episode_length_s"] = 300.0

    fleet = Fleet.from_config(cfg)
    iterations = args.iterations or cfg["rl"]["ppo"]["iterations"]
    n_envs = args.n_envs or min(int(cfg["rl"]["ppo"]["parallel_episodes"]), max(1, (os.cpu_count() or 2) - 1))

    if args.baseline == "ippo":
        return main_ippo(args, cfg, net_dir, n_envs, iterations)

    policy = make_policy(cfg, args.baseline)
    trainer = PPOTrainer(policy, baseline_policy_cfg(cfg, args.baseline), device=args.device)
    print(f"{args.baseline}: {policy.param_count()} params, movement_in_dim="
          f"{cfg['rl_baselines'][args.baseline]['net']['movement_in_dim']}, "
          f"n_neighbours={cfg['rl_baselines'][args.baseline]['obs']['n_neighbours']}, "
          f"reward_form={cfg['rl_baselines'][args.baseline]['reward_form']}")

    start_iteration = 0
    out_dir = None
    if args.resume:
        ckpt = torch.load(args.resume, map_location=args.device)
        policy.load_state_dict(ckpt["policy"])
        trainer.optimizer.load_state_dict(ckpt["optimizer"])
        start_iteration = ckpt["iteration"] + 1
        out_dir = Path(ckpt["out_dir"])
        print(f"Resumed from {args.resume} at iteration {start_iteration}")
    if out_dir is None:
        run_id = f"{args.baseline}_{args.scenario}_seed{args.seed}_{int(time.time())}"
        out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "baseline": args.baseline, "scenario": scenario_key, "net_dir": str(net_dir), "seed": args.seed,
        "reward_form": cfg["rl_baselines"][args.baseline]["reward_form"],
        "n_envs": n_envs, "iterations": iterations,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    csv_path = out_dir / "train_log.csv"
    write_header = not csv_path.exists()
    csv_f = open(csv_path, "a", newline="")
    writer = csv.writer(csv_f)
    if write_header:
        writer.writerow(["iteration", "mean_return", "entropy", "value_loss", "policy_loss", "wall_clock_s"])

    ctx = mp.get_context("spawn")
    wall_history: List[float] = []  # contention guard (PAPER_CHANGELOG P5-1)
    for it in range(start_iteration, iterations):
        t0 = time.time()
        trainer.set_lr(it, iterations)
        state_dict_cpu = _cpu_state_dict(policy)

        eta_rng = np.random.default_rng(np.random.SeedSequence([args.seed, it]))
        etas = eta_rng.uniform(0.0, 0.6, size=n_envs)
        worker_args = [
            (args.baseline, state_dict_cpu, cfg, str(net_dir), args.seed, it, w, float(etas[w]), False)
            for w in range(n_envs)
        ]

        if args.sequential:
            results = [run_baseline_episode(*a) for a in worker_args]
        else:
            results, _ = run_workers_with_watchdog(
                ctx, worker_args, n_envs, args.worker_timeout_s, args.worker_max_retries,
                worker_fn=run_baseline_episode,
            )

        all_trajs: List[Trajectory] = []
        returns = []
        for r in results:
            all_trajs.extend(r["trajectories"].values())
            returns.append(r["episode_return"])

        update_stats = trainer.update(all_trajs)
        mean_return = float(np.mean(returns))
        wall_clock_s = time.time() - t0

        writer.writerow([it, mean_return, update_stats["entropy"], update_stats["value_loss"],
                          update_stats["policy_loss"], wall_clock_s])
        csv_f.flush()
        print(f"[{args.baseline}] iter {it}: return={mean_return:.4f} entropy={update_stats['entropy']:.3f} "
              f"value_loss={update_stats['value_loss']:.4f} wall_clock={wall_clock_s:.1f}s", flush=True)
        warning = check_iteration_contention(wall_history, wall_clock_s)
        if warning:
            print(warning, flush=True)
        wall_history.append(wall_clock_s)

        torch.save({
            "policy": policy.state_dict(), "optimizer": trainer.optimizer.state_dict(),
            "iteration": it, "out_dir": str(out_dir),
        }, out_dir / "checkpoint.pt")

    csv_f.close()

    if not args.skip_eval:
        print(f"\nStage-C sanity gate: {args.baseline} vs MaxPressure, {len(args.eval_seeds)} paired "
              f"seeds, eta=0, {args.scenario}...")
        eval_result = evaluate_vs_mp(
            cfg, str(net_dir), args.baseline, _cpu_state_dict(policy), args.eval_seeds, eta=0.0,
        )
        (out_dir / "stage_c_eval.json").write_text(json.dumps(eval_result, indent=2))
        print(json.dumps(eval_result, indent=2))

    return 0


def main_ippo(args, cfg: dict, net_dir: Path, n_envs: int, iterations: int) -> int:
    """IPPO: N fully independent (HAPLightPolicy, PPOTrainer) pairs, one per
    intersection ID -- the parameter-sharing ablation (src.rl_baselines
    module docstring). Reuses cfg["rl"] verbatim (same state/reward as
    HAPLight-RL) -- no rl_baselines config block, no shadow cfg. No
    MaxPressure Stage-C comparison (IPPO's gate per the approved Phase 5
    plan is "training curve moves," not a published-number gate -- it's an
    ablation, not a competitor for SOTA)."""
    intersections = discover_intersections(str(net_dir), cfg)
    print(f"ippo: {len(intersections)} intersections, one independent policy each, "
          f"reward_form={cfg['rl']['reward']['form']}")

    policies = {i: HAPLightPolicy(cfg) for i in intersections}
    trainers = {i: PPOTrainer(policies[i], cfg, device=args.device) for i in intersections}

    start_iteration = 0
    out_dir = None
    if args.resume:
        ckpt = torch.load(args.resume, map_location=args.device)
        for i in intersections:
            policies[i].load_state_dict(ckpt["policies"][i])
            trainers[i].optimizer.load_state_dict(ckpt["optimizers"][i])
        start_iteration = ckpt["iteration"] + 1
        out_dir = Path(ckpt["out_dir"])
        print(f"Resumed from {args.resume} at iteration {start_iteration}")
    if out_dir is None:
        run_id = f"ippo_{args.scenario}_seed{args.seed}_{int(time.time())}"
        out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metadata.json").write_text(json.dumps({
        "baseline": "ippo", "scenario": args.scenario, "net_dir": str(net_dir), "seed": args.seed,
        "n_intersections": len(intersections), "reward_form": cfg["rl"]["reward"]["form"],
        "n_envs": n_envs, "iterations": iterations,
    }, indent=2))

    csv_path = out_dir / "train_log.csv"
    write_header = not csv_path.exists()
    csv_f = open(csv_path, "a", newline="")
    writer = csv.writer(csv_f)
    if write_header:
        writer.writerow(["iteration", "mean_return", "mean_entropy", "mean_value_loss", "mean_policy_loss", "wall_clock_s"])

    ctx = mp.get_context("spawn")
    wall_history: List[float] = []  # contention guard (PAPER_CHANGELOG P5-1)
    for it in range(start_iteration, iterations):
        t0 = time.time()
        for i in intersections:
            trainers[i].set_lr(it, iterations)
        state_dicts_cpu = {i: _cpu_state_dict(policies[i]) for i in intersections}

        eta_rng = np.random.default_rng(np.random.SeedSequence([args.seed, it]))
        etas = eta_rng.uniform(0.0, 0.6, size=n_envs)
        worker_args = [
            (state_dicts_cpu, cfg, str(net_dir), args.seed, it, w, float(etas[w]), False)
            for w in range(n_envs)
        ]

        if args.sequential:
            results = [run_ippo_episode(*a) for a in worker_args]
        else:
            results, _ = run_workers_with_watchdog(
                ctx, worker_args, n_envs, args.worker_timeout_s, args.worker_max_retries,
                worker_fn=run_ippo_episode,
            )

        trajs_by_i: dict = {i: [] for i in intersections}
        returns = []
        for r in results:
            for i, traj in r["trajectories"].items():
                trajs_by_i[i].append(traj)
            returns.append(r["episode_return"])

        entropies, value_losses, policy_losses = [], [], []
        for i in intersections:
            stats = trainers[i].update(trajs_by_i[i])
            entropies.append(stats["entropy"])
            value_losses.append(stats["value_loss"])
            policy_losses.append(stats["policy_loss"])

        mean_return = float(np.mean(returns))
        wall_clock_s = time.time() - t0
        writer.writerow([it, mean_return, float(np.mean(entropies)), float(np.mean(value_losses)),
                          float(np.mean(policy_losses)), wall_clock_s])
        csv_f.flush()
        print(f"[ippo] iter {it}: return={mean_return:.4f} mean_entropy={np.mean(entropies):.3f} "
              f"mean_value_loss={np.mean(value_losses):.4f} wall_clock={wall_clock_s:.1f}s", flush=True)
        warning = check_iteration_contention(wall_history, wall_clock_s)
        if warning:
            print(warning, flush=True)
        wall_history.append(wall_clock_s)

        torch.save({
            "policies": {i: policies[i].state_dict() for i in intersections},
            "optimizers": {i: trainers[i].optimizer.state_dict() for i in intersections},
            "iteration": it, "out_dir": str(out_dir),
        }, out_dir / "checkpoint.pt")

    csv_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
