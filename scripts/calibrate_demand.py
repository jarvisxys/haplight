"""
Demand calibration (Phase 1b, see PLAN.md / PAPER_CHANGELOG.md P1-8).

RUN scripts/build_nets.py FIRST -- this reuses the net files it produces
(netconvert only ever runs once per scenario here; regenerating a whole net
per swept demand scale would be needless and slow, since topology doesn't
depend on demand).

Two independent things live in this one script because they share all their
plumbing (net reuse, route regeneration, GreedyHAP episode running):

  capacity sweep (default)   Sweep a global demand scale under GreedyHAP,
      locate the throughput plateau -- the empirical boundary of the
      weighted capacity region Lambda in Assumption A3 -- and write
      demand.scale_nominal (v/c~0.85), demand.scale_surge (v/c~1.05) and
      demand.capacity_veh_per_h back into configs/default.yaml, per
      scenario (S1 and S2 have materially different capacities).

  --dispersion-sweep         At demand.scale_nominal on S1, sweep
      composition_dispersion in {0, 0.25, 0.5, 0.75, 1.0} and report
      Greedy HAP vs MaxPressure ATT/AQL/PWD/2W-wait and their decision
      disagreement rate, plus the input vs. *measured*
      metrics.composition_dispersion (they can diverge -- see the
      docstring on that function) and the per-OD / per-movement class
      composition tables at d=1.

Usage
-----
    python scripts/calibrate_demand.py                     # capacity sweep, both scenarios
    python scripts/calibrate_demand.py --quick              # coarse/fast smoke test
    python scripts/calibrate_demand.py --scenario s1
    python scripts/calibrate_demand.py --dispersion-sweep
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_nets import (  # noqa: E402
    _edges_xml,
    _nodes_xml,
    _od_pairs,
    _PEAK_MULTIPLIERS,
    _routes_xml,
    _sumocfg_xml,
    _vtype_distribution_xml,
    build_topology,
    classify_od_pairs,
    netconvert_build,
    od_class_shares,
)
from src import metrics  # noqa: E402
from src.controllers import GreedyHAP  # noqa: E402
from src.env import HAPLightEnv  # noqa: E402
from src.hap import Fleet  # noqa: E402

DEFAULT_BASE_VEH_PER_HOUR = 300.0

# Bengaluru-specific (PAPER_CHANGELOG P4c-16): S1's 300 veh/h is a per-OD-
# pair rate calibrated for S1/S2's COARSE, zone-level entry/exit stubs (12
# total for S1). Bengaluru's leaf-node OD pairs are two orders of
# magnitude more numerous (975) because they represent individual
# residential streets, not aggregate zones -- applying 300 veh/h to each
# of 975 pairs produced 131,625 veh/h offered at the LOWEST tested scale
# (confirmed directly), which gridlocked the simulation so severely it
# made ~635s of progress in 20 hours before being killed. Scaled down by
# the same ratio (300 * 12/975 ~= 3.7, rounded to a plausible quiet-
# residential-street volume) rather than chasing a smaller `scale` value
# in the same mismatched formula.
BENGALURU_BASE_VEH_PER_HOUR = 4.0

SCENARIOS = {
    "s1_arterial": "arterial5",
    "s2_grid": "grid4x4",
}


# --------------------------------------------------------------------------
# Scenario/topology setup (net reused from scripts/build_nets.py's output;
# netconvert runs at most once per scenario here, only if that net is
# missing)
# --------------------------------------------------------------------------


def _scenario_dims(scenario_key: str, cfg: dict) -> Tuple[int, int, float]:
    if scenario_key == "s1_arterial":
        s = cfg["scenarios"]["s1_arterial"]
        return 1, s["n_intersections"], s["spacing_m"]
    s = cfg["scenarios"]["s2_grid"]
    return s["rows"], s["cols"], s["spacing_m"]


def _prepare_net(scenario_key: str, cfg: dict, nets_dir: Path, workdir: Path):
    """Reuses nets/<scenario>/<scenario>.net.xml if it exists (built by
    scripts/build_nets.py); otherwise builds it once into workdir. Returns
    (nodes, edges, entry_edges, exit_edges, net_path)."""
    name = SCENARIOS[scenario_key]
    rows, cols, spacing = _scenario_dims(scenario_key, cfg)
    nodes, edges, entry_edges, exit_edges = build_topology(rows, cols, spacing, stub_len=spacing)

    existing = nets_dir / name / f"{name}.net.xml"
    if existing.exists():
        return nodes, edges, entry_edges, exit_edges, existing

    print(f"  (no {existing} -- run scripts/build_nets.py first; building a throwaway net)")
    net_path = workdir / f"{name}.net.xml"
    netconvert_build(workdir, _nodes_xml(nodes), _edges_xml(edges, 3, 3.5, 13.89), net_path, True)
    return nodes, edges, entry_edges, exit_edges, net_path


def prepare_net_bengaluru(net_path: Path):
    """The real-OSM-network analogue of _prepare_net/build_topology
    (PAPER_CHANGELOG P4c-16) -- Bengaluru has no entry/exit stub
    convention (that's a synthetic-grid construction), so entry/exit
    points are discovered from the ALREADY-PRUNED network's own topology
    instead: a "leaf" node is a one-hop feeder's far endpoint, connected
    to the rest of the network by exactly one bidirectional edge pair
    (in-degree=1, out-degree=1, both to/from the same neighbour) -- this
    is precisely what `compute_feeder_keep_list`'s one-feeder-layer prune
    was designed to produce (P4c-16's earlier entry/exit connectivity
    check), so reusing that same structure for OD entry/exit points is
    not a new assumption, just reading back what the network build
    already established. The edge INTO a leaf is a candidate exit (a
    trip ending on that local street); the edge OUT of a leaf is a
    candidate entry (a trip originating there). Returns
    (nodes, edges, entry_edges, exit_edges) in build_topology's own
    dict/list format so classify_od_pairs/_od_pairs work unchanged."""
    import sumolib

    net = sumolib.net.readNet(str(net_path), withPrograms=True)

    nodes: Dict[str, Tuple[float, float, str]] = {}
    for n in net.getNodes():
        x, y = n.getCoord()
        typ = "traffic_light" if n.getType() == "traffic_light" else "priority"
        nodes[n.getID()] = (x, y, typ)

    edges: Dict[str, Tuple[str, str]] = {}
    for e in net.getEdges():
        edges[e.getID()] = (e.getFromNode().getID(), e.getToNode().getID())

    leaf_pairs: List[Tuple[str, str]] = []  # (exit_edge, entry_edge) per leaf node
    for n in net.getNodes():
        inc, out = n.getIncoming(), n.getOutgoing()
        if len(inc) == 1 and len(out) == 1 and inc[0].getFromNode().getID() == out[0].getToNode().getID():
            leaf_pairs.append((inc[0].getID(), out[0].getID()))

    # Connectivity filter: _od_pairs (build_nets.py) zips entry_edges with a
    # ROTATED exit_edges list, i.e. ANY entry can end up paired with ANY
    # exit -- confirmed by direct testing that some such pairings are not
    # mutually reachable (a generated vehicle got "no valid route" and
    # crashed the SUMO connection outright). Restricting to the graph's
    # largest STRONGLY connected component guarantees every remaining
    # entry can reach every remaining exit, so any pairing _od_pairs
    # produces is automatically valid -- not just the specific one tested.
    import networkx as nx
    g = nx.DiGraph()
    for eid, (a, b) in edges.items():
        g.add_edge(a, b)
    giant = max(nx.strongly_connected_components(g), key=len)

    entry_edges: List[str] = []
    exit_edges: List[str] = []
    n_dropped = 0
    for exit_e, entry_e in leaf_pairs:
        from_node, to_node = edges[exit_e]
        if from_node in giant and to_node in giant:
            exit_edges.append(exit_e)
            entry_edges.append(entry_e)
        else:
            n_dropped += 1
    if n_dropped:
        print(f"  (prepare_net_bengaluru: dropped {n_dropped}/{len(leaf_pairs)} leaf pairs "
              f"outside the giant strongly-connected component)")

    return nodes, edges, entry_edges, exit_edges


def _od_setup(cfg: dict, fleet: Fleet, nodes, edges, entry_edges, exit_edges, dispersion: float):
    od_pairs = _od_pairs(entry_edges, exit_edges)
    path_nodes_list, path_edges_list, fractions = classify_od_pairs(nodes, edges, od_pairs)
    od_shares = od_class_shares(fleet, fractions, dispersion)
    return od_pairs, path_nodes_list, path_edges_list, fractions, od_shares


def offered_veh_h(scale: float, n_od_pairs: int, base_veh_per_hour: float = DEFAULT_BASE_VEH_PER_HOUR) -> float:
    """Analytical offered volume -- the SAME formula build_nets.py uses to
    size flows, so this never drifts from what's actually generated."""
    avg_mult = sum(_PEAK_MULTIPLIERS) / len(_PEAK_MULTIPLIERS)
    return base_veh_per_hour * avg_mult * scale * n_od_pairs


def scale_for_vc(
    target_vc: float, capacity_veh_per_h: float, n_od_pairs: int,
    base_veh_per_hour: float = DEFAULT_BASE_VEH_PER_HOUR,
) -> float:
    """Demand scale hitting a target v/c against an already-measured
    capacity. offered_veh_h is EXACTLY linear in scale by construction (not
    an empirical fit), so this is a direct inversion, not an
    interpolation/extrapolation over whatever happened to be swept.
    Top-level (Phase 1c) so scripts/h1_evidence.py can compute e.g. a
    v/c=0.95 point without re-running the whole capacity sweep."""
    return target_vc * capacity_veh_per_h / offered_veh_h(1.0, n_od_pairs, base_veh_per_hour)


def _routes_xml_staggered(
    fleet: Fleet, cfg: dict, od_pairs, od_shares, base_veh_per_hour: float, demand_scale: float,
) -> str:
    """Bengaluru-only route generator (PAPER_CHANGELOG P4c-16) -- NOT a
    change to `_routes_xml` itself, which S1/S2's already-validated numbers
    depend on (their 12-16 OD pairs make this fix irrelevant for them; not
    worth the risk of touching shared code for zero benefit there).

    `_routes_xml` gives every OD pair's flow in a given time bucket the
    SAME integer `begin` (deliberately, for a different reason -- SUMO
    silently drops out-of-order flows, see that function's docstring). For
    S1/S2's handful of OD pairs this is harmless. For Bengaluru's 975
    independent OD pairs it is not: confirmed DIRECTLY (four capacity-
    sweep-floor runs at scale in {0.5, 0.25, 0.1, 0.05}, a 10x demand
    range) that every one produced BIT-IDENTICAL results (in_net=975 at
    t=0 in every single case, exactly matching n_od) -- because SUMO
    inserts a flow's first vehicle near its own `begin` time almost
    independent of its rate, 975 simultaneously-begun flows means ~975
    near-simultaneous insertions REGARDLESS of scale, an artificial
    cold-start surge that swamps a 5-signal corridor before the demand
    RATE ever gets a chance to matter. This is a demand-generation
    artifact, not a corridor defect or a "just lower the scale" problem --
    confirmed the demand itself DOES scale correctly (offered volume exactly
    proportional across all four tested scales) before concluding this.

    Fix: stagger each OD pair's `begin` uniformly across its bucket
    (`begin = bucket_start + k * bucket_s / n_od`) instead of all pairs
    sharing one integer. `_routes_xml`'s own ordering invariant (globally
    non-decreasing `begin` across the file) is preserved by construction --
    buckets stay in the outer loop, and within a bucket the staggered
    begins are already sorted by construction (k increasing)."""
    episode_s = cfg["demand"]["episode_length_s"]
    n_buckets = len(_PEAK_MULTIPLIERS)
    bucket_s = episode_s / n_buckets
    n_od = len(od_pairs)

    flows = []
    fid = 0
    for b in range(n_buckets):
        bucket_start = b * bucket_s
        end = int((b + 1) * bucket_s)
        vph = base_veh_per_hour * _PEAK_MULTIPLIERS[b] * demand_scale
        for k, (entry, exit_) in enumerate(od_pairs):
            begin = int(bucket_start + k * bucket_s / n_od)
            flows.append(
                f'  <flow id="f{fid}" type="fleet_od{k}" from="{entry}" to="{exit_}" '
                f'begin="{begin}" end="{end}" vehsPerHour="{vph:.2f}" '
                f'departPos="base" departSpeed="max" departLane="best"/>'
            )
            fid += 1

    return (
        "<routes>\n"
        + _vtype_distribution_xml(fleet, cfg, od_shares)
        + "\n"
        + "\n".join(flows)
        + "\n</routes>\n"
    )


def _write_run(
    name: str, net_path: Path, fleet: Fleet, cfg: dict, od_pairs, od_shares,
    scale: float, rundir: Path, base_veh_per_hour: float = DEFAULT_BASE_VEH_PER_HOUR,
    stagger: bool = False,
) -> Path:
    """One (scale, seed) combination gets its OWN directory containing
    exactly one .rou.xml/.sumocfg -- HAPLightEnv._find_sumocfg() globs for a
    single *.sumocfg per net_dir, so multiple scale/seed variants can never
    share a directory. `base_veh_per_hour` (PAPER_CHANGELOG P4c-16): S1/S2's
    DEFAULT_BASE_VEH_PER_HOUR=300 is calibrated per OD pair for their
    COARSE, zone-level entry/exit stubs (S1 has 12 total) -- applying the
    same per-pair rate to Bengaluru's 975 fine-grained, per-residential-
    street OD pairs produced 131,625 veh/h offered at the LOWEST tested
    scale (confirmed directly: ~36 vehicles/second into a 5.7km corridor),
    which gridlocked the simulation so severely it made ~635s of progress
    in 20 hours of wall-clock time before being killed. Bengaluru callers
    MUST pass a correspondingly smaller base rate, not just a smaller
    `scale` in the same formula. `stagger` (Bengaluru only, P4c-16): see
    _routes_xml_staggered's docstring -- avoids the cold-start surge
    artifact from many simultaneous-begin OD-pair flows."""
    rundir.mkdir(parents=True, exist_ok=True)
    gen = _routes_xml_staggered if stagger else _routes_xml
    routes_xml = gen(fleet, cfg, od_pairs, od_shares, base_veh_per_hour, scale)
    route_path = rundir / f"{name}.rou.xml"
    route_path.write_text(routes_xml)
    cfg_path = rundir / f"{name}.sumocfg"
    # Absolute net-file reference: the net lives in a directory shared
    # across every (scale, seed) run, not this one.
    cfg_path.write_text(_sumocfg_xml(str(net_path.resolve()), route_path.name, cfg))
    return rundir


# --------------------------------------------------------------------------
# Episode runner
# --------------------------------------------------------------------------


def run_episode(net_dir: Path, cfg: dict, fleet: Fleet, seed: int, controller_cls=GreedyHAP) -> dict:
    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=seed, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = controller_cls(env)
        ctrl.reset()
        info = env.info
        overflow_events = overflow_total = 0
        pending_samples: List[int] = []
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                for mv in env.movements[i]:
                    overflow_total += 1
                    if info["true_queues"][i][mv] > env.storage[i][mv]:
                        overflow_events += 1
            pending_samples.append(env.pending_count())

        trips = env.completed_trips()
        m = metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        depart_delays = [t.get("depart_delay", 0.0) for t in trips]
        return {
            "trips": len(trips),
            "throughput_veh_h": m["tp"],
            "aql": m["aql"],
            "att": m["att"],
            "pwd": m["pwd"],
            "overflow_fraction": (overflow_events / overflow_total) if overflow_total else float("nan"),
            "pending_mean": float(np.mean(pending_samples)) if pending_samples else 0.0,
            "pending_max": float(np.max(pending_samples)) if pending_samples else 0.0,
            "depart_delay_mean": float(np.mean(depart_delays)) if depart_delays else 0.0,
        }
    finally:
        env.close()


# --------------------------------------------------------------------------
# Part A: capacity sweep
# --------------------------------------------------------------------------

DEFAULT_SCALE_GRID = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
QUICK_SCALE_GRID = [0.5, 1.5, 3.0, 6.0]

KNEE_SLOPE_FRACTION = 0.10   # knee = where marginal slope first drops below this fraction of the initial slope
PLATEAU_TOLERANCE = 0.08     # a scale continues the plateau if within this fraction of the running mean
GRIDLOCK_DROP = 0.10         # a scale STARTS a gridlock region if throughput drops more than this fraction


def _find_knee(scales: List[float], throughput: List[float]) -> Tuple[int, bool]:
    """Returns (knee_index, found). found=False means the marginal slope
    never dropped within the tested grid -- throughput was still climbing
    steeply at the top of the range, so there is no real plateau to report
    yet and the caller must say so rather than silently treating the last
    point as capacity."""
    if len(scales) < 3:
        return 0, False
    slopes = [
        (throughput[i + 1] - throughput[i]) / (scales[i + 1] - scales[i])
        for i in range(len(scales) - 1)
    ]
    initial = slopes[0] if slopes[0] > 0 else max(slopes)
    for idx, s in enumerate(slopes):
        if s < KNEE_SLOPE_FRACTION * initial:
            return idx, True
    return len(scales) - 1, False


def _plateau_and_capacity(scales: List[float], seed_means: List[float]) -> Tuple[List[int], float]:
    """First cut off any gridlock region (a material single-step drop) from
    the tested range. Then, within what's left, grow the plateau BACKWARD
    from the highest tested scale while each earlier point stays within
    tolerance of the plateau's own running mean -- i.e. is actually flat --
    stopping at the first earlier point that is not (still part of the
    rising, pre-saturation region). A monotonically-rising sequence that
    never flattens anywhere therefore yields a single-point "plateau" at
    its last point, not an average over the whole rise (which would
    understate capacity). Returns (plateau_indices, capacity)."""
    n = len(scales)
    cutoff = n
    for idx in range(1, n):
        if seed_means[idx] < seed_means[idx - 1] * (1 - GRIDLOCK_DROP):
            cutoff = idx
            break
    candidates = list(range(cutoff))

    plateau = [candidates[-1]]
    running_mean = seed_means[candidates[-1]]
    for idx in reversed(candidates[:-1]):
        if abs(seed_means[idx] - running_mean) <= PLATEAU_TOLERANCE * running_mean:
            plateau.append(idx)
            running_mean = float(np.mean([seed_means[i] for i in plateau]))
        else:
            break
    plateau.sort()
    capacity = float(np.mean([seed_means[i] for i in plateau]))
    return plateau, capacity


def sweep_capacity(
    scenario_key: str, cfg: dict, fleet: Fleet, nets_dir: Path, workdir: Path,
    scale_grid: List[float], episode_s: float, extra_seeds: int,
    topology: Optional[Tuple] = None, name: Optional[str] = None,
    base_veh_per_hour: float = DEFAULT_BASE_VEH_PER_HOUR,
) -> dict:
    """`topology`/`name`, when given (PAPER_CHANGELOG P4c-16, Bengaluru),
    bypass `_prepare_net`'s synthetic-grid-only lookup entirely -- pass
    `(nodes, edges, entry_edges, exit_edges, net_path)` directly for a
    real OSM-derived network that isn't in SCENARIOS. Every other line of
    this function (OD setup, the scale sweep, knee/plateau detection, the
    nominal-scale sanity check) is topology-agnostic and works unchanged
    for either source. `base_veh_per_hour` MUST be re-derived for a
    topology whose OD-pair count/granularity differs materially from
    S1/S2's (see _write_run's docstring -- Bengaluru's 975 fine-grained
    OD pairs at the S1/S2-calibrated per-pair rate produced a 20-hour
    gridlock that made ~635s of progress out of a 1800s episode before
    being killed)."""
    if topology is not None:
        nodes, edges, entry_edges, exit_edges, net_path = topology
    else:
        name = SCENARIOS[scenario_key]
        nodes, edges, entry_edges, exit_edges, net_path = _prepare_net(scenario_key, cfg, nets_dir, workdir)
    dispersion = cfg["demand"].get("composition_dispersion", 0.5)
    od_pairs, _, _, _, od_shares = _od_setup(cfg, fleet, nodes, edges, entry_edges, exit_edges, dispersion)
    n_od = len(od_pairs)

    cfg_run = copy.deepcopy(cfg)
    cfg_run["demand"]["episode_length_s"] = episode_s

    print(f"\n{scenario_key}: capacity sweep (episode={episode_s:.0f}s)")
    print(f"  {'scale':>6s} {'offered veh/h':>14s} {'throughput veh/h':>17s} {'AQL':>8s} {'ATT':>8s} {'overflow':>9s}")

    # Pass 1: 1 seed across the full grid
    pass1 = []
    for scale in scale_grid:
        rundir = _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, workdir / f"{name}_s{scale}_seed0", base_veh_per_hour)
        r = run_episode(rundir, cfg_run, fleet, seed=0)
        offered = offered_veh_h(scale, n_od, base_veh_per_hour)
        pass1.append({"scale": scale, "offered": offered, "seeds": [r]})
        print(f"  {scale:6.2f} {offered:14.1f} {r['throughput_veh_h']:17.1f} "
              f"{r['aql']:8.2f} {r['att']:8.1f} {r['overflow_fraction']:9.3f}")

    knee_idx, knee_found = _find_knee(scale_grid, [p["seeds"][0]["throughput_veh_h"] for p in pass1])
    if not knee_found:
        print(
            f"  !! throughput was still climbing steeply at the top of the tested "
            f"grid (scale={scale_grid[-1]:.2f}) -- no real plateau found. The "
            f"capacity/scale_nominal/scale_surge below are UNDERESTIMATES; extend "
            f"--scale-grid higher and re-run before trusting them."
        )

    # Pass 2: extra seeds from the knee onward
    print(f"  knee at scale={scale_grid[knee_idx]:.2f} -- refining with {extra_seeds} more seed(s)")
    for idx in range(knee_idx, len(scale_grid)):
        scale = scale_grid[idx]
        for seed in range(1, 1 + extra_seeds):
            rundir = _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, workdir / f"{name}_s{scale}_seed{seed}", base_veh_per_hour)
            r = run_episode(rundir, cfg_run, fleet, seed=seed)
            pass1[idx]["seeds"].append(r)

    seed_means = [float(np.mean([s["throughput_veh_h"] for s in p["seeds"]])) for p in pass1]
    plateau_idx, capacity = _plateau_and_capacity(scale_grid, seed_means)

    print(f"  plateau scales: {[scale_grid[i] for i in plateau_idx]}")
    if len(plateau_idx) < len(scale_grid) - 1:
        excluded = [scale_grid[i] for i in range(len(scale_grid)) if i not in plateau_idx and i >= knee_idx]
        if excluded:
            print(f"  excluded as gridlock/unswept beyond plateau: {excluded}")
    print(f"  capacity_veh_per_h = {capacity:.1f}")

    offered_arr = np.array([offered_veh_h(s, n_od, base_veh_per_hour) for s in scale_grid])

    scale_nominal = scale_for_vc(0.85, capacity, n_od, base_veh_per_hour)
    scale_surge = scale_for_vc(1.05, capacity, n_od, base_veh_per_hour)

    print(f"  scale_nominal={scale_nominal:.3f} (v/c~0.85)   scale_surge={scale_surge:.3f} (v/c~1.05)")

    # Sanity floor + insertion-backlog check: one dedicated full-length run
    # at scale_nominal, at the SCENARIO's actual configured episode length
    # (not the sweep's shortened one).
    full_cfg = copy.deepcopy(cfg)
    rundir = _write_run(name, net_path, fleet, full_cfg, od_pairs, od_shares, scale_nominal, workdir / f"{name}_nominal_check", base_veh_per_hour)
    nominal_r = run_episode(rundir, full_cfg, fleet, seed=0)
    episode_h = full_cfg["demand"]["episode_length_s"] / 3600.0
    print(
        f"  sanity check @ scale_nominal, {full_cfg['demand']['episode_length_s']:.0f}s episode: "
        f"{nominal_r['trips']} trips (want O(1e3) on S1), v/c={offered_veh_h(scale_nominal, n_od, base_veh_per_hour)/capacity:.2f}"
    )
    if scenario_key == "s1_arterial" and nominal_r["trips"] < 300:
        print(
            "  !! trip count is well below the O(1e3) sanity floor for a 3600s S1 "
            "episode -- this points at a demand-GENERATOR bug, not just a scale "
            "that needs raising further. Investigate before trusting scale_nominal."
        )
    if nominal_r["pending_mean"] > 1.0 or nominal_r["depart_delay_mean"] > 5.0:
        print(
            f"  !! insertion backlog at scale_nominal: mean pending="
            f"{nominal_r['pending_mean']:.2f}, mean depart delay="
            f"{nominal_r['depart_delay_mean']:.1f}s -- offered volume assumed "
            f"full insertion at the nominal rate, so the reported v/c is an "
            f"UNDERESTIMATE of true demand pressure."
        )

    return {
        "scenario": scenario_key,
        "scale_grid": scale_grid,
        "offered": offered_arr.tolist(),
        "throughput_seed_mean": seed_means,
        "plateau_scales": [scale_grid[i] for i in plateau_idx],
        "capacity_veh_per_h": capacity,
        "scale_nominal": scale_nominal,
        "scale_surge": scale_surge,
        "nominal_check": nominal_r,
    }


