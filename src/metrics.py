"""
Episode metrics (PLAN.md Phase 1) -- exactly the key list in PLAN.md.

Built from src.env.HAPLightEnv.completed_trips() (per-vehicle records) and
.true_queue_history() (per-decision-step network totals) -- both noise-free,
ground-truth channels that never touch SensingModel.

`aql` is in active weight units (fleet.rho), not vehicle counts, per
PLAN.md. `pwd` is passenger-weighted (fleet.occupancy). `fuel`/`co2` are
SUMO's native per-episode totals: fuel in ml, CO2 in mg -- not silently
converted to litres/kg.
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Sequence

import numpy as np

from src.hap import Fleet


def _gini(values: Sequence[float]) -> float:
    """Standard sorted-array Gini coefficient of a sample. NaN when
    undefined (<2 samples, or all-zero) -- a class with too few completed
    trips (e.g. no bus arrived in a short test episode) should say so, not
    silently report 0."""
    v = np.asarray(list(values), dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 2 or v.sum() <= 0:
        return float("nan")
    v = np.sort(v)
    n = v.size
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * v)) / (n * np.sum(v)) - (n + 1) / n)


def compute(
    trips: List[dict],
    queue_history: List[Dict[str, float]],
    fleet: Fleet,
    cfg: dict,
    gmax_activation_rate: float,
    filter_activation_rate: float = 0.0,
) -> dict:
    episode_h = cfg["demand"]["episode_length_s"] / 3600.0

    if trips:
        tt = np.array([t["travel_time"] for t in trips], dtype=float)
        wt = np.array([t["waiting"] for t in trips], dtype=float)
        tl = np.array([t["timeloss"] for t in trips], dtype=float)
        att = float(tt.mean())
        awt = float(wt.mean())
        ad = float(tl.mean())
        occ = fleet.occupancy
        occ_w = np.array([occ.get(t["vclass"], 1.0) for t in trips], dtype=float)
        pwd = float(np.sum(occ_w * tl) / np.sum(occ_w)) if occ_w.sum() > 0 else float("nan")
    else:
        att = awt = ad = pwd = float("nan")

    tp = len(trips) / episode_h if episode_h > 0 else float("nan")

    if queue_history:
        totals = [sum(step.values()) for step in queue_history]
        aql = float(np.mean(totals))
    else:
        aql = float("nan")

    fuel = float(sum(t.get("fuel_ml", 0.0) for t in trips))
    co2 = float(sum(t.get("co2_mg", 0.0) for t in trips))

    gini_overall = _gini([t["waiting"] for t in trips])
    gini_by_class = {
        cls: _gini([t["waiting"] for t in trips if t["vclass"] == cls]) for cls in fleet.names
    }

    return {
        "att": att,
        "awt": awt,
        "aql": aql,
        "ad": ad,
        "tp": tp,
        "pwd": pwd,
        "fuel": fuel,
        "co2": co2,
        "gini_overall": gini_overall,
        "gini_2w": gini_by_class.get("twowheeler", float("nan")),
        "gini_car": gini_by_class.get("car", float("nan")),
        "gini_auto": gini_by_class.get("auto", float("nan")),
        "gini_bus": gini_by_class.get("bus", float("nan")),
        "gini_truck": gini_by_class.get("truck", float("nan")),
        "filter_activation_rate": float(filter_activation_rate),
        "gmax_activation_rate": float(gmax_activation_rate),
    }


def composition_dispersion(queue_composition: Dict[str, Dict[str, float]]) -> float:
    """Mass-weighted mean pairwise total-variation distance between
    per-movement class-composition vectors (Phase 1b) -- a scalar index of
    how spatially heterogeneous the *realised* queue composition actually
    is, as opposed to the input composition_dispersion knob that generated
    the demand (the two can diverge, e.g. on a grid where every movement
    mixes long- and short-path trips).

    `queue_composition`: flat {movement_id: {class: count}}, e.g.
    env.info["true_counts"] flattened across intersections (movement ids
    are already globally unique). Movements with zero total mass are
    excluded. NaN if fewer than 2 movements have nonzero mass.

    Standalone function, not folded into compute()'s dict -- Phase 1's key
    list is an external contract (parquet schema in later phases); callers
    that want both call them separately and merge.
    """
    masses: Dict[str, float] = {}
    probs: Dict[str, Dict[str, float]] = {}
    for mv, counts in queue_composition.items():
        total = sum(counts.values())
        if total <= 0:
            continue
        masses[mv] = total
        probs[mv] = {cls: n / total for cls, n in counts.items()}

    movements = list(masses.keys())
    if len(movements) < 2:
        return float("nan")

    num = 0.0
    den = 0.0
    for m, m2 in combinations(movements, 2):
        classes = set(probs[m]) | set(probs[m2])
        tv = 0.5 * sum(abs(probs[m].get(c, 0.0) - probs[m2].get(c, 0.0)) for c in classes)
        w = masses[m] * masses[m2]
        num += w * tv
        den += w
    return float(num / den) if den > 0 else float("nan")


def spillback_stats(
    queue_history: List[Dict[str, Dict[str, float]]],
    storage: Dict[str, Dict[str, float]],
    decision_interval_s: float,
    threshold: float = 0.9,
) -> dict:
    """Phase 1c (PAPER_CHANGELOG P1c-4): HAP optimises road-space occupancy,
    so its advantage over count-based control should show up as spillback
    prevention, not vehicle travel time. Three precisely-defined quantities,
    since the prompt this responds to specifies them only loosely:

    `queue_history`: one entry per decision step, each a nested
    {intersection: {movement: weighted_queue}} snapshot -- e.g. a list of
    env.info["true_queues"] collected during the drive loop (this is a
    PER-MOVEMENT time series, unlike compute()'s queue_history argument,
    which is pre-aggregated to per-intersection totals and therefore can't
    support any of these three metrics).
    `storage`: static {intersection: {movement: capacity}}, e.g. env.storage.

    Returns:
      frac_steps_any_over_threshold -- fraction of decision steps where AT
          LEAST ONE movement's queue was >= threshold (default 0.9) of its
          storage capacity. One scalar per episode, not per movement.
      spillback_events -- count of movements CROSSING INTO >=100% of
          storage (a below-capacity -> at-or-above-capacity transition),
          summed over all movements and steps. A queue that reaches 100% of
          its physical storage has, by construction (storage = full edge
          area / a_bar), backed up to the upstream intersection. Counting
          transitions rather than steps-at-or-above avoids inflating the
          count by simple dwell time.
      upstream_blocked_s -- total movement-seconds spent at >=100% of
          storage (steps at-or-above capacity, summed over all movements,
          times decision_interval_s) -- the cumulative blocking exposure
          the spillback_events count doesn't capture on its own.
    """
    steps_any_over = 0
    spillback_events = 0
    blocked_steps = 0
    was_full: Dict[str, bool] = {}

    for snapshot in queue_history:
        any_over = False
        for i, movs in snapshot.items():
            for mv, q in movs.items():
                cap = storage.get(i, {}).get(mv)
                if not cap or cap <= 0:
                    continue
                frac = q / cap
                if frac >= threshold:
                    any_over = True
                is_full = frac >= 1.0
                key = f"{i}/{mv}"
                if is_full:
                    blocked_steps += 1
                    if not was_full.get(key, False):
                        spillback_events += 1
                was_full[key] = is_full
        if any_over:
            steps_any_over += 1

    n_steps = len(queue_history)
    return {
        "frac_steps_any_over_threshold": (steps_any_over / n_steps) if n_steps else float("nan"),
        "spillback_events": spillback_events,
        "upstream_blocked_s": blocked_steps * decision_interval_s,
    }
