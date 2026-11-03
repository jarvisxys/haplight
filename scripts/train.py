"""
PPO training for HAPLight-RL (PLAN.md Phase 4, paper Sec. V-F Algorithm 2).

Trains on ONE scenario/seed. Per iteration: E parallel workers each run one
full episode (libsumo, sensing noise eta ~ U[0, 0.6] resampled per episode),
proposing actions with the shared policy and passing them through the
Corollary-1 safety filter before stepping; rollouts pool back to the main
process for one PPO update (src.ppo.PPOTrainer).

Usage
-----
    python -m scripts.train --scenario s1
    python -m scripts.train --scenario s1 --quick          # smoke test
    python -m scripts.train --scenario s1 --sequential      # no multiprocessing, for debugging
    python -m scripts.train --scenario s1 --resume results/s1_seed0_.../checkpoint.pt
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import psutil
import torch
import yaml
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402
from src.policy import HAPLightPolicy, movement_index_phases  # noqa: E402
from src.ppo import PPOTrainer, Step, Trajectory, select_action  # noqa: E402
from src.safety_filter import SafetyFilter, calibrate_threshold  # noqa: E402

SCENARIO_NET = {"s1_arterial": "arterial5", "s2_grid": "grid4x4"}


def _episode_return(trajs: Dict[str, Trajectory]) -> float:
    """Sum of reward over the episode per intersection, then averaged
    across intersections -- used identically for the greedy-HAP reference
    and for RL rollouts so the two are directly comparable."""
    if not trajs:
        return float("nan")
    per_i = [sum(s.reward for s in t.steps) for t in trajs.values()]
    return float(np.mean(per_i))


def run_episode_worker(
    policy_state_dict: dict, cfg: dict, net_dir: str, B: float,
    run_seed: int, iteration: int, worker_id: int, eta: float,
    deterministic: bool = False,
) -> dict:
    """Runs ONE full episode: policy proposes actions, SafetyFilter may
    override, env executes. Returns per-intersection Trajectories (with
    V(s_T) bootstrap already filled in), filter-activation counts, and the
    episode return. Designed to be picklable/importable at module level so
    multiprocessing (spawn) can call it directly."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # spawned children re-need this

    fleet = Fleet.from_config(cfg)
    policy = HAPLightPolicy(cfg)
    policy.load_state_dict(policy_state_dict)
    policy.eval()

    seed = int(np.random.SeedSequence([run_seed, iteration, worker_id]).generate_state(1)[0] % (2**31 - 1))
    torch.manual_seed(seed)  # reproducible action SAMPLING too, not just env dynamics

    env = HAPLightEnv(net_dir, cfg, fleet, seed=seed, eta=eta, estimator="area")
    try:
        obs = env.reset()
        info = env.info
        # (storage, storage, hysteresis) -- PAPER_CHANGELOG P4c-9/P4c-11/
        # P4c-14, the composed default: storage_aware=True OR's a storage-
        # occupancy trigger alongside the queue-magnitude one (engages
        # before a greedy-irrecoverable spillback state, not just after the
        # queue is already large); fallback_storage_aware=True gives the
        # fallback itself storage-aware pressure (P4c-3 proved a plain
        # fallback can itself deadlock -- P4c-8 regressed S1 by pairing an
        # early trigger with a fallback that inherited that exposure);
        # hysteresis=True fixes confirmed boundary chattering (P4c-11: one
        # intersection toggled 84 times in 720 decisions without it).
        # threshold=0.80 (REVISED from an earlier 0.85 -- P4c-12's sweep had
        # a since-fixed multiprocessing bug, P4c-14): the sweep pool reused
        # worker processes across sequential trials, and a trial's outcome
        # depended on what OTHER trial happened to run earlier in the same
        # worker -- confirmed directly (one seed/threshold pair flipped
        # FAIL<->OK purely by job order, nothing else changed) and fixed
        # with maxtasksperchild=1 (fresh process per trial). Re-run on all
        # 4 sweeps (10 seeds x {S1,S2} x {eta=0,eta=0.6,} = 240 trials):
        # 0.80 is the ONLY threshold with zero failures across all 40
        # tested (seed,scenario,eta) conditions; 0.85 has 3. Independently
        # cross-checked via a second, unrelated code path (standalone
        # single-episode reproduction), not just the fixed sweep alone.
        filt = SafetyFilter(
            env, B, storage_aware=True,
            storage_threshold=cfg["rl"]["filter"].get("storage_trigger_threshold", 0.80),
            fallback_storage_aware=True,
            hysteresis=True,
            storage_threshold_low=cfg["rl"]["filter"].get("storage_trigger_threshold_low", 0.70),
            min_dwell=cfg["rl"]["filter"].get("min_dwell_decisions", 3),
        )
        phase_idx = {i: movement_index_phases(env.movements[i], env.phases[i]) for i in env.intersections}

        trajs: Dict[str, Trajectory] = {i: Trajectory() for i in env.intersections}
        n_filter_active = n_total = 0

        truncated = False
        while not truncated:
            proposed: Dict[str, int] = {}
            meta = {}
            for i in env.intersections:
                a, lp, v = select_action(policy, obs[i], phase_idx[i], info["action_masks"][i], deterministic)
                proposed[i] = a
                meta[i] = (a, lp, v)
            final_actions, filter_active = filt.apply(obs, info, proposed)
            next_obs, reward, truncated, next_info = env.step(final_actions)
            for i in env.intersections:
                a, lp, v = meta[i]
                trajs[i].steps.append(Step(
                    obs=obs[i], phases_idx=phase_idx[i], mask=info["action_masks"][i],
                    action=a, log_prob=lp, value=v, reward=reward[i], filtered=filter_active[i],
                ))
                n_total += 1
                n_filter_active += int(filter_active[i])
            obs, info = next_obs, next_info

        for i in env.intersections:  # V(s_T) bootstrap at truncation
            _, _, v_T = select_action(policy, obs[i], phase_idx[i], info["action_masks"][i], deterministic)
            trajs[i].bootstrap_value = v_T

        return {
            "trajectories": trajs,
            "n_filter_active": n_filter_active,
            "n_total": n_total,
            "episode_return": _episode_return(trajs),
        }
    finally:
        env.close()


