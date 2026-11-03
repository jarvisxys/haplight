"""
Phase 1 acceptance tests (PLAN.md). Short episodes, one seed, Scenario 1.

Run:  pytest tests/test_env.py -v
"""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import metrics  # noqa: E402
from src.controllers import FixedTime, GreedyHAP, MaxPressure  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

NET_DIR = Path(__file__).resolve().parents[1] / "nets" / "arterial5"
CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"


def _short_cfg(episode_length_s: float = 900.0) -> dict:
    cfg = yaml.safe_load(CFG_PATH.read_text())
    cfg = copy.deepcopy(cfg)
    cfg["demand"]["episode_length_s"] = episode_length_s
    return cfg


def _run_episode(env, controller):
    obs = env.reset()
    controller.reset()
    info = env.info
    truncated = False
    while not truncated:
        actions = controller.act(obs, info)
        obs, reward, truncated, info = env.step(actions)
    return info


@pytest.fixture(scope="module")
def cfg():
    return _short_cfg()


@pytest.fixture(scope="module")
def fleet(cfg):
    return Fleet.from_config(cfg)


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_mp_beats_fixed_time(cfg, fleet):
    """MP ATT < FT ATT on S1 (PLAN.md Phase 1 gate)."""
    env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        ft = FixedTime(env, cfg, fleet)
        _run_episode(env, ft)
        ft_metrics = metrics.compute(
            env.completed_trips(), env.true_queue_history(), fleet, cfg,
            env.gmax_activation_rate(),
        )

        mp = MaxPressure(env)
        _run_episode(env, mp)
        mp_metrics = metrics.compute(
            env.completed_trips(), env.true_queue_history(), fleet, cfg,
            env.gmax_activation_rate(),
        )
    finally:
        env.close()

    assert ft_metrics["tp"] > 0 and mp_metrics["tp"] > 0, "no trips completed -- demand too low"
    assert mp_metrics["att"] < ft_metrics["att"], (
        f"MP ATT ({mp_metrics['att']:.2f}s) did not beat FT ATT ({ft_metrics['att']:.2f}s)"
    )


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_min_green_respected(cfg, fleet):
    """No phase is ever held for less than g_min before switching -- drive
    the env with a controller that tries to switch every single step (the
    adversarial case for the g_min gate)."""
    env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        info = env.info
        green_since_switch = {i: 0.0 for i in env.intersections}
        prev_phase = dict(info["current_phase"])
        truncated = False
        while not truncated:
            actions = {
                i: (prev_phase[i] + 1) % len(env.phases[i]) for i in env.intersections
            }
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                cur = info["current_phase"][i]
                if cur != prev_phase[i]:
                    assert green_since_switch[i] >= env.g_min - 1e-6, (
                        f"{i} switched after only {green_since_switch[i]}s "
                        f"(< g_min={env.g_min}s)"
                    )
                    green_since_switch[i] = 0.0
                else:
                    green_since_switch[i] += env.dt
                prev_phase[i] = cur
    finally:
        env.close()


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_mask_never_empty(cfg, fleet):
    """>=1 valid action, every step, every intersection."""
    env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        info = env.info
        for i in env.intersections:
            assert info["action_masks"][i].any()
        actions = {i: 0 for i in env.intersections}
        truncated = False
        while not truncated:
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                assert info["action_masks"][i].any(), f"{i} has an empty action mask"
    finally:
        env.close()


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_true_queues_noise_free(cfg, fleet):
    """eta=1.0 leaves true_queues unchanged. Both runs use the SAME fixed
    (non-reactive) action sequence so the underlying traffic realisation is
    identical regardless of eta -- isolating the sensing pipeline from
    eta-driven differences in control decisions.

    use_libsumo=False (traci, a genuinely separate OS process per episode):
    libsumo is an in-process singleton and does not reproduce bit-identical
    trajectories across separate env instances started earlier in the same
    Python process (observed directly: identical seed/actions, run in
    isolation -> identical; run after other tests already used libsumo in
    this process -> diverges). traci's subprocess isolation sidesteps that
    entirely, which is what this test needs since it is verifying a numeric
    invariant, not exercising the fast path."""
    results = {}
    for eta in (0.0, 1.0):
        env = HAPLightEnv(
            str(NET_DIR), cfg, fleet, seed=0, eta=eta, estimator="count", use_libsumo=False
        )
        try:
            obs = env.reset()
            info = env.info
            history = [copy.deepcopy(info["true_queues"])]
            truncated = False
            while not truncated:
                actions = {i: info["current_phase"][i] for i in env.intersections}
                obs, reward, truncated, info = env.step(actions)
                history.append(copy.deepcopy(info["true_queues"]))
            results[eta] = history
        finally:
            env.close()

    for step_true0, step_true1 in zip(results[0.0], results[1.0]):
        for i in step_true0:
            for mv in step_true0[i]:
                assert step_true0[i][mv] == pytest.approx(step_true1[i][mv], abs=1e-9), (
                    f"true_queues at eta=1.0 diverged from eta=0.0 for {i}/{mv}"
                )
