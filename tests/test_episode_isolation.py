"""
Standing gate for the episode-isolation defect (PAPER_CHANGELOG P4c-14/
P4c-15) confirmed FIVE times independently in this codebase: Phase-1's
subscriptions-across-resets bug, diagnose_gridlock.py's in-process
calibrate_threshold() call, scripts/sweep_storage_threshold.py's
`multiprocessing.Pool` reusing worker processes across trials,
scripts/evaluate_policy.py's old plain sequential loop, and (found while
building this test) two more sequential loops inside scripts/train.py
(compute_greedy_reference, compute_random_policy_filter_control) plus one
in scripts/check_greedy_reference.py. All share one root mechanism:
libsumo is a singleton-per-process simulation engine, and running a SECOND
episode in a process that already ran a FIRST one can silently change the
second episode's outcome, even with an explicit, different seed on it.

TWO gates, not one:

1. `test_fresh_process_per_episode_dispatch` -- a STRUCTURAL check:
   source-inspects every script in this codebase known to dispatch
   multiple episodes (as opposed to a single episode per OS-level
   invocation, which needs no such guard) and asserts each one's
   `multiprocessing.Pool(...)` call includes `maxtasksperchild=1`. This is
   the actual fix applied to all five confirmed instances, and it is
   cheap, fast, and exactly matches "did someone remove the guard" --
   which is what every one of the five historical bugs amounted to. This
   is the PRIMARY gate.

2. `test_episode_isolation` -- a behavioural canary: GreedyHAP-only,
   isolated-vs-warmup-then-target trajectory comparison. Kept because a
   cheap behavioural check costs little to run even though it is NOT
   currently known to be sensitive to the defect -- see the honesty note
   on that test below. Do not treat a pass here as proof of isolation; it
   is gate #1 that carries that weight.

**Investigation record (do not silently drop this if the behavioural
canary is ever "cleaned up")**: while building this test, three separate,
faithful attempts to make an isolated-vs-contaminated comparison diverge
on the CURRENT codebase all failed to reproduce divergence, including a
full, exact replay of the originally-confirmed contaminated case (S1,
--production-filter, the identical 40-job sequence, seed=4/eta=0.6/
HAPLight-RL as job #40) via scripts.evaluate_policy.run_episode itself.
Two other previously-confirmed sweep failures (e.g. S2 seed=6/
threshold=0.85/eta=0) also no longer reproduce as failures at all, isolated
or not. The best-supported explanation is that substantial code changed
between when those specific numbers were recorded and now (hysteresis,
the storage-aware pressure fix, the 0.85->0.80 threshold correction) and
plausibly changed whatever state was leaking too -- NOT that the isolation
defect never existed; the fresh-process fix was independently confirmed
correct by direct A/B testing at the time (PAPER_CHANGELOG P4c-14). This
means gate #2 currently cannot be demonstrated sensitive to the historical
defect, which is exactly why gate #1 (structural, not behavioural) is the
one this suite actually relies on.

Run:  pytest tests/test_episode_isolation.py -v
"""
from __future__ import annotations

import multiprocessing as mp
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

# Every script in this codebase known to dispatch MULTIPLE episodes from
# a single OS-level process invocation (as opposed to scripts.
# diagnose_gridlock, which runs exactly one episode per invocation and
# therefore needs no fresh-process-per-episode guard at all). If a new
# script starts a multi-episode sweep/training/eval loop, add it here --
# that is the whole point of this gate.
SCRIPTS_WITH_PER_EPISODE_POOLS = [
    "scripts/evaluate_policy.py",
    "scripts/sweep_storage_threshold.py",
    "scripts/train.py",
    "scripts/check_greedy_reference.py",
    "scripts/benchmark_backend.py",
]


def test_fresh_process_per_episode_dispatch():
    """Every multiprocessing.Pool(...) construction in every script that
    dispatches multiple episodes must set maxtasksperchild=1. This is the
    literal fix applied independently to all five confirmed instances of
    this defect (PAPER_CHANGELOG P4c-14/P4c-15); a script that constructs
    a Pool without it is exhibiting the exact pattern that caused every
    one of them. Regex, not AST, deliberately -- this must stay readable
    enough that "why did this fail" is obvious from the assertion message
    alone, and every current Pool(...) call in this codebase is a simple
    one-line call, not a multi-line/wrapped construction."""
    import re

    pool_call_re = re.compile(r"\bPool\(([^)]*)\)")
    for rel_path in SCRIPTS_WITH_PER_EPISODE_POOLS:
        path = REPO_ROOT / rel_path
        assert path.exists(), f"{rel_path} listed in SCRIPTS_WITH_PER_EPISODE_POOLS but does not exist"
        source = path.read_text()
        calls = pool_call_re.findall(source)
        assert calls, (
            f"{rel_path} is listed as dispatching multiple episodes via a "
            f"Pool but no Pool(...) call was found in its source -- either "
            f"it was refactored to a different dispatch mechanism (update "
            f"this test to check that mechanism instead) or it no longer "
            f"needs a fresh-process-per-episode guard (remove it from "
            f"SCRIPTS_WITH_PER_EPISODE_POOLS, with a comment explaining why)."
        )
        for call_args in calls:
            assert "maxtasksperchild=1" in call_args, (
                f"{rel_path} constructs a multiprocessing.Pool without "
                f"maxtasksperchild=1: Pool({call_args}). This is the exact "
                f"defect behind PAPER_CHANGELOG P4c-14/P4c-15 -- without it, "
                f"a worker process is reused across multiple episodes, and "
                f"an earlier episode's libsumo/RNG state can silently change "
                f"a later episode's outcome even with an explicit, different "
                f"seed on it. Add maxtasksperchild=1 to this Pool(...) call."
            )