def run_workers_with_watchdog(
    ctx, worker_args: List[tuple], n_envs: int, timeout_s: float, max_retries: int = 2,
    worker_fn=run_episode_worker,
) -> tuple[list, List[float]]:
    """Runs one episode per worker_args entry via a fresh Pool, but never
    blocks indefinitely on a single hung worker (PAPER_CHANGELOG P4-6): a
    16.9h run against a ~224s median iteration was traced to the machine
    sleeping mid-worker, not a code hang, but nothing distinguished "sleeping
    machine" from "genuinely stuck worker" at the time -- this makes that
    distinguishable and recoverable. Each worker gets `timeout_s`; a worker
    that doesn't return in time is retried (fresh process, same args) up to
    `max_retries` times before raising. Returns (results_in_original_order,
    per_worker_wall_clock_s) -- the timing list is what makes a stall
    attributable to a specific worker rather than "the iteration was slow."
    `worker_fn` (PAPER_CHANGELOG P5-1, Phase 5): defaults to this module's
    own `run_episode_worker` so every existing call site is unaffected;
    `scripts/train_baseline.py` passes `src.rl_baselines.run_baseline_episode`
    instead, reusing this exact watchdog/retry machinery for the RL
    baselines rather than duplicating it."""
    n = len(worker_args)
    results: list = [None] * n
    timings: List[float] = [0.0] * n
    pending = list(range(n))
    attempts = {idx: 0 for idx in pending}

    while pending:
        # maxtasksperchild=1: each worker gets at most one episode anyway
        # (len(pending) <= n_envs per Pool lifetime), but making that an
        # explicit guarantee rather than an implicit invariant keeps this
        # uniform with every other episode-dispatching Pool in the
        # codebase (PAPER_CHANGELOG P4c-15) and verifiable by
        # tests/test_episode_isolation.py's structural check.
        pool = ctx.Pool(processes=n_envs, maxtasksperchild=1)
        try:
            async_results = {idx: pool.apply_async(worker_fn, worker_args[idx]) for idx in pending}
            pool.close()
            still_pending = []
            for idx, ar in async_results.items():
                t0 = time.time()
                try:
                    results[idx] = ar.get(timeout=timeout_s)
                    timings[idx] = time.time() - t0
                except mp.TimeoutError:
                    attempts[idx] += 1
                    print(f"  [watchdog] worker {idx} exceeded {timeout_s:.0f}s "
                          f"(attempt {attempts[idx]}/{max_retries}) -- will kill pool and retry")
                    if attempts[idx] > max_retries:
                        raise RuntimeError(
                            f"worker {idx} (args iteration={(worker_args[idx][5] if len(worker_args[idx]) > 5 else '?')}) exceeded "
                            f"{timeout_s:.0f}s {max_retries} times in a row -- treating as a "
                            f"genuine hang, not a transient stall."
                        )
                    still_pending.append(idx)
                except Exception as exc:
                    # PAPER_CHANGELOG P5-8: a worker that RAISES used to
                    # propagate straight out of ar.get() and kill the whole
                    # multi-hour run -- confirmed on CoLight-variant S1, where
                    # one worker's SUMO subprocess failed to bind its TCP port
                    # ("Address already in use"), the TraCI handshake read a
                    # truncated reply (struct.error), and 24 iterations of
                    # progress ended with rc=1. It also discarded the other
                    # workers' already-finished episodes for that iteration.
                    # Now a raising worker is retried exactly like a timed-out
                    # one. The retry re-runs the SAME worker_args (same seed,
                    # iteration and worker id), so the retried episode is the
                    # one that would have run anyway -- training data and
                    # reproducibility are unchanged. A deterministic bug still
                    # surfaces: it fails every retry and is re-raised, chained
                    # to the original exception, after max_retries.
                    attempts[idx] += 1
                    print(f"  [watchdog] worker {idx} raised {type(exc).__name__}: {exc} "
                          f"(attempt {attempts[idx]}/{max_retries}) -- retrying the SAME episode "
                          f"in a fresh process", flush=True)
                    if attempts[idx] > max_retries:
                        raise RuntimeError(
                            f"worker {idx} (args iteration={(worker_args[idx][5] if len(worker_args[idx]) > 5 else '?')}) raised "
                            f"{type(exc).__name__} on {max_retries + 1} consecutive attempts -- "
                            f"treating as a genuine failure, not a transient one."
                        ) from exc
                    still_pending.append(idx)
        finally:
            pool.terminate()  # always reap, including any hung/uncollected worker
            pool.join()
        pending = still_pending
    return results, timings


