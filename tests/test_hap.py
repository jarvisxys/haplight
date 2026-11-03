"""
Pins the implementation to the numbers printed in HAPLight_journal_v2.tex.

If a test here fails, either the code is wrong or the paper is wrong.
Fix one of them -- never delete the test.

Run:  pytest tests/ -v
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hap import (  # noqa: E402
    Fleet,
    capacity_barrier,
    greedy_phase,
    movement_weight,
    occupied_area,
    phase_pressure,
    storage_aware_mu,
    storage_headroom_fraction,
    weighted_queue_from_area,
    weighted_queue_from_counts,
    worst_downstream_occupancy,
)
from src.sensing import SensingModel, build_confusion_kernel  # noqa: E402

CFG = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "configs/default.yaml").read_text()
)

# Paper Table III, verbatim.
PAPER_AREA = {"twowheeler": 2.61, "car": 11.44, "auto": 6.84,
              "bus": 41.25, "truck": 31.35}
PAPER_PI = {"twowheeler": 0.228, "car": 1.000, "auto": 0.598,
            "bus": 3.606, "truck": 2.740}
PAPER_BETA_HCM = {"twowheeler": 5.220, "car": 11.440, "auto": 5.700,
                  "bus": 13.750, "truck": 8.957}


@pytest.fixture
def fleet_hcm():
    return Fleet.from_config(CFG, weight_scheme="hcm")


@pytest.fixture
def fleet_area():
    return Fleet.from_config(CFG, weight_scheme="area")


# ---------------------------------------------------------------------------
# Table III
# ---------------------------------------------------------------------------

def test_effective_areas_match_paper(fleet_area):
    for name, expected in PAPER_AREA.items():
        assert fleet_area.classes[name].area == pytest.approx(expected, abs=5e-3)


def test_area_equivalency_matches_paper(fleet_area):
    pi = fleet_area.pi
    for name, expected in PAPER_PI.items():
        assert pi[name] == pytest.approx(expected, abs=1e-3)


def test_beta_under_hcm_matches_paper(fleet_hcm):
    beta = fleet_hcm.beta
    for name, expected in PAPER_BETA_HCM.items():
        assert beta[name] == pytest.approx(expected, abs=1e-3)


# ---------------------------------------------------------------------------
# Lemma 1  -- the paper's central quantitative claim
# ---------------------------------------------------------------------------

def test_epsilon_star_hcm_is_0450(fleet_hcm):
    """Paper abstract, Remark 1, Table III: eps* = 0.450 under Indo-HCM."""
    assert fleet_hcm.epsilon_star == pytest.approx(0.450, abs=1e-3)


def test_a_bar_star_hcm(fleet_hcm):
    """Paper Remark 1: a_bar* = 9.485 m^2/PCU."""
    assert fleet_hcm.a_bar_star == pytest.approx(9.485, abs=1e-3)


def test_epsilon_star_area_is_exactly_zero(fleet_area):
    """Paper Remark 1: rho = pi  =>  beta_v constant  =>  eps* = 0."""
    assert fleet_area.epsilon_star == pytest.approx(0.0, abs=1e-12)
    assert fleet_area.a_bar_star == pytest.approx(fleet_area.a_c, rel=1e-12)


def test_area_estimator_exact_under_area_weights(fleet_area):
    """The whole point of choosing rho = pi. Must hold for ANY composition."""
    rng = np.random.default_rng(0)
    for _ in range(500):
        counts = {n: float(rng.integers(0, 40)) for n in fleet_area.names}
        if sum(counts.values()) == 0:
            continue
        x_true = weighted_queue_from_counts(fleet_area, counts)
        x_area = weighted_queue_from_area(
            fleet_area, occupied_area(fleet_area, counts)
        )
        assert x_area == pytest.approx(x_true, rel=1e-12)


def test_lemma1_bound_holds_and_is_tight(fleet_hcm):
    """Bound must contain every composition AND be attained by single-class."""
    lo, hi = fleet_hcm.lemma1_bounds()
    rng = np.random.default_rng(1)

    for _ in range(2000):
        counts = {n: float(rng.integers(0, 40)) for n in fleet_hcm.names}
        x = weighted_queue_from_counts(fleet_hcm, counts)
        if x <= 0:
            continue
        ratio = weighted_queue_from_area(
            fleet_hcm, occupied_area(fleet_hcm, counts)
        ) / x
        assert lo - 1e-9 <= ratio <= hi + 1e-9

    # tightness: pure argmin / argmax class queues attain the endpoints
    beta = fleet_hcm.beta
    lo_cls = min(beta, key=beta.get)
    hi_cls = max(beta, key=beta.get)
    for cls, target in ((lo_cls, lo), (hi_cls, hi)):
        counts = {n: (10.0 if n == cls else 0.0) for n in fleet_hcm.names}
        ratio = weighted_queue_from_area(
            fleet_hcm, occupied_area(fleet_hcm, counts)
        ) / weighted_queue_from_counts(fleet_hcm, counts)
        assert ratio == pytest.approx(target, rel=1e-12)


def test_nominal_composition_ratio(fleet_hcm):
    """Paper Remark 2: nominal weighted mean beta at the Phase 1c fleet mix
    (2W 62% / car 22% / auto 10% / bus 2% / truck 4%, PAPER_CHANGELOG
    P1c-5) = 8.115, ratio 0.856. Two-wheelers now dominate the fleet and
    carry the lowest beta (5.22), pulling the weighted mean BELOW
    a_bar_star -- the opposite sign from the earlier bus-heavy mix (which
    gave 9.978 / ratio 1.052). Both are legitimate: this number is a direct
    function of fleet.classes[*].share and is expected to move whenever
    that config value does."""
    assert fleet_hcm.nominal_beta_mean() == pytest.approx(8.115, abs=1e-2)
    ratio = fleet_hcm.nominal_beta_mean() / fleet_hcm.a_bar_star
    assert ratio == pytest.approx(0.856, abs=1e-3)


def test_a_bar_for_matches_nominal_beta_mean_at_fleet_shares(fleet_hcm):
    """a_bar_for(composition) generalises nominal_beta_mean() (Phase 1c,
    used by scripts/calibrate_estimator.py for per-movement calibration) --
    at the fleet's own nominal shares the two must agree exactly, since
    nominal_beta_mean() is just this formula evaluated at composition =
    {name: c.share}."""
    nominal_shares = {n: c.share for n, c in fleet_hcm.classes.items()}
    assert fleet_hcm.a_bar_for(nominal_shares) == pytest.approx(
        fleet_hcm.nominal_beta_mean(), rel=1e-12
    )


def test_a_bar_for_single_class_matches_its_beta(fleet_hcm):
    """A movement observed to carry only one class should calibrate to
    exactly that class's own beta -- the composition-weighted mean of a
    single point mass is the point itself."""
    beta = fleet_hcm.beta
    for name in fleet_hcm.names:
        composition = {n: (1.0 if n == name else 0.0) for n in fleet_hcm.names}
        assert fleet_hcm.a_bar_for(composition) == pytest.approx(beta[name], rel=1e-12)


def test_a_bar_for_empty_composition_falls_back_to_minimax(fleet_hcm):
    """A movement with zero observed mass during the calibration episode
    (never used) must fall back to a_bar_star, not raise or divide by
    zero."""
    assert fleet_hcm.a_bar_for({}) == pytest.approx(fleet_hcm.a_bar_star, rel=1e-12)


def test_epsilon_star_is_scale_free(fleet_hcm):
    """eps* must be invariant under beta -> gamma*beta (paper Appendix E)."""
    base = fleet_hcm.epsilon_star
    scaled = Fleet(
        [type(c)(**{**c.__dict__, "rho_hcm": c.rho_hcm * 3.0})
         for c in fleet_hcm.classes.values()],
        weight_scheme="hcm",
    )
    assert scaled.epsilon_star == pytest.approx(base, rel=1e-12)


# ---------------------------------------------------------------------------
# Remark 3 -- uniform error is free; only dispersion costs capacity
# ---------------------------------------------------------------------------

def test_uniform_multiplicative_error_does_not_change_greedy_action():
    """
    Paper Remark 3 / Appendix B. This is the property that justifies the
    per-movement catchment bias in the noise model. If this test fails, the
    robustness experiment is measuring the wrong thing.
    """
    rng = np.random.default_rng(7)
    phases = {"NS": ["m1", "m2"], "EW": ["m3", "m4"]}
    for _ in range(500):
        movs = ["m1", "m2", "m3", "m4"]
        x = {m: float(rng.uniform(0, 50)) for m in movs}
        down = {m: float(rng.uniform(0, 50)) for m in movs}
        mu = {m: float(rng.uniform(0.5, 2.0)) for m in movs}

        w_true = {m: movement_weight(x[m], {f"d{m}": down[m]}, {f"d{m}": 0.6})
                  for m in movs}
        eps = float(rng.uniform(-0.5, 0.5))
        w_scaled = {m: (1.0 + eps) * v for m, v in w_true.items()}

        assert greedy_phase(phases, mu, w_true) == \
               greedy_phase(phases, mu, w_scaled)


# ---------------------------------------------------------------------------
# Pressure mechanics
# ---------------------------------------------------------------------------

def test_movement_weight_sign_conventions():
    """Downstream congestion must reduce the weight (back-pressure)."""
    w_free = movement_weight(20.0, {"d": 0.0}, {"d": 1.0})
    w_blocked = movement_weight(20.0, {"d": 30.0}, {"d": 1.0})
    assert w_free == pytest.approx(20.0)
    assert w_blocked == pytest.approx(-10.0)
    assert w_blocked < w_free


def test_phase_pressure_uses_mu_weighting():
    """Dropping mu_m gives ablation A', not the paper's measure."""
    mu = {"a": 2.0, "b": 0.5}
    w = {"a": 3.0, "b": 3.0}
    assert phase_pressure(["a", "b"], mu, w) == pytest.approx(7.5)
    assert phase_pressure(["a", "b"], mu, w) != pytest.approx(sum(w.values()))


def test_greedy_ties_resolve_to_current_phase():
    """Anti-chattering: required for the stability argument."""
    phases = {"A": ["m1"], "B": ["m2"]}
    mu = {"m1": 1.0, "m2": 1.0}
    w = {"m1": 5.0, "m2": 5.0}
    assert greedy_phase(phases, mu, w, current="B") == "B"
    assert greedy_phase(phases, mu, w, current="A") == "A"


# ---------------------------------------------------------------------------
# Storage-aware HAP (PAPER_CHANGELOG P4c-1)
# ---------------------------------------------------------------------------


def test_storage_headroom_fraction_basic():
    assert storage_headroom_fraction(x_down=0.0, capacity_down=100.0) == pytest.approx(1.0)
    assert storage_headroom_fraction(x_down=100.0, capacity_down=100.0) == pytest.approx(0.0)
    assert storage_headroom_fraction(x_down=75.0, capacity_down=100.0) == pytest.approx(0.25)


def test_storage_headroom_fraction_clips_and_handles_unknown_capacity():
    # over capacity (sensing noise can overshoot) clips to 0, never negative
    assert storage_headroom_fraction(x_down=150.0, capacity_down=100.0) == pytest.approx(0.0)
    # capacity <= 0 (unknown/boundary edge) is unconstrained, not a divide-by-zero
    assert storage_headroom_fraction(x_down=50.0, capacity_down=0.0) == pytest.approx(1.0)


def test_capacity_barrier_recovers_full_rate_when_ample():
    """phi(h) = 1 whenever h >= theta -- the degrades-to-plain-HAP property."""
    assert capacity_barrier(headroom_frac=1.0, theta=0.15) == pytest.approx(1.0)
    assert capacity_barrier(headroom_frac=0.15, theta=0.15) == pytest.approx(1.0)


def test_capacity_barrier_goes_structurally_to_zero():
    """phi(0) = 0 exactly -- zero downstream headroom credits zero service
    rate, not just a reduced one. This is what prevents the argmax from
    ever being justified by crediting flow into an already-full sink."""
    assert capacity_barrier(headroom_frac=0.0, theta=0.15) == pytest.approx(0.0)


def test_capacity_barrier_ramps_linearly_between():
    assert capacity_barrier(headroom_frac=0.075, theta=0.15) == pytest.approx(0.5)


def test_storage_aware_mu_degrades_to_plain_mu_when_ample():
    """The criterion-4 invariant: storage-aware and plain HAP must be
    BIT-IDENTICAL whenever every movement has ample downstream headroom."""
    mu = {"m1": 2.0, "m2": 0.8}
    headroom = {"m1": 1.0, "m2": 0.5}  # both >= theta
    mu_eff = storage_aware_mu(mu, headroom, theta=0.15)
    assert mu_eff == pytest.approx(mu)


def test_storage_aware_mu_throttles_blocked_movement_only():
    mu = {"m1": 2.0, "m2": 0.8}
    headroom = {"m1": 0.0, "m2": 1.0}  # m1 fully blocked downstream
    mu_eff = storage_aware_mu(mu, headroom, theta=0.15)
    assert mu_eff["m1"] == pytest.approx(0.0)
    assert mu_eff["m2"] == pytest.approx(0.8)


def test_storage_aware_mu_missing_movement_is_unconstrained():
    """A movement absent from headroom_frac (e.g. storage_aware=False path
    never populated it) must not silently zero out -- it means 'no
    constraint known', not 'fully blocked'."""
    mu = {"m1": 2.0}
    mu_eff = storage_aware_mu(mu, headroom_frac={}, theta=0.15)
    assert mu_eff["m1"] == pytest.approx(2.0)


