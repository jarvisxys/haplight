"""
Measurement-correctness gate (PAPER_CHANGELOG P5-2).

WHY THIS FILE EXISTS. A bug that counted every vehicle EXACTLY 8 TIMES
survived four phases and every existing test. It survived because every
count-channel test compares a count against ANOTHER COUNT: e.g.
test_true_queues_noise_free checks x_hat against true_queues, and both
were inflated by the same factor, so the check cancelled out perfectly.
Nothing compared a measured channel against ground truth obtained by an
INDEPENDENT route.

The rule this file enforces, and the only reason it is a separate file
rather than another case in test_env.py: the reference count here must
never be derived from src.env's own measurement path. It is rebuilt from
raw traci lane/vehicle queries, so a systematic error in _measure()
cannot cancel.

Run:  pytest tests/test_measurement.py -v
"""
import copy
import multiprocessing as mp
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "configs" / "default.yaml"
NET_DIRS = {"s1": ROOT / "nets" / "arterial5", "s2": ROOT / "nets" / "grid4x4"}


def _short_cfg(episode_length_s: float = 600.0) -> dict:
    cfg = copy.deepcopy(yaml.safe_load(CFG_PATH.read_text()))
    cfg["demand"]["episode_length_s"] = episode_length_s
    return cfg


def _independent_stopped_count(env, i: str, mv: str) -> int:
    """Ground truth via a route that shares NO code with _measure():
    raw per-lane vehicle ids, each vehicle's own speed and lane position,
    counted once. Deliberately not vectorised or cached -- clarity and
    independence matter here, speed does not."""
    traci = env._traci
    n = 0
    for lane in env._lane_sets[i][mv]:
        lane_len = env._lane_length.get(lane)
        if lane_len is None:
            continue
        for vid in traci.lane.getLastStepVehicleIDs(lane):
            if traci.vehicle.getSpeed(vid) >= env.stop_speed:
                continue  # stopped vehicles only -- matches the true/x_hat channel
            dist = lane_len - traci.vehicle.getLanePosition(vid)
            if 0.0 <= dist <= env.catchment_len:
                n += 1
    return n


@pytest.mark.parametrize("scenario", ["s1", "s2"])
def test_counts_match_ground_truth(scenario):
    """Every sensed count channel must equal an independently-derived
    ground-truth count exactly, at eta=0 (no sensing noise to explain a
    discrepancy). This is the assertion whose absence let an exact-8x
    inflation pass every other test in the suite."""
    net_dir = NET_DIRS[scenario]
    if not net_dir.exists():
        pytest.skip(f"run scripts/build_nets.py first ({net_dir} missing)")

    cfg = _short_cfg()
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        env.reset()
        info = env.info
        n_compared = 0
        n_nonzero = 0
        truncated = False
        steps = 0
        while not truncated and steps < 20:
            for i in env.intersections:
                for mv in env.movements[i]:
                    expected = _independent_stopped_count(env, i, mv)
                    measured = sum(info["counts_hat"][i][mv].values())
                    assert measured == pytest.approx(expected, abs=1e-6), (
                        f"{scenario} {i} {mv}: counts_hat={measured} but independent "
                        f"ground truth={expected} (ratio "
                        f"{measured / expected if expected else float('nan')}). "
                        f"A constant ratio >1 means vehicles are being counted more "
                        f"than once -- see PAPER_CHANGELOG P5-2."
                    )
                    n_compared += 1
                    n_nonzero += expected > 0
            _, _, truncated, info = env.step(
                {i: info["current_phase"][i] for i in env.intersections}
            )
            steps += 1
    finally:
        env.close()

    assert n_compared > 0
    # A test that only ever compared 0 == 0 would pass against any bug.
    assert n_nonzero >= 10, (
        f"only {n_nonzero} non-empty movements sampled -- this test would be "
        f"vacuous; raise the episode length or demand so real vehicles are present"
    )


def test_ground_truth_helper_would_catch_double_counting():
    """Sensitivity check: proves the assertion above actually discriminates.
    Reproduces the pre-fix accumulation (one row per (context edge, vehicle)
    pair, no deduplication) and asserts it does NOT equal ground truth --
    i.e. the gate would have FAILED on the old code rather than silently
    passing as the rest of the suite did."""
    net_dir = NET_DIRS["s1"]
    if not net_dir.exists():
        pytest.skip("run scripts/build_nets.py first")

    cfg = _short_cfg()
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        env.reset()
        info = env.info
        for _ in range(12):
            _, _, _, info = env.step(
                {i: info["current_phase"][i] for i in env.intersections}
            )

        tc = env._tc
        # PRE-FIX behaviour, reconstructed verbatim: accumulate per context
        # row instead of per distinct vehicle.
        naive_per_lane = {}
        for e in env._catchment_edges:
            res = env._traci.edge.getContextSubscriptionResults(e) or {}
            for _vid, v in res.items():
                lane = v[tc.VAR_LANE_ID]
                lane_len = env._lane_length.get(lane)
                if lane_len is None:
                    continue
                dist = lane_len - v[tc.VAR_LANEPOSITION]
                if dist < 0 or dist > env.catchment_len:
                    continue
                if v[tc.VAR_SPEED] < env.stop_speed:
                    naive_per_lane[lane] = naive_per_lane.get(lane, 0.0) + 1.0

        naive_total = 0.0
        true_total = 0
        for i in env.intersections:
            for mv in env.movements[i]:
                naive_total += sum(naive_per_lane.get(l, 0.0) for l in env._lane_sets[i][mv])
                true_total += _independent_stopped_count(env, i, mv)
    finally:
        env.close()

    if true_total == 0:
        pytest.skip("no stopped vehicles in this window -- cannot demonstrate sensitivity")
    ratio = naive_total / true_total
    assert ratio > 1.5, (
        f"expected the un-deduplicated accumulation to over-count (it produced "
        f"{naive_total} vs ground truth {true_total}, ratio {ratio:.3f}). If this "
        f"assertion ever fails, the context subscriptions stopped overlapping and "
        f"test_counts_match_ground_truth has lost its teeth -- investigate rather "
        f"than deleting this test."
    )