def current_load_summary() -> str:
    """Best-effort machine-load snapshot, for the contention guard's warning
    line only (PAPER_CHANGELOG P5-1). Never raises: a guard that crashes the
    run it exists to protect would be worse than no guard."""
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory().percent
        n_proc = len(psutil.pids())
        return f"cpu={cpu:.0f}% mem={mem:.0f}% procs={n_proc}"
    except Exception as exc:  # noqa: BLE001 -- diagnostics only, never fatal
        return f"(load unavailable: {exc})"


def check_iteration_contention(
    history: List[float], current_s: float, min_history: int = 5, factor: float = 2.0,
) -> Optional[str]:
    """Per-iteration contention guard (PAPER_CHANGELOG P5-1). Returns a
    warning string when this iteration took more than `factor` x the rolling
    median of the previous iterations, else None.

    Exists because a multi-night run was silently wrecked once before by
    machine-side load external to this codebase (P4-6's machine-sleep
    incident, and the Phase 5 timing investigation) with nothing in the log
    distinguishing "the machine got busy" from "the code got slower". The
    median (not the mean) is the reference on purpose: one genuinely slow
    iteration must not raise the bar that detects the next one. `history`
    is the iterations BEFORE this one -- pass it un-appended."""
    if len(history) < min_history:
        return None
    med = float(np.median(history))
    if med <= 0.0 or current_s <= factor * med:
        return None
    return (
        f"  [contention] iteration took {current_s:.0f}s vs a rolling median of "
        f"{med:.0f}s over the previous {len(history)} iterations ({current_s / med:.1f}x) "
        f"-- {current_load_summary()}. Not fatal, and NOT necessarily this code: "
        f"check for other load on the machine before treating it as a regression."
    )


