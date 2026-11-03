"""
Shared phase-competition policy network (PLAN.md Phase 4, paper Table V,
Sec. V-C "Shared Phase-Competition Policy Architecture").

One network serves every intersection in every scenario: permutation-
invariant over movements (a shared per-movement encoder, pooled by summing
over the movements in a phase), indifferent to phase count (the
competition head scores phase PAIRS, so it works for any `n_phases`), and
indifferent to movement count (same reason, one level down). This is why
`obs[i]` from `src.env.HAPLightEnv` is a flat, per-intersection-width-
varying array rather than a fixed-size vector -- this module is the
consumer that was designed around.

`HAPLightEnv` already normalises/clips `obs[i]` (x_ref, mu_ref, clip from
cfg["rl"]["obs"]) -- this module must NOT re-normalise it.

Architecture (paper Table V; total 23,650 params, verified by
tests/test_policy.py::test_param_count against
cfg["rl"]["net"]["expected_param_count"]):

    Movement encoder   MLP 8->64->64, ReLU              4,736
    Phase pooling      sum over movements in phase           0
    Phase MLP          64->64, ReLU                     4,160
    Neighbour encoder  MLP 4->32, ReLU                     160
    Phase + context    concat 96->64, ReLU               6,208
    Competition head   pair 128->32->1                   4,161
    Value head         mean-pool 64->64->1               4,225

Two design choices the paper prose doesn't fully pin down (documented here,
not silently assumed):
  - Competition-head aggregation: for phase `a`, logit[a] = sum over b != a
    of competition_head(concat(rep[a], rep[b])) -- FRAP's own mechanism,
    consistent with this architecture's other pooling step (movement->phase
    is also an unweighted sum).
  - Competition head and value head end in a plain Linear (no activation)
    on their final layer -- they emit a raw logit / raw value estimate, not
    a non-negative number; Table V only marks "ReLU" on the hidden-layer
    rows.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn


def movement_index_phases(movements: Sequence[str], phases: Sequence[Sequence[str]]) -> List[List[int]]:
    """Maps env.phases[i] (movement-id strings) to index lists relative to
    env.movements[i]'s order -- the order obs[i]'s per-movement rows are
    laid out in. Call once per intersection (topology is static per
    episode) and reuse, not once per step."""
    index = {mv: k for k, mv in enumerate(movements)}
    return [[index[mv] for mv in phase] for phase in phases]


class HAPLightPolicy(nn.Module):
    def __init__(self, cfg: dict):
        super().__init__()
        net = cfg["rl"]["net"]
        in_dim = int(net["movement_in_dim"])
        mh = int(net["movement_hidden"])
        ph = int(net["phase_hidden"])
        nh = int(net["neighbour_hidden"])
        ch = int(net["competition_hidden"])
        self.n_neighbours = int(cfg["rl"]["obs"]["n_neighbours"])
        self.movement_in_dim = in_dim
        self.phase_hidden = ph

        self.movement_encoder = nn.Sequential(
            nn.Linear(in_dim, mh), nn.ReLU(),
            nn.Linear(mh, mh), nn.ReLU(),
        )
        self.phase_mlp = nn.Sequential(nn.Linear(mh, ph), nn.ReLU())
        self.neighbour_encoder = nn.Sequential(nn.Linear(self.n_neighbours, nh), nn.ReLU())
        self.phase_context = nn.Sequential(nn.Linear(ph + nh, ph), nn.ReLU())
        self.competition_head = nn.Sequential(
            nn.Linear(2 * ph, ch), nn.ReLU(),
            nn.Linear(ch, 1),
        )
        self.value_head = nn.Sequential(
            nn.Linear(ph, ph), nn.ReLU(),
            nn.Linear(ph, 1),
        )

    # -- single-intersection reference path -----------------------------

    def forward(
        self, obs_i: np.ndarray, phases_i: List[List[int]], mask_i: np.ndarray,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """obs_i: flat (8*n_movements + n_neighbours,) array (already
        normalised/clipped by env.py). phases_i: movement_index_phases(...)
        output for this intersection. mask_i: bool array (n_phases,).
        Returns (logits (n_phases,), value (scalar tensor)). Correctness
        reference; also the fallback forward_batch uses for ragged shapes
        that don't share a group with anything else."""
        obs_t = torch.as_tensor(np.asarray(obs_i), dtype=torch.float32)
        n_movements = (obs_t.shape[0] - self.n_neighbours) // self.movement_in_dim
        movement_feats = obs_t[: n_movements * self.movement_in_dim].view(n_movements, self.movement_in_dim)
        neighbour_feats = obs_t[n_movements * self.movement_in_dim:]

        m_emb = self.movement_encoder(movement_feats)  # (n_movements, mh)
        context = self.neighbour_encoder(neighbour_feats)  # (nh,)

        n_phases = len(phases_i)
        phase_reps = []
        for phi in phases_i:
            idx = torch.as_tensor(phi, dtype=torch.long)
            pooled = m_emb[idx].sum(dim=0)
            phase_reps.append(self.phase_mlp(pooled))
        phase_reps = torch.stack(phase_reps, dim=0)  # (n_phases, ph)

        ctx_expand = context.unsqueeze(0).expand(n_phases, -1)
        phase_ctx = self.phase_context(torch.cat([phase_reps, ctx_expand], dim=-1))  # (n_phases, ph)

        logits = phase_ctx.new_zeros(n_phases)
        for a in range(n_phases):
            total = phase_ctx.new_zeros(())
            for b in range(n_phases):
                if a == b:
                    continue
                pair = torch.cat([phase_ctx[a], phase_ctx[b]], dim=-1)
                total = total + self.competition_head(pair).squeeze(-1)
            logits[a] = total

        mask_t = torch.as_tensor(np.asarray(mask_i), dtype=torch.bool)
        logits = logits.masked_fill(~mask_t, -1e9)

        value = self.value_head(phase_ctx.mean(dim=0)).squeeze(-1)
        return logits, value

    # -- batched path, grouped by (n_movements, n_phases) shape signature --

    def forward_batch(
        self, obs_batch: np.ndarray, phases_batch: List[List[List[int]]], mask_batch: np.ndarray,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """obs_batch: (B, 8*n_movements + n_neighbours) -- every sample in
        this call MUST share n_movements (caller groups by shape signature
        first; see src.ppo's grouping helper). phases_batch: length-B list
        of movement_index_phases(...) outputs -- n_phases must match across
        the batch, but WHICH movements belong to which phase may differ
        per-sample (handled via a per-sample membership tensor, not
        assumed identical). mask_batch: (B, n_phases) bool.
        Returns (logits (B, n_phases), value (B,)) -- purely a performance
        path; must match forward() called once per sample (see
        test_policy.py::test_forward_batch_matches_forward)."""
        obs_t = torch.as_tensor(np.asarray(obs_batch), dtype=torch.float32)
        B = obs_t.shape[0]
        n_movements = (obs_t.shape[1] - self.n_neighbours) // self.movement_in_dim
        n_phases = len(phases_batch[0])

        movement_feats = obs_t[:, : n_movements * self.movement_in_dim].view(B, n_movements, self.movement_in_dim)
        neighbour_feats = obs_t[:, n_movements * self.movement_in_dim:]

        m_emb = self.movement_encoder(movement_feats)  # (B, n_movements, mh)
        context = self.neighbour_encoder(neighbour_feats)  # (B, nh)

        membership = torch.zeros(B, n_phases, n_movements, dtype=torch.float32)
        for b, phases_b in enumerate(phases_batch):
            for p, movs in enumerate(phases_b):
                for mv_idx in movs:
                    membership[b, p, mv_idx] = 1.0

        pooled = torch.bmm(membership, m_emb)  # (B, n_phases, mh)
        phase_reps = self.phase_mlp(pooled)  # (B, n_phases, ph)

        ctx_expand = context.unsqueeze(1).expand(-1, n_phases, -1)  # (B, n_phases, nh)
        phase_ctx = self.phase_context(torch.cat([phase_reps, ctx_expand], dim=-1))  # (B, n_phases, ph)

        a_rep = phase_ctx.unsqueeze(2).expand(-1, -1, n_phases, -1)  # (B, n_phases[a], n_phases[b], ph)
        b_rep = phase_ctx.unsqueeze(1).expand(-1, n_phases, -1, -1)
        pairs = torch.cat([a_rep, b_rep], dim=-1)  # (B, n_phases, n_phases, 2*ph)
        pair_scores = self.competition_head(pairs).squeeze(-1)  # (B, n_phases, n_phases)
        eye = torch.eye(n_phases, dtype=torch.bool).unsqueeze(0)
        pair_scores = pair_scores.masked_fill(eye, 0.0)
        logits = pair_scores.sum(dim=2)  # sum over b -> (B, n_phases)

        mask_t = torch.as_tensor(np.asarray(mask_batch), dtype=torch.bool)
        logits = logits.masked_fill(~mask_t, -1e9)

        value = self.value_head(phase_ctx.mean(dim=1)).squeeze(-1)  # (B,)
        return logits, value

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())
