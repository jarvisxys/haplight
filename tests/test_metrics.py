"""
Pure-Python unit tests for src/metrics.py's standalone diagnostics (no SUMO
needed) -- composition_dispersion (Phase 1b) and spillback_stats (Phase 1c).

Run:  pytest tests/test_metrics.py -v
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import metrics  # noqa: E402


# ---------------------------------------------------------------------------
# composition_dispersion
# ---------------------------------------------------------------------------


def test_composition_dispersion_identical_movements_is_zero():
    comp = {
        "a": {"car": 10.0, "bus": 2.0},
        "b": {"car": 5.0, "bus": 1.0},
    }
    assert metrics.composition_dispersion(comp) == 0.0


def test_composition_dispersion_disjoint_classes_is_one():
    comp = {
        "a": {"car": 10.0},
        "b": {"bus": 10.0},
    }
    assert metrics.composition_dispersion(comp) == 1.0


def test_composition_dispersion_nan_below_two_movements():
    assert math.isnan(metrics.composition_dispersion({}))
    assert math.isnan(metrics.composition_dispersion({"a": {"car": 5.0}}))
    # a movement with zero mass doesn't count toward the "at least 2" floor
    assert math.isnan(
        metrics.composition_dispersion({"a": {"car": 5.0}, "b": {"car": 0.0}})
    )


# ---------------------------------------------------------------------------
# spillback_stats
# ---------------------------------------------------------------------------


def test_spillback_stats_empty_history():
    r = metrics.spillback_stats([], {}, decision_interval_s=5.0)
    assert math.isnan(r["frac_steps_any_over_threshold"])
    assert r["spillback_events"] == 0
    assert r["upstream_blocked_s"] == 0.0


def test_spillback_stats_never_over_threshold():
    storage = {"i0": {"m0": 100.0}}
    history = [{"i0": {"m0": 10.0}}, {"i0": {"m0": 20.0}}]
    r = metrics.spillback_stats(history, storage, decision_interval_s=5.0)
    assert r["frac_steps_any_over_threshold"] == 0.0
    assert r["spillback_events"] == 0
    assert r["upstream_blocked_s"] == 0.0


def test_spillback_stats_counts_transitions_not_dwell_time():
    """A movement sitting at/above 100% storage for 3 consecutive steps is
    ONE spillback event (one crossing-in), not three -- dwell time is
    reported separately via upstream_blocked_s."""
    storage = {"i0": {"m0": 10.0}}
    history = [
        {"i0": {"m0": 5.0}},    # 50% -- below threshold
        {"i0": {"m0": 9.5}},    # 95% -- over the 0.9 threshold, not full
        {"i0": {"m0": 10.0}},   # 100% -- full, crossing in: event #1
        {"i0": {"m0": 11.0}},   # still full (dwell)
        {"i0": {"m0": 4.0}},    # drops back below
        {"i0": {"m0": 10.0}},   # full again: event #2 (a new crossing)
    ]
    r = metrics.spillback_stats(history, storage, decision_interval_s=5.0)
    assert r["spillback_events"] == 2
    assert r["upstream_blocked_s"] == 3 * 5.0  # steps 3, 4, 6 were at >=100%
    assert r["frac_steps_any_over_threshold"] == 4 / 6  # steps 2,3,4,6 were >=90%


def test_spillback_stats_any_over_threshold_is_network_wide_per_step():
    """frac_steps_any_over_threshold is ONE scalar per step (true if ANY
    movement qualifies), not averaged per movement."""
    storage = {"i0": {"m0": 10.0, "m1": 10.0}}
    history = [
        {"i0": {"m0": 9.5, "m1": 0.0}},   # m0 over threshold -> step counts
        {"i0": {"m0": 0.0, "m1": 0.0}},   # neither -> step doesn't count
    ]
    r = metrics.spillback_stats(history, storage, decision_interval_s=5.0)
    assert r["frac_steps_any_over_threshold"] == 0.5


def test_spillback_stats_zero_or_missing_storage_is_skipped_not_divzero():
    storage = {"i0": {"m0": 0.0}}
    history = [{"i0": {"m0": 5.0, "m1": 1.0}}]  # m1 has no storage entry at all
    r = metrics.spillback_stats(history, storage, decision_interval_s=5.0)
    assert r["frac_steps_any_over_threshold"] == 0.0
    assert r["spillback_events"] == 0
