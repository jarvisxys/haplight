"""
Stability-preserving action filter (PLAN.md Phase 4, paper Sec. V-D
"Stability-Preserving Action Filter", Corollary 1).

At execution -- and, for distributional consistency, during training -- the
policy's action passes through this filter: if the worst weighted queue
entering intersection i's pressure computation (upstream or immediate
downstream) exceeds a threshold B, `hap.greedy_phase` overrides the policy
at i for that decision. Corollary 1 certifies that ANY policy composed with
this filter yields a strongly stable weighted queue process for every
demand in the interior of the capacity region, with a queue bound that
degrades linearly in B -- a permissive filter buys the learner freedom at
a computable, quantified cost to the certificate.

The filter triggers on `x_hat` (the SENSED channel), never `true_queues`
(PAPER_CHANGELOG P1-1) -- it has to be implementable from cameras, so it
sees exactly what the controller sees. Corollary 1's noisy-measurement
case already covers this (delta replaced by delta - c1*dt*eps).

CALIBRATION, corrected design (do not regress to the naive version): B and
the trigger statistic must be the SAME quantity, or a P90 threshold does
not produce ~10% activation. Pooling every per-movement x_hat[i][mv] value
and firing if ANY exceeds B is wrong -- with ~O(10) movements per
intersection, "any exceeds the P90 of the pooled per-movement
distribution" fires on 40-80% of decisions, not 10%, leaving the learner
almost no room (Remark 6: HAPLight-RL converges behaviourally to greedy
HAP wherever the filter fires). Instead: per (intersection, decision step),
reduce to ONE number -- the worst upstream-or-downstream x_hat entering
that intersection's pressure computation -- and set B to the P90 of THAT
pooled distribution. `SafetyFilter.trigger_stat` and
`calibrate_threshold` compute the identical statistic; keep them in sync.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from src.controllers import GreedyHAP
from src.env import HAPLightEnv
from src.hap import Fleet


def _trigger_stat(env: HAPLightEnv, info: dict, i: str) -> float:
    """m_i(t): the worst upstream-or-immediate-downstream sensed
    (x_hat-channel) queue entering intersection i's pressure computation.
    x_hat[i][mv] is the upstream value; x_hat[i][mv] - w_hat[i][mv]
    recovers the aggregate downstream value (same identity env.py itself
    uses everywhere: w = x - x_down)."""
    return max(
        max(info["x_hat"][i][mv], info["x_hat"][i][mv] - info["w_hat"][i][mv])
        for mv in env.movements[i]
    )


def _storage_trigger_stat(env: HAPLightEnv, info: dict, i: str) -> float:
    """Worst SENSED storage-occupancy fraction (x_hat / env.storage) among
    (a) intersection i's own movements' upstream queues, and (b) whichever
    specific movement(s) i's movements discharge into (PAPER_CHANGELOG
    P4c-4). Unlike `_trigger_stat`'s x_down (an edge-aggregate quantity),
    `info["x_hat"][j][mv2]` is already movement-specific (built from mv2's
    own lane subset, P4c-3's diagnosed fix) -- no edge-aggregation dilution
    here. Still x_hat-only (P1-1): a movement's own upstream sensed queue,
    never true_queues, at either end."""
    worst = 0.0
    for mv in env.movements[i]:
        cap_up = env.storage[i].get(mv, 0.0)
        if cap_up > 0:
            worst = max(worst, info["x_hat"][i][mv] / cap_up)
        out_edge = mv.split("->")[1]
        for j, mv2 in env.downstream_by_edge.get(out_edge, []):
            cap_down = env.storage[j].get(mv2, 0.0)
            if cap_down > 0:
                worst = max(worst, info["x_hat"][j][mv2] / cap_down)
    return worst


def calibrate_threshold(
    net_dir: str,
    cfg: dict,
    fleet: Fleet,
    percentile: float | None = None,
    seed: int = 0,
    controller_cls=GreedyHAP,
) -> float:
    """Runs one episode of `controller_cls` (default GreedyHAP) at nominal
    demand on the scenario in `net_dir`, pools `_trigger_stat` over every
    (intersection, decision step), and returns its `percentile`-th value --
    a single scalar B. `percentile` defaults to
    cfg["rl"]["filter"]["threshold_percentile"] (90) so the {75, 90, 97}
    sensitivity sweep can call this with an explicit override and reuse
    everything else. Not tuned to hit any target activation rate -- P90 is
    the pre-registered default regardless of what activation it measures."""
    if percentile is None:
        percentile = cfg["rl"]["filter"]["threshold_percentile"]

    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=seed, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = controller_cls(env)
        ctrl.reset()
        info = env.info
        samples = []
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                samples.append(_trigger_stat(env, info, i))
        return float(np.percentile(samples, percentile))
    finally:
        env.close()


class SafetyFilter:
    """Wraps a policy's proposed actions with the Corollary-1 override.
    Reuses `GreedyHAP` directly for the fallback action (same x_hat/w_hat
    channel, same `hap.greedy_phase` call) rather than reimplementing it.

    Two INDEPENDENT storage-awareness switches (PAPER_CHANGELOG P4c-8/
    P4c-9 -- P4c-8 found that toggling only one of these can regress a
    healthy scenario, because the two defenses close different gaps):

    `storage_aware` (P4c-4/P4c-5, default False): adds a SECOND,
    independent TRIGGER condition -- storage occupancy -- alongside the
    existing queue-magnitude one (logical OR). Diagnosed need: P4-7's S2
    abort showed the trained policy driving the network into spillback
    before the queue-magnitude trigger fired; Corollary 1's certificate
    assumes greedy control was active all along, not handed a single
    decision at the edge of collapse. Controls WHEN the filter engages.

    `fallback_storage_aware` (P4c-7/P4c-9, default False): the FALLBACK
    controller invoked once triggered uses storage-aware pressure
    (`GreedyHAP(storage_aware=True)`, the P4c-7-validated barrier) instead
    of plain GreedyHAP. Controls WHAT ACTION is taken once triggered.
    P4c-8's regression: `storage_aware=True` with the OLD hardcoded plain
    fallback handed >1/3 of decisions, on one seed, to a controller
    (plain GreedyHAP) that P4c-3 already proved can itself deadlock --
    triggering earlier does not help if what it falls back to can still
    fail. These two switches close different gaps and are tested here as
    an explicit 2x2, not assumed to compose safely."""

    def __init__(
        self, env: HAPLightEnv, B: float,
        storage_aware: bool = False, storage_threshold: float | None = None,
        fallback_storage_aware: bool = False, fallback_theta: float | None = None,
        hysteresis: bool = False, storage_threshold_low: float | None = None,
        min_dwell: int = 1,
    ):
        self.env = env
        self.B = B
        self.storage_aware = storage_aware
        self.storage_threshold = (
            storage_threshold if storage_threshold is not None
            else env.cfg["rl"]["filter"].get("storage_trigger_threshold", 0.85)
        )
        self.fallback_storage_aware = fallback_storage_aware
        self._greedy = GreedyHAP(env, storage_aware=fallback_storage_aware, theta=fallback_theta)

        # Hysteresis + minimum dwell (PAPER_CHANGELOG P4c-11): a naive
        # single-threshold trigger CHATTERS -- confirmed directly, one
        # intersection toggled on/off 84 times in 720 decisions, several
        # stretches flipping every single step -- because the trigger stat
        # can hover right at the boundary. Chattering, not threshold value,
        # is what made P4c-10's sweep non-monotonic: a correct filter must
        # be monotonically safer (or neutral) the earlier it engages; a
        # filter that sometimes CAUSES the deadlock it exists to prevent is
        # the wrong mechanism, not a mistuned parameter. `storage_threshold`
        # (above) is now the ENGAGE (high) threshold; `storage_threshold_low`
        # is the RELEASE threshold (dead zone between them stops immediate
        # re-crossing); `min_dwell` additionally holds the fallback engaged
        # for at least this many decisions once triggered, regardless of the
        # stat, so a single-step dip cannot release it either. Stateful by
        # construction -- a fresh SafetyFilter must be constructed per
        # episode (already true everywhere it's used: run_episode_worker,
        # diagnose_gridlock.py, evaluate_policy.py all build one per
        # episode), so per-intersection state starts clean via __init__,
        # no separate reset() call needed.
        self.hysteresis = hysteresis
        self.storage_threshold_low = (
            storage_threshold_low if storage_threshold_low is not None
            else env.cfg["rl"]["filter"].get("storage_trigger_threshold_low", max(0.0, self.storage_threshold - 0.10))
        )
        self.min_dwell = min_dwell
        self._active: Dict[str, bool] = {}
        self._dwell_remaining: Dict[str, int] = {}

    def trigger_stat(self, info: dict, i: str) -> float:
        return _trigger_stat(self.env, info, i)

    def storage_trigger_stat(self, info: dict, i: str) -> float:
        return _storage_trigger_stat(self.env, info, i)

    def _decide(self, info: dict, i: str) -> bool:
        queue_trig = self.trigger_stat(info, i) > self.B
        if not self.storage_aware:
            return queue_trig
        storage_stat = self.storage_trigger_stat(info, i)

        if not self.hysteresis:
            return queue_trig or (storage_stat > self.storage_threshold)

        was_active = self._active.get(i, False)
        if not was_active:
            engage = queue_trig or (storage_stat > self.storage_threshold)
            if engage:
                self._active[i] = True
                self._dwell_remaining[i] = self.min_dwell
            return self._active.get(i, False)

        # already active: hold for at least min_dwell decisions, THEN
        # release only once both signals have dropped to/below their LOW
        # (release) thresholds -- prevents releasing on a single-step dip
        # that the fallback's own action just caused.
        dwell = self._dwell_remaining.get(i, 0)
        below_low = (not queue_trig) and (storage_stat <= self.storage_threshold_low)
        if dwell <= 0 and below_low:
            self._active[i] = False
        else:
            self._dwell_remaining[i] = max(0, dwell - 1)
        return self._active.get(i, False)

    def apply(
        self, obs, info: dict, policy_actions: Dict[str, int],
    ) -> Tuple[Dict[str, int], Dict[str, bool]]:
        """Returns (final_actions, filter_active) -- filter_active[i] is
        True iff intersection i's action was overridden this step. Callers
        (scripts/train.py) should log the mean of filter_active across all
        (intersection, step) pairs as the reported activation rate."""
        greedy_actions = self._greedy.act(obs, info)
        final_actions = dict(policy_actions)
        filter_active: Dict[str, bool] = {}
        for i in self.env.intersections:
            triggered = self._decide(info, i)
            filter_active[i] = triggered
            if triggered:
                final_actions[i] = greedy_actions[i]
        return final_actions, filter_active
