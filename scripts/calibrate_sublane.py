"""
Phase 3 -- two-wheeler sublane behaviour calibration (PLAN.md Phase 3,
prompts/phase3_sublane.md).

Tests whether SUMO's SL2015 sublane lane-changing model reproduces Indian
two-wheeler gap-filling: released from a mixed standing queue (built at
real fleet shares on scripts/calibrate.py's own single-signalised-cross
testbed), do two-wheelers cross the stop line sooner (lower crossing rank)
than cars, despite starting mixed in with them rather than segregated to
the front?

Reuses scripts/calibrate.py::build_network directly (identical topology
requirement -- one signalised cross, saturate the west approach). Does NOT
reuse SaturationRun's measurement logic, which only ever aggregates by
class; this needs per-vehicle crossing order.

Tunable ONLY: lat_alignment, lc_sublane (existing), lc_pushy, lc_assertive,
lc_accel_lat (new, real SL2015 vType attributes). NEVER length, width,
min_gap, or min_gap_lat -- all four feed a_v = (L+g)(W+g_lat) [Eq. 3] and
would silently move pi/beta/epsilon*/Table III and both C1/C2 calibration
results (PAPER_CHANGELOG P1c-7).

Usage
-----
    python -m scripts.calibrate_sublane
    python -m scripts.calibrate_sublane --quick
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.calibrate import build_network  # noqa: E402
from src.hap import Fleet  # noqa: E402

try:
    import libsumo as traci  # type: ignore
except ImportError:  # pragma: no cover
    import traci  # type: ignore

# cfg["fleet"][<key>] (per-class dict, same shape as lat_alignment/
# lc_sublane) -> SL2015 vType attribute name. Only emitted when a class has
# an explicit value -- omitted (not defaulted) otherwise, so SUMO's own
# built-in default applies untouched.
LC_ATTR_KEYS = {
    "lc_pushy": "lcPushy",
    "lc_assertive": "lcAssertive",
    "lc_accel_lat": "lcAccelLat",
}


def _vtypes_xml_tunable(fleet: Fleet, cfg: dict, lane_change_model: str = "SL2015") -> str:
    """Like scripts.calibrate._vtypes_xml, but the lane-change model is
    swappable (for the SL2015-vs-default runtime comparison) and emits the
    new lc_pushy/lc_assertive/lc_accel_lat knobs when configured. Sublane-
    specific attributes are only emitted under SL2015 -- LC2013 doesn't
    understand them."""
    rows = []
    for name, c in fleet.classes.items():
        sublane_attrs = ""
        if lane_change_model == "SL2015":
            lat = cfg["fleet"]["lat_alignment"]
            lcs = cfg["fleet"]["lc_sublane"]
            sublane_attrs = (
                f' latAlignment="{lat.get(name, "center")}" '
                f'lcSublane="{lcs.get(name, 0.5)}"'
            )
            for cfg_key, attr in LC_ATTR_KEYS.items():
                val = cfg["fleet"].get(cfg_key, {}).get(name)
                if val is not None:
                    sublane_attrs += f' {attr}="{val}"'
        rows.append(
            f'  <vType id="{name}" vClass="{c.sumo_class}" '
            f'length="{c.length}" width="{c.width}" '
            f'minGap="{c.min_gap}" minGapLat="{c.min_gap_lat}" '
            f'maxSpeed="{c.max_speed_ms:.3f}" accel="{c.accel}" '
            f'decel="{c.decel}" sigma="0.5"'
            f'{sublane_attrs} '
            f'carFollowModel="Krauss" laneChangeModel="{lane_change_model}"/>'
        )
    return "\n".join(rows)


def _routes_xml_queue(
    fleet: Fleet, shares: Dict[str, float], cfg: dict,
    total_veh_per_hour: float, red_s: int, lane_change_model: str = "SL2015",
) -> str:
    """Over-capacity flow, insertion window = [0, red_s] only -- every
    vehicle inserts during the red hold, none after release, so the
    released queue is a clean, bounded set (mirrors
    scripts.calibrate._routes_xml's over-capacity mechanism)."""
    flows = []
    for name, share in shares.items():
        if share <= 0:
            continue
        flows.append(
            f'  <flow id="f_{name}" type="{name}" route="wce" begin="0" '
            f'end="{red_s}" vehsPerHour="{total_veh_per_hour * share:.1f}" '
            f'departPos="last" departSpeed="0" departLane="random"/>'
        )
    return (
        '<routes>\n'
        + _vtypes_xml_tunable(fleet, cfg, lane_change_model)
        + '\n  <route id="wce" edges="wc ce"/>\n'
        + "\n".join(flows)
        + "\n</routes>\n"
    )


class QueueReleaseRun:
    """Holds red for red_s to load a mixed queue, then releases green for
    up to green_s and tracks each vehicle's crossing rank (0-indexed order
    of first appearance on OUT_EDGE) by class -- same direct
    setRedYellowGreenState control as scripts.calibrate.SaturationRun,
    adapted for per-vehicle order instead of aggregate counts."""

    IN_EDGE, OUT_EDGE, TLS = "wc", "ce", "c"

    def __init__(self, net: Path, routes: Path, cfg: dict, red_s: int = 60,
                 green_s: int = 150, seed: int = 0, gui: bool = False,
                 sublane_simulation: bool = True):
        self.red_s, self.green_s = red_s, green_s
        self.sumo_cmd = [
            "sumo-gui" if gui else "sumo",
            "-n", str(net), "-r", str(routes),
            "--step-length", str(cfg["signal"]["sim_step_s"]),
            "--time-to-teleport", "-1",
            "--no-warnings", "true",
            "--no-step-log", "true",
            "--seed", str(seed),
            "--default.carfollowmodel", "Krauss",
        ]
        if sublane_simulation:
            # SUMO's sublane simulation infrastructure (continuous lateral
            # position) is opt-in via --lateral-resolution, and once on,
            # EVERY vType in the simulation must use a sublane-compatible
            # model -- LC2013 (the classical default) raises a fatal error
            # under it ("not compatible with sublane simulation"). So the
            # SL2015-vs-default runtime comparison must run LC2013 WITHOUT
            # this flag at all, not merely swap the vType's model name.
            self.sumo_cmd += ["--lateral-resolution", str(cfg["signal"]["lateral_resolution_m"])]

    def _states(self):
        links = traci.trafficlight.getControlledLinks(self.TLS)
        green, allred = [], []
        for grp in links:
            is_west = bool(grp) and grp[0][0].startswith(self.IN_EDGE + "_")
            green.append("G" if is_west else "r")
            allred.append("r")
        return "".join(green), "".join(allred)

    def run(self) -> Dict[str, List[int]]:
        """Returns {class_name: [crossing_rank, ...]}."""
        traci.start(self.sumo_cmd)
        try:
            green_state, red_state = self._states()
            for _ in range(self.red_s):
                traci.trafficlight.setRedYellowGreenState(self.TLS, red_state)
                traci.simulationStep()

            traci.trafficlight.setRedYellowGreenState(self.TLS, green_state)
            seen: set = set()
            order: List[Tuple[str, int]] = []
            for _ in range(self.green_s):
                traci.simulationStep()
                for vid in traci.edge.getLastStepVehicleIDs(self.OUT_EDGE):
                    if vid not in seen:
                        seen.add(vid)
                        order.append((traci.vehicle.getTypeID(vid), len(order)))
                if traci.simulation.getMinExpectedNumber() <= 0:
                    break

            ranks: Dict[str, List[int]] = {}
            for cls, rank in order:
                ranks.setdefault(cls, []).append(rank)
            return ranks
        finally:
            traci.close()


def run_queue_release(
    cfg: dict, fleet: Fleet, workdir: Path, lane_change_model: str = "SL2015",
    red_s: int = 60, green_s: int = 150, total_veh_per_hour: float = 20000.0,
    seed: int = 0,
) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    net = build_network(workdir, cfg)
    shares = {n: c.share for n, c in fleet.classes.items()}
    routes = workdir / f"queue_{lane_change_model}_{seed}.rou.xml"
    routes.write_text(_routes_xml_queue(fleet, shares, cfg, total_veh_per_hour, red_s, lane_change_model))

    t0 = time.perf_counter()
    ranks = QueueReleaseRun(
        net, routes, cfg, red_s=red_s, green_s=green_s, seed=seed,
        sublane_simulation=(lane_change_model == "SL2015"),
    ).run()
    wall_clock_s = time.perf_counter() - t0

    mean_rank = {cls: sum(r) / len(r) for cls, r in ranks.items() if r}
    n_vehicles = {cls: len(r) for cls, r in ranks.items()}
    return {"mean_rank": mean_rank, "n_vehicles": n_vehicles, "wall_clock_s": wall_clock_s}


# --------------------------------------------------------------------------


def _print_result(label: str, result: dict) -> None:
    mr, n = result["mean_rank"], result["n_vehicles"]
    print(f"  {label}: n={n}  wall_clock={result['wall_clock_s']:.2f}s")
    for cls in sorted(mr, key=lambda c: mr[c]):
        print(f"    {cls:12s} mean_rank={mr[cls]:7.2f}  n={n.get(cls, 0)}")
    if "twowheeler" in mr and "car" in mr:
        gap = mr["car"] - mr["twowheeler"]
        verdict = "2W ahead of car" if gap > 0 else "2W behind car"
        print(f"    -> twowheeler vs car: gap={gap:+.2f}  ({verdict})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quick", action="store_true", help="shorter red/green hold -- smoke test only")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    fleet = Fleet.from_config(cfg)
    red_s = 30 if args.quick else 60
    green_s = 90 if args.quick else 150

    with tempfile.TemporaryDirectory(prefix="haplight_sublane_") as td:
        workdir = Path(td)
        print("Baseline (current configs/default.yaml lane-change settings):")
        baseline = run_queue_release(cfg, fleet, workdir, "SL2015", red_s, green_s, seed=args.seed)
        _print_result("SL2015 (current config)", baseline)

        print("\nRuntime comparison, SAME queue, SL2015 vs LC2013 (default):")
        lc2013 = run_queue_release(cfg, fleet, workdir, "LC2013", red_s, green_s, seed=args.seed)
        _print_result("LC2013 (default)", lc2013)
        ratio = baseline["wall_clock_s"] / lc2013["wall_clock_s"] if lc2013["wall_clock_s"] else float("nan")
        print(f"\n  SL2015/LC2013 wall-clock ratio = {ratio:.2f}x (PLAN.md budget: 2-4x)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
