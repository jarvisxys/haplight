"""
Calibration experiments C1 and C2  (paper Sec. VII-A).

RUN THIS BEFORE ANYTHING ELSE. It tests the two empirical claims the rest of
the paper is conditional on. If C2 fails, Theorem 1 must be restated as
conditional and the paper's framing changes -- you want to know that on day
two, not after four weeks of training runs.

    C1  Realised area-estimator error.
        Logs x_hat_area / x over a real standing queue and compares the
        measured distribution against the Lemma 1 prediction:
            support in [beta_min/a_bar, beta_max/a_bar]
            = [0.550, 1.450] under Indo-HCM weights
            = {1.000} exactly under area weights
        Produces Table VIII of the paper.

    C2  Composition invariance of saturation flow (Assumption A5).
        Sweeps the two-wheeler share 0 -> 70% on a saturated approach and
        measures discharge in three unit systems. A5 predicts the weighted
        columns are flat and vehicles/s is not.
        Produces Table IX of the paper, and the calibrated value of
        hap.saturation_flow.per_metre_width.

This script is deliberately standalone: it builds its own SUMO network and
does not import src/env.py, so it can run before the environment exists.

Usage
-----
    python scripts/calibrate.py --config configs/default.yaml --out results/
    python scripts/calibrate.py --only c2 --quick        # fast smoke test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.hap import (  # noqa: E402
    Fleet,
    occupied_area,
    weighted_queue_from_area,
    weighted_queue_from_counts,
)

# --------------------------------------------------------------------------
# SUMO bootstrap: prefer libsumo (2-3x faster, no socket), fall back to traci
# --------------------------------------------------------------------------

def _ensure_sumo_on_path() -> None:
    """Also needed for the `netconvert` subprocess call in build_network()
    below -- SUMO_HOME alone (used just below for the traci/libsumo tools
    import) doesn't put netconvert.exe on PATH. Mirrors
    scripts/build_nets.py::_ensure_sumo_on_path exactly."""
    candidates: List[Path] = []
    if os.environ.get("SUMO_HOME"):
        candidates.append(Path(os.environ["SUMO_HOME"]))
    try:
        import sumo as _sumo_pkg  # type: ignore

        candidates.append(Path(_sumo_pkg.__file__).resolve().parent)
    except ImportError:
        pass

    for c in candidates:
        if (c / "tools").is_dir():
            os.environ["PATH"] = str(c / "bin") + os.pathsep + os.environ.get("PATH", "")
            os.environ["SUMO_HOME"] = str(c)
            return


_ensure_sumo_on_path()

if "SUMO_HOME" in os.environ:
    tools = Path(os.environ["SUMO_HOME"]) / "tools"
    if tools.is_dir():
        sys.path.insert(0, str(tools))

try:
    import libsumo as traci  # type: ignore
    _BACKEND = "libsumo"
except ImportError:  # pragma: no cover
    try:
        import traci  # type: ignore
        _BACKEND = "traci"
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Neither libsumo nor traci importable.\n"
            "Set SUMO_HOME and add $SUMO_HOME/tools to PYTHONPATH, or\n"
            "  pip install eclipse-sumo\n"
            f"(underlying error: {exc})"
        )


# --------------------------------------------------------------------------
# Network construction: one signalised cross, we saturate the west approach
# --------------------------------------------------------------------------

NODES_XML = """<nodes>
  <node id="c" x="0"    y="0"    type="traffic_light"/>
  <node id="w" x="-700" y="0"    type="priority"/>
  <node id="e" x="400"  y="0"    type="priority"/>
  <node id="n" x="0"    y="400"  type="priority"/>
  <node id="s" x="0"    y="-400" type="priority"/>
