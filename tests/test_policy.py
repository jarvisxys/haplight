"""
Phase 4 acceptance tests (PLAN.md): policy architecture pins exactly to
paper Table V, and masking is respected. Pure PyTorch, no SUMO.

Run:  pytest tests/test_policy.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.policy import HAPLightPolicy, movement_index_phases  # noqa: E402

CFG = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "configs" / "default.yaml").read_text()
)


@pytest.fixture
def model():
    torch.manual_seed(0)
    return HAPLightPolicy(CFG)


def test_param_count(model):
    """PLAN.md Phase 4 gate: exactly 23,650 parameters. If this fails, the
    architecture differs from paper Table V -- fix the code, not this
    test or the config's expected_param_count."""
    assert model.param_count() == CFG["rl"]["net"]["expected_param_count"] == 23650


def test_mask_blocks_invalid(model):
    """Masked phases get logit -1e9 and exactly zero softmax probability."""
    movements = ["a->b", "c->d", "e->f"]
    phases = [["a->b", "c->d"], ["e->f"], ["a->b"]]
    phases_idx = movement_index_phases(movements, phases)
    n_neighbours = CFG["rl"]["obs"]["n_neighbours"]
    obs = np.random.default_rng(0).standard_normal(8 * 3 + n_neighbours).astype(np.float32)

    mask = np.array([True, False, True])
    logits, _ = model.forward(obs, phases_idx, mask)
    assert logits[1].item() == pytest.approx(-1e9)
    probs = torch.softmax(logits, dim=0)
    assert probs[1].item() == 0.0
    assert probs[0].item() > 0.0 and probs[2].item() > 0.0


def test_mask_always_leaves_room_for_current_phase():
    """A fully-open mask (all True) should never itself raise or produce
    degenerate output -- sanity check alongside the masking gate above."""
    torch.manual_seed(1)
    model = HAPLightPolicy(CFG)
    movements = ["a->b", "c->d"]
    phases = [["a->b"], ["c->d"]]
    phases_idx = movement_index_phases(movements, phases)
    n_neighbours = CFG["rl"]["obs"]["n_neighbours"]
    obs = np.zeros(8 * 2 + n_neighbours, dtype=np.float32)
    mask = np.array([True, True])
    logits, value = model.forward(obs, phases_idx, mask)
    assert torch.isfinite(logits).all()
    assert torch.isfinite(value)


def test_forward_batch_matches_forward():
    """forward_batch is a performance path (grouping by shape signature),
    not a different model -- it must exactly reproduce per-sample forward()
    even when phase-movement membership differs between same-shaped
    intersections (only counts need to match within a group, not
    membership)."""
    torch.manual_seed(2)
    model = HAPLightPolicy(CFG)
    model.eval()
    n_neighbours = CFG["rl"]["obs"]["n_neighbours"]
    movements = ["a->b", "c->d", "e->f"]
    phase_defs = [
        [["a->b", "c->d"], ["e->f"]],
        [["a->b"], ["c->d", "e->f"]],
        [["a->b", "c->d"], ["e->f"]],
        [["c->d"], ["a->b", "e->f"]],
    ]
    rng = np.random.default_rng(3)
    obs_batch = rng.standard_normal((4, 8 * 3 + n_neighbours)).astype(np.float32)
    mask_batch = np.array([[True, True]] * 4)
    phases_batch = [movement_index_phases(movements, p) for p in phase_defs]

    with torch.no_grad():
        logits_b, value_b = model.forward_batch(obs_batch, phases_batch, mask_batch)
        for k in range(4):
            logits_i, value_i = model.forward(obs_batch[k], phases_batch[k], mask_batch[k])
            assert torch.allclose(logits_b[k], logits_i, atol=1e-5), (logits_b[k], logits_i)
            assert torch.allclose(value_b[k], value_i, atol=1e-5), (value_b[k], value_i)


def test_forward_batch_respects_mask():
    torch.manual_seed(4)
    model = HAPLightPolicy(CFG)
    n_neighbours = CFG["rl"]["obs"]["n_neighbours"]
    movements = ["a->b", "c->d"]
    phases = [["a->b"], ["c->d"]]
    phases_idx = movement_index_phases(movements, phases)
    rng = np.random.default_rng(5)
    obs_batch = rng.standard_normal((2, 8 * 2 + n_neighbours)).astype(np.float32)
    mask_batch = np.array([[True, False], [False, True]])
    phases_batch = [phases_idx, phases_idx]

    logits_b, _ = model.forward_batch(obs_batch, phases_batch, mask_batch)
    probs = torch.softmax(logits_b, dim=1)
    assert probs[0, 1].item() == 0.0
    assert probs[1, 0].item() == 0.0
