"""
Heterogeneity-Aware Occupancy Pressure (HAP).

This module is the single source of truth for the paper's core measure.
Everything else (controllers, RL reward, calibration, baselines) imports from
here. If a formula appears both in the paper and in the code, it lives here.

Paper cross-references (HAPLight_journal_v2.tex):
    Eq. (1)  weighted queue                  -> weighted_queue_from_counts
    Eq. (3)  effective dynamic area          -> VehicleClass.area
    Eq. (4)  count-based estimator           -> weighted_queue_from_counts
    Eq. (5)  area estimator                  -> weighted_queue_from_area
    Eq. (6)/(7)  Lemma 1 bound and eps*      -> Fleet.epsilon_star / a_bar_star
    Eq. (8)  movement weight w_m             -> movement_weight
    Eq. (9)  phase pressure P_i(phi)         -> phase_pressure

DESIGN NOTE (do not "simplify" this away):
    The weight vector rho is a *parameter*, not a constant. Setting
    weight_scheme="area" makes the area estimator exact (Lemma 1, eps*=0);
    weight_scheme="hcm" makes it lossy (eps*=0.450). H5 compares them.
    Any code that assumes a fixed rho breaks the paper's central experiment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Fleet definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VehicleClass:
    """One vehicle class. Geometry doubles as the SUMO vType spec."""

    name: str
    sumo_class: str
    length: float          # m
    width: float           # m
    min_gap: float         # m, longitudinal standstill gap
    min_gap_lat: float     # m, lateral standstill clearance
    max_speed_kmh: float
    accel: float
    decel: float
    rho_hcm: float         # Indo-HCM PCU factor
    share: float           # nominal fleet share
    occupancy: float       # nominal passengers per vehicle

    @property
    def area(self) -> float:
        """Effective dynamic area a_v, paper Eq. (3)."""
        return (self.length + self.min_gap) * (self.width + self.min_gap_lat)

    @property
    def max_speed_ms(self) -> float:
        return self.max_speed_kmh / 3.6


class Fleet:
    """
    A fleet plus an *active* space-equivalency weight vector.

    weight_scheme:
        "area" -> rho_v = pi_v = a_v / a_car   (Lemma 1 gives eps* = 0)
        "hcm"  -> rho_v = Indo-HCM PCU factor  (Lemma 1 gives eps* = 0.450)
    """

    VALID_SCHEMES = ("area", "hcm")

    def __init__(
        self,
        classes: Sequence[VehicleClass],
        weight_scheme: str = "area",
        reference_class: str = "car",
        equivalency_perturbation: float = 0.0,
        a_bar_calibrated: float | None = None,
    ):
        if weight_scheme not in self.VALID_SCHEMES:
            raise ValueError(
                f"weight_scheme must be one of {self.VALID_SCHEMES}, "
                f"got {weight_scheme!r}"
            )
        if not classes:
            raise ValueError("Fleet needs at least one vehicle class")

        self.classes: Dict[str, VehicleClass] = {c.name: c for c in classes}
        self.names: tuple = tuple(c.name for c in classes)
        self.weight_scheme = weight_scheme
        self.reference_class = reference_class

        if reference_class not in self.classes:
            raise ValueError(f"reference_class {reference_class!r} not in fleet")

        self.a_c = self.classes[reference_class].area
        # Sensitivity sweep (paper Sec. VII-H iii): perturb the two-wheeler
        # weight by +-20% and re-run. Applied to the *active* vector only.
        self._perturbation = equivalency_perturbation
        # Empirically calibrated calibration constant (scripts/calibrate.py C1).
        # The minimax a_bar* of Lemma 1 is optimal against the WORST composition;
        # calibrating to the realised composition is far tighter, and the
        # resulting uniform offset is free by Remark 3. Scheme-specific.
        self._a_bar_cal = a_bar_calibrated

    # -- weight vector -------------------------------------------------------

    @property
    def rho(self) -> Dict[str, float]:
        """Active space-equivalency weight vector."""
        if self.weight_scheme == "area":
            base = {n: c.area / self.a_c for n, c in self.classes.items()}
        else:
            base = {n: c.rho_hcm for n, c in self.classes.items()}
        if self._perturbation:
            # Perturb the two-wheeler factor specifically (paper flags it as
            # the most contested value in the literature).
            base = dict(base)
            for n in base:
                if n.startswith("two") or n == "2w":
                    base[n] *= 1.0 + self._perturbation
        return base

    @property
    def pi(self) -> Dict[str, float]:
        """Dynamic-area equivalency, regardless of active scheme."""
        return {n: c.area / self.a_c for n, c in self.classes.items()}

    @property
    def area_of(self) -> Dict[str, float]:
        return {n: c.area for n, c in self.classes.items()}

    # -- Lemma 1 -------------------------------------------------------------

    @property
    def beta(self) -> Dict[str, float]:
        """beta_v = a_v / rho_v, in m^2 per weight-unit (Lemma 1)."""
        rho = self.rho
        return {n: c.area / rho[n] for n, c in self.classes.items()}

    @property
    def a_bar_star(self) -> float:
        """Minimax calibration constant, a_bar* = (beta_min + beta_max)/2."""
        b = self.beta.values()
        return 0.5 * (min(b) + max(b))

    @property
    def epsilon_star(self) -> float:
        """
        Tight worst-case relative error of the area estimator, paper Eq. (7):

            eps* = (beta_max - beta_min) / (beta_max + beta_min)

        Scale-free: it measures dispersion of footprint-to-weight ratios only.
        Zero iff rho_v is proportional to a_v.
        """
        b = list(self.beta.values())
        lo, hi = min(b), max(b)
        return (hi - lo) / (hi + lo)

    @property
    def a_bar(self) -> float:
        """Calibration constant actually used by the area estimator.

        Falls back to the minimax a_bar* when no calibrated value is supplied.
        """
        return self._a_bar_cal if self._a_bar_cal is not None else self.a_bar_star

    def lemma1_bounds(self, a_bar: float | None = None) -> tuple:
        """(lower, upper) on x_hat_area / x, attained by single-class queues.

        Evaluated at the a_bar actually in use (calibrated if available), so
        the bound describes the deployed estimator rather than a hypothetical.
        """
        if a_bar is None:
            a_bar = self.a_bar
        b = list(self.beta.values())
        return (min(b) / a_bar, max(b) / a_bar)

    def epsilon_achieved(self, a_bar: float | None = None) -> float:
        """Worst-case relative error at a given a_bar.

        epsilon_star is the minimax value of Eq. (7) -- optimal against the
        worst composition. This is what the deployed calibration achieves.
        """
        lo, hi = self.lemma1_bounds(a_bar)
        return max(hi - 1.0, 1.0 - lo)

    def nominal_beta_mean(self) -> float:
        """
        Composition-weighted mean of beta at the nominal fleet shares.
        Paper Remark 2: the realised ratio concentrates near this / a_bar*.
        """
        rho, beta = self.rho, self.beta
        w = {n: rho[n] * c.share for n, c in self.classes.items()}
        tot = sum(w.values())
        return sum(w[n] / tot * beta[n] for n in self.names)

    def a_bar_for(self, composition: Mapping[str, float]) -> float:
        """
        Composition-weighted mean of beta for an ARBITRARY class mix, not
        just the fleet-wide nominal shares -- same formula as
        nominal_beta_mean() above, generalised (paper Remark 2) to whatever
        composition was actually observed at a given movement.

        This is what scripts/calibrate_estimator.py calls per movement,
        using a short classified count taken at that approach (the
        simulated stand-in is one full episode's worth of true_counts),
        exactly mirroring how a real camera would be commissioned in the
        field. `composition` need not include every class or be
        pre-normalised -- only relative weights matter.

        Falls back to the minimax a_bar_star when the composition carries
        no mass (e.g. a movement nothing was observed to use during the
        calibration episode).
        """
        rho, beta = self.rho, self.beta
        w = {n: rho[n] * composition.get(n, 0.0) for n in self.names}
        tot = sum(w.values())
        if tot <= 0:
            return self.a_bar_star
        return sum(w[n] / tot * beta[n] for n in self.names)

    # -- passenger weighting -------------------------------------------------

    @property
    def occupancy(self) -> Dict[str, float]:
        return {n: c.occupancy for n, c in self.classes.items()}

    # -- construction --------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: Mapping, **overrides) -> "Fleet":
        f = cfg["fleet"]
        classes = [VehicleClass(**c) for c in f["classes"]]
        scheme = overrides.pop("weight_scheme", f.get("weight_scheme", "hcm"))
        cal = (f.get("a_bar_calibrated") or {}).get(scheme)
        kwargs = dict(weight_scheme=scheme, a_bar_calibrated=cal)
        kwargs.update(overrides)
        return cls(classes, **kwargs)

    def __repr__(self) -> str:
        return (
            f"Fleet(scheme={self.weight_scheme!r}, n={len(self.classes)}, "
            f"eps*={self.epsilon_star:.4f}, a_bar={self.a_bar:.3f})"
        )


# ---------------------------------------------------------------------------
# Queue estimators
# ---------------------------------------------------------------------------


def weighted_queue_from_counts(
    fleet: Fleet, counts: Mapping[str, float]
) -> float:
    """
    Count-based estimator, paper Eq. (4):  x_hat_cnt = sum_v rho_v n_{m,v}.

    Exact given perfect classification; inherits every misclassification.
    `counts` may hold non-integer values (post-noise expected counts).
    """
    rho = fleet.rho
    return sum(rho[v] * n for v, n in counts.items())


def occupied_area(fleet: Fleet, counts: Mapping[str, float]) -> float:
    """Ground-truth occupied area A_m = sum_v a_v n_{m,v}, paper Eq. (5)."""
    a = fleet.area_of
    return sum(a[v] * n for v, n in counts.items())


def weighted_queue_from_area(
    fleet: Fleet, area: float, a_bar: float | None = None
) -> float:
    """
    Classification-free area estimator, paper Eq. (5): x_hat_area = A_m / a_bar.

    Defaults to the minimax-optimal a_bar* of Lemma 1. Under
    weight_scheme="area" this is exactly a_c and the estimator is exact.
    """
    if a_bar is None:
        a_bar = fleet.a_bar
    return area / a_bar


# ---------------------------------------------------------------------------
# Pressure
# ---------------------------------------------------------------------------


def movement_weight(
    x_up: float,
    downstream: Mapping[str, float],
    turning: Mapping[str, float],
) -> float:
    """
    Movement weight, paper Eq. (8):  w_m = x_m - sum_{m'} r_{mm'} x_{m'}.

    `downstream` maps downstream movement id -> its weighted queue.
    `turning` maps the same ids -> turning proportions r_{mm'} (sum <= 1).
    Pass the aggregate downstream-link form by using a single entry with r=1.
    """
    return x_up - sum(turning.get(k, 0.0) * v for k, v in downstream.items())


def phase_pressure(
    movements: Iterable[str],
    mu: Mapping[str, float],
    w: Mapping[str, float],
) -> float:
    """
    HAP pressure of a phase, paper Eq. (9):  P_i(phi) = sum_{m in phi} mu_m w_m.

    The mu_m factor is NOT optional: it is what makes the greedy argmax the
    max-weight functional of Theorem 1, and what makes the RL reward
    (Eq. 12) the exact Lyapunov drift functional. Dropping it gives the
    PressLight-style variant, which is ablation A' in the paper.
    """
    return sum(mu[m] * w[m] for m in movements)


def greedy_phase(
    phases: Mapping[str, Sequence[str]],
    mu: Mapping[str, float],
    w: Mapping[str, float],
    current: str | None = None,
) -> str:
    """
    Greedy HAP action, paper Eq. (10). Ties resolve to the current phase,
    which suppresses chattering (and is required for the stability argument
    to avoid pathological oscillation).
    """
    best_phase, best_val = None, float("-inf")
    for name, movs in phases.items():
        val = phase_pressure(movs, mu, w)
        if val > best_val + 1e-12:
            best_phase, best_val = name, val
        elif current is not None and name == current and val >= best_val - 1e-12:
            best_phase, best_val = name, val
    return best_phase


def storage_headroom_fraction(x_down: float, capacity_down: float) -> float:
    """h_m(t): fraction of movement m's downstream link still physically
    free, in [0, 1]. `capacity_down` <= 0 means no storage constraint is
    known for this edge (e.g. a network boundary) -- treated as unconstrained
    (PAPER_CHANGELOG P4c-1, storage-aware HAP)."""
    if capacity_down <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - x_down / capacity_down))


def capacity_barrier(headroom_frac: float, theta: float) -> float:
    """phi(h): the capacity-aware throttle on effective service rate.
    phi(h) = 1 for h >= theta (ample downstream storage -- recovers plain
    HAP exactly), ramping LINEARLY to phi(0) = 0 (zero downstream headroom
    -> zero credited service rate, structurally, not just probabilistically
    -- this is what prevents the argmax from ever being justified by
    crediting flow into an already-full sink). theta <= 0 degenerates to a
    hard indicator (barrier only at exactly zero headroom)."""
    if theta <= 0:
        return 1.0 if headroom_frac > 0 else 0.0
    return max(0.0, min(1.0, headroom_frac / theta))


def worst_downstream_occupancy(downstream_movements: Iterable[tuple]) -> float:
    """Worst SENSED occupancy fraction among the specific movements sharing
    a downstream edge (PAPER_CHANGELOG P4c-3/P4c-7 -- the validated,
    deployable replacement for the edge-aggregate `storage_headroom_
    fraction(x_down, edge_capacity)` path, which P4c-3 confirmed fails: a
    low-capacity turn pocket is invisible inside a healthy-looking edge-
    wide average). `downstream_movements` is an iterable of (x_hat_mv2,
    storage_mv2) pairs -- one per movement sharing the edge, each compared
    against its OWN storage, never a summed edge capacity (summing double-
    counts shared lanes -- P4c-6). No oracle: x_hat is already movement-
    resolved (built from that movement's own lane subset), so this needs
    no new sensing plumbing beyond what env.py already computes."""
    worst = 0.0
    for x_hat, storage in downstream_movements:
        if storage > 0:
            worst = max(worst, x_hat / storage)
    return worst


def storage_aware_mu(
    mu: Mapping[str, float],
    headroom_frac: Mapping[str, float],
    theta: float,
) -> Dict[str, float]:
    """mu_m^eff = mu_m * phi(h_m) -- capacity-aware effective saturation
    flow (PAPER_CHANGELOG P4c-1). Movements missing from `headroom_frac`
    are treated as storage-unconstrained (phi=1), so this is a drop-in
    replacement for `mu` in `phase_pressure`/`greedy_phase` -- neither of
    those functions needs to change. Degrades to `mu` exactly whenever
    every movement's headroom is >= theta (ample storage everywhere)."""
    return {
        m: rate * capacity_barrier(headroom_frac.get(m, 1.0), theta)
        for m, rate in mu.items()
    }


def saturation_flow(width_m: float, cfg: Mapping) -> float:
    """
    mu_m in weight-units/s from effective approach width (Indo-HCM form).
    The per-metre coefficient is CALIBRATED by scripts/calibrate.py (C2) and
    written back into configs/default.yaml -- do not leave it at the default.
    """
    s = cfg["hap"]["saturation_flow"]
    mu = s["per_metre_width"] * width_m
    return max(s["min_mu"], min(s["max_mu"], mu))