def _patch_yaml_scalar(text: str, dict_key: str, sub_key: str, value: float) -> str:
    pattern = re.compile(rf"({re.escape(dict_key)}:\s*\{{[^}}]*?{re.escape(sub_key)}:\s*)([^,}}]+)")
    new_text, n = pattern.subn(lambda m: m.group(1) + f"{value:.4f}", text)
    if n != 1:
        raise RuntimeError(f"expected exactly 1 match patching {dict_key}.{sub_key}, got {n}")
    return new_text


def write_back_config(config_path: Path, results: Dict[str, dict]) -> None:
    text = config_path.read_text()
    for scenario_key, r in results.items():
        text = _patch_yaml_scalar(text, "scale_nominal", scenario_key, r["scale_nominal"])
        text = _patch_yaml_scalar(text, "scale_surge", scenario_key, r["scale_surge"])
        text = _patch_yaml_scalar(text, "capacity_veh_per_h", scenario_key, r["capacity_veh_per_h"])
    config_path.write_text(text)
    print(f"\nWritten calibrated scales into {config_path}")


# --------------------------------------------------------------------------
# Deliverable: composition-dispersion sweep (HAP vs MP)
# --------------------------------------------------------------------------

DISPERSION_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]


def _mp_shadow_action(env, info) -> Dict[str, int]:
    """What MaxPressure would choose from this SAME info, without stepping
    a second simulation -- reuses controllers._pressure_action directly."""
    from src.controllers import _pressure_action, _rho1

    x_up = {i: {mv: _rho1(info["counts_hat"][i][mv]) for mv in env.movements[i]} for i in env.intersections}
    x_down = {
        i: {mv: _rho1(info["counts_hat_downstream"][i][mv]) for mv in env.movements[i]}
        for i in env.intersections
    }
    return _pressure_action(env, info, x_up, x_down)