# -- stale first observation after reset() under libsumo -------------------
#
# libsumo keeps context-subscription RESULTS in a process-wide cache that
# survives close()+start() and is not cleared by unsubscribeContext() or by
# a new subscribeContext(); only simulationStep() refreshes it. So the
# observation built inside reset() -- before any step -- used to read the
# PREVIOUS simulation's last-step vehicles (verified 2026-11-04: 966 cached
# rows at t=0 of a new simulation with 0 vehicles). TCP traci refreshes on
# subscribe, so it never showed this. Same bug class as v2 changelog P4c-12.
# Production is unaffected (one fresh process per episode); any code that
# runs two simulations in one process (tests, ad-hoc scripts) was not.

_RESET_CHANNELS = (
    "true_queues", "true_counts", "x_hat", "u_hat", "w_hat",
    "counts_hat", "running_counts_hat", "counts_hat_downstream",
)
_STALE_SEED = 7


def _reset_snapshot(env, obs) -> dict:
    snap = {k: copy.deepcopy(env.info[k]) for k in _RESET_CHANNELS}
    snap["obs"] = {i: obs[i].tolist() for i in sorted(obs)}
    return snap


def _fresh_process_reset_snapshot(out_queue) -> None:
    """Reference: reset observation in a process where nothing ran before."""
    sys.path.insert(0, str(ROOT))
    cfg = _short_cfg()
    env = HAPLightEnv(str(NET_DIRS["s1"]), cfg, Fleet.from_config(cfg),
                      seed=_STALE_SEED, eta=0.0, estimator="area")
    try:
        out_queue.put(_reset_snapshot(env, env.reset()))
    finally:
        env.close()


@pytest.fixture(scope="module")
def fresh_reset_snapshot():
    if not NET_DIRS["s1"].exists():
        pytest.skip("run scripts/build_nets.py first")
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_fresh_process_reset_snapshot, args=(q,))
    p.start()
    snap = q.get(timeout=300)
    p.join()
    return snap


@pytest.mark.parametrize("second_start", ["same_env_reset", "new_env"])
def test_reset_observation_not_stale_after_previous_simulation(second_start, fresh_reset_snapshot):
    """Two simulations in ONE process: the second one's reset() observation
    must match independent ground truth and be identical to the reset
    observation of a fresh process."""
    cfg = _short_cfg()
    fleet = Fleet.from_config(cfg)

    # Simulation A: long enough that libsumo's result cache is full of
    # queued vehicles when it ends. "same_env_reset" reuses this env (the
    # seed is fixed per instance, so its second reset() replays _STALE_SEED);
    # "new_env" builds a second env, as a sequential script would.
    seed_a = _STALE_SEED if second_start == "same_env_reset" else 0
    env_a = HAPLightEnv(str(NET_DIRS["s1"]), cfg, fleet, seed=seed_a, eta=0.0, estimator="area")
    env_b = env_a
    try:
        env_a.reset()
        info = env_a.info
        for _ in range(60):
            _, _, _, info = env_a.step({i: info["current_phase"][i] for i in env_a.intersections})
        stopped_at_end_of_a = sum(
            _independent_stopped_count(env_a, i, mv)
            for i in env_a.intersections for mv in env_a.movements[i]
        )
        # Without this the test would compare 0 == 0 and pass against the bug.
        assert stopped_at_end_of_a > 0, "simulation A left no queued vehicles; test is vacuous"

        if second_start == "new_env":
            env_a.close()
            env_b = HAPLightEnv(str(NET_DIRS["s1"]), cfg, fleet, seed=_STALE_SEED, eta=0.0,
                                estimator="area")


        obs = env_b.reset()
        for i in env_b.intersections:
            for mv in env_b.movements[i]:
                expected = _independent_stopped_count(env_b, i, mv)
                measured = sum(env_b.info["counts_hat"][i][mv].values())
                assert measured == pytest.approx(expected, abs=1e-6), (
                    f"reset() observation of a second simulation in this process "
                    f"reports {measured} stopped vehicles on {i} {mv}; ground truth is "
                    f"{expected}. Stale libsumo context-subscription results."
                )
        assert _reset_snapshot(env_b, obs) == fresh_reset_snapshot, (
            "reset() observation differs from the one a fresh process produces"
        )
    finally:
        env_a.close()
        env_b.close()
