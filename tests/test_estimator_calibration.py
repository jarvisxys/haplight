"""
Phase 1c acceptance test (PLAN.md Phase 1c gate: "area ~ count estimator").

P1b-7 found Greedy HAP collapsing under estimator="area" once composition
varies by movement (a single global a_bar carries a fixed per-movement
bias). Phase 1c's fix is per-movement calibration
(scripts/calibrate_estimator.py, src/hap.py::Fleet.a_bar_for); this test
is the gate PLAN.md names for that fix: with per-movement calibration
installed, the area estimator's throughput should track the count
estimator's, not diverge from it the way P1b-7 measured.

Run:  pytest tests/test_estimator_calibration.py -v
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import metrics  # noqa: E402
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
NET_DIR = Path(__file__).resolve().parents[1] / "nets" / "arterial5"

# Set from scripts/calibrate_estimator.py's own three-way sweep output, not
# invented ahead of the measurement -- see PAPER_CHANGELOG P1c-1. Measured
# per-movement-vs-count throughput gap was 0.16% (d=0), 0.57% (d=0.5), 0.56%
# (d=1.0) -- i.e. per-movement calibration recovers to well under 1% of
# count at every dispersion level tested, comfortably beating the "a few
# percent" prediction. 5% leaves real margin (this test runs a different
# episode length/seed than the sweep) while still being a meaningful gate --
# the pre-fix global estimator's own gap at d=0 was 10.9%, well outside it.
MAX_RELATIVE_THROUGHPUT_GAP = 0.05


def _run(net_dir: Path, cfg: dict, fleet: Fleet, estimator: str) -> dict:
    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=0, eta=0.0, estimator=estimator)
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
        trips = env.completed_trips()
        return metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
    finally:
        env.close()


@pytest.mark.skipif(
    not (NET_DIR / "a_bar_per_movement.json").exists(),
    reason="run scripts/calibrate_estimator.py first to install per-movement calibration",
)
def test_per_movement_calibration_recovers_area_estimator():
    """With nets/arterial5/a_bar_per_movement.json installed, GreedyHAP
    under estimator="area" (per-movement calibrated) should achieve
    throughput within MAX_RELATIVE_THROUGHPUT_GAP of estimator="count" --
    P1b-7 measured a ~30% gap under the single global a_bar; the
    per-movement fix should close most of it (PAPER_CHANGELOG P1c-1)."""
    cfg = yaml.safe_load(CFG_PATH.read_text())
    fleet = Fleet.from_config(cfg)

    area_m = _run(NET_DIR, cfg, fleet, estimator="area")
    count_m = _run(NET_DIR, cfg, fleet, estimator="count")

    assert area_m["tp"] > 0 and count_m["tp"] > 0, "no trips completed -- demand too low"
    gap = abs(area_m["tp"] - count_m["tp"]) / count_m["tp"]
    assert gap < MAX_RELATIVE_THROUGHPUT_GAP, (
        f"per-movement-calibrated area throughput ({area_m['tp']:.1f} veh/h) "
        f"is {gap:.1%} off count ({count_m['tp']:.1f} veh/h), expected within "
        f"{MAX_RELATIVE_THROUGHPUT_GAP:.0%}"
    )