def test_worst_downstream_occupancy_picks_the_worst_not_the_average():
    """P4c-3's diagnosed failure mode: a low-capacity turn pocket at 90%
    must not be diluted by a healthy-looking large through movement at 5%
    -- the worst-of-the-group must win, not an average."""
    # through movement: x_hat=20, storage=400 (5%); turn pocket: x_hat=45, storage=50 (90%)
    assert worst_downstream_occupancy([(20.0, 400.0), (45.0, 50.0)]) == pytest.approx(0.9)


def test_worst_downstream_occupancy_ignores_zero_capacity_and_empty():
    assert worst_downstream_occupancy([(10.0, 0.0)]) == pytest.approx(0.0)
    assert worst_downstream_occupancy([]) == pytest.approx(0.0)


def test_storage_aware_argmax_avoids_serving_blocked_movement():
    """End-to-end: with a naive weight, m1's huge upstream queue would win
    the argmax even though its downstream is completely full; storage-aware
    mu must flip the choice to m2."""
    phases = {"A": ["m1"], "B": ["m2"]}
    mu = {"m1": 2.0, "m2": 2.0}
    w = {"m1": 100.0, "m2": 5.0}  # m1's raw pressure is far larger
    assert greedy_phase(phases, mu, w, current="B") == "A"  # plain HAP wastes green on m1

    mu_eff = storage_aware_mu(mu, headroom_frac={"m1": 0.0, "m2": 1.0}, theta=0.15)
    assert greedy_phase(phases, mu_eff, w, current="B") == "B"  # storage-aware avoids it


