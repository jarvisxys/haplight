"""
Phase 1b acceptance tests: composition dispersion, demand calibration,
reset determinism.

Run:  pytest tests/test_composition.py -v
"""
import copy
import math
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_nets import build_scenario  # noqa: E402
from scripts.calibrate_demand import _mp_shadow_action, offered_veh_h  # noqa: E402
from src import metrics  # noqa: E402
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
NET_DIR = Path(__file__).resolve().parents[1] / "nets" / "arterial5"


def _cfg(episode_length_s: float = 900.0) -> dict:
    cfg = yaml.safe_load(CFG_PATH.read_text())
    cfg = copy.deepcopy(cfg)
    cfg["demand"]["episode_length_s"] = episode_length_s
    return cfg


def _build_s1(tmp_path: Path, cfg: dict, dispersion: float, tag: str, demand_scale: float = 1.0) -> Path:
    outdir = tmp_path / f"arterial5_{tag}"
    s1 = cfg["scenarios"]["s1_arterial"]
    build_scenario(
        "arterial5", 1, s1["n_intersections"], s1["spacing_m"], cfg, outdir,
        lefthand=True, demand_scale=demand_scale, composition_dispersion=dispersion,
    )
    return outdir


def _hap_vs_mp_disagreement(net_dir: Path, cfg: dict, fleet: Fleet, seed: int = 0):
    """Drives one GreedyHAP episode; at every decision also computes what
    MaxPressure would have chosen from the SAME info (via the shared
    calibrate_demand._mp_shadow_action, no second simulation needed).
    Returns (n_decisions, n_disagreements).

    estimator="count", not the paper-default "area": MaxPressure's shadow
    always reads counts_hat (count-corruption pipeline regardless of
    env.estimator, by src/env.py's design), so pairing it against
    GreedyHAP's x_hat under estimator="area" would conflate the area
    estimator's OWN approximation error (Lemma 1) with the composition
    effect this test is isolating -- roughly doubled the measured
    disagreement rate in practice. "count" is the channel on which
    x^HAP = c*x^MP holds exactly (in expectation; see the docstring on
    the uniform-composition test for the finite-sample caveat)."""
    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=seed, eta=0.0, estimator="count")
    try:
        obs = env.reset()
        hap = GreedyHAP(env)
        hap.reset()
        info = env.info
        n_decisions = disagreements = 0
        truncated = False
        while not truncated:
            hap_actions = hap.act(obs, info)
            mp_actions = _mp_shadow_action(env, info)
            for i in env.intersections:
                n_decisions += 1
                if hap_actions[i] != mp_actions[i]:
                    disagreements += 1
            obs, reward, truncated, info = env.step(hap_actions)
        return n_decisions, disagreements
    finally:
        env.close()


def _metrics_equal(a: dict, b: dict) -> bool:
    """Dict equality with nan==nan (a short episode legitimately has NaN
    gini values for classes with <2 completed trips in BOTH runs; Python's
    default nan != nan would otherwise flag that as a "difference")."""
    if a.keys() != b.keys():
        return False
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


# ---------------------------------------------------------------------------
# Composition dispersion vs HAP/MP equivalence (Remark 3 applied to rho)
# ---------------------------------------------------------------------------


def test_uniform_composition_makes_hap_equal_mp(tmp_path):
    """At dispersion 0, x^HAP = c*x^MP componentwise in EXPECTATION (every
    OD pair draws vehicle classes from the same nominal shares) -- Remark 3
    applied to the weight vector.

    Not asserted as exactly zero disagreements: `c` is only exactly
    constant across movements for the population mix, not for any single
    finite realised queue (a movement with 2 cars and 1 auto queued has a
    different sample composition than one with 1 car and 2 autos, purely
    from Poisson/vType-sampling noise, even though both drew from the
    identical distribution). That residual is expected and should be small
    -- measured at ~1% here -- and structurally different from the
    heterogeneous case below, where composition itself differs by
    construction."""
    cfg = _cfg(episode_length_s=900.0)
    fleet = Fleet.from_config(cfg)
    net_dir = _build_s1(tmp_path, cfg, dispersion=0.0, tag="d0")

    n_decisions, disagreements = _hap_vs_mp_disagreement(net_dir, cfg, fleet)
    rate = disagreements / n_decisions if n_decisions else 0.0
    assert n_decisions > 0
    assert rate < 0.05, (
        f"{disagreements}/{n_decisions} ({rate:.1%}) decisions disagreed at "
        f"composition dispersion 0 -- expected only sparse finite-sample "
        f"noise (<5%), not a systematic difference"
    )