def run_hap_vs_mp(net_dir: Path, cfg: dict, fleet: Fleet, seed: int = 0) -> dict:
    """Drives ONE episode with GreedyHAP; at every decision also computes
    what MaxPressure would have chosen from the same info (no second
    simulation needed) -- this is both the disagreement-rate measurement
    and the HAP/MP-equivalence tests' shared mechanism.

    estimator="count": MaxPressure's shadow always reads counts_hat
    (count-corruption pipeline regardless of env.estimator); pairing it
    against GreedyHAP's x_hat under "area" would conflate the area
    estimator's own approximation error with the composition effect being
    measured here (roughly doubled the disagreement rate in practice --
    see tests/test_composition.py)."""
    env = HAPLightEnv(str(net_dir), cfg, fleet, seed=seed, eta=0.0, estimator="count")
    try:
        obs = env.reset()
        hap = GreedyHAP(env)
        hap.reset()
        info = env.info
        n_decisions = disagreements = 0
        truncated = False
        comp_dispersion_samples = []
        while not truncated:
            hap_actions = hap.act(obs, info)
            mp_actions = _mp_shadow_action(env, info)
            for i in env.intersections:
                n_decisions += 1
                if hap_actions[i] != mp_actions[i]:
                    disagreements += 1
            flat_counts = {mv: c for i in env.intersections for mv, c in info["true_counts"][i].items()}
            d = metrics.composition_dispersion(flat_counts)
            if np.isfinite(d):
                comp_dispersion_samples.append(d)
            obs, reward, truncated, info = env.step(hap_actions)

        trips = env.completed_trips()
        m = metrics.compute(trips, env.true_queue_history(), fleet, cfg, env.gmax_activation_rate())
        two_w_wait = [t["waiting"] for t in trips if t["vclass"] == "twowheeler"]
        return {
            "att": m["att"], "aql": m["aql"], "pwd": m["pwd"],
            "two_w_wait": float(np.mean(two_w_wait)) if two_w_wait else float("nan"),
            "disagreement_rate": disagreements / n_decisions if n_decisions else float("nan"),
            "measured_dispersion": float(np.mean(comp_dispersion_samples)) if comp_dispersion_samples else float("nan"),
        }
    finally:
        env.close()


