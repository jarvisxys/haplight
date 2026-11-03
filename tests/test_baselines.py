"""
Phase 5 acceptance test (prompts/phase5_baselines.md): every registered RL
baseline completes a short episode on S1 and S2 without error. Wiring
correctness only -- no training, no published-number gate (that's Stage
C, run separately and reported, not asserted in a fast test).

Run:  pytest tests/test_baselines.py -v
"""
import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.policy import HAPLightPolicy  # noqa: E402
from src.rl_baselines import (  # noqa: E402
    STATE_FNS, discover_intersections, make_policy, run_baseline_episode, run_ippo_episode,
)

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "configs" / "default.yaml"
NET_DIRS = {"s1": ROOT / "nets" / "arterial5", "s2": ROOT / "nets" / "grid4x4"}


def _short_cfg(episode_length_s: float = 300.0) -> dict:
    cfg = yaml.safe_load(CFG_PATH.read_text())
    cfg = copy.deepcopy(cfg)
    cfg["demand"]["episode_length_s"] = episode_length_s
    return cfg


@pytest.mark.parametrize("baseline_name", sorted(STATE_FNS.keys()))
@pytest.mark.parametrize("scenario", ["s1", "s2"])
def test_all_baselines_run(baseline_name, scenario):
    net_dir = NET_DIRS[scenario]
    if not net_dir.exists():
        pytest.skip(f"run scripts/build_nets.py first ({net_dir} missing)")

    cfg = _short_cfg()
    policy = make_policy(cfg, baseline_name)
    state_dict = {k: v.detach().cpu().clone() for k, v in policy.state_dict().items()}

    result = run_baseline_episode(
        baseline_name, state_dict, cfg, str(net_dir),
        run_seed=0, iteration=0, worker_id=0, eta=0.0, deterministic=True,
    )
    assert result["trajectories"], "no intersections produced trajectories"
    for traj in result["trajectories"].values():
        assert len(traj.steps) > 0
    assert result["episode_return"] == result["episode_return"]  # not NaN


@pytest.mark.parametrize("scenario", ["s1", "s2"])
def test_ippo_runs(scenario):
    """IPPO's own wiring test (not in STATE_FNS -- it reuses HAPLight's
    native obs/reward via N independent policies, not a custom state_fn)."""
    net_dir = NET_DIRS[scenario]
    if not net_dir.exists():
        pytest.skip(f"run scripts/build_nets.py first ({net_dir} missing)")

    cfg = _short_cfg()
    intersections = discover_intersections(str(net_dir), cfg)
    assert len(intersections) > 0
    state_dicts = {}
    for i in intersections:
        p = HAPLightPolicy(cfg)
        state_dicts[i] = {k: v.detach().cpu().clone() for k, v in p.state_dict().items()}

    result = run_ippo_episode(
        state_dicts, cfg, str(net_dir),
        run_seed=0, iteration=0, worker_id=0, eta=0.0, deterministic=True,
    )
    assert set(result["trajectories"].keys()) == set(intersections)
    for traj in result["trajectories"].values():
        assert len(traj.steps) > 0
    assert result["episode_return"] == result["episode_return"]
