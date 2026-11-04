"""
Backend parity gate (v3 plan, Sec. "Repository blueprint", practice
`test_backend_parity`): traci (TCP) and libsumo (in-process) must produce the
IDENTICAL trajectory for the same seed. v2 ran every experiment on traci;
v3 runs on libsumo. Results from the two backends may only be treated as
interchangeable while this test passes. CLAUDE.md still forbids mixing
backends inside one comparison table.

Each backend runs in its own freshly spawned process: libsumo is a
per-process singleton and must not share a process with another simulation.

What must match, exactly (no tolerance): at every decision step the
observation arrays, reward, true queues, sensed queues (eta > 0, so the
sensing pipeline is covered) and chosen actions; at the end, every completed
trip record and the episode metrics.

Run:  pytest tests/test_backend_parity.py -v
"""
from __future__ import annotations

import copy
import hashlib
import multiprocessing as mp
import pickle
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import metrics
from src.controllers import GreedyHAP
from src.env import HAPLightEnv
from src.hap import Fleet

CFG_PATH = ROOT / "configs" / "default.yaml"
NET_DIRS = {"s1": ROOT / "nets" / "arterial5", "s2": ROOT / "nets" / "grid4x4"}
EPISODE_LENGTH_S = 600.0  # short for the test suite; the benchmark checks full length
SEED = 5
ETA = 0.6


def _digest(*parts) -> str:
    return hashlib.sha256(pickle.dumps(parts)).hexdigest()


def _trajectory(scenario: str, backend: str, out_queue) -> None:
    """One GreedyHAP episode on the requested backend. Module-level and
    picklable for multiprocessing spawn."""
    sys.path.insert(0, str(ROOT))
    cfg = copy.deepcopy(yaml.safe_load(CFG_PATH.read_text()))
    cfg["demand"]["episode_length_s"] = EPISODE_LENGTH_S
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(str(NET_DIRS[scenario]), cfg, fleet, seed=SEED, eta=ETA,
                      estimator="area", use_libsumo=(backend == "libsumo"))
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        steps = [_digest({i: obs[i].tobytes() for i in sorted(obs)},
                         info["true_queues"], info["x_hat"])]
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            steps.append(_digest({i: obs[i].tobytes() for i in sorted(obs)}, reward,
                                 info["true_queues"], info["x_hat"], actions))
        trips = env.completed_trips()
        m = metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        out_queue.put({
            "backend_used": env.backend,
            "steps": steps,
            "n_trips": len(trips),
            "trips": _digest(trips),
            "metrics": m,
            "metrics_digest": _digest(sorted(m.items())),  # NaN-safe exact comparison
        })
    finally:
        env.close()


def _run_in_fresh_process(scenario: str, backend: str) -> dict:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_trajectory, args=(scenario, backend, q))
    p.start()
    result = q.get(timeout=600)
    p.join()
    return result


@pytest.mark.parametrize("scenario", ["s1", "s2"])
def test_backend_parity(scenario):
    if not NET_DIRS[scenario].exists():
        pytest.skip(f"run scripts/build_nets.py first ({NET_DIRS[scenario]} missing)")

    tr = _run_in_fresh_process(scenario, "traci")
    ls = _run_in_fresh_process(scenario, "libsumo")

    # bootstrap_sumo() falls back to traci if libsumo cannot be imported;
    # without this check the test could compare traci with itself.
    assert tr["backend_used"] == "traci"
    assert ls["backend_used"] == "libsumo"

    assert len(tr["steps"]) == len(ls["steps"]) > 1
    first_diff = next((k for k, (a, b) in enumerate(zip(tr["steps"], ls["steps"])) if a != b), None)
    assert first_diff is None, (
        f"{scenario}: traci and libsumo trajectories diverge at decision step {first_diff} "
        f"(0 = the reset observation). Results from the two backends are not interchangeable."
    )
    assert tr["n_trips"] == ls["n_trips"] > 0
    assert tr["trips"] == ls["trips"], f"{scenario}: completed-trip records differ between backends"
    assert tr["metrics_digest"] == ls["metrics_digest"], (
        f"{scenario}: episode metrics differ: traci={tr['metrics']} libsumo={ls['metrics']}"
    )
