"""
PPO trainer for HAPLightPolicy (PLAN.md Phase 4, paper Sec. V-F
"Training and Credit Assignment Under the Filter", Algorithm 2).

Pools per-intersection trajectories from E parallel episodes and updates
theta by PPO with a clipped surrogate and GAE. Three subtleties are load-
bearing (paper Sec. V-F) and each has a dedicated test:

  1. Filtered steps carry no policy gradient. When the safety filter
     (src.safety_filter) overrides intersection i at time t, the executed
     action was not the policy's -- masking those steps out of the policy-
     gradient and entropy terms (but NOT out of GAE/value regression) is
     what `compute_losses` does. test_filtered_steps_no_gradient proves
     this: two batches differing only in a filtered step's (masked-out)
     action produce byte-identical loss AND identical gradients.
  2. Time-limit bootstrapping. Every src.env.HAPLightEnv episode ends by
     TRUNCATION, never termination -- `compute_gae` always bootstraps with
     `traj.bootstrap_value` (V(s_T)) rather than treating the last step's
     return as terminal. test_truncation_bootstraps proves the bootstrap
     value is actually used, not silently dropped to 0.
  3. Advantages are normalised across the pooled batch (every intersection
     and timestep together), not per-intersection. Rewards keep the fixed
     Eq. (12) scaling from src.env -- no reward normalisation here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from src.policy import HAPLightPolicy


@dataclass
class Step:
    """One (intersection, decision-step) sample."""
    obs: np.ndarray
    phases_idx: List[List[int]]
    mask: np.ndarray
    action: int
    log_prob: float
    value: float
    reward: float
    filtered: bool


@dataclass
class Trajectory:
    """One full episode, one intersection. `bootstrap_value` is V(s_T),
    a forward pass on the final observation after the episode truncates --
    filled in by the rollout worker, never left at a default 0 (that would
    silently reintroduce the terminal-state bug Sec. V-F warns about)."""
    steps: List[Step] = field(default_factory=list)
    bootstrap_value: float = 0.0


def select_action(
    policy: HAPLightPolicy, obs_i: np.ndarray, phases_idx: List[List[int]],
    mask_i: np.ndarray, deterministic: bool = False,
) -> Tuple[int, float, float]:
    """Used by rollout workers (scripts.train) to propose the policy's own
    action BEFORE the safety filter is consulted -- the log_prob/value
    stored here are of the policy's genuine proposal, regardless of
    whether the filter later overrides the executed action."""
    with torch.no_grad():
        logits, value = policy.forward(obs_i, phases_idx, mask_i)
        dist = torch.distributions.Categorical(logits=logits)
        action = torch.argmax(logits) if deterministic else dist.sample()
        log_prob = dist.log_prob(action)
    return int(action.item()), float(log_prob.item()), float(value.item())


def compute_gae(traj: Trajectory, gamma: float, lam: float) -> Tuple[List[float], List[float]]:
    """Standard GAE(lambda), ALWAYS bootstrapping with traj.bootstrap_value
    at the final step -- see module docstring point 2."""
    n = len(traj.steps)
    if n == 0:
        return [], []
    advantages = [0.0] * n
    values = [s.value for s in traj.steps] + [traj.bootstrap_value]
    gae = 0.0
    for t in reversed(range(n)):
        delta = traj.steps[t].reward + gamma * values[t + 1] - values[t]
        gae = delta + gamma * lam * gae
        advantages[t] = gae
    returns = [advantages[t] + values[t] for t in range(n)]
    return advantages, returns


def _shape_signature(step: Step) -> Tuple[int, int]:
    n_phases = len(step.phases_idx)
    n_movements = max((idx for phase in step.phases_idx for idx in phase), default=-1) + 1
    return (n_movements, n_phases)


def forward_grouped(policy: HAPLightPolicy, steps: List[Step]) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
    """Groups `steps` by (n_movements, n_phases) shape signature and calls
    policy.forward_batch once per group (falling back to policy.forward
    for singleton groups) -- the batching optimisation from the plan: a
    naive per-step Python loop calling forward() individually is ~370k
    small nn.Module invocations per PPO update across a full rollout,
    which would make the update rival SUMO's own cost. Returns
    (logits_per_step, values_per_step), same order as `steps` (each
    logits[k] has length steps[k]'s own n_phases, so this stays a plain
    list, not a stacked tensor, across groups with different n_phases)."""
    groups: Dict[Tuple[int, int], List[int]] = {}
    for k, s in enumerate(steps):
        groups.setdefault(_shape_signature(s), []).append(k)

    logits_out: List[torch.Tensor] = [None] * len(steps)  # type: ignore[list-item]
    values_out: List[torch.Tensor] = [None] * len(steps)  # type: ignore[list-item]
    for idxs in groups.values():
        if len(idxs) == 1:
            k = idxs[0]
            s = steps[k]
            logits, value = policy.forward(s.obs, s.phases_idx, s.mask)
            logits_out[k], values_out[k] = logits, value
        else:
            obs_batch = np.stack([steps[k].obs for k in idxs])
            phases_batch = [steps[k].phases_idx for k in idxs]
            mask_batch = np.stack([steps[k].mask for k in idxs])
            logits_b, value_b = policy.forward_batch(obs_batch, phases_batch, mask_batch)
            for j, k in enumerate(idxs):
                logits_out[k], values_out[k] = logits_b[j], value_b[j]
    return logits_out, values_out


def compute_losses(
    policy: HAPLightPolicy,
    steps: List[Step],
    advantages: torch.Tensor,
    returns: torch.Tensor,
    old_log_probs: torch.Tensor,
    clip: float,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """One PPO minibatch's (policy_loss, value_loss, entropy_loss).
    `advantages` must already be normalised across the FULL pooled batch
    (not just this minibatch) before being sliced and passed in here --
    see PPOTrainer.update. Filtered steps are masked out of policy_loss
    and entropy_loss (mean over UNfiltered steps only); value_loss uses
    every step, unmasked -- module docstring point 1."""
    logits_list, values_list = forward_grouped(policy, steps)

    new_log_probs = []
    entropies = []
    for k, s in enumerate(steps):
        dist = torch.distributions.Categorical(logits=logits_list[k])
        new_log_probs.append(dist.log_prob(torch.as_tensor(s.action, dtype=torch.long)))
        entropies.append(dist.entropy())
    new_log_probs = torch.stack(new_log_probs)
    entropies = torch.stack(entropies)
    values = torch.stack(values_list)

    ratio = torch.exp(new_log_probs - old_log_probs)
    surr1 = ratio * advantages
    surr2 = torch.clamp(ratio, 1 - clip, 1 + clip) * advantages
    per_step_policy_loss = -torch.min(surr1, surr2)

    unfiltered = torch.tensor([0.0 if s.filtered else 1.0 for s in steps], dtype=torch.float32)
    denom = unfiltered.sum().clamp(min=1.0)
    policy_loss = (unfiltered * per_step_policy_loss).sum() / denom
    entropy_loss = -(unfiltered * entropies).sum() / denom

    value_loss = F.mse_loss(values, returns)  # ALL steps, unmasked

    return policy_loss, value_loss, entropy_loss


class PPOTrainer:
    def __init__(self, policy: HAPLightPolicy, cfg: dict, device: str = "cpu"):
        self.policy = policy.to(device)
        self.device = device
        ppo_cfg = cfg["rl"]["ppo"]
        self.clip = float(ppo_cfg["clip"])
        self.epochs = int(ppo_cfg["epochs"])
        self.minibatch = int(ppo_cfg["minibatch"])
        self.gamma = float(ppo_cfg["gamma"])
        self.gae_lambda = float(ppo_cfg["gae_lambda"])
        self.entropy_coef = float(ppo_cfg["entropy_coef"])
        self.value_coef = float(ppo_cfg["value_coef"])
        self.grad_clip = float(ppo_cfg["grad_clip"])
        self.base_lr = float(ppo_cfg["lr"])
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=self.base_lr)

    def set_lr(self, iteration: int, total_iterations: int) -> None:
        """Linear decay to zero over training (Sec. V-F point 3)."""
        frac = max(0.0, 1.0 - iteration / max(1, total_iterations))
        for g in self.optimizer.param_groups:
            g["lr"] = self.base_lr * frac

    def update(self, trajectories: List[Trajectory]) -> Dict[str, float]:
        all_steps: List[Step] = []
        all_adv: List[float] = []
        all_ret: List[float] = []
        for traj in trajectories:
            adv, ret = compute_gae(traj, self.gamma, self.gae_lambda)
            all_steps.extend(traj.steps)
            all_adv.extend(adv)
            all_ret.extend(ret)

        n = len(all_steps)
        if n == 0:
            return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0}

        adv_t = torch.tensor(all_adv, dtype=torch.float32)
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std(unbiased=False) + 1e-8)  # pooled-batch normalisation
        ret_t = torch.tensor(all_ret, dtype=torch.float32)
        old_log_probs_t = torch.tensor([s.log_prob for s in all_steps], dtype=torch.float32)

        stats = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0}
        n_mb = 0
        idx_all = np.arange(n)
        for _ in range(self.epochs):
            np.random.shuffle(idx_all)
            for start in range(0, n, self.minibatch):
                mb = idx_all[start:start + self.minibatch]
                mb_steps = [all_steps[k] for k in mb]
                mb_adv = adv_t[mb]
                mb_ret = ret_t[mb]
                mb_old_lp = old_log_probs_t[mb]

                policy_loss, value_loss, entropy_loss = compute_losses(
                    self.policy, mb_steps, mb_adv, mb_ret, mb_old_lp, self.clip,
                )
                total_loss = policy_loss + self.value_coef * value_loss + self.entropy_coef * entropy_loss

                self.optimizer.zero_grad()
                total_loss.backward()
                nn.utils.clip_grad_norm_(self.policy.parameters(), self.grad_clip)
                self.optimizer.step()

                stats["policy_loss"] += float(policy_loss.item())
                stats["value_loss"] += float(value_loss.item())
                stats["entropy"] += float(-entropy_loss.item())
                n_mb += 1

        return {k: v / max(1, n_mb) for k, v in stats.items()}
