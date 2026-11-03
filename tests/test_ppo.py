"""
Phase 4 acceptance tests (PLAN.md): the two PPO subtleties that are load-
bearing per paper Sec. V-F -- filtered steps carry no policy gradient, and
truncation is bootstrapped, not treated as terminal. Pure PyTorch/synthetic
data, no SUMO.

Run:  pytest tests/test_ppo.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.policy import HAPLightPolicy  # noqa: E402
from src.ppo import Step, Trajectory, compute_gae, compute_losses  # noqa: E402

CFG = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "configs" / "default.yaml").read_text()
)


def _fake_step(rng, n_movements=3, n_phases=2, action=0, log_prob=-0.5,
               value=1.0, reward=1.0, filtered=False):
    n_neighbours = CFG["rl"]["obs"]["n_neighbours"]
    obs = rng.standard_normal(8 * n_movements + n_neighbours).astype(np.float32)
    phases_idx = [[0, 1], [2]] if n_phases == 2 else [list(range(n_movements))]
    mask = np.ones(n_phases, dtype=bool)
    return Step(obs=obs, phases_idx=phases_idx, mask=mask, action=action,
                log_prob=log_prob, value=value, reward=reward, filtered=filtered)


def test_filtered_steps_no_gradient():
    """Two batches, identical except a FILTERED step's action (and hence
    its own log_prob/entropy contribution) differs -- masking must make
    the aggregate policy_loss/entropy_loss, and every gradient, byte-
    identical. value_loss is also unaffected since it never depended on
    action, only obs (same obs in both), confirming value regression is
    untouched by the masking logic entirely, as intended."""
    torch.manual_seed(0)
    policy = HAPLightPolicy(CFG)
    rng = np.random.default_rng(0)

    shared_obs_steps = [_fake_step(rng, action=0, filtered=False) for _ in range(3)]
    filtered_step_a = _fake_step(rng, action=0, filtered=True)
    filtered_step_b = Step(
        obs=filtered_step_a.obs, phases_idx=filtered_step_a.phases_idx,
        mask=filtered_step_a.mask, action=1,  # different action
        log_prob=filtered_step_a.log_prob, value=filtered_step_a.value,
        reward=filtered_step_a.reward, filtered=True,
    )

    steps_a = shared_obs_steps + [filtered_step_a]
    steps_b = shared_obs_steps + [filtered_step_b]

    advantages = torch.tensor([1.0, -0.5, 0.3, 2.0], dtype=torch.float32)
    returns = torch.tensor([1.0, 1.0, 1.0, 1.0], dtype=torch.float32)
    old_log_probs = torch.tensor([s.log_prob for s in steps_a], dtype=torch.float32)

    policy_loss_a, value_loss_a, entropy_loss_a = compute_losses(
        policy, steps_a, advantages, returns, old_log_probs, clip=0.2,
    )
    policy_loss_b, value_loss_b, entropy_loss_b = compute_losses(
        policy, steps_b, advantages, returns, old_log_probs, clip=0.2,
    )

    assert torch.allclose(policy_loss_a, policy_loss_b), (policy_loss_a, policy_loss_b)
    assert torch.allclose(entropy_loss_a, entropy_loss_b), (entropy_loss_a, entropy_loss_b)
    assert torch.allclose(value_loss_a, value_loss_b), (value_loss_a, value_loss_b)

    # policy_loss's graph never touches value_head (value doesn't depend on
    # action), so those params legitimately have grad=None -- compare
    # None-ness and, where present, the actual gradient values.
    policy.zero_grad(set_to_none=True)
    policy_loss_a.backward(retain_graph=True)
    grads_a = [p.grad.clone() if p.grad is not None else None for p in policy.parameters()]

    policy.zero_grad(set_to_none=True)
    policy_loss_b.backward()
    grads_b = [p.grad.clone() if p.grad is not None else None for p in policy.parameters()]

    assert any(g is not None for g in grads_a), "test is vacuous -- no gradients were computed at all"
    for ga, gb in zip(grads_a, grads_b):
        assert (ga is None) == (gb is None)
        if ga is not None:
            assert torch.allclose(ga, gb, atol=1e-6), "gradient differs despite only a filtered step changing"


def test_filtered_steps_excluded_but_present_in_batch():
    """A batch of ALL filtered steps must not divide-by-zero (denom
    clamp) and must produce a zero policy/entropy loss (nothing
    contributes)."""
    torch.manual_seed(1)
    policy = HAPLightPolicy(CFG)
    rng = np.random.default_rng(1)
    steps = [_fake_step(rng, filtered=True) for _ in range(4)]
    advantages = torch.tensor([1.0, -1.0, 0.5, -0.5], dtype=torch.float32)
    returns = torch.tensor([1.0, 1.0, 1.0, 1.0], dtype=torch.float32)
    old_log_probs = torch.tensor([s.log_prob for s in steps], dtype=torch.float32)

    policy_loss, value_loss, entropy_loss = compute_losses(
        policy, steps, advantages, returns, old_log_probs, clip=0.2,
    )
    assert policy_loss.item() == 0.0
    assert entropy_loss.item() == 0.0
    assert torch.isfinite(value_loss)


def test_truncation_bootstraps():
    """GAE at the final step must actually use traj.bootstrap_value
    (V(s_T)) -- two trajectories identical except bootstrap_value produce
    different advantages/returns at the last step, and the bootstrapped
    one matches the hand-computed GAE delta exactly."""
    rng = np.random.default_rng(2)
    steps = [
        _fake_step(rng, value=1.0, reward=1.0),
        _fake_step(rng, value=1.0, reward=1.0),
    ]
    gamma, lam = 0.99, 0.95

    traj_bootstrap = Trajectory(steps=steps, bootstrap_value=10.0)
    traj_zero = Trajectory(steps=steps, bootstrap_value=0.0)

    adv_b, ret_b = compute_gae(traj_bootstrap, gamma, lam)
    adv_z, ret_z = compute_gae(traj_zero, gamma, lam)

    assert adv_b[-1] != pytest.approx(adv_z[-1])
    assert ret_b[-1] != pytest.approx(ret_z[-1])

    expected_last_delta = steps[-1].reward + gamma * 10.0 - steps[-1].value
    assert adv_b[-1] == pytest.approx(expected_last_delta)

    expected_last_delta_zero = steps[-1].reward + gamma * 0.0 - steps[-1].value
    assert adv_z[-1] == pytest.approx(expected_last_delta_zero)


def test_gae_empty_trajectory():
    traj = Trajectory(steps=[], bootstrap_value=5.0)
    adv, ret = compute_gae(traj, gamma=0.99, lam=0.95)
    assert adv == [] and ret == []