def _greedy_reference_episode(cfg: dict, net_dir: str, seed: int, eta: float) -> float:
    """One greedy-HAP reference episode. Module-level and picklable so it
    can run in a fresh process per episode (PAPER_CHANGELOG P4c-15):
    compute_greedy_reference previously ran every reference episode
    sequentially in one process -- the same episode-isolation defect
    confirmed elsewhere in this codebase (Phase-1 subscriptions-across-
    resets, the P4c sweep's Pool worker reuse, evaluate_policy.py's old
    sequential loop)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(net_dir, cfg, fleet, seed=seed, eta=eta, estimator="area")
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


def compute_greedy_reference(
    cfg: dict, net_dir: str, n_episodes: int, seed: int = 0,
    fixed_eta: float | None = None, max_workers: int | None = None,
) -> float:
    """Greedy HAP's mean return under the IDENTICAL reward definition
    (env.step()'s Eq. 12 reward, computed the same way regardless of
    controller). Two callers need two DIFFERENT eta distributions and must
    not be compared against a single shared reference (approved
    correction): `fixed_eta=None` samples eta~U[0,0.6] per episode,
    matching the RANDOMISED training rollout distribution; `fixed_eta=0.0`
    matches the clean deterministic eval. Compare mean_return against the
    former, eta0_return against the latter -- never both against one
    number. Each episode runs in its own fresh process
    (`maxtasksperchild=1`, PAPER_CHANGELOG P4c-15) -- see
    _greedy_reference_episode's docstring. `max_workers` MUST be passed
    through from the caller's own concurrency budget (e.g. `--n-envs`) --
    defaulting independently to `os.cpu_count()-1` here caused two
    concurrent training runs (S1+S2) to each try to open up to 15 SUMO
    processes for this call alone, ~30 total, crashing SUMO itself
    ("Connection closed by SUMO") on a machine already shown to hit a
    MemoryError at 15 (PAPER_CHANGELOG P4c-15)."""
    rng = np.random.default_rng(seed)
    jobs = []
    for ep in range(n_episodes):
        eta = float(rng.uniform(0.0, 0.6)) if fixed_eta is None else float(fixed_eta)
        ep_seed = int(np.random.SeedSequence([seed, 0xC1EEDA, ep]).generate_state(1)[0] % (2**31 - 1))
        jobs.append((cfg, net_dir, ep_seed, eta))
    ctx = mp.get_context("spawn")
    cap = max_workers if max_workers is not None else max(1, (os.cpu_count() or 2) - 1)
    n_workers = min(len(jobs), cap)
    with ctx.Pool(processes=n_workers, maxtasksperchild=1) as pool:
        returns = pool.starmap(_greedy_reference_episode, jobs)
    return float(np.mean(returns))


def compute_random_policy_filter_control(
    cfg: dict, net_dir: str, B: float, n_episodes: int, seed: int = 0,
    max_workers: int | None = None,
) -> float:
    """Ablation control: a FRESH, never-trained (random-init) policy
    composed with the safety filter, same eta~U[0,0.6] distribution as
    training. Answers directly, not by inference from iteration 0 of a
    real run, how much of an early "return already beats greedy HAP"
    reading is the filter rescuing the worst decisions (Remark 6) rather
    than anything learned. Kept as a permanent, separately-logged ablation
    row, not folded into the training log. Each episode runs in its own
    fresh process (`maxtasksperchild=1`, PAPER_CHANGELOG P4c-15) -- this
    previously called run_episode_worker in a plain sequential loop, the
    same episode-isolation defect confirmed elsewhere in this codebase.
    `max_workers`: see compute_greedy_reference's docstring -- same reason
    this must come from the caller's own concurrency budget, not
    `os.cpu_count()-1` computed independently here."""
    fresh_policy = HAPLightPolicy(cfg)
    state_dict = _cpu_state_dict(fresh_policy)
    rng = np.random.default_rng(seed)
    jobs = []
    for ep in range(n_episodes):
        eta = float(rng.uniform(0.0, 0.6))
        # SeedSequence entropy must be non-negative -- 0xBADC0DE tags this
        # as the control run's own seed namespace (distinct from real
        # training iterations, which are always >= 0).
        jobs.append((state_dict, cfg, net_dir, B, seed, 0xBADC0DE, ep, eta, False))
    ctx = mp.get_context("spawn")
    cap = max_workers if max_workers is not None else max(1, (os.cpu_count() or 2) - 1)
    n_workers = min(len(jobs), cap)
    with ctx.Pool(processes=n_workers, maxtasksperchild=1) as pool:
        results = pool.starmap(run_episode_worker, jobs)
    returns = [r["episode_return"] for r in results]
    return float(np.mean(returns))


def reward_queue_correlation(cfg: dict, net_dir: str, fleet: Fleet, seed: int = 0) -> float:
    """Pearson correlation between the network-wide summed per-step reward
    (Eq. 12, true channel) and the change in total true (ground-truth)
    weighted queue over that same step, under GreedyHAP driving (a
    reasonable, non-degenerate policy -- checking signal quality against a
    literally random policy would conflate two different noise sources).
    A large-magnitude NEGATIVE correlation is the expected/healthy sign
    (higher reward <-> queue decreasing that step); near-zero means the
    intersection-wide sum in _compute_reward is telescoping away most of
    its own signal and the learner would be training against noise
    regardless of budget."""
    env = HAPLightEnv(net_dir, cfg, fleet, seed=seed, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info

        def _total_queue(info_) -> float:
            return sum(sum(info_["true_queues"][i].values()) for i in env.intersections)

        total_rewards: List[float] = []
        total_queues: List[float] = [_total_queue(info)]
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            total_rewards.append(float(sum(reward.values())))
            total_queues.append(_total_queue(info))
        delta_queues = np.diff(np.array(total_queues))
        corr = float(np.corrcoef(np.array(total_rewards), delta_queues)[0, 1])
        return corr
    finally:
        env.close()


def _cpu_state_dict(policy: HAPLightPolicy) -> dict:
    return {k: v.detach().cpu().clone() for k, v in policy.state_dict().items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--scenario", choices=["s1", "s2"], default="s1")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--iterations", type=int, default=None)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="results")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--n-envs", type=int, default=None)
    ap.add_argument("--sequential", action="store_true", help="no multiprocessing -- for debugging")
    ap.add_argument("--early-check-iterations", type=int, default=5,
                     help="iterations before reporting filter activation rate and deciding whether to continue")
    ap.add_argument("--quick", action="store_true", help="short episodes, few iterations -- smoke test only")
    ap.add_argument("--worker-timeout-s", type=float, default=900.0,
                     help="per-worker watchdog timeout (default 900s, well above the ~224s median "
                          "iteration measured on this machine, well below a multi-hour stall)")
    ap.add_argument("--worker-max-retries", type=int, default=2)
    ap.add_argument("--reference-episodes", type=int, default=24,
                     help="episode count for the two greedy-HAP references (PAPER_CHANGELOG P4-6: "
                          "GreedyHAP at exact eta=0 has a rare but real deterministic gridlock failure "
                          "mode on some demand draws -- n=8 let one such episode dominate the mean by "
                          "~4x; decoupled from n_envs since this is a one-time pre-flight cost, not "
                          "per-iteration)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    scenario_key = {"s1": "s1_arterial", "s2": "s2_grid"}[args.scenario]
    net_name = SCENARIO_NET[scenario_key]
    net_dir = Path("nets") / net_name

    a_bar_path = net_dir / "a_bar_per_movement.json"
    assert a_bar_path.exists(), (
        f"{a_bar_path} missing -- training against the global (uncalibrated) area "
        f"estimator wastes the entire run (PAPER_CHANGELOG P1c-1/P1c-9, ~11% throughput "
        f"cost). Run scripts/calibrate_estimator.py first."
    )

    if args.quick:
        cfg = dict(cfg)
        cfg["demand"] = dict(cfg["demand"])
        cfg["demand"]["episode_length_s"] = 300.0

    fleet = Fleet.from_config(cfg)
    iterations = args.iterations or cfg["rl"]["ppo"]["iterations"]
    n_envs = args.n_envs or min(int(cfg["rl"]["ppo"]["parallel_episodes"]), max(1, (os.cpu_count() or 2) - 1))

    policy = HAPLightPolicy(cfg)
    trainer = PPOTrainer(policy, cfg, device=args.device)

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
        run_id = f"{args.scenario}_seed{args.seed}_{int(time.time())}"
        out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Calibrating safety filter threshold (P{cfg['rl']['filter']['threshold_percentile']})...")
    B = calibrate_threshold(str(net_dir), cfg, fleet, seed=args.seed)
    print(f"  B = {B:.3f}")

    # Three pre-flight checks (approved additions) before committing to the
    # full run -- two matched greedy-HAP references (not one shared
    # reference for two differently-distributed return series), a
    # random-policy+filter ablation control, and a reward/queue signal
    # sanity check.
    print(f"Computing greedy-HAP reference returns ({args.reference_episodes} episodes each)...")
    ref_return_random = compute_greedy_reference(cfg, str(net_dir), n_episodes=args.reference_episodes, seed=args.seed, max_workers=n_envs)
    ref_return_eta0 = compute_greedy_reference(cfg, str(net_dir), n_episodes=args.reference_episodes, seed=args.seed, fixed_eta=0.0, max_workers=n_envs)
    print(f"  greedy-HAP reference (eta~U[0,0.6], matches training return) = {ref_return_random:.4f}")
    print(f"  greedy-HAP reference (eta=0, matches clean eval)             = {ref_return_eta0:.4f}")

    print(f"Running random-policy + filter control ({n_envs} episodes, eta~U[0,0.6])...")
    control_return = compute_random_policy_filter_control(cfg, str(net_dir), B, n_episodes=n_envs, seed=args.seed, max_workers=n_envs)
    print(f"  random-policy+filter control return = {control_return:.4f} "
          f"(vs greedy-HAP random-eta reference {ref_return_random:.4f})")

    print("Checking reward/queue signal quality (one GreedyHAP episode, eta=0)...")
    reward_corr = reward_queue_correlation(cfg, str(net_dir), fleet, seed=args.seed)
    print(f"  corr(per-step reward, per-step change in total true queue) = {reward_corr:+.3f} "
          f"(expect a large-magnitude negative value; near-zero means the reward is mostly noise)")

    metadata = {
        "scenario": scenario_key, "net_dir": str(net_dir), "seed": args.seed,
        "a_bar_per_movement_path": str(a_bar_path),
        "a_bar_per_movement_mtime": a_bar_path.stat().st_mtime,
        "safety_filter_B": B,
        "safety_filter_percentile": cfg["rl"]["filter"]["threshold_percentile"],
        "safety_filter_storage_aware": True,
        "safety_filter_storage_threshold": cfg["rl"]["filter"].get("storage_trigger_threshold", 0.80),
        "safety_filter_fallback_storage_aware": True,
        "safety_filter_hysteresis": True,
        "safety_filter_storage_threshold_low": cfg["rl"]["filter"].get("storage_trigger_threshold_low", 0.70),
        "safety_filter_min_dwell": cfg["rl"]["filter"].get("min_dwell_decisions", 3),
        "greedy_hap_reference_return_random_eta": ref_return_random,
        "greedy_hap_reference_return_eta0": ref_return_eta0,
        "random_policy_filter_control_return": control_return,
        "reward_queue_correlation": reward_corr,
        "n_envs": n_envs, "iterations": iterations, "reference_episodes": args.reference_episodes,
        "reward_channel": "true_w (noise-free) -- PAPER_CHANGELOG P4-2",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    csv_path = out_dir / "train_log.csv"
    write_header = not csv_path.exists()
    csv_f = open(csv_path, "a", newline="")
    writer = csv.writer(csv_f)
    if write_header:
        writer.writerow([
            "iteration", "mean_return", "eta0_return", "filter_activation_rate",
            "entropy", "value_loss", "policy_loss", "wall_clock_s",
            "worker_min_s", "worker_max_s", "worker_mean_s",
        ])

    ctx = mp.get_context("spawn")
    stop_code = 0
    eta0_history: List[float] = []
    wall_history: List[float] = []  # contention guard (PAPER_CHANGELOG P5-1)
    TREND_CHECK_ITERATIONS = 40  # ~2.3h at the ~208s/iteration measured on this machine
    for it in range(start_iteration, iterations):
        t0 = time.time()
        trainer.set_lr(it, iterations)
        state_dict_cpu = _cpu_state_dict(policy)

        eta_rng = np.random.default_rng(np.random.SeedSequence([args.seed, it]))
        etas = eta_rng.uniform(0.0, 0.6, size=n_envs)
        worker_args = [
            (state_dict_cpu, cfg, str(net_dir), B, args.seed, it, w, float(etas[w]), False)
            for w in range(n_envs)
        ]

        if args.sequential:
            t_workers = []
            results = []
            for a in worker_args:
                tw0 = time.time()
                results.append(run_episode_worker(*a))
                t_workers.append(time.time() - tw0)
        else:
            results, t_workers = run_workers_with_watchdog(
                ctx, worker_args, n_envs, args.worker_timeout_s, args.worker_max_retries,
            )

        all_trajs: List[Trajectory] = []
        returns = []
        n_active_total = n_total_total = 0
        for r in results:
            all_trajs.extend(r["trajectories"].values())
            returns.append(r["episode_return"])
            n_active_total += r["n_filter_active"]
            n_total_total += r["n_total"]

        update_stats = trainer.update(all_trajs)
        mean_return = float(np.mean(returns))
        activation_rate = n_active_total / max(1, n_total_total)

        eval_result = run_episode_worker(
            _cpu_state_dict(policy), cfg, str(net_dir), B, args.seed, it, 9999, 0.0, True,
        )
        eta0_return = eval_result["episode_return"]
        eta0_history.append(eta0_return)

        wall_clock_s = time.time() - t0
        worker_min_s, worker_max_s, worker_mean_s = min(t_workers), max(t_workers), float(np.mean(t_workers))
        writer.writerow([
            it, mean_return, eta0_return, activation_rate,
            update_stats["entropy"], update_stats["value_loss"], update_stats["policy_loss"], wall_clock_s,
            worker_min_s, worker_max_s, worker_mean_s,
        ])
        csv_f.flush()
        print(
            f"iter {it}: return={mean_return:.4f} (ref_random_eta={ref_return_random:.4f}) "
            f"eta0_return={eta0_return:.4f} (ref_eta0={ref_return_eta0:.4f}) "
            f"filter_activation={activation_rate:.1%} entropy={update_stats['entropy']:.3f} "
            f"value_loss={update_stats['value_loss']:.4f} wall_clock={wall_clock_s:.1f}s "
            f"worker[min/mean/max]={worker_min_s:.1f}/{worker_mean_s:.1f}/{worker_max_s:.1f}s",
            flush=True,
        )
        warning = check_iteration_contention(wall_history, wall_clock_s)
        if warning:
            print(warning, flush=True)
        wall_history.append(wall_clock_s)

        torch.save({
            "policy": policy.state_dict(), "optimizer": trainer.optimizer.state_dict(),
            "iteration": it, "out_dir": str(out_dir),
        }, out_dir / "checkpoint.pt")

        if it == args.early_check_iterations - 1:
            print(
                f"\n[Phase 4 checkpoint] filter activation rate after "
                f"{args.early_check_iterations} iterations: {activation_rate:.1%}"
            )
            if activation_rate > 0.25:
                print(
                    "!! activation rate exceeds ~25% -- STOPPING per prompts/phase4_rl.md. "
                    "The P90 calibration may not have transferred from the calibration "
                    "episode to real training conditions; decide whether B moves to P97 "
                    "or the calibration needs revisiting before continuing.\n"
                )
                stop_code = 2
                break
            print("activation rate within the expected range (~10% at P90) -- continuing.\n")

        if len(eta0_history) == TREND_CHECK_ITERATIONS:
            xs = np.arange(len(eta0_history), dtype=float)
            y = np.array(eta0_history, dtype=float)
            ols_slope = float(np.polyfit(xs, y, 1)[0])
            # Robust trend check (PAPER_CHANGELOG P4c-15), not the bare OLS
            # slope: a plain least-squares fit over TREND_CHECK_ITERATIONS
            # points is exactly as outlier-sensitive as the mean/variance
            # problem the whole P4c deadlock-rate thread exists to
            # characterize -- a rare, real near-zero-noise near-deadlock
            # episode (the SAME phenomenon, not a different one) drags an
            # OLS fit down even when the underlying trend is flat-to-rising.
            # Confirmed directly on this run's own iteration-39 abort: OLS
            # slope=-19.7, but Theil-Sen=-3.5 with 95% CI=[-22.4,+10.3]
            # (straddles zero) and Spearman rho=-0.06 p=0.69 (no significant
            # trend at all) -- removing just the two flagged outlier
            # episodes drops the OLS slope to -2.7. Gate on the ROBUST
            # estimator and require its CI to exclude zero before treating
            # a negative point estimate as evidence of decline.
            ts = sstats.theilslopes(y, xs)
            print(
                f"\n[Phase 4 checkpoint] eta=0 clean-return trend over the first "
                f"{TREND_CHECK_ITERATIONS} iterations: OLS slope={ols_slope:+.4f}, "
                f"Theil-Sen slope={ts.slope:+.4f} 95% CI=[{ts.low_slope:+.4f}, {ts.high_slope:+.4f}] "
                f"return/iteration (first={eta0_history[0]:.2f}, last={eta0_history[-1]:.2f}, "
                f"eta0 reference={ref_return_eta0:.4f})"
            )
            confidently_declining = ts.slope < 0.0 and ts.high_slope < 0.0
            if confidently_declining:
                print(
                    "!! clean-eta return is ROBUSTLY declining over the first "
                    f"{TREND_CHECK_ITERATIONS} iterations (Theil-Sen CI entirely below "
                    "zero) -- STOPPING. Below the reference while rising would be fine; "
                    "flat is not. Debug in this order: (1) reward signal quality -- see "
                    "reward_queue_correlation in metadata.json, (2) the filter masks "
                    "15-20% of policy-gradient steps and those are precisely the "
                    "high-queue states the policy most needs to learn from, "
                    "(3) observation content.\n"
                )
                stop_code = 3
                break
            print(f"no robust evidence of decline (Theil-Sen {ts.slope:+.4f}/iter, "
                  f"CI includes zero or positive) -- continuing toward the full run.\n")

    csv_f.close()
    return stop_code


if __name__ == "__main__":
    raise SystemExit(main())