def dispersion_sweep(cfg: dict, fleet: Fleet, nets_dir: Path, workdir: Path, episode_s: float) -> None:
    scenario_key = "s1_arterial"
    name = SCENARIOS[scenario_key]
    nodes, edges, entry_edges, exit_edges, net_path = _prepare_net(scenario_key, cfg, nets_dir, workdir)
    od_pairs = _od_pairs(entry_edges, exit_edges)

    nominal = (cfg.get("demand", {}) or {}).get("scale_nominal") or {}
    scale = nominal.get(scenario_key)
    if scale is None:
        print("  (no calibrated demand.scale_nominal.s1_arterial -- using 1.0; "
              "run the capacity sweep first for a meaningful result)")
        scale = 1.0

    cfg_run = copy.deepcopy(cfg)
    cfg_run["demand"]["episode_length_s"] = episode_s

    print(f"\nComposition-dispersion sweep on S1 (scale={scale:.2f}, episode={episode_s:.0f}s)")
    print(f"  {'d':>5s} {'ATT':>8s} {'AQL':>8s} {'PWD':>8s} {'2W wait':>8s} "
          f"{'MP disagree':>12s} {'measured disp.':>14s}")

    last_shares = None
    last_fractions = None
    last_path_nodes = None
    for d in DISPERSION_GRID:
        path_nodes_list, path_edges_list, fractions = classify_od_pairs(nodes, edges, od_pairs)
        od_shares = od_class_shares(fleet, fractions, d)
        rundir = _write_run(name, net_path, fleet, cfg_run, od_pairs, od_shares, scale, workdir / f"disp{d}")
        r = run_hap_vs_mp(rundir, cfg_run, fleet, seed=0)
        print(
            f"  {d:5.2f} {r['att']:8.1f} {r['aql']:8.2f} {r['pwd']:8.2f} "
            f"{r['two_w_wait']:8.1f} {r['disagreement_rate']:12.1%} {r['measured_dispersion']:14.3f}"
        )
        if d == 1.0:
            last_shares, last_fractions, last_path_nodes = od_shares, fractions, path_nodes_list

    print("\nPer-OD composition at d=1 (analytical, from path-length classification):")
    print(f"  {'entry':>12s} {'exit':>12s} {'n_int':>6s} {'t':>5s} {'2w':>6s} {'car':>6s} {'auto':>6s} {'bus':>6s} {'truck':>6s}")
    for (entry, exit_), pn, t, s in zip(od_pairs, last_path_nodes, last_fractions, last_shares):
        n_int = sum(1 for n in pn if n.startswith("n")) if pn else 0
        print(
            f"  {entry:>12s} {exit_:>12s} {n_int:6d} {t:5.2f} "
            f"{s['twowheeler']:6.2f} {s['car']:6.2f} {s['auto']:6.2f} {s['bus']:6.2f} {s['truck']:6.2f}"
        )

    print("\nPer-movement MEASURED composition at d=1 (from one episode's true_counts, network-wide):")
    rundir = _write_run(name, net_path, fleet, cfg_run, od_pairs, last_shares, scale, workdir / "disp1_measure")
    env = HAPLightEnv(str(rundir), cfg_run, fleet, seed=0, eta=0.0, estimator="area")
    try:
        obs = env.reset()
        ctrl = GreedyHAP(env)
        ctrl.reset()
        info = env.info
        totals: Dict[str, Dict[str, float]] = {}
        truncated = False
        while not truncated:
            actions = ctrl.act(obs, info)
            obs, reward, truncated, info = env.step(actions)
            for i in env.intersections:
                for mv, counts in info["true_counts"][i].items():
                    bucket = totals.setdefault(mv, {})
                    for cls, n in counts.items():
                        bucket[cls] = bucket.get(cls, 0.0) + n
    finally:
        env.close()

    print(f"  {'movement':>28s} {'mass':>8s} {'2w':>6s} {'car':>6s} {'auto':>6s} {'bus':>6s} {'truck':>6s}")
    for mv, counts in sorted(totals.items(), key=lambda kv: -sum(kv[1].values()))[:20]:
        mass = sum(counts.values())
        if mass <= 0:
            continue
        frac = {c: counts.get(c, 0.0) / mass for c in fleet.names}
        print(
            f"  {mv:>28s} {mass:8.1f} {frac.get('twowheeler',0):6.2f} {frac.get('car',0):6.2f} "
            f"{frac.get('auto',0):6.2f} {frac.get('bus',0):6.2f} {frac.get('truck',0):6.2f}"
        )


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--nets", default="nets")
    ap.add_argument("--scenario", choices=["s1", "s2", "bengaluru", "all"], default="all")
    ap.add_argument("--bengaluru-net", default="nets/bengaluru/bengaluru.net.xml")
    ap.add_argument("--quick", action="store_true", help="coarse grid, short episodes -- smoke test only")
    ap.add_argument(
        "--scale-grid", type=float, nargs="+", default=None,
        help="override the swept demand-scale grid, e.g. --scale-grid 0.5 1 2 4 8 12",
    )
    ap.add_argument("--extra-seeds", type=int, default=2, help="additional seeds near/past the knee (total = 1 + this)")
    ap.add_argument("--dispersion-sweep", action="store_true", help="run the composition-dispersion deliverable instead of the capacity sweep")
    ap.add_argument("--no-write", action="store_true", help="print results without writing back to --config")
    args = ap.parse_args()

    config_path = Path(args.config)
    cfg = yaml.safe_load(config_path.read_text())
    nets_dir = Path(args.nets)
    fleet = Fleet.from_config(cfg)

    if args.scale_grid is not None:
        scale_grid = sorted(args.scale_grid)
    else:
        scale_grid = QUICK_SCALE_GRID if args.quick else DEFAULT_SCALE_GRID
    episode_s = 600.0 if args.quick else 1800.0

    with tempfile.TemporaryDirectory(prefix="haplight_calib_") as td:
        workdir = Path(td)

        if args.dispersion_sweep:
            dispersion_sweep(cfg, fleet, nets_dir, workdir, episode_s=600.0 if args.quick else 1800.0)
            return 0

        if args.scenario == "bengaluru":
            # Bengaluru is a real OSM corridor, not a SCENARIOS-registered
            # synthetic grid (PAPER_CHANGELOG P4c-16) -- topology comes
            # from prepare_net_bengaluru, not _prepare_net, and results are
            # NOT written back to configs/default.yaml (write_back_config's
            # patcher is keyed to the existing s1_arterial/s2_grid YAML
            # structure, which has no Bengaluru section yet -- printing,
            # not silently inventing a new config schema, until that's a
            # deliberate decision).
            net_path = Path(args.bengaluru_net)
            if not net_path.exists():
                raise FileNotFoundError(f"Bengaluru net not found: {net_path} -- run scripts/build_nets.py --scenario bengaluru first")
            topology = prepare_net_bengaluru(net_path) + (net_path,)
            result = sweep_capacity(
                "bengaluru", cfg, fleet, nets_dir, workdir, scale_grid, episode_s, args.extra_seeds,
                topology=topology, name="bengaluru", base_veh_per_hour=BENGALURU_BASE_VEH_PER_HOUR,
            )
            print(f"\nBengaluru corridor capacity: {result['capacity_veh_per_h']:.1f} veh/h")
            print(f"  scale_nominal={result['scale_nominal']:.4f} (v/c~0.85)")
            print(f"  scale_surge={result['scale_surge']:.4f} (v/c~1.05)")
            return 0

        scenario_keys = []
        if args.scenario in ("s1", "all"):
            scenario_keys.append("s1_arterial")
        if args.scenario in ("s2", "all"):
            scenario_keys.append("s2_grid")

        results = {}
        for sk in scenario_keys:
            results[sk] = sweep_capacity(
                sk, cfg, fleet, nets_dir, workdir, scale_grid, episode_s, args.extra_seeds
            )

        if not args.no_write:
            write_back_config(config_path, results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