NET_DIR = Path(__file__).resolve().parents[1] / "nets" / "arterial5"
CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
N_STEPS = 20  # short and GreedyHAP-only (no policy/torch) -- fast, still sensitive


def _short_cfg() -> dict:
    cfg = yaml.safe_load(CFG_PATH.read_text())
    cfg = dict(cfg)
    cfg["demand"] = dict(cfg["demand"])
    cfg["demand"]["episode_length_s"] = 300.0  # matches the --quick convention elsewhere
    return cfg


def _true_queue_trajectory(seed: int) -> list:
    """GreedyHAP-controlled trajectory of network-wide true total queue for
    the first N_STEPS decisions, at a fixed seed. Module-level and
    picklable so multiprocessing (spawn) can call it directly. Uses the
    TRUE (ground-truth) channel deliberately -- it is the most sensitive
    signal available: any divergence in SUMO's own vehicle-arrival/
    car-following state shows up here immediately, with no sensing-noise
    layer to average it out."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    cfg = _short_cfg()
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=seed, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        trajectory = []
        for _ in range(N_STEPS):
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            trajectory.append(sum(sum(info["true_queues"][i].values()) for i in env.intersections))
            if truncated:
                break
        return trajectory
    finally:
        env.close()


def _isolated_only(seed: int, out_queue) -> None:
    """Runs ONLY the target episode -- a genuinely fresh process; nothing
    ran before it. This is the ground truth."""
    out_queue.put(_true_queue_trajectory(seed))


def _warm_up_then_target(warm_up_seed: int, target_seed: int, out_queue) -> None:
    """Runs a DIFFERENT episode first, then the target episode, in the
    SAME process -- deliberately reproducing the exact "sequential trials
    share a process" pattern already confirmed to cause contamination."""
    _true_queue_trajectory(warm_up_seed)  # discarded -- only its side effects on process state matter
    out_queue.put(_true_queue_trajectory(target_seed))


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_episode_isolation():
    """The target episode's trajectory must be IDENTICAL whether it is the
    only episode run in its process, or the second episode after an
    unrelated warm-up in the same process. A prior episode must never be
    able to change a later one's outcome when the later one has its own
    explicit seed -- if it can, some code path is reusing a process across
    episodes without the fresh-process discipline every other
    episode-producing script in this codebase follows.

    HONESTY NOTE (see module docstring): this specific GreedyHAP/eta=0/
    single-warm-up design is NOT currently known to be sensitive to the
    historical defect -- three separate attempts, including a full replay
    of the exact originally-confirmed contaminated case, did not reproduce
    divergence on the current codebase. It is kept anyway as a cheap,
    fast sanity check (a pass costs seconds; catching even one future
    regression this way is worth it), but test_fresh_process_per_episode_
    dispatch above is the gate this suite actually relies on for coverage.
    If this test ever DOES fail, that is real signal and must not be
    waved away -- but its passing is not proof of isolation."""
    ctx = mp.get_context("spawn")
    target_seed = 424242
    warm_up_seed = 131313  # deliberately unrelated to target_seed

    q1 = ctx.Queue()
    p1 = ctx.Process(target=_isolated_only, args=(target_seed, q1))
    p1.start()
    isolated = q1.get()
    p1.join()

    q2 = ctx.Queue()
    p2 = ctx.Process(target=_warm_up_then_target, args=(warm_up_seed, target_seed, q2))
    p2.start()
    contaminated = q2.get()
    p2.join()

    assert len(isolated) == N_STEPS, "sanity check: episode truncated before N_STEPS -- shorten episode_length_s further or reduce N_STEPS"
    assert isolated == contaminated, (
        f"Episode isolation violated: an unrelated episode run earlier in "
        f"the same process changed this episode's true-queue trajectory, "
        f"despite an explicit, different seed ({target_seed}) on it. "
        f"isolated={isolated}\ncontaminated={contaminated}\n"
        f"This is the exact defect behind PAPER_CHANGELOG P4c-14/P4c-15 -- "
        f"every episode-producing script MUST use a fresh process per "
        f"episode (multiprocessing.Pool(..., maxtasksperchild=1), or one "
        f"multiprocessing.Process per episode), never a plain sequential "
        f"loop or a Pool without maxtasksperchild=1."
    )
