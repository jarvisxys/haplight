"""
HAPLightEnv -- SUMO wrapper (PLAN.md Phase 1).

Movements/phases are read from the live TLS program (traci.trafficlight.
getControlledLinks / getAllProgramLogics), not parsed from net XML or
assumed from build_nets.py's lane layout -- this file makes zero assumption
about how many phases an intersection has. SUMO's own program timer is
bypassed entirely: every sim step this env drives the TLS directly via
setRedYellowGreenState, exactly like scripts/calibrate.py's SaturationRun
already does, so yellow/all-red clearance stays fully internal to step().

Two queue channels, by construction, not by convention:
  - true_queues / true_w are built ONLY from traci ground truth (raw class
    counts on tracked lanes) -- this code path never calls into
    SensingModel. They feed metrics.py, the reward (Eq. 12 has no hats on
    w_m), and offline verification. Never the policy's observation.
  - x_hat / u_hat / counts_hat / running_counts_hat are built by routing
    the SAME raw counts through SensingModel (dropout, misclassification,
    lognormal area noise, catchment bias) before weighting. This is what
    the observation (Eq. 7) and the classical baselines in
    src/controllers.py are driven from.
Movement attribution is LANE-based (which lane a vehicle currently
occupies), not route-based -- a real camera can see lane occupancy, not a
SUMO vehicle's route object, and the paper's x_m is defined as counts "in
the catchment region of m". Lanes shared by more than one turning movement
(SUMO consolidates lanes when 3 physical lanes must serve >3 directions)
therefore contribute to more than one movement's count; that is an honest
reflection of what a lane-level detector could resolve, not a bug.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.hap import (  # noqa: E402
    Fleet,
    movement_weight,
    occupied_area,
    saturation_flow,
    weighted_queue_from_area,
    weighted_queue_from_counts,
)
from src.sensing import SensingModel  # noqa: E402

# ---------------------------------------------------------------------------
# SUMO bootstrap
# ---------------------------------------------------------------------------


def _ensure_sumo_binaries_on_path() -> None:
    """Binaries (sumo/sumo-gui, for the traci-subprocess backend) need to be
    on PATH regardless of which Python backend we end up importing. Prefer
    $SUMO_HOME if it looks real; otherwise fall back to the installed `sumo`
    pip package's own location, which is authoritative regardless of a
    stale/inherited SUMO_HOME env var."""
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


def bootstrap_sumo(prefer_libsumo: bool = True):
    """Returns (traci_module, backend_name)."""
    _ensure_sumo_binaries_on_path()
    if prefer_libsumo:
        try:
            import libsumo as traci  # type: ignore

            return traci, "libsumo"
        except ImportError:
            pass
    try:
        import traci  # type: ignore

        return traci, "traci"
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Neither libsumo nor traci importable.\n"
            "  pip install eclipse-sumo libsumo\n"
            f"(underlying error: {exc})"
        )


# ---------------------------------------------------------------------------


class HAPLightEnv:
    """SUMO wrapper. One instance = one network = one episode at a time."""

    def __init__(
        self,
        net_dir: str,
        cfg: dict,
        fleet: Fleet,
        seed: int = 0,
        eta: float = 0.0,
        estimator: str = "area",
        gui: bool = False,
        use_libsumo: bool = True,
        sublane_simulation: bool = True,
        advanced_mp_running_demand: bool = False,
    ):
        self.net_dir = Path(net_dir)
        self.cfg = cfg
        self.fleet = fleet
        self.eta = float(eta)
        self.estimator = estimator
        self.gui = gui
        self.use_libsumo = use_libsumo
        self.sublane_simulation = sublane_simulation
        # PAPER_CHANGELOG P5-1: opt-in, default False (every existing
        # validated result is byte-for-byte unaffected). When True,
        # Advanced-MP's running-demand term (d(s), Zhang et al.) is
        # computed once per step from a cached/subscribed channel in
        # _measure() instead of live per-vehicle traci queries -- see
        # running_demand_hat's docstring for why this is exact, not an
        # approximation, for this codebase's own scenario geometry.
        self.advanced_mp_running_demand = advanced_mp_running_demand
        self._lane_max_speed: Dict[str, float] = {}
        self._lane_to_edge: Dict[str, str] = {}  # P5-2: lane -> its OWN edge
        self._advanced_mp_radius: Dict[str, float] = {}  # edge -> subscribeContext radius
        self._per_lane_running_fixed_range: Dict[str, float] = {}

        # Phase 1c per-movement estimator calibration (PAPER_CHANGELOG
        # P1c-1): scripts/calibrate_estimator.py writes a_bar_per_movement.
        # json into a scenario's net_dir, mapping movement id -> a_bar_m
        # fitted to that movement's own realised composition (the simulated
        # stand-in for a one-hour classified count at camera commissioning).
        # Falls back to the fleet's single global a_bar (Fleet.a_bar) for
        # any movement not present in the file, and for every movement when
        # the file itself is absent -- the pre-Phase-1c behaviour.
        a_bar_path = self.net_dir / "a_bar_per_movement.json"
        if a_bar_path.exists():
            self._a_bar_per_movement: Dict[str, float] = json.loads(a_bar_path.read_text())
        else:
            self._a_bar_per_movement = {}
            print(
                f"[HAPLightEnv] no a_bar_per_movement.json found in {self.net_dir} "
                "-- falling back to the global calibrated a_bar for every movement "
                "(run scripts/calibrate_estimator.py to commission per-movement "
                "calibration)."
            )

        sig = cfg["signal"]
        self.sim_step_s = float(sig["sim_step_s"])
        self.dt = float(sig["decision_interval_s"])
        self.g_min = float(sig["min_green_s"])
        self.g_max = float(sig["max_green_s"])
        self.yellow_s = float(sig["yellow_s"])
        self.all_red_s = float(sig["all_red_s"])
        self.t_y = self.yellow_s + self.all_red_s
        self.lateral_resolution_m = float(sig["lateral_resolution_m"])

        hap_cfg = cfg["hap"]
        self.stop_speed = float(hap_cfg["stop_speed_threshold_ms"])
        self.catchment_len = float(hap_cfg["catchment_length_m"])
        self.running_horizon_s = float(hap_cfg["running_horizon_s"])

        self.episode_length_s = float(cfg["demand"]["episode_length_s"])

        obs_cfg = cfg["rl"]["obs"]
        self.obs_x_ref = float(obs_cfg["x_ref"])
        self.obs_mu_ref = float(obs_cfg["mu_ref"])
        self.obs_clip = float(obs_cfg["clip"])
        self.n_neighbours = int(obs_cfg["n_neighbours"])

        self.c_switch = float(cfg["rl"]["reward"]["c_switch"])
        self.reward_form = cfg["rl"]["reward"].get("form", "pressure_all")
        assert self.reward_form in ("pressure_all", "total_queue", "served_pressure", "pressure_raw"), (
            f"unknown rl.reward.form {self.reward_form!r}"
        )

        # Three independent, reproducible seed streams (paper robustness
        # sweeps must not let SUMO's own stochastic realisation and the
        # sensing-noise draw be correlated through a shared seed).
        ss = np.random.SeedSequence(seed)
        sumo_ss, sensing_ss, env_ss = ss.spawn(3)
        self._sumo_seed = int(sumo_ss.generate_state(1)[0] % (2**31 - 1))
        self._sensing_ss = sensing_ss
        self._rng = np.random.default_rng(env_ss)

        self._traci = None
        self._tc = None
        self.backend: Optional[str] = None
        self._started = False
        self._sim_time = 0.0

        # static geometry, discovered once and cached across episodes
        self._topology_ready = False
        self.intersections: List[str] = []
        self.phases: Dict[str, List[List[str]]] = {}
        self.movements: Dict[str, List[str]] = {}
        self.mu: Dict[str, Dict[str, float]] = {}
        self.storage: Dict[str, Dict[str, float]] = {}
        self.edge_capacity: Dict[str, float] = {}
        self.downstream_by_edge: Dict[str, List[Tuple[str, str]]] = {}
        self._vtype_class_cache: Dict[str, str] = {}
        self._n_lanes: Dict[str, Dict[str, int]] = {}
        self._link_mv: Dict[str, List[Optional[str]]] = {}
        self._lane_sets: Dict[str, Dict[str, List[str]]] = {}  # i -> mv -> [lanes]
        self._mv_phases: Dict[str, Dict[str, List[int]]] = {}  # i -> mv -> [phase idx]
        self._catchment_edges: List[str] = []
        self._lane_length: Dict[str, float] = {}
        self._n_lanes_edge: Dict[str, int] = {}
        self._neighbours: Dict[str, List[str]] = {}

        # per-episode dynamic state
        self._current_phase_idx: Dict[str, int] = {}
        self._green_elapsed: Dict[str, float] = {}
        self._tau: Dict[str, Dict[int, float]] = {}
        self._sensing: Optional[SensingModel] = None
        self._vehicle_shadow: Dict[str, dict] = {}
        self._completed_trips: List[dict] = []
        self._queue_history: List[Dict[str, float]] = []
        self._gmax_events = 0
        self._gmax_total = 0
        self._green_steps = 0
        self._total_steps = 0
        self._last_action: Dict[str, int] = {}

        self.action_masks: Dict[str, np.ndarray] = {}
        self.true_queues: Dict[str, Dict[str, float]] = {}
        self.info: dict = {}

    # -- lifecycle ------------------------------------------------------

    def _find_sumocfg(self) -> Path:
        matches = sorted(self.net_dir.glob("*.sumocfg"))
        if not matches:
            raise FileNotFoundError(f"No .sumocfg found in {self.net_dir}")
        return matches[0]

    def close(self) -> None:
        if self._started:
            self._traci.close()
            self._started = False

    def reset(self) -> Dict[str, np.ndarray]:
        if self._started:
            self._traci.close()
            self._started = False

        if self._traci is None:
            self._traci, self.backend = bootstrap_sumo(self.use_libsumo)
            self._tc = self._traci.constants

        binary = "sumo-gui" if self.gui else "sumo"
        cmd = [
            binary,
            "-c", str(self._find_sumocfg()),
            "--step-length", str(self.sim_step_s),
            "--time-to-teleport", "-1",
            # deliberately NOT --no-warnings: that flag hid a real bug for a
            # long time (route file not sorted by departure time silently
            # dropped 5/6 of every OD pair's flows -- see PAPER_CHANGELOG.md
            # P1b-6). --no-step-log only silences the routine per-tick
            # progress line, not actual warnings, so it stays.
            "--no-step-log", "true",
            "--seed", str(self._sumo_seed),
        ]
        if self.sublane_simulation:
            # SUMO's sublane simulation (continuous lateral position) is
            # opt-in via --lateral-resolution, and once on, EVERY vType must
            # use a sublane-compatible laneChangeModel -- LC2013 raises a
            # fatal error under it. Production nets always use SL2015, so
            # this stays True by default; False exists only for the
            # SL2015-vs-LC2013 runtime comparison (Phase 4 pre-check,
            # PAPER_CHANGELOG P3-2), which needs a route file with
            # laneChangeModel="LC2013" run through this same code path for
            # an apples-to-apples timing comparison.
            cmd += ["--lateral-resolution", str(self.lateral_resolution_m)]
        self._traci.start(cmd)
        self._started = True

        if not self._topology_ready:
            self._discover_topology()
            self._topology_ready = True
        # Context subscriptions live on the traci/libsumo CONNECTION, not
        # the network -- close()+start() above is a brand-new simulation
        # session with no memory of subscriptions made on a prior one, so
        # this must be reissued on every reset(), not guarded behind
        # _topology_ready (empty subscriptions silently measure every
        # queue as zero -- no error, just wrong from episode 2 onward).
        self._subscribe_context()

        all_movements = sorted({mv for movs in self.movements.values() for mv in movs})
        self._sensing = SensingModel(
            self.cfg, all_movements, eta=self.eta,
            rng=np.random.default_rng(self._sensing_ss),
        )

        self._sim_time = 0.0
        self._current_phase_idx = {i: 0 for i in self.intersections}
        self._green_elapsed = {i: 0.0 for i in self.intersections}
        self._tau = {
            i: {p: 0.0 for p in range(len(self.phases[i]))} for i in self.intersections
        }
        self._last_action = dict(self._current_phase_idx)
        self._vehicle_shadow = {}
        self._completed_trips = []
        self._queue_history = []
        self._gmax_events = 0
        self._gmax_total = 0
        self._green_steps = 0
        self._total_steps = 0

        for i in self.intersections:
            state = self._phase_state_string(i, self._current_phase_idx[i])
            self._traci.trafficlight.setRedYellowGreenState(i, state)

        obs, info = self._observe(gmax_active={i: False for i in self.intersections})
        self.info = info
        return obs

    # -- topology discovery ----------------------------------------------

    def _discover_topology(self) -> None:
        traci = self._traci
        tls_ids = list(traci.trafficlight.getIDList())
        self.intersections = tls_ids

        edge_of_lane: Dict[str, str] = {}

        for i in tls_ids:
            links = traci.trafficlight.getControlledLinks(i)
            link_mv: List[Optional[str]] = []
            lane_sets: Dict[str, List[str]] = {}
            for grp in links:
                if not grp:
                    link_mv.append(None)
                    continue
                from_lane, to_lane, _via = grp[0]
                in_edge = edge_of_lane.get(from_lane) or traci.lane.getEdgeID(from_lane)
                out_edge = edge_of_lane.get(to_lane) or traci.lane.getEdgeID(to_lane)
                edge_of_lane[from_lane] = in_edge
                edge_of_lane[to_lane] = out_edge
                mv = f"{in_edge}->{out_edge}"
                link_mv.append(mv)
                lane_sets.setdefault(mv, [])
                if from_lane not in lane_sets[mv]:
                    lane_sets[mv].append(from_lane)
            self._link_mv[i] = link_mv
            self._lane_sets[i] = lane_sets

            logics = traci.trafficlight.getAllProgramLogics(i)
            prog = logics[0]
            phi: List[List[str]] = []
            seen_keys = set()
            for ph in prog.phases:
                state = ph.state
                if "y" in state.lower():
                    continue
                if not any(ch in "Gg" for ch in state):
                    continue
                seen_mv = []
                seen_set = set()
                for idx, ch in enumerate(state):
                    if ch in "Gg" and idx < len(link_mv) and link_mv[idx] is not None:
                        mv = link_mv[idx]
                        if mv not in seen_set:
                            seen_set.add(mv)
                            seen_mv.append(mv)
                key = tuple(sorted(seen_mv))
                if not seen_mv or key in seen_keys:
                    continue
                seen_keys.add(key)
                phi.append(seen_mv)
            self.phases[i] = phi
            self.movements[i] = sorted({mv for movs in phi for mv in movs})

            mv_phases: Dict[str, List[int]] = {}
            for pidx, movs in enumerate(phi):
                for mv in movs:
                    mv_phases.setdefault(mv, []).append(pidx)
            self._mv_phases[i] = mv_phases

            self._n_lanes[i] = {mv: len(lanes) for mv, lanes in lane_sets.items()}
            self.mu[i] = {}
            self.storage[i] = {}
            for mv, lanes in lane_sets.items():
                width = sum(traci.lane.getWidth(l) for l in lanes)
                self.mu[i][mv] = saturation_flow(width, self.cfg)
                # Physical storage capacity (Phase 1b), from the movement's
                # ACTUAL edge length -- not catchment_length_m, which is a
                # sensing-zone constant (200m) unrelated to how long the
                # edge actually is (~300-400m here); using it would over-
                # or under-state overflow depending on scenario spacing.
                # Geometric area / assumes perfect packing, so this is an
                # UPPER BOUND on real storage, not an exact capacity.
                edge_length = traci.lane.getLength(lanes[0])
                self.storage[i][mv] = weighted_queue_from_area(
                    self.fleet, edge_length * width,
                    a_bar=self._a_bar_per_movement.get(mv, self.fleet.a_bar),
                )

        # catchment edges: union of every movement's in-edge and out-edge,
        # network-wide (out-edges double as the "downstream aggregate" for
        # whichever movement feeds them).
        edges = set()
        for i in tls_ids:
            for mv in self.movements[i]:
                a, b = mv.split("->")
                edges.add(a)
                edges.add(b)
        self._catchment_edges = sorted(edges)
        for e in self._catchment_edges:
            n_lanes = traci.edge.getLaneNumber(e)
            self._n_lanes_edge[e] = n_lanes
            edge_max_len = 0.0
            edge_max_speed = 0.0
            for k in range(n_lanes):
                lane_id = f"{e}_{k}"
                lane_len = traci.lane.getLength(lane_id)
                lane_speed = traci.lane.getMaxSpeed(lane_id)
                self._lane_length[lane_id] = lane_len
                self._lane_max_speed[lane_id] = lane_speed  # STATIC (speed limit) -- cache once, never re-query
                self._lane_to_edge[lane_id] = e
                edge_max_len = max(edge_max_len, lane_len)
                edge_max_speed = max(edge_max_speed, lane_speed)
            # PAPER_CHANGELOG P5-1: Advanced-MP's running-demand radius is
            # lane_max_speed * g_max (often >>1000m for urban speed limits
            # and g_max=120s) -- but a vehicle can never be further from
            # the stop line than the LANE'S OWN physical length regardless
            # of that nominal threshold (the original live per-lane query
            # this replaces, src.env.running_count_within_range, only ever
            # iterated vehicles already ON that lane -- the same bound was
            # always implicit there too). Capping the subscribeContext
            # radius at min(lane_max_speed*g_max, edge's own longest lane)
            # is therefore EXACT, not an approximation, and stays cheap
            # (bounded by real network geometry, ~300-400m on S1/S2) rather
            # than requesting a multi-hundred/thousand-metre radius that
            # would pull in many unrelated upstream edges for no benefit.
            self._advanced_mp_radius[e] = min(edge_max_speed * self.g_max, edge_max_len)

        # first-hop neighbours: intersection j is a neighbour of i if some
        # movement of i exits onto an edge that is the in-edge of some
        # movement of j (or vice versa).
        edge_to_tls_in: Dict[str, str] = {}
        for i in tls_ids:
            for mv in self.movements[i]:
                in_edge = mv.split("->")[0]
                edge_to_tls_in[in_edge] = i
        adj: Dict[str, set] = {i: set() for i in tls_ids}
        for i in tls_ids:
            for mv in self.movements[i]:
                out_edge = mv.split("->")[1]
                j = edge_to_tls_in.get(out_edge)
                if j and j != i:
                    adj[i].add(j)
                    adj[j].add(i)
        self._neighbours = {i: sorted(adj[i])[: self.n_neighbours] for i in tls_ids}

        # Physical capacity of each EDGE (not movement), for storage-aware
        # HAP (PAPER_CHANGELOG P4c-1): a movement's downstream headroom is
        # about the edge it discharges onto, not about the movement identity
        # -- an edge with a dedicated through-lane and a dedicated turn-lane
        # is represented by TWO movements at the next intersection (both
        # with this edge as their in_edge), so their storage sums to the
        # edge's total capacity across all its lanes. Static (topology-only,
        # like env.storage itself) -- built once here, reused every step.
        edge_capacity: Dict[str, float] = {}
        downstream_by_edge: Dict[str, List[Tuple[str, str]]] = {}
        for i in tls_ids:
            for mv in self.movements[i]:
                in_edge = mv.split("->")[0]
                edge_capacity[in_edge] = edge_capacity.get(in_edge, 0.0) + self.storage[i][mv]
                downstream_by_edge.setdefault(in_edge, []).append((i, mv))
        self.edge_capacity = edge_capacity
        # PAPER_CHANGELOG P4c-4: per-EDGE aggregation (edge_capacity above)
        # dilutes a narrow, low-capacity turn pocket inside a healthy-
        # looking edge total (confirmed root cause of P4c-3's gate
        # failure) -- this map gives the SPECIFIC (intersection, movement)
        # pairs sharing an edge, so a headroom signal can be computed at
        # movement resolution (worst-of-the-group) instead of edge-wide.
        self.downstream_by_edge = downstream_by_edge

    def _subscribe_context(self) -> None:
        traci = self._traci
        tc = self._tc
        variables = [tc.VAR_LANE_ID, tc.VAR_LANEPOSITION, tc.VAR_SPEED, tc.VAR_TYPE]
        for e in self._catchment_edges:
            # PAPER_CHANGELOG P5-2: ONE radius for every caller, always
            # self.catchment_len. An earlier P5-1 version widened this for
            # the Advanced-MP running-demand channel, on the assumption
            # that a vehicle far along a long edge might otherwise fall
            # outside the context. That assumption was wrong: a vehicle ON
            # edge e is at distance 0 from e's own geometry and is
            # therefore ALWAYS in e's context regardless of radius.
            # Verified directly after the dedup fix -- narrow (200m) vs
            # widened gives 0/1200 mismatches against the live
            # running_count_within_range reference, and narrow is ~9x
            # faster per episode (1.3s vs 11.9s), because the wide radius
            # was pulling in large numbers of far-away vehicles that
            # deduplication then discarded anyway. That redundant work is
            # what made Advanced-MPLight ~1.8x slower to train than every
            # other method.
            traci.edge.subscribeContext(e, tc.CMD_GET_VEHICLE_VARIABLE, self.catchment_len, variables)

    # -- phase/state helpers ----------------------------------------------

    def _phase_state_string(self, i: str, phase_idx: int, char: str = "G") -> str:
        n_links = len(self._link_mv[i])
        chars = ["r"] * n_links
        movs = set(self.phases[i][phase_idx])
        for idx, mv in enumerate(self._link_mv[i]):
            if mv in movs:
                chars[idx] = char
        return "".join(chars)

    def _all_red_string(self, i: str) -> str:
        return "r" * len(self._link_mv[i])

    # -- step ---------------------------------------------------------------

    def step(
        self, actions: Dict[str, int]
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, float], bool, dict]:
        assert self._started, "call reset() before step()"
        traci = self._traci

        # 1. g_max anti-starvation override (per Algorithm 1: still gated by
        #    g_min below -- it is not an unconditional preemption).
        chosen = dict(actions)
        gmax_active = {i: False for i in self.intersections}
        for i in self.intersections:
            starved = [
                p for p in range(len(self.phases[i]))
                if p != self._current_phase_idx[i] and self._tau[i][p] >= self.g_max
            ]
            if starved:
                p_star = max(starved, key=lambda p: self._tau[i][p])
                chosen[i] = p_star
                gmax_active[i] = True

        # 2. g_min hard gate (mask should already enforce this; re-applied
        #    defensively so an out-of-mask action can never violate it).
        final_action: Dict[str, int] = {}
        switching: Dict[str, bool] = {}
        for i in self.intersections:
            want = chosen[i]
            cur = self._current_phase_idx[i]
            if want != cur and self._green_elapsed[i] < self.g_min:
                want = cur
            final_action[i] = want
            switching[i] = want != cur

        # 3. clearance + green, ticked at sim_step_s resolution. A switching
        #    step spends the first yellow_s+all_red_s seconds on clearance;
        #    any remainder of Delta t is real green in the new phase. With
        #    the default config yellow_s+all_red_s == decision_interval_s,
        #    so a switch consumes the whole interval and the new phase's
        #    green starts counting on the NEXT step -- both "advances
        #    Delta t seconds" and "clearance is internal" hold literally.
        # We bypass SUMO's own program timer entirely, so the state must be
        # (re)applied on EVERY tick for EVERY intersection -- setting it only
        # when it changes lets SUMO's underlying default program silently
        # take back over on ticks where we don't call setRedYellowGreenState
        # (this bit calibrate.py's SaturationRun already, hence its
        # unconditional per-step call; matched here for the same reason).
        n_ticks = max(1, round(self.dt / self.sim_step_s))
        elapsed_switch: Dict[str, float] = {i: 0.0 for i in self.intersections if switching[i]}

        for _tick in range(n_ticks):
            for i in self.intersections:
                if not switching[i]:
                    traci.trafficlight.setRedYellowGreenState(
                        i, self._phase_state_string(i, self._current_phase_idx[i])
                    )
                    continue
                e = elapsed_switch[i]
                if e < self.yellow_s:
                    traci.trafficlight.setRedYellowGreenState(
                        i, self._phase_state_string(i, self._current_phase_idx[i], char="y")
                    )
                elif e < self.t_y:
                    traci.trafficlight.setRedYellowGreenState(i, self._all_red_string(i))
                else:
                    traci.trafficlight.setRedYellowGreenState(
                        i, self._phase_state_string(i, final_action[i])
                    )
            traci.simulationStep()
            self._sim_time += self.sim_step_s
            for i in elapsed_switch:
                elapsed_switch[i] += self.sim_step_s
            self._tick_vehicles()

        # 4. bookkeeping: phase/green/tau after the interval
        for i in self.intersections:
            if switching[i]:
                leftover_green = max(0.0, self.dt - self.t_y)
                self._current_phase_idx[i] = final_action[i]
                self._green_elapsed[i] = leftover_green
            else:
                self._green_elapsed[i] += self.dt
            for p in range(len(self.phases[i])):
                if p == self._current_phase_idx[i]:
                    self._tau[i][p] = 0.0
                else:
                    self._tau[i][p] += self.dt

            self._total_steps += 1
            got_green = (not switching[i]) or (self.dt > self.t_y)
            if got_green:
                self._green_steps += 1
            self._gmax_total += 1
            if gmax_active[i]:
                self._gmax_events += 1

        obs, info = self._observe(gmax_active)

        reward = self._compute_reward(info, switching)

        self._queue_history.append(
            {i: sum(info["true_queues"][i].values()) for i in self.intersections}
        )
        self._last_action = dict(final_action)
        self.info = info

        truncated = self._sim_time >= self.episode_length_s
        return obs, reward, truncated, info

    # -- vehicle bookkeeping (subscriptions, not per-vehicle round trips) --

    def _class_of_vtype(self, vtype_id: str) -> str:
        """build_nets.py generates one vType per (fleet class, OD pair) as
        "{class}_od{k}" (SUMO vType ids must be unique per route file, since
        composition is per-OD -- Phase 1b), so the sampled vehicle's vType
        id is not the class name directly. Cached: computed once per
        distinct vtype id, not per vehicle."""
        cached = self._vtype_class_cache.get(vtype_id)
        if cached is not None:
            return cached
        cls = vtype_id
        for name in self.fleet.names:
            if vtype_id == name or vtype_id.startswith(name + "_od"):
                cls = name
                break
        self._vtype_class_cache[vtype_id] = cls
        return cls

    def _tick_vehicles(self) -> None:
        traci = self._traci
        tc = self._tc

        for vid in traci.simulation.getDepartedIDList():
            self._vehicle_shadow[vid] = {
                "depart": self._sim_time,
                "vclass": self._class_of_vtype(traci.vehicle.getTypeID(vid)),
                "fuel_ml": 0.0,
                "co2_mg": 0.0,
                "waiting": 0.0,
                "timeloss": 0.0,
                # One-off read at departure (not the per-step hot path):
                # how long this vehicle waited OUTSIDE the network before it
                # could be inserted. Large values here mean SUMO is holding
                # back demand invisibly, censoring ATT/AWT (Phase 1b).
                "depart_delay": traci.vehicle.getDepartDelay(vid),
            }
            traci.vehicle.subscribe(
                vid,
                [
                    tc.VAR_ACCUMULATED_WAITING_TIME,
                    tc.VAR_TIMELOSS,
                    tc.VAR_FUELCONSUMPTION,
                    tc.VAR_CO2EMISSION,
                ],
            )

        for vid, res in traci.vehicle.getAllSubscriptionResults().items():
            rec = self._vehicle_shadow.get(vid)
            if rec is None:
                continue
            rec["waiting"] = res.get(tc.VAR_ACCUMULATED_WAITING_TIME, rec["waiting"])
            rec["timeloss"] = res.get(tc.VAR_TIMELOSS, rec["timeloss"])
            rec["fuel_ml"] += res.get(tc.VAR_FUELCONSUMPTION, 0.0) * self.sim_step_s
            rec["co2_mg"] += res.get(tc.VAR_CO2EMISSION, 0.0) * self.sim_step_s

        for vid in traci.simulation.getArrivedIDList():
            rec = self._vehicle_shadow.pop(vid, None)
            if rec is None:
                continue
            rec["arrive"] = self._sim_time
            rec["travel_time"] = rec["arrive"] - rec["depart"]
            self._completed_trips.append(rec)

    def pending_count(self) -> int:
        """Vehicles loaded but not yet inserted (blocked at their source
        edge/lane) -- SUMO holds these OUTSIDE the network, invisible to
        ATT/AWT, which would silently censor those metrics under heavy
        demand (Phase 1b insertion-backlog check)."""
        return len(self._traci.simulation.getPendingVehicles())

    def in_network_count(self) -> int:
        """Vehicles currently active in the simulation (inserted, not yet
        arrived). Paired with pending_count(), this separates 'stuck waiting
        to enter' from 'stuck already inside' when diagnosing whether a
        policy has driven the network into gridlock (PAPER_CHANGELOG P4-3)."""
        return self._traci.vehicle.getIDCount()

    def mean_depart_delay(self) -> float:
        """Mean SUMO insertion delay (time a vehicle waited outside the
        network before SUMO could insert it) over every vehicle recorded so
        far this episode -- both still in-network and already arrived. A
        value that rises over the course of an episode means newly-inserted
        vehicles are waiting longer to get in, i.e. the insertion backlog is
        worsening (PAPER_CHANGELOG P4-3 gridlock diagnostic)."""
        delays = [r["depart_delay"] for r in self._vehicle_shadow.values()]
        delays += [t["depart_delay"] for t in self._completed_trips]
        return float(np.mean(delays)) if delays else float("nan")

    def lane_max_speed(self, i: str, mv: str) -> float:
        """The road's own SUMO speed limit for movement mv (max across its
        lanes) -- Advanced-MP's V_max (Zhang et al., ICML 2022,
        arXiv:2112.10107; PAPER_CHANGELOG P4c-16), the maximum a vehicle
        COULD travel, not any specific vehicle's current speed. Reads the
        `_lane_max_speed` cache populated once in _discover_topology
        (PAPER_CHANGELOG P5-1) -- a lane's speed LIMIT is static for the
        whole episode, so this was always safe to memoise; it just wasn't
        until the Phase 5 Advanced-MPLight state-builder made it a
        per-movement-per-step hot path instead of the classical AdvancedMP
        controller's current-phase-only, low-frequency one."""
        lanes = self._lane_sets[i][mv]
        if not lanes:
            return 0.0
        return max(self._lane_max_speed[lane] for lane in lanes)

    def running_count_within_range(self, i: str, mv: str, max_distance_m: float) -> float:
        """Count of non-stopped vehicles on movement (i, mv)'s lanes within
        `max_distance_m` of the stop line -- Advanced-MP's fixed-effective-
        range demand d(s) (PAPER_CHANGELOG P4c-16), DISTINCT from
        running_counts_hat/x_hat (the sensed observation channel every
        other controller and the RL policy read, which uses each vehicle's
        OWN speed * a fixed running_horizon_s reachability estimate, not a
        shared distance threshold). Live per-vehicle traci query -- the
        CORRECTNESS REFERENCE this codebase's classical `AdvancedMP`
        controller still uses directly (current-phase-only, low-frequency,
        cheap enough there). PAPER_CHANGELOG P5-1: the Phase 5
        Advanced-MPLight RL state-builder calls this for EVERY movement,
        EVERY decision step, across every parallel training worker --
        measured directly to cost ~4x a normal training iteration's
        wall-clock time at that call volume. `running_demand_hat` below is
        the fast, cached alternative for that hot path (opt-in via
        `advanced_mp_running_demand=True`); this method is UNCHANGED and
        remains what `src.controllers.AdvancedMP` uses, so that
        already-validated controller's behaviour is not put at risk by
        this fix."""
        traci = self._traci
        count = 0.0
        for lane in self._lane_sets[i][mv]:
            lane_len = self._lane_length.get(lane)
            if lane_len is None:
                continue
            for vid in traci.lane.getLastStepVehicleIDs(lane):
                speed = traci.vehicle.getSpeed(vid)
                if speed < self.stop_speed:
                    continue  # stopped vehicles are queued demand, not running demand
                dist = lane_len - traci.vehicle.getLanePosition(vid)
                if 0.0 <= dist <= max_distance_m:
                    count += 1.0
        return count

    def running_demand_hat(self, i: str, mv: str) -> float:
        """Fast, cached equivalent of
        `running_count_within_range(i, mv, lane_max_speed(i, mv) * g_max)`
        -- Advanced-MP's own specific usage, not a general-purpose
        arbitrary-max_distance_m API (PAPER_CHANGELOG P5-1). Reads
        `self._per_lane_running_fixed_range`, computed once per step
        inside `_measure()`'s existing per-vehicle subscription pass (zero
        extra traci round-trips), gated behind
        `advanced_mp_running_demand=True` (constructor flag, default
        False -- every other channel/caller is completely unaffected).
        EXACT, not an approximation, for the reason `_advanced_mp_radius`
        documents in `_discover_topology`: a vehicle can never be further
        from the stop line than its own lane's physical length, so
        capping the underlying subscription radius at
        min(lane_max_speed*g_max, lane_length) changes nothing a vehicle
        could ever have been counted for under the live-query version.
        Requires advanced_mp_running_demand=True -- asserts loudly rather
        than silently returning zero if called without it, since a silent
        zero would look like "no running demand" instead of "not
        measured\""""
        assert self.advanced_mp_running_demand, (
            "running_demand_hat requires HAPLightEnv(..., advanced_mp_running_demand=True) "
            "-- the cache it reads is never populated otherwise."
        )
        return sum(
            self._per_lane_running_fixed_range.get(lane, 0.0)
            for lane in self._lane_sets[i][mv]
        )

    def completed_trips(self) -> List[dict]:
        return self._completed_trips

    def true_queue_history(self) -> List[Dict[str, float]]:
        return self._queue_history

    def gmax_activation_rate(self) -> float:
        return self._gmax_events / self._gmax_total if self._gmax_total else float("nan")

    def green_fraction(self) -> float:
        """Fraction of (intersection, decision-step) pairs with >0s of actual
        green this episode -- with the default config a switch costs the
        whole Delta t, so this is worth logging, not just AQL."""
        return self._green_steps / self._gmax_total if self._gmax_total else float("nan")

    # -- measurement: true (ground-truth) and hat (sensed) queues ----------

    def _measure(self):
        traci = self._traci
        tc = self._tc

        per_lane_true: Dict[str, Dict[str, float]] = {}
        per_lane_running: Dict[str, Dict[str, float]] = {}
        per_edge_true: Dict[str, Dict[str, float]] = {}
        per_lane_running_fixed_range: Dict[str, float] = {}  # PAPER_CHANGELOG P5-1

        # PAPER_CHANGELOG P5-2 (measurement correctness): deduplicate across
        # context subscriptions BEFORE accumulating. traci/libsumo's
        # edge.subscribeContext(e, ..., radius) returns every vehicle within
        # `radius` of edge e, so a single vehicle appears in MANY edges'
        # result sets -- measured at EXACTLY 8 on S1 at the default 200m
        # catchment (ratio env/independent-ground-truth = 8.000, min = max =
        # median). Accumulating one row per (edge, vehicle) pair therefore
        # counted every vehicle once per context it happened to fall in.
        # Deduplicating by vehicle id makes each vehicle contribute exactly
        # once, which is what every downstream channel already assumed.
        vehicles: Dict[str, dict] = {}
        for e in self._catchment_edges:
            res = traci.edge.getContextSubscriptionResults(e) or {}
            for vid, v in res.items():
                if vid not in vehicles:
                    vehicles[vid] = v

        for _vid, v in vehicles.items():
                lane = v[tc.VAR_LANE_ID]
                lane_len = self._lane_length.get(lane)
                if lane_len is None:
                    continue
                # The vehicle's OWN edge -- NOT the context edge it was
                # discovered through (P5-2). per_edge_true previously keyed
                # on the loop's context edge, attributing each vehicle to
                # whichever edges' contexts happened to contain it rather
                # than to the edge it is actually on.
                edge = self._lane_to_edge.get(lane)
                dist = lane_len - v[tc.VAR_LANEPOSITION]
                speed = v[tc.VAR_SPEED]
                stopped = speed < self.stop_speed

                # PAPER_CHANGELOG P5-1: Advanced-MP's running-demand count
                # -- non-stopped AND within lane_max_speed*g_max of the
                # stop line (capped at the lane's own physical length,
                # exactly matching running_count_within_range's original
                # per-lane semantics, see _discover_topology). Computed
                # from the SAME per-vehicle subscription record already
                # read above, independent of the catchment_len/
                # running_horizon_s classification below (a different
                # channel, different threshold) -- zero extra traci calls.
                # Gated: only accumulated when opted in, so this loop's
                # per-vehicle cost is unchanged for every other caller.
                if self.advanced_mp_running_demand and not stopped:
                    max_dist = min(
                        self._lane_max_speed.get(lane, 0.0) * self.g_max, lane_len,
                    )
                    if 0.0 <= dist <= max_dist:
                        per_lane_running_fixed_range[lane] = per_lane_running_fixed_range.get(lane, 0.0) + 1.0

                if dist < 0 or dist > self.catchment_len:
                    continue
                vclass = self._class_of_vtype(v[tc.VAR_TYPE])
                if stopped:
                    per_lane_true.setdefault(lane, {})
                    per_lane_true[lane][vclass] = per_lane_true[lane].get(vclass, 0.0) + 1.0
                    if edge is not None:
                        per_edge_true.setdefault(edge, {})
                        per_edge_true[edge][vclass] = per_edge_true[edge].get(vclass, 0.0) + 1.0
                elif dist <= speed * self.running_horizon_s:
                    per_lane_running.setdefault(lane, {})
                    per_lane_running[lane][vclass] = per_lane_running[lane].get(vclass, 0.0) + 1.0
        self._per_lane_running_fixed_range = per_lane_running_fixed_range

        def agg_lanes(lanes: Sequence[str], src: Dict[str, Dict[str, float]]) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for lane in lanes:
                for cls, n in src.get(lane, {}).items():
                    out[cls] = out.get(cls, 0.0) + n
            return out

        true_counts: Dict[str, Dict[str, Dict[str, float]]] = {}
        running_counts: Dict[str, Dict[str, Dict[str, float]]] = {}
        for i in self.intersections:
            true_counts[i] = {}
            running_counts[i] = {}
            for mv in self.movements[i]:
                lanes = self._lane_sets[i][mv]
                true_counts[i][mv] = agg_lanes(lanes, per_lane_true)
                running_counts[i][mv] = agg_lanes(lanes, per_lane_running)

        downstream_true_area = {e: occupied_area(self.fleet, cnts) for e, cnts in per_edge_true.items()}
        downstream_true_x = {
            e: weighted_queue_from_counts(self.fleet, cnts) for e, cnts in per_edge_true.items()
        }
        return true_counts, running_counts, downstream_true_x, downstream_true_area, per_edge_true

    def _observe(self, gmax_active: Dict[str, bool]):
        fleet = self.fleet
        true_counts, running_counts, downstream_true_x, downstream_true_area, per_edge_true = self._measure()

        true_queues: Dict[str, Dict[str, float]] = {}
        true_w: Dict[str, Dict[str, float]] = {}
        x_hat: Dict[str, Dict[str, float]] = {}
        u_hat: Dict[str, Dict[str, float]] = {}
        w_hat: Dict[str, Dict[str, float]] = {}
        counts_hat: Dict[str, Dict[str, Dict[str, float]]] = {}
        running_counts_hat: Dict[str, Dict[str, Dict[str, float]]] = {}
        counts_hat_downstream: Dict[str, Dict[str, Dict[str, float]]] = {}

        for i in self.intersections:
            true_queues[i] = {}
            true_w[i] = {}
            x_hat[i] = {}
            u_hat[i] = {}
            w_hat[i] = {}
            counts_hat[i] = {}
            running_counts_hat[i] = {}
            counts_hat_downstream[i] = {}

            for mv in self.movements[i]:
                out_edge = mv.split("->")[1]
                tcounts = true_counts[i][mv]
                rcounts = running_counts[i][mv]

                # -- TRUE channel: never touches SensingModel --------------
                x_true = weighted_queue_from_counts(fleet, tcounts)
                x_down_true = downstream_true_x.get(out_edge, 0.0)
                w_true = movement_weight(x_true, {"agg": x_down_true}, {"agg": 1.0})
                true_queues[i][mv] = x_true
                true_w[i][mv] = w_true

                # -- SENSED channel: always through SensingModel ------------
                corrupted = self._sensing.corrupt_counts(mv, tcounts)
                bias = self._sensing.bias(mv)
                if self.estimator == "area":
                    area = occupied_area(fleet, tcounts)
                    corrupted_area = self._sensing.corrupt_area(mv, area)
                    x_hat_raw = weighted_queue_from_area(
                        fleet, corrupted_area,
                        a_bar=self._a_bar_per_movement.get(mv, fleet.a_bar),
                    )
                else:
                    x_hat_raw = weighted_queue_from_counts(fleet, corrupted)
                x_hat[i][mv] = x_hat_raw * bias

                corrupted_running = self._sensing.corrupt_counts(mv, rcounts)
                u_hat[i][mv] = weighted_queue_from_counts(fleet, corrupted_running) * bias

                counts_hat[i][mv] = {c: n * bias for c, n in corrupted.items()}
                running_counts_hat[i][mv] = {c: n * bias for c, n in corrupted_running.items()}

                down_true_counts = per_edge_true.get(out_edge, {})
                corrupted_down = self._sensing.corrupt_counts(out_edge, down_true_counts)
                down_bias = self._sensing.bias(out_edge)
                counts_hat_downstream[i][mv] = {c: n * down_bias for c, n in corrupted_down.items()}
                if self.estimator == "area":
                    # NOT threaded through _a_bar_per_movement (Phase 1c
                    # scope decision, see __init__): this is keyed by
                    # out_edge, not a movement id -- an out-edge can be the
                    # shared downstream target of movements from several
                    # different intersections, so there is no single
                    # well-defined "camera at that approach" to commission
                    # here the way there is for a movement's own upstream
                    # measurement. Stays on the global calibrated a_bar.
                    down_area = occupied_area(fleet, down_true_counts)
                    corrupted_down_area = self._sensing.corrupt_area(out_edge, down_area)
                    x_down_hat = weighted_queue_from_area(fleet, corrupted_down_area) * down_bias
                else:
                    x_down_hat = weighted_queue_from_counts(fleet, corrupted_down) * down_bias
                w_hat[i][mv] = movement_weight(x_hat[i][mv], {"agg": x_down_hat}, {"agg": 1.0})

        if self.estimator == "count" and self.eta == 0.0:
            for i in self.intersections:
                for mv in self.movements[i]:
                    assert abs(x_hat[i][mv] - true_queues[i][mv]) < 1e-6, (
                        "sensing pipeline perturbed x_hat at eta=0 -- "
                        "true_queues must stay noise-free"
                    )

        action_masks = {}
        for i in self.intersections:
            n_phases = len(self.phases[i])
            mask = np.zeros(n_phases, dtype=bool)
            cur = self._current_phase_idx[i]
            if self._green_elapsed[i] >= self.g_min:
                mask[:] = True
            mask[cur] = True
            action_masks[i] = mask
        self.action_masks = action_masks
        self.true_queues = true_queues

        obs = self._build_obs(x_hat, u_hat, w_hat)

        info = {
            "true_queues": true_queues,
            "true_w": true_w,
            "true_counts": true_counts,
            "x_hat": x_hat,
            "u_hat": u_hat,
            "w_hat": w_hat,
            "counts_hat": counts_hat,
            "running_counts_hat": running_counts_hat,
            "counts_hat_downstream": counts_hat_downstream,
            "mu": self.mu,
            "phases": self.phases,
            "n_lanes": self._n_lanes,
            "n_lanes_edge": self._n_lanes_edge,
            "action_masks": action_masks,
            "current_phase": dict(self._current_phase_idx),
            "green_elapsed": dict(self._green_elapsed),
            "tau": {i: dict(self._tau[i]) for i in self.intersections},
            "gmax_active": gmax_active,
            "filter_active": {i: False for i in self.intersections},
            "backend": self.backend,
        }
        return obs, info

    def _build_obs(self, x_hat, u_hat, w_hat) -> Dict[str, np.ndarray]:
        x_ref, mu_ref, clip = self.obs_x_ref, self.obs_mu_ref, self.obs_clip
        agg_pressure = {i: sum(w_hat[i].values()) for i in self.intersections}

        obs: Dict[str, np.ndarray] = {}
        for i in self.intersections:
            cur_movs = set(self.phases[i][self._current_phase_idx[i]])
            rows = []
            for mv in self.movements[i]:
                phase_ids = self._mv_phases[i].get(mv, [])
                tau_m = min((self._tau[i][p] for p in phase_ids), default=0.0)
                x_down_hat = x_hat[i][mv] - w_hat[i][mv]  # w = x - x_down (agg form, r=1)
                rows.extend([
                    1.0 if mv in cur_movs else 0.0,
                    x_hat[i][mv] / x_ref,
                    u_hat[i][mv] / x_ref,
                    x_down_hat / x_ref,
                    w_hat[i][mv] / x_ref,
                    self.mu[i][mv] / mu_ref,
                    tau_m / self.g_max,
                    self._green_elapsed[i] / self.g_max,
                ])
            neighbour_feats = []
            for j in self._neighbours[i][: self.n_neighbours]:
                neighbour_feats.append(agg_pressure[j] / x_ref)
            while len(neighbour_feats) < self.n_neighbours:
                neighbour_feats.append(0.0)
            arr = np.array(rows + neighbour_feats, dtype=np.float32)
            obs[i] = np.clip(arr, -clip, clip)
        return obs

    def _compute_reward(self, info, switching: Dict[str, bool]) -> Dict[str, float]:
        """rl.reward.form selects the reward functional (PAPER_CHANGELOG
        P4-3 -- Eq. 12's "pressure_all" summed over ALL movements is NOT the
        Appendix A drift term, which is served-only: Sigma_m mu_m w_m S_m
        with the service indicator S_m. pressure_all partially telescopes
        (upstream vs downstream) and is near-maximal both for an empty
        network and for a uniformly gridlocked one -- validated/selected via
        scripts/validate_reward.py, not asserted):
          - "pressure_all": Eq. 12 as originally implemented -- negative
            pressure summed over every movement at i, service-indicator-free.
          - "total_queue": -(1/x_ref) * sum of true (unweighted-by-mu) queue
            mass at i -- monotone in congestion, exactly the quantity
            Theorem 1's strong-stability bound controls.
          - "served_pressure": +(1/(mu_ref*x_ref)) * sum of mu_m*w_m over
            ONLY the movements served by the phase actually executed this
            step -- the real Appendix A drift term, service indicator
            included.
          - "pressure_raw" (PAPER_CHANGELOG P5-1, Phase 5): +(1/x_ref) *
            sum of true_w (unweighted-by-mu pressure differential) over
            ONLY the movements served by the phase actually executed this
            step -- the MPLight/PressLight-lineage published reward (Chen
            et al. 2020 / Wei et al. 2019 define "pressure" in raw
            vehicle-count terms, with no saturation-flow weighting;
            mu-weighting is Zhang et al.'s own STATE refinement, not part
            of the base pressure-reward definition these three baselines
            share), given the SAME service-indicator restriction as
            "served_pressure" for the SAME reason: an earlier all-movements
            version of this form was built and run through
            scripts/validate_reward.py FIRST (P5-1) -- it failed
            (Spearman rho = -0.700 against both -AQL and throughput,
            Random ranked highest of all five controllers), the identical
            telescoping failure mode "pressure_all" already has documented
            above (upstream queue for one movement is downstream queue for
            another; summing every movement's w cancels rather than
            reflecting real congestion). Restricting to served movements
            only, exactly as "served_pressure" already does, removes the
            possibility of that cancellation. This corrected, service-
            restricted form is what actually shipped -- the all-movements
            attempt was never used by any baseline (Advanced-MPLight was
            the first and only consumer, gated before any training run).
            Distinct from "pressure_all" (mu-weighted) and "served_pressure"
            (mu-weighted, HAPLight's own) despite structural similarity to
            both -- do not confuse the three. Never used by HAPLight-RL
            itself.
        """
        reward = {}
        scale = 1.0 / (self.obs_mu_ref * self.obs_x_ref)
        for i in self.intersections:
            if self.reward_form == "total_queue":
                r = -sum(info["true_queues"][i].values()) / self.obs_x_ref
            elif self.reward_form == "served_pressure":
                served_movs = self.phases[i][self._current_phase_idx[i]]
                served = sum(self.mu[i][mv] * info["true_w"][i][mv] for mv in served_movs)
                r = scale * served
            elif self.reward_form == "pressure_raw":
                served_movs = self.phases[i][self._current_phase_idx[i]]
                served_raw = sum(info["true_w"][i][mv] for mv in served_movs)
                r = served_raw / self.obs_x_ref
            else:  # "pressure_all"
                pressure = sum(self.mu[i][mv] * info["true_w"][i][mv] for mv in self.movements[i])
                r = -scale * pressure
            if switching[i]:
                r -= self.c_switch
            reward[i] = r
        return reward
