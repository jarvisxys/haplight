"""
Network + demand generation for HAPLight Scenario 1 (5-node arterial) and
Scenario 2 (4x4 grid).  Phase 1 (see PLAN.md).  Scenario 3 (Bengaluru OSM
corridor) is Phase 6: `--scenario bengaluru` runs netconvert_build_
bengaluru + validate_bengaluru_net against a manually-selected corridor
.osm (not the earlier region-scale bounding-box extraction, which was not
a corridor at all -- PAPER_CHANGELOG P4c-16). Demand generation for it is
a separate, not-yet-built pipeline (the synthetic-grid entry/exit-stub
machinery below does not apply to a real road network); this scenario is
therefore NOT included in `--scenario all`, opt-in only.

Both scenarios are instances of the same R x C signalised-intersection grid
(S1 is a 1x5 row, S2 is a 4x4 grid): every intersection gets exactly four
approaches by construction -- interior nodes connect to their real grid
neighbours, boundary nodes get a short unsignalised stub in whichever
direction(s) have no neighbour. Movements and phases are *not* decided here;
netconvert's default static-TLS builder produces them from the lane/connection
geometry, and src/env.py reads whatever program results at runtime
(traci.trafficlight.getControlledLinks / getAllProgramLogics) rather than
this script hard-coding a phase count.

Alongside the net/route/sumocfg, this also writes two sidecars:
  - `<scenario>/movement_demand.json`: real per-movement demand (veh/h AND
    the composition-weighted mean rho of that traffic), computed by
    shortest-pathing every OD flow over this script's own topology graph.
    controllers.FixedTime reads this to Webster-tune real splits (including
    the per-movement mean rho -- a global mean would mistune FixedTime once
    composition varies by OD, see Phase 1b). Do not delete it.
  - `<scenario>/od_composition.json`: the per-OD path-length classification
    and resulting class-share vector, so downstream reporting doesn't need
    to re-run the shortest-path computation.

Composition is per-OD, not global (Phase 1b): every OD pair's class shares
are interpolated between the fleet's nominal (uniform) shares and a
documented "local vs arterial" archetype, by `demand.composition_dispersion`
in [0,1]. At dispersion 0 every OD gets exactly the nominal shares --
byte-identical to Phase 1's behaviour.

Usage
-----
    python scripts/build_nets.py --config configs/default.yaml --out nets
    python scripts/build_nets.py --scenario s1 --lefthand true
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.hap import Fleet  # noqa: E402

# --------------------------------------------------------------------------
# SUMO bootstrap: only need netconvert on PATH here (no traci/libsumo import)
# --------------------------------------------------------------------------


def _ensure_sumo_on_path() -> None:
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

# --------------------------------------------------------------------------
# Grid topology: nodes, edges, boundary stubs
# --------------------------------------------------------------------------


def _nid(r: int, c: int) -> str:
    return f"n{r}_{c}"


def build_topology(
    rows: int, cols: int, spacing: float, stub_len: float
) -> Tuple[Dict[str, Tuple[float, float, str]], Dict[str, Tuple[str, str]], List[str], List[str]]:
    """
    Returns (nodes, edges, entry_edges, exit_edges).

    nodes: id -> (x, y, type)
    edges: id -> (from_node, to_node)          -- both directions emitted
    entry_edges: edge ids that carry traffic INTO the network (stub -> grid)
    exit_edges:  edge ids that carry traffic OUT of the network (grid -> stub)
    """
    nodes: Dict[str, Tuple[float, float, str]] = {}
    edges: Dict[str, Tuple[str, str]] = {}

    for r in range(rows):
        for c in range(cols):
            nodes[_nid(r, c)] = (c * spacing, -r * spacing, "traffic_light")

    def add_pair(a: str, b: str) -> None:
        edges[f"{a}_{b}"] = (a, b)
        edges[f"{b}_{a}"] = (b, a)

    # interior grid edges
    for r in range(rows):
        for c in range(cols - 1):
            add_pair(_nid(r, c), _nid(r, c + 1))
    for r in range(rows - 1):
        for c in range(cols):
            add_pair(_nid(r, c), _nid(r + 1, c))

    # boundary stubs: every intersection must end up with 4 approaches
    entry_edges: List[str] = []
    exit_edges: List[str] = []
    stub_i = 0
    for r in range(rows):
        for c in range(cols):
            nid = _nid(r, c)
            x0, y0, _ = nodes[nid]
            missing = []
            if c - 1 < 0:
                missing.append((x0 - stub_len, y0))
            if c + 1 >= cols:
                missing.append((x0 + stub_len, y0))
            if r - 1 < 0:
                missing.append((x0, y0 + stub_len))
            if r + 1 >= rows:
                missing.append((x0, y0 - stub_len))
            for sx, sy in missing:
                sid = f"stub{stub_i}"
                stub_i += 1
                nodes[sid] = (sx, sy, "priority")
                add_pair(nid, sid)
                entry_edges.append(f"{sid}_{nid}")
                exit_edges.append(f"{nid}_{sid}")

    return nodes, edges, entry_edges, exit_edges


def _nodes_xml(nodes: Dict[str, Tuple[float, float, str]]) -> str:
    rows = [
        f'  <node id="{nid}" x="{x:.1f}" y="{y:.1f}" type="{typ}"/>'
        for nid, (x, y, typ) in nodes.items()
    ]
    return "<nodes>\n" + "\n".join(rows) + "\n</nodes>\n"


def _edges_xml(
    edges: Dict[str, Tuple[str, str]], lanes: int, width: float, speed: float
) -> str:
    rows = [
        f'  <edge id="{eid}" from="{a}" to="{b}" numLanes="{lanes}" '
        f'width="{width}" speed="{speed:.3f}"/>'
        for eid, (a, b) in edges.items()
    ]
    return "<edges>\n" + "\n".join(rows) + "\n</edges>\n"


def netconvert_build(
    workdir: Path, nodes_xml: str, edges_xml: str, out_net: Path, lefthand: bool
) -> None:
    (workdir / "n.nod.xml").write_text(nodes_xml)
    (workdir / "n.edg.xml").write_text(edges_xml)
    cmd = [
        "netconvert",
        "-n", str(workdir / "n.nod.xml"),
        "-e", str(workdir / "n.edg.xml"),
        "-o", str(out_net),
        "--no-turnarounds", "true",
        "--tls.default-type", "static",
        "--lefthand", "true" if lefthand else "false",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_net.exists():
        raise RuntimeError(f"netconvert failed:\n{res.stdout}\n{res.stderr}")


# --------------------------------------------------------------------------
# Scenario 3 (Bengaluru, Phase 6): a real OSM corridor extract, not a
# synthetic grid. Deliberately NOT routed through build_scenario/
# build_topology above -- those assume a regular grid with known
# entry/exit stub edges, which a real road network does not have. Every
# netconvert flag lives here, in this script, not in a hand-edited XML
# (the paper's reproducibility claim in Sec. VI-C is "from the bounding
# box / source .osm file alone").
# --------------------------------------------------------------------------


# Original OSM export box (author, openstreetmap.org, drivable roads only) --
# the outermost boundary anything in nets/bengaluru/ is reproducible from.
BENGALURU_OSM_BOX = (77.640, 12.995, 77.760, 13.020)  # min_lon, min_lat, max_lon, max_lat

# Crop boundary (PAPER_CHANGELOG P4c-16 coherence check): a SECOND, tighter
# geo-boundary applied at netconvert time, one step removed from the OSM
# box above -- drops a structurally-valid but geographically disconnected
# TLS (cluster_567320389_7396736269, lon~77.757) reachable from the other
# 8 only via a 5.3km/95-edge detour through tertiary/residential/secondary
# streets, zero trunk/primary road on that path. Same min_lon/min_lat/
# max_lat as the OSM box; only max_lon tightens.
BENGALURU_CROP_BOX = (77.640, 12.995, 77.720, 13.020)

# Explicit exclusion (PAPER_CHANGELOG P4c-16): geo-boundary cropping proved
# unreliable for surgically dropping just this cluster -- confirmed by
# direct testing that even a boundary well below its coordinates
# (max_lon=77.710, vs. the cluster's own ~77.71-77.75 span) still let it
# through, most likely via interaction with --junctions.join/--tls.join
# pulling in nodes beyond the nominal box to complete a cluster. Excluded
# by node ID instead, via the SAME plain-XML-reimport mechanism already
# confirmed reliable for the sprawl prune (exact edge-ID matching against
# stable, already-finalized IDs, not a geographic boundary heuristic).
# Topology inspection (each has 2-3 of its OWN external road connections,
# not just duplicate endpoints of one road) suggests a genuinely complex
# real junction, not a splitting artifact -- excluded rather than
# force-merged, since netconvert's own join algorithm (informed by the
# actual topology) declined to merge them despite 0.2-1.1m connecting
# edges and both join-dist thresholds raised well past that.
BENGALURU_EXCLUDE_TLS_NODES = {"1837297544", "1837297545", "1837297546"}

# Turning movements removed at the network level (PAPER_CHANGELOG P4c-16
# health-check finding): each is (junction, from_edge, to_edge). Found by
# the below-capacity-floor health check -- a U-turn at 1837297484 on a
# 31.75m single-lane link (weighted storage=13.22, the smallest of that
# junction's four movements by 5x) saturates to 366% occupancy even under
# the LOWEST tested demand (scale=0.05, 175.5 veh/h corridor-wide),
# identically regardless of scale -- a genuine structural turn-pocket
# bottleneck, not a demand-volume problem (confirmed directly: the same
# health check at four scales spanning a 10x range gave bit-identical
# results before this fix). Removed as a connection, not by deleting the
# edges themselves (the through movements at this junction are unaffected
# and must stay routable).
BENGALURU_REMOVE_CONNECTIONS = [
    ("1837297484", "-1207691763#0", "1207691763#0"),
]

# Road classes kept whole during the sprawl prune (PAPER_CHANGELOG P4c-16):
# the arterial itself, never touched by the prune regardless of connectivity.
ARTERIAL_EDGE_TYPES = {
    "highway.trunk", "highway.trunk_link",
    "highway.primary", "highway.primary_link",
    "highway.secondary", "highway.secondary_link",
    "highway.tertiary", "highway.tertiary_link",
}


def netconvert_build_bengaluru(
    osm_file: Path, out_net: Path,
    geo_boundary: Tuple[float, float, float, float] = BENGALURU_CROP_BOX,
    junctions_join_dist: int = 20,
) -> None:
    """Corridor-scale conversion (PAPER_CHANGELOG P4c-16/Phase 6 kickoff):
    replaces the earlier region-scale bounding-box extraction (26,162
    junctions, 27 TLS, 13 invalid -- not a corridor at all) with a tight,
    manually-selected corridor .osm and this exact, deterministic
    netconvert invocation. `--tls.discard-simple` drops trivial
    one-in/one-out pseudo-signals (the earlier extraction's <2-incoming-
    edge TLS failures); `--remove-edges.isolated` + `--keep-edges.by-vclass
    passenger` prune orphan/non-car edges; `--junctions.join-dist 20`
    merges the split-junction clusters `--tls.join`/`--tls.guess-signals`
    need whole to recover a real signal. **Deliberately NOT 30** (P4c-16):
    tried widening this to 30 to merge three TLS 13-26m apart into one --
    confirmed by direct testing this does NOT merge them (netconvert's own
    `--junctions.join-output` debug log shows they are never even
    considered join candidates, despite being connected by 0.2-1.1m edges
    -- not a distance-threshold problem at all), and separately confirmed
    by direct testing that widening to 30 has an UNRELATED side effect:
    it silently drops a different, legitimate, single-node TLS elsewhere
    on the corridor. Reverted to 20, the value that does NOT have that
    side effect; the three close TLS are excluded instead, by tightening
    `geo_boundary` (see BENGALURU_CROP_BOX) -- topology inspection (each
    of the three has 2-3 of its OWN external road connections, not just
    duplicate endpoints of one road) suggests this is a genuinely complex
    real junction, not a splitting artifact, so excluding it is more
    honest than forcing an uncertain merge the join algorithm itself
    declined to make. `junctions_join_dist` (default 20, matching this
    analysis) is exposed as a parameter -- not because production ever
    calls it with anything else, but because a later, separate test swept
    {30, 40, 50} to check whether widening it could also resolve the
    corridor's short-single-lane-arterial-edge problem found in the
    below-capacity-floor health check; it did not (PAPER_CHANGELOG P4c-16,
    "join-dist confirmation test" -- the short-link percentage got WORSE,
    not better, as join-dist widened, and N only ever shrank). `geo_boundary`
    applies a SECOND,
    tighter geo-crop on top of the OSM export's own box (default:
    BENGALURU_CROP_BOX, dropping first the disconnected straggler TLS,
    then this three-node complex too -- coherence checks, P4c-16). No
    manual repair step follows -- a junction
    that still fails validation is pruned by netconvert itself, never
    hand-fixed in the XML. The sprawl prune (arterial + one feeder layer)
    is a SEPARATE stage, `prune_via_plain_reimport` below -- see its
    docstring for why it can't just be another flag on this same call."""
    out_net.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "netconvert",
        "--osm-files", str(osm_file),
        "-o", str(out_net),
        "--geometry.remove", "--roundabouts.guess", "--ramps.guess",
        "--junctions.join", "--junctions.join-dist", str(junctions_join_dist),
        "--tls.guess-signals", "--tls.discard-simple", "--tls.join",
        "--tls.default-type", "actuated",
        "--remove-edges.isolated", "--keep-edges.by-vclass", "passenger",
        "--lefthand", "--no-turnarounds",
        "--keep-edges.in-geo-boundary", ",".join(f"{v:.6f}" for v in geo_boundary),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_net.exists():
        raise RuntimeError(f"netconvert failed:\n{res.stdout}\n{res.stderr}")


