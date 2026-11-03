"""
RL baselines (PLAN.md Phase 5, prompts/phase5_baselines.md).

What differs between these methods is the state, the reward and the
network -- not the training loop. This module holds, per baseline: a
state-builder function (reads `info` directly, mirrors how
`src.controllers.AdvancedMP` builds its own literature-faithful features --
NOT `env._build_obs`, which is hardcoded to HAPLight's own 8-feature-per-
movement layout and is not reusable here), and two small config-shadowing
helpers so the SAME `src.policy.HAPLightPolicy` / `src.ppo.PPOTrainer`
classes serve every baseline with their own net width / reward form,
without editing either file.

Fairness constraints (PAPER_CHANGELOG P4-2, P5-1; carried into every
baseline here):
  - State reads the SENSED channel (`x_hat`/`counts_hat`/
    `counts_hat_downstream`) -- same convention `AdvancedMP`/`EfficientMP`
    already use, so a robustness/noise sweep hits every method identically.
  - Reward always reads the TRUE channel (`info["true_w"]`/`true_queues`)
    via `env.py`'s own `_compute_reward` -- never recomputed here from the
    sensed channel.
  - No safety filter on any baseline here (approved Phase 5 plan, decision
    A): Corollary-1's filter is HAPLight-RL's own contribution; composing
    it onto a competitor would confound the pooled gridlock-rate
    comparison the paper is making. Every baseline in this file is a bare,
    literature-faithful RL controller.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402
from src.policy import HAPLightPolicy, movement_index_phases  # noqa: E402
from src.ppo import PPOTrainer, Step, Trajectory, select_action  # noqa: E402

# ---------------------------------------------------------------------------
# Config shadowing: HAPLightPolicy reads cfg["rl"]["net"]/cfg["rl"]["obs"]
# and env reads cfg["rl"]["reward"]["form"] -- both hardcoded to that path
# (PAPER_CHANGELOG P5-1: confirmed directly, not assumed, before writing
# this). Rather than edit either class to accept an arbitrary cfg path,
# build a shallow-copied "shadow" cfg per baseline with just those two
# leaves swapped -- zero changes to policy.py/env.py's own read path.
# ---------------------------------------------------------------------------


def baseline_policy_cfg(cfg: dict, name: str) -> dict:
    b = cfg["rl_baselines"][name]
    shadow = dict(cfg)
    shadow["rl"] = dict(cfg["rl"])
    shadow["rl"]["net"] = b["net"]
    shadow["rl"]["obs"] = dict(cfg["rl"]["obs"])
    shadow["rl"]["obs"]["n_neighbours"] = b["obs"]["n_neighbours"]
    return shadow


def baseline_env_cfg(cfg: dict, name: str) -> dict:
    b = cfg["rl_baselines"][name]
    shadow = dict(cfg)
    shadow["rl"] = dict(cfg["rl"])
    shadow["rl"]["reward"] = dict(cfg["rl"]["reward"])
    shadow["rl"]["reward"]["form"] = b["reward_form"]
    # CoLight needs env._neighbours populated at its OWN n_neighbours width
    # (env.py reads cfg["rl"]["obs"]["n_neighbours"] at construction to
    # size/truncate it -- every other baseline here has n_neighbours=0 and
    # never touches _neighbours, so this shadow is a no-op for them).
    shadow["rl"]["obs"] = dict(cfg["rl"]["obs"])
    shadow["rl"]["obs"]["n_neighbours"] = b["obs"]["n_neighbours"]
    return shadow


# ---------------------------------------------------------------------------
# Advanced-MPLight (b_advxlight, Zhang et al. ICML 2022) -- Advanced Traffic
# State: per movement, [lane-normalised efficient pressure, running-vehicle
# demand within influence range]. Decentralised (no neighbour term). Same
# two ingredients as src.controllers.AdvancedMP -- ground-truth-only, no
# sensing-noise model of its own in this codebase, same convention that
# classical controller already accepts. The running-demand ingredient
# reads env.running_demand_hat (cached), NOT env.running_count_within_range
# (live per-vehicle traci, what AdvancedMP the classical controller still
# uses) -- PAPER_CHANGELOG P5-1: the live version, called for every
# movement/step/worker at RL-rollout volume, cost ~4x a normal training
# iteration; running_demand_hat is numerically EXACT for this codebase's
# scenario geometry (see running_demand_hat's own docstring), not a looser
# approximation, so classical AdvancedMP and this RL variant still agree
# on what "running demand" means, just via two different code paths sized
# for two very different call volumes. Requires the env to be constructed
# with advanced_mp_running_demand=True (run_baseline_episode/
# _run_metrics_episode below do this whenever name == "advanced_mplight").
# ---------------------------------------------------------------------------


def build_state_advanced_mplight(env: HAPLightEnv, info: dict) -> Dict[str, np.ndarray]:
    b = env.cfg["rl_baselines"]["advanced_mplight"]
    x_ref = float(b["obs"]["x_ref"])
    clip = float(b["obs"]["clip"])
    n_lanes_mv = info["n_lanes"]
    n_lanes_edge = info["n_lanes_edge"]
    # P5-3: composition-weighted mean rho, i.e. the weight-units one
    # average vehicle contributes. Converts the raw running-vehicle COUNT
    # into the same units as the rho-weighted pressure channel.
    rho = env.fleet.rho
    mean_rho = sum(rho[n] * c.share for n, c in env.fleet.classes.items())

    obs: Dict[str, np.ndarray] = {}
    for i in env.intersections:
        rows: List[float] = []
        for mv in env.movements[i]:
            out_edge = mv.split("->")[1]
            nl_up = max(1, n_lanes_mv[i].get(mv, 1))
            nl_down = max(1, n_lanes_edge.get(out_edge, 1))
            x_up = sum(info["counts_hat"][i][mv].values()) / nl_up
            x_down = sum(info["counts_hat_downstream"][i][mv].values()) / nl_down
            eff_pressure = x_up - x_down

            # PAPER_CHANGELOG P5-1: running_demand_hat (cached, from
            # _measure()'s existing subscription pass) replaces the live
            # per-vehicle running_count_within_range call here -- this is
            # the hot path (every movement, every step, every parallel
            # worker) that made Advanced-MPLight ~4x slower than every
            # other baseline. Requires the env to be constructed with
            # advanced_mp_running_demand=True (see run_baseline_episode/
            # _run_metrics_episode below); the classical AdvancedMP
            # controller in src.controllers is UNCHANGED and still uses
            # the live-query method directly, and running_demand_hat
            # still matches it EXACTLY (verified 1500/1500), which is the
            # property that makes this port faithful. Do not change the
            # count itself here.
            #
            # P5-3 UNIT FIX: the count is a raw VEHICLE COUNT, while
            # eff_pressure above is rho-WEIGHTED queue mass. Dividing both
            # by x_ref (a weight-unit reference, 50) was a genuine
            # dimensional error -- correct for the pressure channel,
            # wrong for a vehicle count -- and left the demand channel at
            # 2.29x the pressure channel's std and 7.4x its mean. Convert
            # the count to the SAME weight units first, using the fleet's
            # composition-weighted mean rho, so both channels are
            # dimensionally comparable before the shared x_ref divide.
            running_demand = env.running_demand_hat(i, mv) * mean_rho

            rows.extend([eff_pressure / x_ref, running_demand / x_ref])
        arr = np.array(rows, dtype=np.float32)
        obs[i] = np.clip(arr, -clip, clip)
    return obs


def build_state_mplight(env: HAPLightEnv, info: dict) -> Dict[str, np.ndarray]:
    """MPLight (b_mplight, Chen et al. AAAI 2020) -- per-movement state is
    pressure ONLY (1 feature: lane-normalised x_up - x_down, sensed
    channel), no running-demand term (that's Advanced-MPLight's own later
    refinement). Decentralised, same as Advanced-MPLight -- no neighbour
    term."""
    b = env.cfg["rl_baselines"]["mplight"]
    x_ref = float(b["obs"]["x_ref"])
    clip = float(b["obs"]["clip"])
    n_lanes_mv = info["n_lanes"]
    n_lanes_edge = info["n_lanes_edge"]

    obs: Dict[str, np.ndarray] = {}
    for i in env.intersections:
        rows: List[float] = []
        for mv in env.movements[i]:
            out_edge = mv.split("->")[1]
            nl_up = max(1, n_lanes_mv[i].get(mv, 1))
            nl_down = max(1, n_lanes_edge.get(out_edge, 1))
            x_up = sum(info["counts_hat"][i][mv].values()) / nl_up
            x_down = sum(info["counts_hat_downstream"][i][mv].values()) / nl_down
            pressure = x_up - x_down
            rows.append(pressure / x_ref)
        arr = np.array(rows, dtype=np.float32)
        obs[i] = np.clip(arr, -clip, clip)
    return obs


def build_state_presslight(env: HAPLightEnv, info: dict) -> Dict[str, np.ndarray]:
    """PressLight (b_presslight, Wei et al. SIGKDD 2019) -- per-movement
    state is RAW (not lane-normalised, not differenced) vehicle counts on
    the upstream approach and the downstream edge it feeds, 2 separate
    features (sensed channel) -- distinct from MPLight's single, already-
    differenced pressure feature: PressLight's own published state keeps
    queue/count information raw and lets the network learn the
    relationship, whereas MPLight's later contribution was showing a
    single precomputed pressure value is enough. Decentralised, no
    neighbour term (matches MPLight/Advanced-MPLight here)."""
    b = env.cfg["rl_baselines"]["presslight"]
    x_ref = float(b["obs"]["x_ref"])
    clip = float(b["obs"]["clip"])

    obs: Dict[str, np.ndarray] = {}
    for i in env.intersections:
        rows: List[float] = []
        for mv in env.movements[i]:
            x_up = sum(info["counts_hat"][i][mv].values())
            x_down = sum(info["counts_hat_downstream"][i][mv].values())
            rows.extend([x_up / x_ref, x_down / x_ref])
        arr = np.array(rows, dtype=np.float32)
        obs[i] = np.clip(arr, -clip, clip)
    return obs


def build_state_colight(env: HAPLightEnv, info: dict) -> Dict[str, np.ndarray]:
    """CoLight (b_colight, Wei et al. CIKM 2019) -- per-intersection LOCAL
    state is PressLight-style raw per-movement counts [x_up, x_down]
    (sensed channel), followed by a FIXED-width per-neighbour summary
    block ([aggregate queue, aggregate pressure], sensed channel) for each
    of up to n_neighbours real graph neighbours (env._neighbours -- a
    documented, deliberate exception to "policy never touches env
    internals": CoLight's whole mechanism is attention over REAL neighbour
    identity, unlike HAPLight's own pre-aggregated 4-scalar summary),
    zero-padded exactly like env._build_obs's own neighbour tail. This
    carries RAW (pre-attention) neighbour features into `Step.obs` -- the
    attention computation itself happens inside CoLightPolicy.forward,
    fresh on every call with real gradients, NOT precomputed/frozen here.
    That is what lets this baseline reuse ppo.py's flat-shuffle
    minibatching completely unmodified (PAPER_CHANGELOG P5-1): every Step
    already carries everything its own forward pass needs, independent of
    which other Steps land in the same minibatch or what order they're
    processed in -- unlike a design that baked in a precomputed attention
    OUTPUT, which would need cross-Step coupling at loss time to receive
    any gradient at all."""
    b = env.cfg["rl_baselines"]["colight"]
    x_ref = float(b["obs"]["x_ref"])
    clip = float(b["obs"]["clip"])
    n_neighbours = int(b["obs"]["n_neighbours"])

    def _agg_summary(j: str) -> List[float]:
        x_up_sum = sum(sum(info["counts_hat"][j][mv].values()) for mv in env.movements[j])
        w_sum = sum(info["w_hat"][j][mv] for mv in env.movements[j])
        return [x_up_sum / x_ref, w_sum / x_ref]

    obs: Dict[str, np.ndarray] = {}
    for i in env.intersections:
        rows: List[float] = []
        for mv in env.movements[i]:
            x_up = sum(info["counts_hat"][i][mv].values())
            x_down = sum(info["counts_hat_downstream"][i][mv].values())
            rows.extend([x_up / x_ref, x_down / x_ref])

        neigh_rows: List[float] = []
        for j in env._neighbours[i][:n_neighbours]:
            neigh_rows.extend(_agg_summary(j))
        while len(neigh_rows) < 2 * n_neighbours:
            neigh_rows.append(0.0)

        arr = np.array(rows + neigh_rows, dtype=np.float32)
        obs[i] = np.clip(arr, -clip, clip)
    return obs


STATE_FNS: Dict[str, Callable[[HAPLightEnv, dict], Dict[str, np.ndarray]]] = {
    "advanced_mplight": build_state_advanced_mplight,
    "mplight": build_state_mplight,
    "presslight": build_state_presslight,
    "colight": build_state_colight,
}

# Reporting label (PAPER_CHANGELOG P5-1, author instruction): "colight"
# stays the internal config/dict key throughout this file, but every
# TABLE and CHANGELOG entry must display the precise, non-overclaiming
# name -- single-hop attention over raw sensed neighbour features, not
# multi-hop attention over other intersections' hidden embeddings (see
# CoLightPolicy's own docstring). Never print bare "CoLight".
DISPLAY_NAMES: Dict[str, str] = {
    "colight": "single-hop attention (CoLight variant)",
}


def display_name(name: str) -> str:
    return DISPLAY_NAMES.get(name, name)


class CoLightPolicy(nn.Module):
    """Single-hop graph-attention policy (PLAN.md Phase 5, decision B):
    a local per-movement encoder (PressLight-shaped), pooled to one
    per-intersection embedding, attends (single-head scaled dot-product,
    self included) over up to n_neighbours REAL neighbours' fixed-width
    raw summary blocks -- both computed fresh inside this forward pass, so
    gradients reach the attention weights AND the encoders on every call,
    not just at rollout time. Phase representations (same movement-pooling
    pattern as HAPLightPolicy) are combined with the attention context,
    then scored via the same pairwise phase-competition head. NOT
    multi-hop attention over other intersections' hidden embeddings (that
    would require cross-Step coupling ppo.py's flat-shuffle minibatching
    doesn't support) -- a real, disclosed simplification, not a frozen
    approximation (see build_state_colight's docstring)."""

    def __init__(self, cfg: dict):
        super().__init__()
        b = cfg["rl_baselines"]["colight"]
        net = b["net"]
        self.movement_in_dim = int(net["movement_in_dim"])
        self.n_neighbours = int(b["obs"]["n_neighbours"])
        mh = int(net["movement_hidden"])
        ph = int(net["phase_hidden"])
        ch = int(net["competition_hidden"])
        self.mh = mh
        self.phase_hidden = ph

        self.movement_encoder = nn.Sequential(
            nn.Linear(self.movement_in_dim, mh), nn.ReLU(),
            nn.Linear(mh, mh), nn.ReLU(),
        )
        self.neighbour_proj = nn.Sequential(nn.Linear(2, mh), nn.ReLU())
        self.attn_q = nn.Linear(mh, mh)
        self.attn_k = nn.Linear(mh, mh)
        self.attn_v = nn.Linear(mh, mh)
        self.phase_mlp = nn.Sequential(nn.Linear(mh, ph), nn.ReLU())
        self.phase_context = nn.Sequential(nn.Linear(ph + mh, ph), nn.ReLU())
        self.competition_head = nn.Sequential(
            nn.Linear(2 * ph, ch), nn.ReLU(),
            nn.Linear(ch, 1),
        )
        self.value_head = nn.Sequential(
            nn.Linear(ph, ph), nn.ReLU(),
            nn.Linear(ph, 1),
        )

    def _attend(self, e_i: torch.Tensor, neigh_feats: torch.Tensor) -> torch.Tensor:
        """e_i: (mh,). neigh_feats: (n_neighbours, 2) raw summary blocks
        (may be n_neighbours=0). Returns context: (mh,)."""
        if neigh_feats.shape[0] == 0:
            return e_i.new_zeros(self.mh)
        neigh_emb = self.neighbour_proj(neigh_feats)          # (n_neigh, mh)
        kv = torch.cat([e_i.unsqueeze(0), neigh_emb], dim=0)   # (1+n_neigh, mh)
        q = self.attn_q(e_i)                                   # (mh,)
        k = self.attn_k(kv)                                    # (1+n_neigh, mh)
        v = self.attn_v(kv)                                    # (1+n_neigh, mh)
        scores = (k @ q) / (self.mh ** 0.5)                    # (1+n_neigh,)
        alpha = torch.softmax(scores, dim=0)
        return (alpha.unsqueeze(-1) * v).sum(dim=0)             # (mh,)

    def forward(
        self, obs_i: np.ndarray, phases_i: List[List[int]], mask_i: np.ndarray,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        obs_t = torch.as_tensor(np.asarray(obs_i), dtype=torch.float32)
        neigh_len = 2 * self.n_neighbours
        local_len = obs_t.shape[0] - neigh_len
        n_movements = local_len // self.movement_in_dim
        movement_feats = obs_t[:local_len].view(n_movements, self.movement_in_dim)
        neigh_feats = obs_t[local_len:].view(self.n_neighbours, 2) if self.n_neighbours > 0 else obs_t.new_zeros(0, 2)

        m_emb = self.movement_encoder(movement_feats)   # (n_movements, mh)
        e_i = m_emb.mean(dim=0)                          # (mh,)
        context = self._attend(e_i, neigh_feats)          # (mh,)

        n_phases = len(phases_i)
        phase_reps = []
        for phi in phases_i:
            idx = torch.as_tensor(phi, dtype=torch.long)
            phase_reps.append(self.phase_mlp(m_emb[idx].sum(dim=0)))
        phase_reps = torch.stack(phase_reps, dim=0)       # (n_phases, ph)

        ctx_expand = context.unsqueeze(0).expand(n_phases, -1)
        phase_ctx = self.phase_context(torch.cat([phase_reps, ctx_expand], dim=-1))  # (n_phases, ph)

        logits = phase_ctx.new_zeros(n_phases)
        for a in range(n_phases):
            total = phase_ctx.new_zeros(())
            for bb in range(n_phases):
                if a == bb:
                    continue
                pair = torch.cat([phase_ctx[a], phase_ctx[bb]], dim=-1)
                total = total + self.competition_head(pair).squeeze(-1)
            logits[a] = total

        mask_t = torch.as_tensor(np.asarray(mask_i), dtype=torch.bool)
        logits = logits.masked_fill(~mask_t, -1e9)
        value = self.value_head(phase_ctx.mean(dim=0)).squeeze(-1)
        return logits, value

    def forward_batch(
        self, obs_batch: np.ndarray, phases_batch: List[List[List[int]]], mask_batch: np.ndarray,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        obs_t = torch.as_tensor(np.asarray(obs_batch), dtype=torch.float32)
        B = obs_t.shape[0]
        neigh_len = 2 * self.n_neighbours
        local_len = obs_t.shape[1] - neigh_len
        n_movements = local_len // self.movement_in_dim
        n_phases = len(phases_batch[0])

        movement_feats = obs_t[:, :local_len].view(B, n_movements, self.movement_in_dim)
        m_emb = self.movement_encoder(movement_feats)     # (B, n_movements, mh)
        e_i = m_emb.mean(dim=1)                             # (B, mh)

        if self.n_neighbours > 0:
            neigh_feats = obs_t[:, local_len:].view(B, self.n_neighbours, 2)
            neigh_emb = self.neighbour_proj(neigh_feats)     # (B, n_neigh, mh)
            kv = torch.cat([e_i.unsqueeze(1), neigh_emb], dim=1)  # (B, 1+n_neigh, mh)
            q = self.attn_q(e_i)                              # (B, mh)
            k = self.attn_k(kv)                               # (B, 1+n_neigh, mh)
            v = self.attn_v(kv)                               # (B, 1+n_neigh, mh)
            scores = torch.einsum("bnh,bh->bn", k, q) / (self.mh ** 0.5)  # (B, 1+n_neigh)
            alpha = torch.softmax(scores, dim=1)
            context = torch.einsum("bn,bnh->bh", alpha, v)    # (B, mh)
        else:
            context = e_i.new_zeros(B, self.mh)

        membership = torch.zeros(B, n_phases, n_movements, dtype=torch.float32)
        for b_idx, phases_b in enumerate(phases_batch):
            for p, movs in enumerate(phases_b):
                for mv_idx in movs:
                    membership[b_idx, p, mv_idx] = 1.0
        pooled = torch.bmm(membership, m_emb)               # (B, n_phases, mh)
        phase_reps = self.phase_mlp(pooled)                   # (B, n_phases, ph)

        ctx_expand = context.unsqueeze(1).expand(-1, n_phases, -1)
        phase_ctx = self.phase_context(torch.cat([phase_reps, ctx_expand], dim=-1))  # (B, n_phases, ph)

        a_rep = phase_ctx.unsqueeze(2).expand(-1, -1, n_phases, -1)
        b_rep = phase_ctx.unsqueeze(1).expand(-1, n_phases, -1, -1)
        pairs = torch.cat([a_rep, b_rep], dim=-1)
        pair_scores = self.competition_head(pairs).squeeze(-1)  # (B, n_phases, n_phases)
        eye = torch.eye(n_phases, dtype=torch.bool).unsqueeze(0)
        pair_scores = pair_scores.masked_fill(eye, 0.0)
        logits = pair_scores.sum(dim=2)

        mask_t = torch.as_tensor(np.asarray(mask_batch), dtype=torch.bool)
        logits = logits.masked_fill(~mask_t, -1e9)
        value = self.value_head(phase_ctx.mean(dim=1)).squeeze(-1)
        return logits, value

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

# ---------------------------------------------------------------------------
# Shared rollout worker -- same shape as scripts/train.py's
# run_episode_worker, minus the SafetyFilter (decision A) and parameterised
# by baseline name so a new entry in STATE_FNS + configs/default.yaml's
# rl_baselines block is all a future baseline needs, not a new worker
# function. Module-level and picklable for multiprocessing (spawn), same
# convention as every other rollout worker in this codebase.
# ---------------------------------------------------------------------------


def run_baseline_episode(
    name: str, policy_state_dict: dict, cfg: dict, net_dir: str,
    run_seed: int, iteration: int, worker_id: int, eta: float,
    deterministic: bool = False,
) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    fleet = Fleet.from_config(cfg)
    policy = make_policy(cfg, name)
    policy.load_state_dict(policy_state_dict)
    policy.eval()

    seed = int(np.random.SeedSequence([run_seed, iteration, worker_id]).generate_state(1)[0] % (2**31 - 1))
    torch.manual_seed(seed)

    env_cfg = baseline_env_cfg(cfg, name)
    state_fn = STATE_FNS[name]

    env = HAPLightEnv(
        net_dir, env_cfg, fleet, seed=seed, eta=eta, estimator="area",
        advanced_mp_running_demand=(name == "advanced_mplight"),
    )
    try:
        env.reset()
        info = env.info
        obs = state_fn(env, info)
        phase_idx = {i: movement_index_phases(env.movements[i], env.phases[i]) for i in env.intersections}

        trajs: Dict[str, Trajectory] = {i: Trajectory() for i in env.intersections}
        truncated = False
        while not truncated:
            actions: Dict[str, int] = {}
            meta = {}
            for i in env.intersections:
                a, lp, v = select_action(policy, obs[i], phase_idx[i], info["action_masks"][i], deterministic)
                actions[i] = a
                meta[i] = (a, lp, v)
            # env.step's own obs return is HAPLight's 8-feature layout --
            # discarded here; this baseline's own state_fn rebuilds obs
            # from `info` instead (see build_state_advanced_mplight).
            _env_obs, reward, truncated, next_info = env.step(actions)
            next_obs = state_fn(env, next_info)
            for i in env.intersections:
                a, lp, v = meta[i]
                trajs[i].steps.append(Step(
                    obs=obs[i], phases_idx=phase_idx[i], mask=info["action_masks"][i],
                    action=a, log_prob=lp, value=v, reward=reward[i], filtered=False,
                ))
            obs, info = next_obs, next_info

        for i in env.intersections:  # V(s_T) bootstrap at truncation
            _, _, v_T = select_action(policy, obs[i], phase_idx[i], info["action_masks"][i], deterministic)
            trajs[i].bootstrap_value = v_T

        per_i = [sum(s.reward for s in t.steps) for t in trajs.values()]
        return {
            "trajectories": trajs,
            "episode_return": float(np.mean(per_i)) if per_i else float("nan"),
        }
    finally:
        env.close()


def make_policy(cfg: dict, name: str):
    if name == "colight":
        return CoLightPolicy(cfg)
    return HAPLightPolicy(baseline_policy_cfg(cfg, name))


# ---------------------------------------------------------------------------
# IPPO -- the parameter-sharing ablation, not a literature baseline with its
# own state/reward (PAPER_CHANGELOG P5-1: `prompts/phase5_baselines.md`
# calls out PressLight/MPLight's own state/reward explicitly; IPPO has no
# citation and no such callout, and the scientifically honest reading of
# "independent PPO without parameter sharing" is that it isolates
# parameter-sharing as the SOLE independent variable). State = HAPLight's
# own obs (env._build_obs, unmodified), reward = whatever
# cfg["rl"]["reward"]["form"] HAPLight-RL actually trains with (currently
# total_queue, NOT pressure_all/"Eq. 12", which is flagged wrong-signed in
# configs/default.yaml) -- so IPPO does NOT go through STATE_FNS/
# baseline_policy_cfg/baseline_env_cfg at all; it reuses cfg["rl"] and
# HAPLightPolicy(cfg) verbatim, N times, one fully independent
# (HAPLightPolicy, PPOTrainer) pair per intersection ID (never per shape
# signature -- that would silently reintroduce sharing).
# ---------------------------------------------------------------------------


def discover_intersections(net_dir: str, cfg: dict) -> List[str]:
    """One throwaway reset to learn the static intersection-ID list for
    this net -- needed up front so N per-intersection policies can be
    constructed before any rollout worker runs. Topology is static per
    scenario (fixed net file), so this is a one-time cost, not per-episode."""
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(net_dir, cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        env.reset()
        return list(env.intersections)
    finally:
        env.close()


def run_ippo_episode(
    policy_state_dicts: Dict[str, dict], cfg: dict, net_dir: str,
    run_seed: int, iteration: int, worker_id: int, eta: float,
    deterministic: bool = False,
) -> dict:
    """Same shape as scripts.train.run_episode_worker, minus the
    SafetyFilter (decision A), and querying a SEPARATE policy per
    intersection ID instead of one shared network."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    fleet = Fleet.from_config(cfg)
    seed = int(np.random.SeedSequence([run_seed, iteration, worker_id]).generate_state(1)[0] % (2**31 - 1))
    torch.manual_seed(seed)

    env = HAPLightEnv(net_dir, cfg, fleet, seed=seed, eta=eta, estimator="area")
    try:
        obs = env.reset()
        info = env.info
        policies = {}
        for i in env.intersections:
            p = HAPLightPolicy(cfg)
            p.load_state_dict(policy_state_dicts[i])
            p.eval()
            policies[i] = p
        phase_idx = {i: movement_index_phases(env.movements[i], env.phases[i]) for i in env.intersections}

        trajs: Dict[str, Trajectory] = {i: Trajectory() for i in env.intersections}
        truncated = False
        while not truncated:
            actions: Dict[str, int] = {}
            meta = {}
            for i in env.intersections:
                a, lp, v = select_action(policies[i], obs[i], phase_idx[i], info["action_masks"][i], deterministic)
                actions[i] = a
                meta[i] = (a, lp, v)
            next_obs, reward, truncated, next_info = env.step(actions)
            for i in env.intersections:
                a, lp, v = meta[i]
                trajs[i].steps.append(Step(
                    obs=obs[i], phases_idx=phase_idx[i], mask=info["action_masks"][i],
                    action=a, log_prob=lp, value=v, reward=reward[i], filtered=False,
                ))
            obs, info = next_obs, next_info

        for i in env.intersections:
            _, _, v_T = select_action(policies[i], obs[i], phase_idx[i], info["action_masks"][i], deterministic)
            trajs[i].bootstrap_value = v_T

        per_i = [sum(s.reward for s in t.steps) for t in trajs.values()]
        return {
            "trajectories": trajs,
            "episode_return": float(np.mean(per_i)) if per_i else float("nan"),
        }
    finally:
        env.close()


# ---------------------------------------------------------------------------
# Stage-C sanity-gate evaluation: paired {MaxPressure, this baseline}
# episodes on task metrics (ATT/AQL/TP), reusing src.metrics.compute exactly
# as scripts/evaluate_policy.py does. Deliberately NOT reward-return --
# reward-form differs per baseline (pressure_raw etc.) and is a training
# diagnostic, not the paper's actual deliverable metric (same principle
# already stated at the top of evaluate_policy.py). Reward form does not
# affect these metrics at all (metrics.compute reads env.completed_trips()/
# true_queue_history(), never accumulated reward) -- so, unlike training,
# this evaluation can reuse the plain, unmodified cfg for env construction.
# ---------------------------------------------------------------------------

from src import metrics as _metrics  # noqa: E402
from src.controllers import Controller, MaxPressure  # noqa: E402


class BaselineRLController(Controller):
    """Bare (no safety filter) deterministic evaluation controller for a
    trained baseline -- Stage 5 decision A: baselines are never composed
    with Corollary-1's filter."""

    def __init__(self, env: HAPLightEnv, name: str, policy: HAPLightPolicy):
        self.env = env
        self.name = name
        self.policy = policy
        self.state_fn = STATE_FNS[name]
        self.phase_idx = None

    def reset(self) -> None:
        self.phase_idx = {
            i: movement_index_phases(self.env.movements[i], self.env.phases[i])
            for i in self.env.intersections
        }

    def act(self, obs, info) -> Dict[str, int]:
        state = self.state_fn(self.env, info)
        actions = {}
        for i in self.env.intersections:
            a, _, _ = select_action(
                self.policy, state[i], self.phase_idx[i], info["action_masks"][i], deterministic=True,
            )
            actions[i] = a
        return actions


def _run_metrics_episode(controller_name: str, name: str, cfg: dict, net_dir: str,
                          seed: int, eta: float, policy_state_dict: dict | None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(
        net_dir, cfg, fleet, seed=seed, eta=eta, estimator="area",
        advanced_mp_running_demand=(controller_name != "MaxPressure" and name == "advanced_mplight"),
    )
    try:
        if controller_name == "MaxPressure":
            controller = MaxPressure(env)
        else:
            policy = make_policy(cfg, name)
            policy.load_state_dict(policy_state_dict)
            policy.eval()
            controller = BaselineRLController(env, name, policy)

        obs = env.reset()
        controller.reset()
        info = env.info
        truncated = False
        while not truncated:
            actions = controller.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
        m = _metrics.compute(env.completed_trips(), env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        m["gridlock"] = 1.0 if env.pending_count() > 0 else 0.0
    finally:
        env.close()
    return {"controller": controller_name, "seed": seed, **m}


def evaluate_vs_mp(
    cfg: dict, net_dir: str, name: str, policy_state_dict: dict,
    seeds: List[int], eta: float = 0.0,
) -> dict:
    """Stage-C sanity gate: paired {MaxPressure, `name`} episodes, same
    (seed, eta) demand realisation per seed (paired methodology, matches
    evaluate_policy.py). Returns per-controller metric means plus the
    relative ATT/TP improvement of `name` over MaxPressure -- the number
    prompts/phase5_baselines.md asks be reported before moving on."""
    mp_runs = [_run_metrics_episode("MaxPressure", name, cfg, net_dir, s, eta, None) for s in seeds]
    rl_runs = [_run_metrics_episode(name, name, cfg, net_dir, s, eta, policy_state_dict) for s in seeds]

    def _mean(runs, key):
        vals = [r[key] for r in runs]
        return float(np.mean(vals))

    mp_att, rl_att = _mean(mp_runs, "att"), _mean(rl_runs, "att")
    mp_tp, rl_tp = _mean(mp_runs, "tp"), _mean(rl_runs, "tp")
    mp_aql, rl_aql = _mean(mp_runs, "aql"), _mean(rl_runs, "aql")

    return {
        "name": name, "seeds": seeds, "eta": eta,
        "maxpressure": {"att": mp_att, "tp": mp_tp, "aql": mp_aql,
                         "gridlock": sum(r["gridlock"] for r in mp_runs)},
        name: {"att": rl_att, "tp": rl_tp, "aql": rl_aql,
               "gridlock": sum(r["gridlock"] for r in rl_runs)},
        "att_improvement_pct": 100.0 * (mp_att - rl_att) / mp_att if mp_att else float("nan"),
        "tp_improvement_pct": 100.0 * (rl_tp - mp_tp) / mp_tp if mp_tp else float("nan"),
        "aql_improvement_pct": 100.0 * (mp_aql - rl_aql) / mp_aql if mp_aql else float("nan"),
    }