def test_heterogeneous_composition_separates_hap_from_mp(tmp_path):
    """At dispersion 1, composition genuinely varies across movements, so
    HAP and MP should disagree on a non-trivial fraction of decisions.

    demand_scale=4.0 (not the default 1.0, uncalibrated/free-flow level):
    with near-empty queues most decisions are a trivial "serve whichever
    phase has anything at all" that any reasonable controller agrees on
    regardless of composition -- this needs genuine congestion to exercise
    the mechanism at all, independent of how the archetypes are chosen. Not
    a tuning knob for the disagreement rate itself, which is asserted
    as-measured either way."""
    cfg = _cfg(episode_length_s=900.0)
    fleet = Fleet.from_config(cfg)
    net_dir = _build_s1(tmp_path, cfg, dispersion=1.0, tag="d1", demand_scale=4.0)

    n_decisions, disagreements = _hap_vs_mp_disagreement(net_dir, cfg, fleet)
    rate = disagreements / n_decisions if n_decisions else 0.0
    # Asserting non-identity, not a magnitude: measured on this topology the
    # rate is modest (order 0.3%, not the 5%+ one might hope for) -- that is
    # the result, not a cue to retune LOCAL_ARCHETYPE/ARTERIAL_ARCHETYPE or
    # this threshold until a bigger number appears. The real measured rate
    # is reported honestly by calibrate_demand.py --dispersion-sweep.
    assert disagreements > 0, (
        "HAP and MP never disagreed even at full composition dispersion -- "
        "expected at least some decisions to differ (rate was "
        f"{rate:.2%} over {n_decisions} decisions)"
    )


# ---------------------------------------------------------------------------
# Demand calibration
# ---------------------------------------------------------------------------


def test_nominal_demand_is_congested():
    """At the calibrated nominal scale, S1 should be genuinely congested
    (v/c in [0.8, 0.9], AQL above a free-flow-excluding threshold) --
    skipped until scripts/calibrate_demand.py has been run."""
    cfg = yaml.safe_load(CFG_PATH.read_text())
    nominal = (cfg.get("demand", {}) or {}).get("scale_nominal") or {}
    capacity = (cfg.get("demand", {}) or {}).get("capacity_veh_per_h") or {}
    scale = nominal.get("s1_arterial")
    cap = capacity.get("s1_arterial")
    if scale is None or cap is None:
        pytest.skip("demand.scale_nominal/capacity_veh_per_h not calibrated yet -- run scripts/calibrate_demand.py")

    cfg = _cfg(episode_length_s=cfg["demand"]["episode_length_s"])
    fleet = Fleet.from_config(cfg)
    if not NET_DIR.exists():
        pytest.skip("run scripts/build_nets.py first")

    env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=0, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
        m = metrics.compute(env.completed_trips(), env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
    finally:
        env.close()

    n_od = 12  # S1's boundary-edge count (5 intersections, 1 row) -- see build_nets.build_topology
    vc = offered_veh_h(scale, n_od) / cap
    assert 0.8 <= vc <= 0.9, f"measured v/c={vc:.2f} at scale_nominal, expected [0.8, 0.9]"
    assert m["aql"] > 5.0, f"AQL={m['aql']:.2f} at nominal demand looks like free-flow, not congested"


# ---------------------------------------------------------------------------
# Reset determinism (Phase 1 P1-11: subscriptions must survive reset())
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_reset_determinism():
    """Two consecutive episodes on the SAME env instance, same (fixed,
    constructor-level) seed -> identical metrics. Verified empirically that
    libsumo supports this for repeated reset() on one instance (distinct
    from the cross-*instance* libsumo reuse issue in Phase 1, which does
    NOT hold and is why test_true_queues_noise_free uses traci instead)."""
    cfg = _cfg(episode_length_s=300.0)
    fleet = Fleet.from_config(cfg)
    env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=7, eta=0.0, estimator="area")
    try:
        runs = []
        for _ in range(2):
            obs = env.reset()
            ctrl = GreedyHAP(env)
            ctrl.reset()
            info = env.info
            truncated = False
            while not truncated:
                actions = ctrl.act(obs, info)
                obs, reward, truncated, info = env.step(actions)
            runs.append(metrics.compute(env.completed_trips(), env.true_queue_history(), fleet, cfg, env.gmax_activation_rate()))
    finally:
        env.close()
    assert _metrics_equal(runs[0], runs[1]), f"reset() is not deterministic: {runs[0]} != {runs[1]}"


@pytest.mark.skipif(not NET_DIR.exists(), reason="run scripts/build_nets.py first")
def test_seed_changes_outcome():
    """Two env instances with different constructor-level seeds should
    give different metrics (sanity check that `seed` actually does
    something, complementing test_reset_determinism)."""
    cfg = _cfg(episode_length_s=300.0)
    fleet = Fleet.from_config(cfg)
    runs = []
    for seed in (1, 2):
        env = HAPLightEnv(str(NET_DIR), cfg, fleet, seed=seed, eta=0.0, estimator="area")
        try:
            obs = env.reset()
            ctrl = GreedyHAP(env)
            ctrl.reset()
            info = env.info
            truncated = False
            while not truncated:
                actions = ctrl.act(obs, info)
                obs, reward, truncated, info = env.step(actions)
            runs.append(metrics.compute(env.completed_trips(), env.true_queue_history(), fleet, cfg, env.gmax_activation_rate()))
        finally:
            env.close()
    assert not _metrics_equal(runs[0], runs[1]), "different seeds produced identical metrics"