# ---------------------------------------------------------------------------
# Sensing model
# ---------------------------------------------------------------------------

def test_confusion_kernel_is_row_stochastic_and_size_adjacent():
    order = CFG["sensing"]["size_order"]
    U = build_confusion_kernel(order)
    assert np.allclose(U.sum(axis=1), 1.0)
    assert np.allclose(np.diag(U), 0.0)
    # two-wheeler (index 0) may only be confused with its single neighbour
    assert U[0, 1] == pytest.approx(1.0)
    # a two-wheeler must never be confused with a bus (opposite ends)
    assert U[0, -1] == pytest.approx(0.0)


def test_eta_zero_is_a_noop():
    movs = ["m1", "m2"]
    sm = SensingModel(CFG, movs, eta=0.0, rng=np.random.default_rng(0))
    counts = {"twowheeler": 12.0, "car": 5.0, "auto": 2.0,
              "bus": 1.0, "truck": 0.0}
    assert sm.corrupt_counts("m1", counts) == counts
    assert sm.corrupt_area("m1", 123.4) == pytest.approx(123.4)
    assert sm.apply_catchment_bias("m1", 10.0) == pytest.approx(10.0)


def test_catchment_bias_is_per_movement_and_stable_within_episode():
    """
    Must differ across movements (that is what costs capacity) and must NOT
    change between calls within an episode (it models fixed calibration
    error, not per-step noise).
    """
    movs = [f"m{i}" for i in range(20)]
    sm = SensingModel(CFG, movs, eta=1.0, rng=np.random.default_rng(3))
    first = {m: sm.bias(m) for m in movs}
    second = {m: sm.bias(m) for m in movs}
    assert first == second
    assert len(set(first.values())) > 1
    sm.reset_episode()
    assert {m: sm.bias(m) for m in movs} != first


