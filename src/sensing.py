"""
Camera-grade sensing noise model (paper Sec. V-E).

A single scalar eta in [0,1] scales four mechanisms simultaneously so that
robustness curves are indexed by one interpretable number:

    1. Misclassification   C(eta) = (1 - theta*eta) I + theta*eta U
    2. Detection dropout   q(eta) = q_max * eta
    3. Area noise          lognormal, sigma(eta) = sigma_max * eta
    4. Catchment bias      b_m ~ U[1 - 0.1 eta, 1 + 0.1 eta], PER MOVEMENT,
                           PER EPISODE

CRITICAL (paper Remark 3 / Prop. 1):
    Mechanism 4 is the one that actually costs capacity. A *uniform*
    multiplicative error leaves the greedy argmax unchanged and is provably
    free. If you drop the per-movement bias, or resample it every step
    instead of every episode, the robustness experiment measures the wrong
    thing and H3 becomes untestable. Do not "simplify" it.
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

import numpy as np


def build_confusion_kernel(size_order: Sequence[str]) -> np.ndarray:
    """
    Row-stochastic kernel U that redistributes each class's mass uniformly
    over its size-adjacent neighbours in `size_order`.

    Endpoints send all mass to their single neighbour; interior classes split
    it evenly. This models the realistic failure mode -- a detector confuses
    a car with an auto or a truck, not with a motorcycle.
    """
    n = len(size_order)
    if n < 2:
        raise ValueError("need at least two classes to build a confusion kernel")
    U = np.zeros((n, n), dtype=float)
    for i in range(n):
        nbrs = [j for j in (i - 1, i + 1) if 0 <= j < n]
        for j in nbrs:
            U[i, j] = 1.0 / len(nbrs)
    return U


class SensingModel:
    """
    Applies the composite noise at a given level eta.

    Usage per episode:
        sm = SensingModel(cfg, movement_ids, eta=0.4, rng=rng)
        sm.reset_episode()                    # redraws the per-movement bias
        obs = sm.corrupt_counts(m, true_counts)
        area = sm.corrupt_area(m, true_area)
    """

    def __init__(
        self,
        cfg: Mapping,
        movement_ids: Sequence[str],
        eta: float = 0.0,
        rng: np.random.Generator | None = None,
    ):
        if not 0.0 <= eta <= 1.0:
            raise ValueError(f"eta must be in [0,1], got {eta}")
        s = cfg["sensing"]
        self.eta = float(eta)
        self.theta_max = s["theta_max"]
        self.q_max = s["q_max"]
        self.sigma_max = s["sigma_max"]
        self.bias_max = s["bias_max"]
        self.size_order: List[str] = list(s["size_order"])
        self.movement_ids = list(movement_ids)
        self.rng = rng if rng is not None else np.random.default_rng()

        self._U = build_confusion_kernel(self.size_order)
        self._C = self._confusion_matrix()
        self._bias: Dict[str, float] = {}
        self.reset_episode()

    # -- derived noise parameters -------------------------------------------

    def _confusion_matrix(self) -> np.ndarray:
        n = len(self.size_order)
        mix = self.theta_max * self.eta
        return (1.0 - mix) * np.eye(n) + mix * self._U

    @property
    def dropout_prob(self) -> float:
        return self.q_max * self.eta

    @property
    def area_sigma(self) -> float:
        return self.sigma_max * self.eta

    # -- per-episode state ---------------------------------------------------

    def reset_episode(self) -> None:
        """Redraw the per-movement catchment bias. Call once per episode."""
        lo, hi = 1.0 - self.bias_max * self.eta, 1.0 + self.bias_max * self.eta
        self._bias = {
            m: float(self.rng.uniform(lo, hi)) for m in self.movement_ids
        }

    def bias(self, movement: str) -> float:
        return self._bias.get(movement, 1.0)

    # -- corruption ----------------------------------------------------------

    def corrupt_counts(
        self, movement: str, counts: Mapping[str, float]
    ) -> Dict[str, float]:
        """
        Apply dropout then misclassification to per-class queued counts.

        Dropout first (a vehicle that is not detected cannot be misclassified),
        then multinomial resampling through C. The per-movement bias is applied
        downstream by the caller on x_hat, not here, because it models
        catchment-polygon calibration error rather than per-vehicle error.
        """
        if self.eta <= 0.0:
            return dict(counts)

        n = np.array([counts.get(v, 0.0) for v in self.size_order], dtype=float)

        # 1. detection dropout (binomial thinning)
        q = self.dropout_prob
        if q > 0.0:
            n = np.array(
                [self.rng.binomial(int(round(k)), 1.0 - q) if k > 0 else 0.0
                 for k in n],
                dtype=float,
            )

        # 2. misclassification (multinomial resampling through C)
        out = np.zeros_like(n)
        for i, k in enumerate(n):
            k = int(round(k))
            if k <= 0:
                continue
            out += self.rng.multinomial(k, self._C[i]).astype(float)

        return {v: float(out[i]) for i, v in enumerate(self.size_order)}

    def corrupt_area(self, movement: str, area: float) -> float:
        """
        Median-unbiased lognormal multiplicative noise on the segmented area.

        ln(1+zeta) ~ N(-sigma^2/2, sigma^2) so that E[1+zeta] = 1: the noise
        adds dispersion without a systematic scale shift, which matters
        because a systematic shift would be free (Remark 3).
        """
        if self.eta <= 0.0:
            return area
        sigma = self.area_sigma
        if sigma <= 0.0:
            return area
        factor = float(self.rng.lognormal(-0.5 * sigma * sigma, sigma))
        return area * factor

    def apply_catchment_bias(self, movement: str, x_hat: float) -> float:
        """Per-movement, per-episode multiplicative bias. THE mechanism that
        costs capacity under Proposition 1."""
        return x_hat * self.bias(movement)

    def __repr__(self) -> str:
        return (
            f"SensingModel(eta={self.eta:.2f}, q={self.dropout_prob:.3f}, "
            f"sigma={self.area_sigma:.3f}, bias_max={self.bias_max*self.eta:.3f})"
        )
