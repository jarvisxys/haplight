"""
Classical signal controllers (PLAN.md Phase 1).

All six read from `info` (src/env.py's per-step return), never re-derive
anything env.py already computed, and never call SensingModel directly --
whatever channel (`x_hat`/`counts_hat`/`true_...`) they read from is
whatever env.py decided to corrupt or not. All six only ever select among
`info["action_masks"][i]`-permitted phases (env.py enforces g_min/g_max
itself regardless of what a controller returns, so this is a courtesy that
avoids requesting the same illegal switch every step, not a safety
requirement).

GreedyHAP calls `src.hap.greedy_phase` directly on the sensed channel
(`x_hat`/`mu`) -- same channel MaxPressure/EfficientMP/AdvancedMP read from
(`counts_hat`), so all four classical pressure controllers see the same
noise a robustness sweep applies, per the paper's evaluation protocol.
FixedTime and SOTL don't touch the sensed channel at all: FixedTime is a
static plan and SOTL is literally defined on vehicle counts (its historical
form), for which counts_hat is not the point of the ablation anyway.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from src.hap import (
    Fleet,
    greedy_phase,
    movement_weight,
    phase_pressure,
    storage_aware_mu,
    worst_downstream_occupancy,
)

# ---------------------------------------------------------------------------


class Controller:
    def act(self, obs, info) -> Dict[str, int]:
        raise NotImplementedError

    def reset(self) -> None:
        pass


def _rho1(counts: Dict[str, float]) -> float:
    return sum(counts.values())


def _pressure_action(env, info, x_up: Dict[str, Dict[str, float]],
                      x_down: Dict[str, Dict[str, float]]) -> Dict[str, int]:
    """Shared argmax-phase-pressure decision for the rho=1 classical family
    (MaxPressure / EfficientMP / AdvancedMP) -- all three differ only in how
    x_up/x_down are built, never in how the phase is chosen."""
    actions = {}
    for i in env.intersections:
        w = {
            mv: movement_weight(x_up[i][mv], {"agg": x_down[i][mv]}, {"agg": 1.0})
            for mv in env.movements[i]
        }
        phases = {str(p): movs for p, movs in enumerate(env.phases[i])}
        mask = info["action_masks"][i]
        allowed = {k: v for k, v in phases.items() if mask[int(k)]}
        cur = info["current_phase"][i]
        current_key = str(cur) if mask[cur] else None
        best = greedy_phase(allowed, env.mu[i], w, current=current_key)
        actions[i] = int(best)
    return actions


def _masked_or_current(env, i: str, want: int, info) -> int:
    mask = info["action_masks"][i]
    if mask[want]:
        return want
    return info["current_phase"][i]


# ---------------------------------------------------------------------------


class FixedTime(Controller):
    """Webster fixed-time from Indo-HCM saturation flows AND the actual
    per-movement demand build_nets.py computed (nets/<scenario>/
    movement_demand.json) -- q_i is real, not assumed uniform, so
    y_i=q_i/mu_i is the genuine flow ratio for every phase's critical
    movement. Static: never looks at live queues.

    Uses each movement's own composition-weighted mean rho (Phase 1b),
    not a single fleet-wide mean -- composition is per-OD now
    (build_nets.py), so a global mean would mistune this exactly along the
    axis Phase 1b introduces (the same mistake changelog P1-2 already
    flagged once, for a uniform-demand assumption rather than composition)."""

    #: Webster's formula is undefined at Y>=1 (oversaturated design volume);
    #: cap only the CYCLE-LENGTH sizing at this value, never the y_i/Y split
    #: proportions (those stay exact).
    _Y_CAP = 0.95

    def __init__(self, env, cfg: dict, fleet: Fleet, net_dir: Optional[str] = None):
        # env.intersections/phases/mu are only populated after env's first
        # reset() (topology discovery happens there, not at env
        # construction) -- so the Webster splits are computed lazily on
        # this controller's own reset(), not here.
        self.env = env
        self.cfg = cfg
        self.fleet = fleet
        self.net_dir = net_dir
        self._durations: Optional[Dict[str, List[float]]] = None

    def reset(self) -> None:
        if self._durations is not None:
            return  # topology is static for a given net_dir; compute once
        env, cfg = self.env, self.cfg
        sig = cfg["signal"]
        g_min, g_max = sig["min_green_s"], sig["max_green_s"]
        t_y = sig["yellow_s"] + sig["all_red_s"]

        demand_path = Path(self.net_dir or env.net_dir) / "movement_demand.json"
        demand = json.loads(demand_path.read_text()) if demand_path.exists() else {}

        self._durations = {}
        for i in env.intersections:
            phases = env.phases[i]
            mu_i = env.mu[i]
            q_i = demand.get(i, {})
            y_per_phase = []
            for movs in phases:
                y_phase = 0.0
                for mv in movs:
                    rec = q_i.get(mv) or {}
                    q_veh_h = rec.get("vph", 0.0)
                    mean_rho_mv = rec.get("mean_rho", 0.0)
                    q_weighted_s = q_veh_h * mean_rho_mv / 3600.0
                    mu_m = mu_i.get(mv, 1e-6)
                    y_phase = max(y_phase, q_weighted_s / mu_m if mu_m > 0 else 0.0)
                y_per_phase.append(y_phase)

            n_phases = len(phases)
            Y = sum(y_per_phase)
            L = n_phases * t_y
            if Y <= 1e-9:
                self._durations[i] = [g_min for _ in phases]
                continue
            y_safe = min(Y, self._Y_CAP)
            cycle_webster = (1.5 * L + 5.0) / (1.0 - y_safe)
            # At this network's per-movement demand, Y is small enough that
            # Webster's raw minimum-delay cycle is too short for a
            # proportional split (green_total * y_i/Y) to clear g_min on
            # every phase -- naively clamping each phase to g_min afterwards
            # would silently discard the real y_i ratio and produce an
            # identical (wrong) split for every phase regardless of demand.
            # Instead size the cycle so the *smallest*-demand phase already
            # clears g_min under pure proportional allocation; every other
            # phase, having a larger y_i, then clears it too, and relative
            # demand is preserved rather than overwritten.
            positive_y = [y for y in y_per_phase if y > 1e-12]
            if positive_y:
                required_green_total = g_min * Y / min(positive_y)
            else:
                required_green_total = n_phases * g_min
            cycle = max(cycle_webster, L + required_green_total)
            green_total = cycle - L
            self._durations[i] = [
                min(g_max, max(g_min, green_total * (y / Y))) for y in y_per_phase
            ]

    def act(self, obs, info) -> Dict[str, int]:
        actions = {}
        for i in self.env.intersections:
            cur = info["current_phase"][i]
            elapsed = info["green_elapsed"][i]
            if elapsed >= self._durations[i][cur]:
                nxt = (cur + 1) % len(self.env.phases[i])
                actions[i] = _masked_or_current(self.env, i, nxt, info)
            else:
                actions[i] = cur
        return actions


# ---------------------------------------------------------------------------


class SOTL(Controller):
    """Self-organizing traffic lights (Cools, Gershenson & D'Hooghe 2013),
    at Delta-t decision granularity. Vehicle-count based (its historical
    definition, not rho-weighted): accumulate a red phase's queued-vehicle
    count every decision it stays red; once the current phase has served
    g_min and some other phase's accumulator clears a threshold, switch to
    the highest one."""

    def __init__(self, env, cfg: dict, theta: float = 40.0):
        self.env = env
        self.theta = theta
        self._kappa: Dict[str, Dict[int, float]] = {}
        self.reset()

    def reset(self) -> None:
        self._kappa = {
            i: {p: 0.0 for p in range(len(self.env.phases[i]))} for i in self.env.intersections
        }

    def act(self, obs, info) -> Dict[str, int]:
        actions = {}
        for i in self.env.intersections:
            cur = info["current_phase"][i]
            n_phases = len(self.env.phases[i])
            for p in range(n_phases):
                if p == cur:
                    self._kappa[i][p] = 0.0
                    continue
                demand = sum(
                    _rho1(info["counts_hat"][i][mv]) for mv in self.env.phases[i][p]
                )
                self._kappa[i][p] += demand

            if info["green_elapsed"][i] < self.env.g_min:
                actions[i] = cur
                continue
            best_p = max(range(n_phases), key=lambda p: self._kappa[i][p])
            if best_p != cur and self._kappa[i][best_p] > self.theta:
                actions[i] = _masked_or_current(self.env, i, best_p, info)
            else:
                actions[i] = cur
        return actions


# ---------------------------------------------------------------------------


class MaxPressure(Controller):
    """Count-based max-pressure (Varaiya): the HAP machinery with rho≡1."""

    def __init__(self, env):
        self.env = env

    def act(self, obs, info) -> Dict[str, int]:
        x_up = {
            i: {mv: _rho1(info["counts_hat"][i][mv]) for mv in self.env.movements[i]}
            for i in self.env.intersections
        }
        x_down = {
            i: {mv: _rho1(info["counts_hat_downstream"][i][mv]) for mv in self.env.movements[i]}
            for i in self.env.intersections
        }
        return _pressure_action(self.env, info, x_up, x_down)


class EfficientMP(Controller):
    """Lane-normalised max-pressure: divide each movement's (and its
    downstream edge's) count by its own lane count before differencing, so
    intersections with unequal lane counts across movements aren't biased
    toward the wider approach."""

    def __init__(self, env):
        self.env = env

    def act(self, obs, info) -> Dict[str, int]:
        n_lanes_mv = info["n_lanes"]
        n_lanes_edge = info["n_lanes_edge"]
        x_up, x_down = {}, {}
        for i in self.env.intersections:
            x_up[i], x_down[i] = {}, {}
            for mv in self.env.movements[i]:
                out_edge = mv.split("->")[1]
                nl_up = max(1, n_lanes_mv[i].get(mv, 1))
                nl_down = max(1, n_lanes_edge.get(out_edge, 1))
                x_up[i][mv] = _rho1(info["counts_hat"][i][mv]) / nl_up
                x_down[i][mv] = _rho1(info["counts_hat_downstream"][i][mv]) / nl_down
        return _pressure_action(self.env, info, x_up, x_down)


class AdvancedMP(Controller):
    """Advanced-MP (Zhang et al., "Expression might be enough: representing
    pressure and demand for reinforcement learning based traffic signal
    control," ICML 2022, arXiv:2112.10107 -- the Advanced-XLight paper's
    classical baseline). PAPER_CHANGELOG P4c-16 corrects an earlier,
    structurally different port that folded queued+running counts into one
    uniform cross-phase pressure term; the reference algorithm is a
    two-term STAY/SWITCH decision, not a pressure argmax:

    - p(s): standard EFFICIENT pressure per phase (lane-normalised,
      queue-only -- identical x_up/x_down to EfficientMP; the source
      paper's own title names "efficient pressure" as its baseline
      pressure term, not plain unnormalised MaxPressure).
    - d(a_cur): running-vehicle demand for ONLY the CURRENTLY ACTIVE
      phase -- count of non-stopped vehicles on its movements within
      effective range L = V_max * t_duration (env.lane_max_speed *
      env.g_max; this codebase's phases don't carry individually-tuned
      durations, so g_max, the one duration constant available, stands in
      for the paper's fixed per-decision t_duration).
    - Decision: stay on the current phase unless d(a_cur) * W1 <=
      max(p(s) for s in the OTHER allowed phases); switch to the
      max-pressure phase only then. This is an asymmetric stickiness
      bonus for whichever phase is active, not a symmetric term added to
      every phase's pressure alike.

    W1 is not pinned to a specific value by the source paper text
    available to this port; W1=1.0 here is an inferred default, not a
    transcribed literature constant -- documented, not silently assumed."""

    W1 = 1.0  # inferred default (PAPER_CHANGELOG P4c-16), not a transcribed constant

    def __init__(self, env):
        self.env = env

    def act(self, obs, info) -> Dict[str, int]:
        env = self.env
        n_lanes_mv = info["n_lanes"]
        n_lanes_edge = info["n_lanes_edge"]
        actions = {}
        for i in env.intersections:
            w = {}
            for mv in env.movements[i]:
                out_edge = mv.split("->")[1]
                nl_up = max(1, n_lanes_mv[i].get(mv, 1))
                nl_down = max(1, n_lanes_edge.get(out_edge, 1))
                x_up = _rho1(info["counts_hat"][i][mv]) / nl_up
                x_down = _rho1(info["counts_hat_downstream"][i][mv]) / nl_down
                w[mv] = movement_weight(x_up, {"agg": x_down}, {"agg": 1.0})

            phases = {str(p): movs for p, movs in enumerate(env.phases[i])}
            mask = info["action_masks"][i]
            allowed = {k: v for k, v in phases.items() if mask[int(k)]}
            cur = info["current_phase"][i]
            current_key = str(cur) if mask[cur] else None

            other_pressures = [
                phase_pressure(movs, env.mu[i], w)
                for k, movs in allowed.items() if k != current_key
            ]
            best_other = max(other_pressures) if other_pressures else float("-inf")

            stay = False
            if current_key is not None:
                d_cur = sum(
                    env.running_count_within_range(i, mv, env.lane_max_speed(i, mv) * env.g_max)
                    for mv in phases[current_key]
                )
                stay = (d_cur * self.W1) > best_other

            if stay:
                actions[i] = int(current_key)
            else:
                best = greedy_phase(allowed, env.mu[i], w, current=current_key)
                actions[i] = int(best)
        return actions


# ---------------------------------------------------------------------------


class GreedyHAP(Controller):
    """Layer 1 of the paper. Calls hap.greedy_phase directly -- no
    reimplementation of the argmax -- on whichever sensed channel env.py
    was configured with (x_hat, weighted by fleet.rho under env.estimator).

    `storage_aware` (PAPER_CHANGELOG P4c-7, default False -- preserves every
    existing result exactly): when True, the saturation flow mu_m used in
    the pressure computation is replaced by mu_m^eff = mu_m * phi(h_m),
    where h_m is movement m's downstream headroom -- the worst SENSED
    occupancy fraction among the SPECIFIC movements sharing m's downstream
    edge, each against its OWN env.storage capacity
    (hap.worst_downstream_occupancy). This is the validated, deployable
    signal: P4c-3 found the edge-AGGREGATE version (a single x_down_hat
    against a summed edge_capacity) never engages, because one overloaded
    low-capacity turn pocket is invisible inside a healthy-looking edge-wide
    average; P4c-7 confirmed the movement-resolved version clears the exact
    seed that broke the aggregate one, using only x_hat -- already
    movement-resolved from that movement's own lane subset, no new sensing
    plumbing (P1-1: x_hat, never true_queues). This is a pure reweighting
    of `mu` passed into the unmodified `greedy_phase`/`phase_pressure` --
    the argmax logic itself never changes. Degrades to plain GreedyHAP
    exactly whenever every movement's headroom is >= theta (see
    hap.storage_aware_mu)."""

    def __init__(self, env, storage_aware: bool = False, theta: float | None = None):
        self.env = env
        self.storage_aware = storage_aware
        self.theta = theta if theta is not None else env.cfg["hap"].get("storage_aware_theta", 0.15)

    def act(self, obs, info) -> Dict[str, int]:
        actions = {}
        for i in self.env.intersections:
            w = {}
            headroom = {}
            for mv in self.env.movements[i]:
                x_up = info["x_hat"][i][mv]
                x_down = x_up - info["w_hat"][i][mv]  # w = x - x_down (agg form)
                w[mv] = movement_weight(x_up, {"agg": x_down}, {"agg": 1.0})
                if self.storage_aware:
                    out_edge = mv.split("->")[1]
                    downstream = [
                        (info["x_hat"][j][mv2], self.env.storage[j].get(mv2, 0.0))
                        for j, mv2 in self.env.downstream_by_edge.get(out_edge, [])
                    ]
                    worst_occ = worst_downstream_occupancy(downstream)
                    headroom[mv] = max(0.0, 1.0 - worst_occ)
            mu_i = storage_aware_mu(self.env.mu[i], headroom, self.theta) if self.storage_aware else self.env.mu[i]
            phases = {str(p): movs for p, movs in enumerate(self.env.phases[i])}
            mask = info["action_masks"][i]
            allowed = {k: v for k, v in phases.items() if mask[int(k)]}
            cur = info["current_phase"][i]
            current_key = str(cur) if mask[cur] else None
            best = greedy_phase(allowed, mu_i, w, current=current_key)
            actions[i] = int(best)
        return actions