def test_dropout_and_area_noise_scale_monotonically_with_eta():
    movs = ["m1"]
    prev_q = prev_s = -1.0
    for eta in CFG["sensing"]["eval_eta_grid"]:
        sm = SensingModel(CFG, movs, eta=eta, rng=np.random.default_rng(0))
        assert sm.dropout_prob >= prev_q
        assert sm.area_sigma >= prev_s
        prev_q, prev_s = sm.dropout_prob, sm.area_sigma


def test_area_noise_is_median_unbiased():
    """E[factor] = 1: no systematic scale shift (which would be free anyway)."""
    sm = SensingModel(CFG, ["m1"], eta=1.0, rng=np.random.default_rng(11))
    factors = [sm.corrupt_area("m1", 1.0) for _ in range(200_000)]
    assert float(np.mean(factors)) == pytest.approx(1.0, abs=0.01)


def test_dropout_never_increases_counts():
    sm = SensingModel(CFG, ["m1"], eta=1.0, rng=np.random.default_rng(5))
    counts = {"twowheeler": 30.0, "car": 20.0, "auto": 5.0,
              "bus": 3.0, "truck": 2.0}
    for _ in range(200):
        out = sm.corrupt_counts("m1", counts)
        assert sum(out.values()) <= sum(counts.values())