</nodes>
"""


def _edges_xml(lanes: int, width: float, speed: float) -> str:
    rows = []
    for a, b in [("w", "c"), ("c", "e"), ("n", "c"), ("c", "s"),
                 ("e", "c"), ("c", "w"), ("s", "c"), ("c", "n")]:
        rows.append(
            f'  <edge id="{a}{b}" from="{a}" to="{b}" numLanes="{lanes}" '
            f'width="{width}" speed="{speed}"/>'
        )
    return "<edges>\n" + "\n".join(rows) + "\n</edges>\n"


def _vtypes_xml(fleet: Fleet, cfg: dict) -> str:
    lat = cfg["fleet"]["lat_alignment"]
    lcs = cfg["fleet"]["lc_sublane"]
    rows = []
    for name, c in fleet.classes.items():
        rows.append(
            f'  <vType id="{name}" vClass="{c.sumo_class}" '
            f'length="{c.length}" width="{c.width}" '
            f'minGap="{c.min_gap}" minGapLat="{c.min_gap_lat}" '
            f'maxSpeed="{c.max_speed_ms:.3f}" accel="{c.accel}" '
            f'decel="{c.decel}" sigma="0.5" '
            f'latAlignment="{lat.get(name, "center")}" '
            f'lcSublane="{lcs.get(name, 0.5)}" '
            f'carFollowModel="Krauss" laneChangeModel="SL2015"/>'
        )
    return "\n".join(rows)


def _routes_xml(fleet: Fleet, shares: Dict[str, float], cfg: dict,
                total_veh_per_hour: float, end_s: int) -> str:
    """
    Flow is set far above capacity on purpose: SUMO inserts as fast as space
    allows, which guarantees the approach stays saturated for the whole
    measurement window. Insertion is the natural throttle.
    """
    flows = []
    for i, (name, share) in enumerate(shares.items()):
        if share <= 0:
            continue
        flows.append(
            f'  <flow id="f_{name}" type="{name}" route="wce" begin="0" '
            f'end="{end_s}" vehsPerHour="{total_veh_per_hour * share:.1f}" '
            f'departPos="last" departSpeed="0" departLane="random"/>'
        )
    return (
        '<routes>\n'
        + _vtypes_xml(fleet, cfg)
        + '\n  <route id="wce" edges="wc ce"/>\n'
        + "\n".join(flows)
        + "\n</routes>\n"
    )


def build_network(workdir: Path, cfg: dict, lanes: int = 3,
                  lane_width: float = 3.5) -> Path:
    """netconvert a single signalised cross. Returns the .net.xml path."""
    (workdir / "n.nod.xml").write_text(NODES_XML)
    (workdir / "n.edg.xml").write_text(_edges_xml(lanes, lane_width, 13.89))
    net = workdir / "calib.net.xml"
    cmd = [
        "netconvert",
        "-n", str(workdir / "n.nod.xml"),
        "-e", str(workdir / "n.edg.xml"),
        "-o", str(net),
        "--no-turnarounds", "true",
        "--tls.default-type", "static",
        "--lefthand", "true",          # India drives on the left
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not net.exists():
        raise RuntimeError(f"netconvert failed:\n{res.stdout}\n{res.stderr}")
    return net


# --------------------------------------------------------------------------
# Simulation driver
# --------------------------------------------------------------------------


class SaturationRun:
    """
    Drives one saturated-approach experiment.

    The signal is controlled directly through setRedYellowGreenState rather
    than by parsing the generated TLS program: we build the state string from
    getControlledLinks, so the code is robust to whatever phase layout
    netconvert happens to produce.
    """

    IN_EDGE, OUT_EDGE, TLS = "wc", "ce", "c"

    def __init__(self, net: Path, routes: Path, cfg: dict, fleet: Fleet,
                 red_s: int = 90, green_s: int = 45, cycles: int = 3,
                 startup_lost_s: int = 6, seed: int = 0, gui: bool = False):
        self.cfg, self.fleet = cfg, fleet
        self.red_s, self.green_s, self.cycles = red_s, green_s, cycles
        self.startup_lost_s = startup_lost_s
        self.sumo_cmd = [
            "sumo-gui" if gui else "sumo",
            "-n", str(net), "-r", str(routes),
            "--step-length", str(cfg["signal"]["sim_step_s"]),
            "--lateral-resolution", str(cfg["signal"]["lateral_resolution_m"]),
            "--time-to-teleport", "-1",
            "--no-warnings", "true",
            "--no-step-log", "true",
            "--seed", str(seed),
            "--default.carfollowmodel", "Krauss",
        ]

    # -- signal control ---------------------------------------------------

    def _states(self):
        links = traci.trafficlight.getControlledLinks(self.TLS)
        green, allred = [], []
        for grp in links:
            is_west = bool(grp) and grp[0][0].startswith(self.IN_EDGE + "_")
            green.append("G" if is_west else "r")
            allred.append("r")
        return "".join(green), "".join(allred)

    # -- main loop --------------------------------------------------------

    def run(self) -> dict:
        traci.start(self.sumo_cmd)
        try:
            green_state, red_state = self._states()
            seen_out, discharged, queue_ratios = set(), [], []
            queue_emptied = False
            measured_steps = 0
            step = 0
            cycle_len = self.red_s + self.green_s

            for _ in range(self.cycles * cycle_len):
                phase_t = step % cycle_len
                in_green = phase_t >= self.red_s
                traci.trafficlight.setRedYellowGreenState(
                    self.TLS, green_state if in_green else red_state
                )
                traci.simulationStep()
                step += 1

                # --- C1: composition of the standing queue during red ------
                if not in_green and phase_t > 10:
                    counts = self._queue_counts()
                    if sum(counts.values()) >= 5:
                        queue_ratios.append(self._area_ratio(counts))

                # --- C2: discharge during the steady part of green ---------
                if in_green:
                    green_t = phase_t - self.red_s
                    crossed = self._new_crossings(seen_out)
                    if green_t >= self.startup_lost_s:
                        if self._queue_counts():
                            discharged.extend(crossed)
                            measured_steps += 1
                        else:
                            # Queue drained: from here on we would be
                            # measuring the arrival rate, not the saturation
                            # flow. Stop counting this green.
                            queue_emptied = True
                    if green_t >= self.green_s - 1:
                        seen_out.clear()

            measured_s = max(1.0, measured_steps * self.cfg["signal"]["sim_step_s"])
            return {
                "discharge": self._summarise(discharged, measured_s),
                "queue_ratios": queue_ratios,
                "queue_emptied": queue_emptied,
                "n_discharged": len(discharged),
                "measured_s": measured_s,
            }
        finally:
            traci.close()

    # -- measurement helpers ----------------------------------------------

    def _queue_counts(self) -> Dict[str, float]:
        thr = self.cfg["hap"]["stop_speed_threshold_ms"]
        counts: Dict[str, float] = {}
        for vid in traci.edge.getLastStepVehicleIDs(self.IN_EDGE):
            if traci.vehicle.getSpeed(vid) < thr:
                t = traci.vehicle.getTypeID(vid)
                counts[t] = counts.get(t, 0.0) + 1.0
        return counts

    def _new_crossings(self, seen: set) -> List[str]:
        out = []
        for vid in traci.edge.getLastStepVehicleIDs(self.OUT_EDGE):
            if vid not in seen:
                seen.add(vid)
                out.append(traci.vehicle.getTypeID(vid))
        return out

    def _area_ratio(self, counts: Dict[str, float]) -> float:
        x_true = weighted_queue_from_counts(self.fleet, counts)
        if x_true <= 0:
            return float("nan")
        area = occupied_area(self.fleet, counts)
        return weighted_queue_from_area(self.fleet, area) / x_true

    def _summarise(self, types: List[str], seconds: float) -> Dict[str, float]:
        """Discharge rate in three unit systems -- the heart of C2."""
        counts: Dict[str, float] = {}
        for t in types:
            counts[t] = counts.get(t, 0.0) + 1.0
        hcm = Fleet(list(self.fleet.classes.values()), weight_scheme="hcm")
        area_f = Fleet(list(self.fleet.classes.values()), weight_scheme="area")
        return {
            "veh_per_s": len(types) / seconds,
            "hcm_pcu_per_s": weighted_queue_from_counts(hcm, counts) / seconds,
            "area_units_per_s": weighted_queue_from_counts(area_f, counts) / seconds,
        }


# --------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------


def sweep_shares(fleet: Fleet, tw_share: float) -> Dict[str, float]:
    """Set the two-wheeler share, redistributing the rest proportionally."""
    others = {n: c.share for n, c in fleet.classes.items()
              if not n.startswith("two")}
    tot = sum(others.values())
    shares = {n: (1.0 - tw_share) * s / tot for n, s in others.items()}
    for n in fleet.classes:
        if n.startswith("two"):
            shares[n] = tw_share
    return shares


def run_c2(cfg: dict, fleet: Fleet, workdir: Path, quick: bool) -> dict:
    """Assumption A5: is discharge composition-invariant in weighted units?"""
    net = build_network(workdir, cfg)
    tw_grid = [0.0, 0.35, 0.7] if quick else [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    cycles = 1 if quick else 3
    rows = []

    for tw in tw_grid:
        shares = sweep_shares(fleet, tw)
        routes = workdir / f"c2_{int(tw*100)}.rou.xml"
        routes.write_text(_routes_xml(fleet, shares, cfg, 20000.0, 3600))
        run = SaturationRun(net, routes, cfg, fleet, cycles=cycles)
        out = run.run()
        sat_frac = out["measured_s"] / (cycles * (run.green_s - run.startup_lost_s))
        row = {"tw_share": tw, **out["discharge"],
               "n_discharged": out["n_discharged"],
               "saturated_fraction": sat_frac,
               "queue_emptied": out["queue_emptied"]}
        rows.append(row)
        print(f"  2W={tw:4.0%}  veh/s={row['veh_per_s']:6.3f}  "
              f"HCM-PCU/s={row['hcm_pcu_per_s']:6.3f}  "
              f"area/s={row['area_units_per_s']:6.3f}"
              + f"  sat={sat_frac:5.1%}"
              + ("  [WARN under-saturated]" if sat_frac < 0.9 else ""))

    def cv(key: str) -> float:
        v = np.array([r[key] for r in rows], dtype=float)
        return float(100.0 * v.std() / v.mean()) if v.mean() > 0 else float("nan")

    summary = {u: {"min": min(r[u] for r in rows),
                   "max": max(r[u] for r in rows),
                   "cv_pct": cv(u)}
               for u in ("veh_per_s", "hcm_pcu_per_s", "area_units_per_s")}

    a5_supported = (
        summary["area_units_per_s"]["cv_pct"] < 0.5 * summary["veh_per_s"]["cv_pct"]
        or summary["hcm_pcu_per_s"]["cv_pct"] < 0.5 * summary["veh_per_s"]["cv_pct"]
    )
    return {"rows": rows, "summary": summary, "a5_supported": bool(a5_supported)}


def run_c1(cfg: dict, workdir: Path, quick: bool) -> dict:
    """Realised area-estimator error under both weight schemes."""
    out = {}
    for scheme in ("hcm", "area"):
        fleet = Fleet.from_config(cfg, weight_scheme=scheme)
        net = build_network(workdir, cfg)
        routes = workdir / f"c1_{scheme}.rou.xml"
        shares = {n: c.share for n, c in fleet.classes.items()}
        routes.write_text(_routes_xml(fleet, shares, cfg, 20000.0, 3600))
        run = SaturationRun(net, routes, cfg, fleet,
                            cycles=1 if quick else 3)
        r = np.array([x for x in run.run()["queue_ratios"] if np.isfinite(x)])
        lo, hi = fleet.lemma1_bounds()
        out[scheme] = {
            "n_samples": int(r.size),
            "p1": float(np.percentile(r, 1)) if r.size else None,
            "p25": float(np.percentile(r, 25)) if r.size else None,
            "median": float(np.median(r)) if r.size else None,
            "p75": float(np.percentile(r, 75)) if r.size else None,
            "p99": float(np.percentile(r, 99)) if r.size else None,
            "measured_epsilon": float(np.max(np.abs(r - 1.0))) if r.size else None,
            "lemma1_bounds": [lo, hi],
            "epsilon_star": fleet.epsilon_star,
            "bound_respected": bool(
                r.size and (r.min() >= lo - 1e-9) and (r.max() <= hi + 1e-9)
            ),
        }
        s = out[scheme]
        print(f"  {scheme:5s}  median={s['median']:.4f}  "
              f"P1={s['p1']:.4f}  P99={s['p99']:.4f}  "
              f"eps_measured={s['measured_epsilon']:.4f}  "
              f"eps*={s['epsilon_star']:.4f}  "
              f"bound_ok={s['bound_respected']}")
    return out


def derive_design_constants(results: dict, cfg: dict) -> dict:
    """
    Turn the raw C1/C2 measurements into the two constants the paper needs,
    and into the weight-vector decision.

      a_bar_calibrated : recentre the area estimator on the REALISED
                         composition. The residual uniform offset is free
                         (Remark 3); only the dispersion is charged.
      nu               : size of the A5 violation. It enters the Lyapunov
                         drift exactly as the sensing error eps does, so the
                         certified-capacity loss is ~ c*(eps + nu) and the
                         weight vector should be chosen to minimise the sum.
    """
    out = {}

    if "c1" in results:
        for scheme, r in results["c1"].items():
            med = r["median"]
            fleet = Fleet.from_config(cfg, weight_scheme=scheme)
            a_bar_cal = fleet.a_bar_star * med
            lo, hi = r["p1"] / med, r["p99"] / med
            out[scheme] = {
                "a_bar_star": fleet.a_bar_star,
                "a_bar_calibrated": a_bar_cal,
                "eps_worstcase": fleet.epsilon_star,
                "eps_measured_minimax": r["measured_epsilon"],
                "eps_calibrated": max(abs(1 - lo), abs(hi - 1)),
            }

    if "c2" in results:
        rows = results["c2"]["rows"]
        for unit, key in (("hcm", "hcm_pcu_per_s"), ("area", "area_units_per_s"),
                          ("count", "veh_per_s")):
            v = np.array([r[key] for r in rows], dtype=float)
            nu = float(max(abs(v.max() - v.mean()), abs(v.min() - v.mean())) / v.mean())
            out.setdefault(unit, {})["nu_a5"] = nu
            out[unit]["mu_mean"] = float(v.mean())
        out["fitted_2w_discharge_equivalency"] = _fit_2w(rows, cfg)

    for scheme in ("hcm", "area"):
        d = out.get(scheme, {})
        if "eps_calibrated" in d and "nu_a5" in d:
            d["total_capacity_loss"] = d["eps_calibrated"] + d["nu_a5"]
    return out


def _fit_2w(rows, cfg) -> dict:
    """
    Which two-wheeler weight makes saturation discharge composition-invariant?

    Only the 2W share varies in the sweep, so exactly one parameter is
    identifiable; the other classes stay at their Indo-HCM values.
    """
    fleet = Fleet.from_config(cfg, weight_scheme="hcm")
    others = {n: c.share for n, c in fleet.classes.items() if not n.startswith("two")}
    tot = sum(others.values())
    rho_o = {n: fleet.classes[n].rho_hcm for n in others}

    def cv(r2w: float) -> float:
        vals = []
        for row in rows:
            tw = row["tw_share"]
            mean_rho = tw * r2w + sum(
                (1 - tw) * others[n] / tot * rho_o[n] for n in others
            )
            vals.append(row["veh_per_s"] * mean_rho)
        v = np.array(vals)
        return float(v.std() / v.mean())

    grid = np.arange(0.05, 1.501, 0.001)
    best = float(grid[int(np.argmin([cv(r) for r in grid]))])
    return {"rho_2w_fitted": best, "cv_at_fit_pct": 100 * cv(best),
            "cv_at_indohcm_0.5_pct": 100 * cv(0.5),
            "cv_at_area_0.228_pct": 100 * cv(0.228)}


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--out", default="results")
    ap.add_argument("--only", choices=["c1", "c2"], default=None)
    ap.add_argument("--red", type=int, default=90)
    ap.add_argument("--green", type=int, default=45)
    ap.add_argument("--quick", action="store_true",
                    help="coarse grid, 1 cycle -- smoke test only")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    fleet = Fleet.from_config(cfg)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"SUMO backend: {_BACKEND}")
    print(f"Fleet: {fleet}\n")

    results = {"backend": _BACKEND, "quick": args.quick}
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        if args.only in (None, "c1"):
            print("C1: realised area-estimator error")
            results["c1"] = run_c1(cfg, workdir, args.quick)
            print()
        if args.only in (None, "c2"):
            print("C2: composition invariance of saturation flow (A5)")
            results["c2"] = run_c2(cfg, fleet, workdir, args.quick)
            print()

    results["derived"] = derive_design_constants(results, cfg)
    d = results["derived"]
    print("--- derived design constants " + "-" * 36)
    for scheme in ("hcm", "area"):
        if scheme in d and "eps_calibrated" in d[scheme]:
            v = d[scheme]
            print(f"  {scheme:5s} a_bar: {v['a_bar_star']:.3f} (minimax) -> "
                  f"{v['a_bar_calibrated']:.3f} (calibrated)")
            print(f"        eps: {v['eps_worstcase']:.3f} (worst) -> "
                  f"{v['eps_measured_minimax']:.3f} (measured) -> "
                  f"{v['eps_calibrated']:.3f} (calibrated)")
            if "total_capacity_loss" in v:
                print(f"        nu(A5)={v['nu_a5']:.4f}   "
                      f"TOTAL eps+nu = {v['total_capacity_loss']:.4f}")
    if "fitted_2w_discharge_equivalency" in d:
        f = d["fitted_2w_discharge_equivalency"]
        print(f"  fitted 2W discharge equivalency = {f['rho_2w_fitted']:.3f}  "
              f"(CV {f['cv_at_fit_pct']:.2f}%)")
        print(f"        Indo-HCM 0.500 -> CV {f['cv_at_indohcm_0.5_pct']:.2f}%   "
              f"area 0.228 -> CV {f['cv_at_area_0.228_pct']:.2f}%")
    best = min((s for s in ("hcm", "area") if "total_capacity_loss" in d.get(s, {})),
               key=lambda s: d[s]["total_capacity_loss"], default=None)
    if args.quick:
        print("  !! --quick uses a 3-point grid, which is TOO COARSE to decide")
        print("     the weight vector. Re-run without --quick before changing")
        print("     configs/default.yaml.")
    if best:
        print(f"  => set fleet.weight_scheme: {best}  "
              f"and fleet.a_bar_calibrated.{best}: "
              f"{d[best]['a_bar_calibrated']:.3f}")
    print()

    path = outdir / "calibration.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"Written: {path}")

    if "c2" in results:
        s = results["c2"]["summary"]
        print("\n--- A5 verdict " + "-" * 50)
        for unit, v in s.items():
            print(f"  {unit:20s} CV = {v['cv_pct']:6.2f}%   "
                  f"[{v['min']:.3f}, {v['max']:.3f}]")
        if results["c2"]["a5_supported"]:
            print("  A5 SUPPORTED: weighted discharge is materially flatter "
                  "than vehicle counts.")
        else:
            print("  *** A5 NOT SUPPORTED ***")
            print("  Theorem 1 must be restated as conditional. Report this "
                  "honestly in Sec. IX;\n  do not proceed as if the "
                  "assumption held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
