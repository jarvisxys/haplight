"""
Phase 3 acceptance test (PLAN.md): SUMO's SL2015 sublane lane-changing
model should let two-wheelers filter past slower/larger vehicles in a
mixed queue, ending up at the front more often than cars do.

Run:  pytest tests/test_sublane.py -v
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.calibrate_sublane import run_queue_release  # noqa: E402
from src.hap import Fleet  # noqa: E402

CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"


def test_2w_reach_front(tmp_path):
    """Mean two-wheeler stop-line crossing rank < mean car crossing rank in
    a mixed standing queue (real fleet shares) released together on
    scripts.calibrate's single-signalised-cross testbed -- two-wheelers
    should filter to the front despite starting interleaved with, not
    segregated ahead of, cars.

    Measured (untuned config, 3 seeds, full red_s=60/green_s=150 window):
    mean rank gap (car - twowheeler) = +7.6 to +12.0, i.e. two-wheelers
    consistently finish ~8-12 places ahead of cars on average out of a
    ~200-vehicle queue -- the existing lat_alignment="arbitrary" /
    lc_sublane=1.0 two-wheeler settings already pass this gate; no new
    lc_pushy/lc_assertive/lc_accel_lat tuning was needed.
    """
    cfg = yaml.safe_load(CFG_PATH.read_text())
    fleet = Fleet.from_config(cfg)

    result = run_queue_release(cfg, fleet, tmp_path, seed=0)
    mean_rank = result["mean_rank"]
    n = result["n_vehicles"]

    assert n.get("twowheeler", 0) >= 5 and n.get("car", 0) >= 5, (
        f"too few vehicles queued to measure filtering: {n}"
    )
    assert mean_rank["twowheeler"] < mean_rank["car"], (
        f"two-wheelers did not filter to the front: mean_rank twowheeler="
        f"{mean_rank['twowheeler']:.1f} car={mean_rank['car']:.1f} (n={n})"
    )