def prune_via_plain_reimport(net_file: Path, keep_edges_file: Path, out_net: Path, plain_dir: Path) -> None:
    """The sprawl prune's actual mechanism (PAPER_CHANGELOG P4c-16).
    `--keep-edges.input-file` applied directly on a fresh OSM->net build is
    a no-op in practice, confirmed directly: netconvert's --keep-edges.*
    family UNIONS together ("only keep edges in FILE OR those kept due to
    OTHER keep-edges options" -- --help), so combined with
    --keep-edges.by-vclass passenger (which alone already matches nearly
    every OSM road), the explicit list added nothing -- edge count was
    IDENTICAL before/after (17105 -> 17105, then -> 17109) on direct
    testing. Root cause, not just symptom: even removing the vclass flag
    still didn't filter, because --keep-edges.input-file's ID matching
    happens at an EARLIER internal stage than --junctions.join/--tls.join/
    --geometry.remove finish renaming and splitting edges, so IDs read
    from the ALREADY-processed crop network don't line up with what
    netconvert is matching against mid-pipeline on a fresh OSM parse.
    Fix: round-trip through netconvert's own plain-XML export/reimport
    (`--plain-output-prefix` then `-n/-e/-x/-i/-t` reimport) -- the plain
    XML's edge IDs ARE the network's final, stable IDs (all joining/
    splitting/geometry processing already baked in), so
    --keep-edges.input-file matches correctly against them. Verified
    directly: 17105 edges -> 4954 kept (list had 4955; one edge became
    isolated post-filter and --remove-edges.isolated correctly dropped
    it), all 8 TLS junctions preserved intact."""
    plain_dir.mkdir(parents=True, exist_ok=True)
    prefix = plain_dir / "plain"
    export_cmd = ["netconvert", "--sumo-net-file", str(net_file), "--plain-output-prefix", str(prefix)]
    res = subprocess.run(export_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"netconvert plain-XML export failed:\n{res.stdout}\n{res.stderr}")

    # Deliberately NOT reimporting -x (connections) or -i (TLS programs):
    # both can reference specific edges that keep_edges_file drops (a
    # connection's from/to edge, or a TLS program's controlled link) --
    # confirmed by direct testing (excluding just 12 edges by node ID
    # produced 40 "Unknown edge given in connection" errors and a hard
    # failure). Recomputing both fresh from the surviving edges/geometry
    # (netconvert's normal behaviour when building from OSM in the first
    # place) is safe and avoids reusing stale references altogether,
    # rather than trying to hand-patch the plain XML to match.
    reimport_cmd = [
        "netconvert",
        "-n", f"{prefix}.nod.xml", "-e", f"{prefix}.edg.xml", "-t", f"{prefix}.typ.xml",
        "-o", str(out_net),
        "--keep-edges.input-file", str(keep_edges_file),
        "--remove-edges.isolated", "--lefthand",
        "--tls.guess-signals", "--tls.discard-simple", "--tls.join",
        "--tls.default-type", "actuated",
    ]
    res = subprocess.run(reimport_cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_net.exists():
        raise RuntimeError(f"netconvert plain-XML reimport failed:\n{res.stdout}\n{res.stderr}")


def remove_connections(net_file: Path, connections: List[Tuple[str, str, str]], out_net: Path, plain_dir: Path) -> int:
    """Removes specific turning movements at the network level
    (PAPER_CHANGELOG P4c-16 health-check finding, BENGALURU_REMOVE_
    CONNECTIONS) -- a `<connection from=".." to="..">` entry, not the
    edges themselves, so the edges' OTHER movements stay routable. This
    DOES reimport the plain `.con.xml` (with the target line(s) removed --
    safe, since no edges are dropped, so no connection can reference a
    now-missing edge), but does NOT reimport `.tll.xml`: confirmed
    directly that the OLD TLS program still references the just-removed
    connection as a controlled link ("Connection ... not found" on first
    attempt) -- same stale-reference class as prune_via_plain_reimport,
    different file. TLS programs are regenerated fresh from the updated
    connections instead. `connections`: list of (junction_id, from_edge,
    to_edge) -- junction_id is accepted for documentation/readability in
    the caller but not needed to match the line (SUMO's plain connection
    format has no junction field; the (from, to) edge pair is already
    junction-unambiguous by construction, since an edge has exactly one
    downstream junction). Returns the number of connection lines actually
    removed, so a caller can confirm the expected line was really there
    rather than silently matching zero and reporting false success."""
    plain_dir.mkdir(parents=True, exist_ok=True)
    prefix = plain_dir / "plain"
    export_cmd = ["netconvert", "--sumo-net-file", str(net_file), "--plain-output-prefix", str(prefix)]
    res = subprocess.run(export_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"netconvert plain-XML export failed:\n{res.stdout}\n{res.stderr}")

    con_path = Path(f"{prefix}.con.xml")
    lines = con_path.read_text().splitlines()
    targets = {(f, t) for _junction, f, t in connections}
    n_removed = 0
    kept = []
    for line in lines:
        matched = any(f'from="{f}" to="{t}"' in line for f, t in targets)
        if matched:
            n_removed += 1
        else:
            kept.append(line)
    con_path.write_text("\n".join(kept) + "\n")

    # -i (.tll.xml) deliberately NOT reimported, same reason as
    # prune_via_plain_reimport: the OLD TLS program still references the
    # just-removed connection as a controlled link (confirmed directly --
    # "Connection ... not found" on the first attempt with -i included).
    # Regenerating fresh from the updated connections avoids the stale
    # reference entirely.
    reimport_cmd = [
        "netconvert",
        "-n", f"{prefix}.nod.xml", "-e", f"{prefix}.edg.xml", "-x", str(con_path), "-t", f"{prefix}.typ.xml",
        "-o", str(out_net),
        "--lefthand",
        "--tls.guess-signals", "--tls.discard-simple", "--tls.join",
        "--tls.default-type", "actuated",
    ]
    res = subprocess.run(reimport_cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_net.exists():
        raise RuntimeError(f"netconvert plain-XML reimport failed:\n{res.stdout}\n{res.stderr}")
    return n_removed


def compute_feeder_keep_list(
    net_file: Path, out_file: Path,
    exclude_nodes: frozenset = frozenset(),
) -> dict:
    """The sprawl prune (PAPER_CHANGELOG P4c-16): keep every ARTERIAL_EDGE_
    TYPES edge unconditionally, plus exactly ONE layer of residential/other
    feeder edges -- those touching (as either endpoint) a node that some
    kept arterial edge also touches. Everything else (deeper residential
    capillaries, two-hops-removed side streets) is dropped. `exclude_nodes`
    (BENGALURU_EXCLUDE_TLS_NODES, P4c-16) additionally drops every edge
    touching any of the given node IDs -- the surgical exclusion of the
    three-node complex geo-boundary cropping couldn't reliably isolate.
    Writes the resulting edge-ID list to `out_file` (one ID per line,
    netconvert's `--keep-edges.input-file` format) and returns a counts
    report."""
    import sumolib

    net = sumolib.net.readNet(str(net_file), withPrograms=True)
    edges = net.getEdges()

    def touches_excluded(e) -> bool:
        return e.getFromNode().getID() in exclude_nodes or e.getToNode().getID() in exclude_nodes

    arterial = [e for e in edges if e.getType() in ARTERIAL_EDGE_TYPES and not touches_excluded(e)]
    arterial_ids = {e.getID() for e in arterial}
    arterial_nodes = set()
    for e in arterial:
        arterial_nodes.add(e.getFromNode().getID())
        arterial_nodes.add(e.getToNode().getID())

    feeders = [
        e for e in edges
        if e.getID() not in arterial_ids
        and not touches_excluded(e)
        and (e.getFromNode().getID() in arterial_nodes or e.getToNode().getID() in arterial_nodes)
    ]
    keep_ids = sorted(arterial_ids | {e.getID() for e in feeders})

    n_excluded = sum(1 for e in edges if touches_excluded(e))

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(keep_ids) + "\n")

    return {
        "n_edges_total": len(edges),
        "n_arterial": len(arterial_ids),
        "n_feeder": len(feeders),
        "n_kept": len(keep_ids),
        "n_excluded_by_node": n_excluded,
    }


def validate_bengaluru_net(net_file: Path) -> dict:
    """Phase 6's required validation gate (prompts/phase6_bengaluru.md):
    every TLS has >=2 incoming edges, no isolated junctions, no zero-lane
    edges. Returns a dict report; does NOT repair anything -- a network
    that fails is reported, not patched, per the "no hand-editing" rule."""
    import sumolib  # local import: only needed for this OSM-derived path

    net = sumolib.net.readNet(str(net_file), withPrograms=True)
    nodes = net.getNodes()
    edges = net.getEdges()

    tls_nodes = [n for n in nodes if n.getType() == "traffic_light"]
    tls_valid = [n for n in tls_nodes if len(n.getIncoming()) >= 2]
    tls_invalid = [n for n in tls_nodes if len(n.getIncoming()) < 2]
    isolated = [n for n in nodes if not n.getIncoming() and not n.getOutgoing()]
    zero_lane = [e for e in edges if e.getLaneNumber() == 0]

    return {
        "n_junctions": len(nodes),
        "n_edges": len(edges),
        "n_tls_total": len(tls_nodes),
        "n_tls_valid": len(tls_valid),
        "n_tls_invalid": len(tls_invalid),
        "invalid_tls_ids": [n.getID() for n in tls_invalid],
        "n_isolated_junctions": len(isolated),
        "n_zero_lane_edges": len(zero_lane),
        "valid": len(tls_invalid) == 0 and len(isolated) == 0 and len(zero_lane) == 0,
    }


# --------------------------------------------------------------------------
# Shortest-path helper, shared by movement-demand decomposition and OD
# arterial-ness classification so the two never compute different routes
# for the same OD pair.
# --------------------------------------------------------------------------


def _build_graph(nodes: Dict[str, Tuple[float, float, str]], edges: Dict[str, Tuple[str, str]]):
    g = nx.DiGraph()
    for eid, (a, b) in edges.items():
        ax, ay, _ = nodes[a]
        bx, by, _ = nodes[b]
        length = math.hypot(bx - ax, by - ay)
        g.add_edge(a, b, edge_id=eid, traveltime=length)
    return g


def _shortest_path(g, edge_by_pair, edges, entry: str, exit_: str):
    """Returns (path_nodes, path_edges), or (None, None) if unreachable."""
    src, dst = edges[entry][0], edges[exit_][1]
    try:
        path_nodes = nx.shortest_path(g, src, dst, weight="traveltime")
    except nx.NetworkXNoPath:
        return None, None
    path_edges = [edge_by_pair[(path_nodes[i], path_nodes[i + 1])] for i in range(len(path_nodes) - 1)]
    return path_nodes, path_edges


# --------------------------------------------------------------------------
# Per-OD composition: interpolate between nominal (uniform) shares and a
# documented "local vs arterial" archetype, driven by how many
# intersections an OD pair's shortest path crosses. Topology-agnostic --
# the same rule applies to the S1 row and the S2 grid.
# --------------------------------------------------------------------------

# Directional archetypes reflecting the patterns in the Phase 1b prompt
# (minor/side approaches two-wheeler-dominated; buses and trucks
# concentrated on the through-arterial; cars over-represented on the
# arterial). NOT from a cited source -- flagged in PAPER_CHANGELOG.md, same
# as the base fleet shares in configs/default.yaml. Fixed here deliberately
# and not retuned after seeing the HAP/MP disagreement rate.
LOCAL_ARCHETYPE = {
    "twowheeler": 0.70, "car": 0.20, "auto": 0.08, "bus": 0.01, "truck": 0.01,
}
ARTERIAL_ARCHETYPE = {
    "twowheeler": 0.15, "car": 0.45, "auto": 0.08, "bus": 0.20, "truck": 0.12,
}


def classify_od_pairs(
    nodes: Dict[str, Tuple[float, float, str]],
    edges: Dict[str, Tuple[str, str]],
    od_pairs: List[Tuple[str, str]],
):
    """Returns (path_nodes_list, path_edges_list, arterial_fractions).

    arterial_fractions[k] in [0,1]: the number of intersections OD pair k's
    shortest path crosses, min-max normalised across this scenario's OD set
    (0 = shortest/most local-turning, 1 = longest/most through-arterial).
    """
    g = _build_graph(nodes, edges)
    edge_by_pair = {(a, b): eid for eid, (a, b) in edges.items()}
    path_nodes_list, path_edges_list, lengths = [], [], []
    for entry, exit_ in od_pairs:
        pn, pe = _shortest_path(g, edge_by_pair, edges, entry, exit_)
        path_nodes_list.append(pn)
        path_edges_list.append(pe)
        lengths.append(sum(1 for n in pn if n.startswith("n")) if pn else 0)

    lo, hi = min(lengths), max(lengths)
    if hi > lo:
        fractions = [(n - lo) / (hi - lo) for n in lengths]
    else:
        fractions = [0.5 for _ in lengths]
    return path_nodes_list, path_edges_list, fractions


def od_class_shares(
    fleet: Fleet, fractions: List[float], dispersion: float
) -> List[Dict[str, float]]:
    """shares_k = (1-d)*nominal + d*archetype(t_k). At d=0 every OD gets
    exactly the nominal shares (today's uniform behaviour), byte for byte."""
    nominal = {name: c.share for name, c in fleet.classes.items()}
    shares = []
    for t in fractions:
        archetype = {
            v: (1 - t) * LOCAL_ARCHETYPE[v] + t * ARTERIAL_ARCHETYPE[v] for v in nominal
        }
        shares.append(
            {v: (1 - dispersion) * nominal[v] + dispersion * archetype[v] for v in nominal}
        )
    return shares


# --------------------------------------------------------------------------
# Demand: per-OD vType distributions + two-peak boundary OD flows
# --------------------------------------------------------------------------


def _vtype_distribution_xml(fleet: Fleet, cfg: dict, od_shares: List[Dict[str, float]]) -> str:
    """One <vTypeDistribution> per OD pair -- shares vType geometry across
    ODs but not the `probability` (composition) attribute, since vType ids
    must be unique per SUMO route file, hence the per-OD id suffix."""
    lat = cfg["fleet"]["lat_alignment"]
    lcs = cfg["fleet"]["lc_sublane"]
    blocks = []
    for k, shares in enumerate(od_shares):
        rows = []
        for name, c in fleet.classes.items():
            rows.append(
                f'    <vType id="{name}_od{k}" vClass="{c.sumo_class}" '
                f'length="{c.length}" width="{c.width}" '
                f'minGap="{c.min_gap}" minGapLat="{c.min_gap_lat}" '
                f'maxSpeed="{c.max_speed_ms:.3f}" accel="{c.accel}" '
                f'decel="{c.decel}" sigma="0.5" '
                f'latAlignment="{lat.get(name, "center")}" '
                f'lcSublane="{lcs.get(name, 0.5)}" '
                f'probability="{shares[name]}" '
                f'carFollowModel="Krauss" laneChangeModel="SL2015"/>'
            )
        blocks.append(
            f'  <vTypeDistribution id="fleet_od{k}">\n' + "\n".join(rows) + "\n  </vTypeDistribution>"
        )
    return "\n".join(blocks)


# Two local peaks across the episode (paper: "two-peak diurnal profile").
_PEAK_MULTIPLIERS = [0.5, 0.8, 1.3, 0.9, 1.3, 0.6]


def _od_pairs(entry_edges: List[str], exit_edges: List[str]) -> List[Tuple[str, str]]:
    """Deterministic through-ish OD pairing: rotate exits by half the list so
    an entry rarely maps back onto the exit at the same stub."""
    n = len(entry_edges)
    half = max(1, n // 2)
    rotated_exits = exit_edges[half:] + exit_edges[:half]
    return list(zip(entry_edges, rotated_exits))


def _routes_xml(
    fleet: Fleet,
    cfg: dict,
    od_pairs: List[Tuple[str, str]],
    od_shares: List[Dict[str, float]],
    base_veh_per_hour: float,
    demand_scale: float,
) -> str:
    episode_s = cfg["demand"]["episode_length_s"]
    n_buckets = len(_PEAK_MULTIPLIERS)
    bucket_s = episode_s / n_buckets

    # SUMO requires <flow>/<vehicle> elements sorted by `begin` time in the
    # route file -- anything out of order relative to what it has already
    # read is SILENTLY DROPPED (a warning is printed, but nothing raises,
    # and that warning is invisible wherever --no-warnings is set, as it is
    # in src/env.py). Looping buckets in the OUTER loop and OD pairs in the
    # INNER loop keeps `begin` globally non-decreasing across the whole
    # file; the reverse order (OD-outer, bucket-inner, as this used to be)
    # silently discarded 5 of every 6 flows for every OD pair after the
    # first -- see PAPER_CHANGELOG.md.
    flows = []
    fid = 0
    for b in range(n_buckets):
        begin = int(b * bucket_s)
        end = int((b + 1) * bucket_s)
        vph = base_veh_per_hour * _PEAK_MULTIPLIERS[b] * demand_scale
        for k, (entry, exit_) in enumerate(od_pairs):
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


def _sumocfg_xml(net_file: str, route_file: str, cfg: dict) -> str:
    end = int(cfg["demand"]["episode_length_s"]) + 600
    return (
        "<configuration>\n"
        "  <input>\n"
        f'    <net-file value="{net_file}"/>\n'
        f'    <route-files value="{route_file}"/>\n'
        "  </input>\n"
        "  <time>\n"
        '    <begin value="0"/>\n'
        f'    <end value="{end}"/>\n'
        "  </time>\n"
        "  <processing>\n"
        '    <time-to-teleport value="-1"/>\n'
        "  </processing>\n"
        "</configuration>\n"
    )


# --------------------------------------------------------------------------
# Movement-demand sidecar: decompose every OD flow's shortest path into
# per-intersection (in_edge->out_edge) movements, so FixedTime can
# Webster-tune against REAL demand (both volume and composition) instead of
# guessing.
# --------------------------------------------------------------------------


def compute_movement_demand(
    fleet: Fleet,
    od_pairs: List[Tuple[str, str]],
    path_nodes_list: List[Optional[List[str]]],
    path_edges_list: List[Optional[List[str]]],
    od_shares: List[Dict[str, float]],
    base_veh_per_hour: float,
    demand_scale: float,
) -> Dict[str, Dict[str, dict]]:
    """{intersection_node_id: {"in_edge->out_edge": {"vph": ..., "mean_rho": ...}}}.

    mean_rho is the vph-weighted average of each contributing OD's own
    composition-weighted rho -- a movement fed by more than one OD pair (a
    through OD and a local OD both crossing the same intersection) gets the
    correct blend, not a single global mean, which is what FixedTime needs
    once composition is per-OD rather than uniform.
    """
    avg_mult = sum(_PEAK_MULTIPLIERS) / len(_PEAK_MULTIPLIERS)
    avg_vph = base_veh_per_hour * demand_scale * avg_mult
    rho = fleet.rho

    vph_acc: Dict[str, Dict[str, float]] = {}
    rho_vph_acc: Dict[str, Dict[str, float]] = {}
    for path_nodes, path_edges, shares in zip(path_nodes_list, path_edges_list, od_shares):
        if path_edges is None:
            continue
        od_mean_rho = sum(rho[v] * shares[v] for v in shares)
        for k in range(1, len(path_edges)):
            node = path_nodes[k]
            if not node.startswith("n"):
                continue
            mv = f"{path_edges[k - 1]}->{path_edges[k]}"
            vph_acc.setdefault(node, {})
            vph_acc[node][mv] = vph_acc[node].get(mv, 0.0) + avg_vph
            rho_vph_acc.setdefault(node, {})
            rho_vph_acc[node][mv] = rho_vph_acc[node].get(mv, 0.0) + avg_vph * od_mean_rho

    demand: Dict[str, Dict[str, dict]] = {}
    for node, mvs in vph_acc.items():
        demand[node] = {}
        for mv, vph in mvs.items():
            mean_rho = rho_vph_acc[node][mv] / vph if vph > 0 else 0.0
            demand[node][mv] = {"vph": vph, "mean_rho": mean_rho}
    return demand


# --------------------------------------------------------------------------
# Fleet composition diagnostic (printed, never auto-corrected)
# --------------------------------------------------------------------------


def print_passenger_share_breakdown(fleet: Fleet) -> None:
    """Vehicle-share vs passenger-share side by side. Flags composition
    skew (e.g. buses at a small vehicle share but a large passenger share)
    without silently changing configs/default.yaml -- see PAPER_CHANGELOG.md,
    these base shares need a cited source, not a code-side fix."""
    weighted = {n: c.share * c.occupancy for n, c in fleet.classes.items()}
    total = sum(weighted.values())
    print("Fleet composition (vehicle share -> passenger share):")
    for n, c in fleet.classes.items():
        pax_share = weighted[n] / total if total > 0 else float("nan")
        print(f"    {n:12s} {c.share:5.1%} veh  ->  {pax_share:5.1%} pax  (occupancy {c.occupancy:g})")
    print()


# --------------------------------------------------------------------------
# Per-scenario driver
# --------------------------------------------------------------------------


def build_scenario(
    name: str,
    rows: int,
    cols: int,
    spacing: float,
    cfg: dict,
    outdir: Path,
    lefthand: bool,
    demand_scale: float,
    composition_dispersion: float,
    lanes: int = 3,
    lane_width: float = 3.5,
    speed_ms: float = 13.89,
    base_veh_per_hour: float = 300.0,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    nodes, edges, entry_edges, exit_edges = build_topology(
        rows, cols, spacing, stub_len=spacing
    )
    nodes_xml = _nodes_xml(nodes)
    edges_xml = _edges_xml(edges, lanes, lane_width, speed_ms)

    net_path = outdir / f"{name}.net.xml"
    netconvert_build(outdir, nodes_xml, edges_xml, net_path, lefthand)

    od_pairs = _od_pairs(entry_edges, exit_edges)
    path_nodes_list, path_edges_list, fractions = classify_od_pairs(nodes, edges, od_pairs)

    fleet = Fleet.from_config(cfg)
    od_shares = od_class_shares(fleet, fractions, composition_dispersion)

    routes_xml = _routes_xml(fleet, cfg, od_pairs, od_shares, base_veh_per_hour, demand_scale)
    route_path = outdir / f"{name}.rou.xml"
    route_path.write_text(routes_xml)

    cfg_path = outdir / f"{name}.sumocfg"
    cfg_path.write_text(_sumocfg_xml(net_path.name, route_path.name, cfg))

    demand = compute_movement_demand(
        fleet, od_pairs, path_nodes_list, path_edges_list, od_shares,
        base_veh_per_hour, demand_scale,
    )
    (outdir / "movement_demand.json").write_text(json.dumps(demand, indent=2))

    od_table = [
        {
            "entry": e, "exit": x,
            "path_length_intersections": (
                sum(1 for n in pn if n.startswith("n")) if pn else None
            ),
            "arterial_fraction": t,
            "shares": s,
        }
        for (e, x), pn, t, s in zip(od_pairs, path_nodes_list, fractions, od_shares)
    ]
    (outdir / "od_composition.json").write_text(json.dumps(od_table, indent=2))

    n_tls = sum(1 for _, (_, _, t) in nodes.items() if t == "traffic_light")
    n_movements = sum(len(v) for v in demand.values())
    print(
        f"  {name}: {n_tls} intersections, {len(entry_edges)} boundary "
        f"entries, {n_movements} demanded movements, scale={demand_scale:.2f}, "
        f"dispersion={composition_dispersion:.2f}, net={net_path.name}, "
        f"cfg={cfg_path.name}"
    )


def _parse_bool(s: str) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y")


def resolve_demand_scale(cfg: dict, scenario_key: str, override: Optional[float]) -> float:
    """CLI override wins; else the calibrated demand.scale_nominal.<scenario>
    (scripts/calibrate_demand.py); else 1.0 with a printed note."""
    if override is not None:
        return override
    nominal = (cfg.get("demand", {}) or {}).get("scale_nominal") or {}
    val = nominal.get(scenario_key)
    if val is not None:
        return float(val)
    print(
        f"  (no calibrated demand.scale_nominal.{scenario_key} yet -- using "
        f"1.0; run scripts/calibrate_demand.py to calibrate)"
    )
    return 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--out", default="nets")
    ap.add_argument("--scenario", choices=["s1", "s2", "bengaluru", "all"], default="all")
    ap.add_argument("--bengaluru-osm", default="nets/bengaluru/bengaluru_corridor.osm")
    ap.add_argument("--lefthand", type=_parse_bool, default=True)
    ap.add_argument("--demand-scale", type=float, default=None)
    ap.add_argument("--composition-dispersion", type=float, default=None)
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    outbase = Path(args.out)

    fleet = Fleet.from_config(cfg)
    print_passenger_share_breakdown(fleet)

    dispersion = (
        args.composition_dispersion
        if args.composition_dispersion is not None
        else cfg["demand"].get("composition_dispersion", 0.5)
    )

    if args.scenario in ("s1", "all"):
        s1 = cfg["scenarios"]["s1_arterial"]
        print("Scenario 1: arterial")
        build_scenario(
            "arterial5", 1, s1["n_intersections"], s1["spacing_m"], cfg,
            outbase / "arterial5", args.lefthand,
            resolve_demand_scale(cfg, "s1_arterial", args.demand_scale),
            dispersion,
        )

    if args.scenario in ("s2", "all"):
        s2 = cfg["scenarios"]["s2_grid"]
        print("Scenario 2: grid")
        build_scenario(
            "grid4x4", s2["rows"], s2["cols"], s2["spacing_m"], cfg,
            outbase / "grid4x4", args.lefthand,
            resolve_demand_scale(cfg, "s2_grid", args.demand_scale),
            dispersion,
        )

    if args.scenario == "bengaluru":
        print("Scenario 3: Bengaluru corridor (Phase 6)")
        osm_path = Path(args.bengaluru_osm)
        if not osm_path.exists():
            raise FileNotFoundError(f"Bengaluru corridor .osm not found: {osm_path}")
        ben_dir = outbase / "bengaluru"

        # Stage 1: crop (coherence fix -- drops the disconnected straggler TLS)
        cropped_net = ben_dir / "bengaluru_cropped.net.xml"
        netconvert_build_bengaluru(osm_path, cropped_net, geo_boundary=BENGALURU_CROP_BOX)
        crop_report = validate_bengaluru_net(cropped_net)
        print(f"  [crop]  junctions={crop_report['n_junctions']} edges={crop_report['n_edges']} "
              f"TLS={crop_report['n_tls_valid']}/{crop_report['n_tls_total']} "
              f"valid={crop_report['valid']}")

        # Stage 2: prune sprawl (arterial + one feeder layer only) AND
        # exclude the three-node complex (P4c-16) in the same pass
        keep_file = ben_dir / "bengaluru_keep_edges.txt"
        feeder_report = compute_feeder_keep_list(
            cropped_net, keep_file, exclude_nodes=frozenset(BENGALURU_EXCLUDE_TLS_NODES),
        )
        print(f"  [prune] arterial={feeder_report['n_arterial']} "
              f"feeder={feeder_report['n_feeder']} "
              f"kept={feeder_report['n_kept']}/{feeder_report['n_edges_total']} "
              f"excluded_by_node={feeder_report['n_excluded_by_node']}")

        pruned_net = ben_dir / "bengaluru_pruned.net.xml"
        prune_via_plain_reimport(cropped_net, keep_file, pruned_net, ben_dir / "_plain")

        # Stage 3: remove specific turning movements found by the below-
        # capacity-floor health check (P4c-16) -- a network-level fix, not
        # a demand-side one; see BENGALURU_REMOVE_CONNECTIONS's docstring.
        out_net = ben_dir / "bengaluru.net.xml"
        n_removed = remove_connections(pruned_net, BENGALURU_REMOVE_CONNECTIONS, out_net, ben_dir / "_plain2")
        print(f"  [connections] removed {n_removed}/{len(BENGALURU_REMOVE_CONNECTIONS)} "
              f"targeted turning movement(s): {BENGALURU_REMOVE_CONNECTIONS}")
        if n_removed != len(BENGALURU_REMOVE_CONNECTIONS):
            print(f"  !! expected to remove {len(BENGALURU_REMOVE_CONNECTIONS)} connection(s), "
                  f"actually removed {n_removed} -- a target line was not found; investigate "
                  f"before trusting this build (the net may have changed upstream).")

        report = validate_bengaluru_net(out_net)
        print(f"  [final] junctions={report['n_junctions']} edges={report['n_edges']}")
        print(f"  TLS: {report['n_tls_valid']} valid / {report['n_tls_total']} total "
              f"({report['n_tls_invalid']} invalid: {report['invalid_tls_ids']})")
        print(f"  isolated junctions: {report['n_isolated_junctions']}")
        print(f"  zero-lane edges: {report['n_zero_lane_edges']}")
        print(f"  VALID: {report['valid']}")
        print(f"  FINAL VALID TLS COUNT: {report['n_tls_valid']}")
        print(f"  EDGE COUNT: before(cropped)={crop_report['n_edges']} after(pruned)={report['n_edges']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
