"""
Hysteresis + minimum-dwell unit tests (PAPER_CHANGELOG P4c-11).

Pure state-machine tests -- no SUMO/env needed. `SafetyFilter._decide`
only touches `self.trigger_stat`/`self.storage_trigger_stat`, which are
monkey-patched here to script an exact storage-stat sequence, isolating
the hysteresis logic from the sensing pipeline entirely.

Run:  pytest tests/test_safety_filter.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.safety_filter import SafetyFilter  # noqa: E402


class _FakeEnv:
    def __init__(self, intersections=("i0",)):
        self.intersections = intersections
        self.cfg = {"rl": {"filter": {}}}


def _make_filter(hysteresis: bool, min_dwell: int = 3) -> SafetyFilter:
    return SafetyFilter(
        _FakeEnv(), B=1e9,  # B effectively disabled -- isolate the storage trigger
        storage_aware=True, storage_threshold=0.85, storage_threshold_low=0.75,
        fallback_storage_aware=True, fallback_theta=0.15,
        hysteresis=hysteresis, min_dwell=min_dwell,
    )


def _script(filt: SafetyFilter, values):
    """Feeds a scripted storage_trigger_stat sequence through _decide,
    returns the list of engage/disengage booleans."""
    filt.trigger_stat = lambda info, i: 0.0  # never trips the queue-magnitude trigger
    out = []
    for v in values:
        filt.storage_trigger_stat = lambda info, i, _v=v: _v
        out.append(filt._decide({}, "i0"))
    return out


def test_naive_no_hysteresis_chatters_at_the_boundary():
    """Baseline: without hysteresis, crossing back and forth across a
    single threshold toggles every step -- this IS the confirmed P4c-11
    chattering mechanism, reproduced here as the control case."""
    filt = _make_filter(hysteresis=False)
    values = [0.86, 0.84, 0.86, 0.84, 0.86, 0.84]  # oscillates around 0.85
    result = _script(filt, values)
    assert result == [True, False, True, False, True, False]


def test_hysteresis_dead_zone_prevents_chatter_at_the_boundary():
    """The exact oscillation that chatters without hysteresis must NOT
    toggle once engaged, as long as the stat stays within the dead zone
    (0.75, 0.85] -- it can only release below 0.75."""
    filt = _make_filter(hysteresis=True, min_dwell=0)
    values = [0.86, 0.84, 0.86, 0.84, 0.86, 0.84]  # same oscillation as the naive test
    result = _script(filt, values)
    # engages once at the first 0.86, then stays engaged throughout since
    # every value is > storage_threshold_low (0.75)
    assert result == [True, True, True, True, True, True]


def test_hysteresis_releases_once_below_the_low_threshold():
    filt = _make_filter(hysteresis=True, min_dwell=0)
    values = [0.90, 0.80, 0.70]  # engage, stay (in dead zone), release (below low)
    result = _script(filt, values)
    assert result == [True, True, False]


def test_min_dwell_holds_engagement_even_below_the_low_threshold():
    """A single-step dip below storage_threshold_low right after engaging
    must NOT release early -- min_dwell holds it regardless of the stat."""
    filt = _make_filter(hysteresis=True, min_dwell=3)
    values = [0.90, 0.10, 0.10, 0.10, 0.10]  # engage, then immediately "clear"
    result = _script(filt, values)
    # engaged at step 0 (dwell=3 remaining after this step's countdown starts);
    # held through the dwell window even though the stat is already low,
    # then released once dwell is exhausted AND stat is still low.
    assert result[0] is True
    assert result[-1] is False
    assert sum(result) >= 3  # held for at least the dwell window


def test_hysteresis_still_engages_immediately_on_first_crossing():
    """Hysteresis changes the RELEASE condition, not the engage one -- a
    fresh trigger crossing high must still activate on the very next
    decision, same as the naive filter."""
    filt = _make_filter(hysteresis=True, min_dwell=0)
    result = _script(filt, [0.10, 0.10, 0.90])
    assert result == [False, False, True]


def test_hysteresis_low_defaults_below_high_when_not_specified():
    env = _FakeEnv()
    filt = SafetyFilter(env, B=1.0, storage_aware=True, storage_threshold=0.85, fallback_theta=0.15)
    assert filt.storage_threshold_low < filt.storage_threshold
