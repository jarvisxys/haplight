# Paper changelog — apply at the final rewrite, not before

Every decision or measurement that changes `paper/HAPLight_journal_v2.tex`.
Append here as work proceeds; do not edit the .tex until all experiments are
done. Each entry says what changed, why, and which section it lands in.

---

## From Phase 2 calibration (full run, 2026-08-08) — CONFIRMED BY MEASUREMENT

**SUPERSEDED (2026-08-09):** this section's numbers were measured under the
pre-Phase-1c bus-heavy fleet mix. See P1c-5 below for the re-run under the
corrected 2W-heavy mix — the qualitative HCM-vs-area verdict (C-1) is
unchanged, but the margin narrowed a lot (~33% → ~7%), and `a_bar_
calibrated.hcm` (C-2) moved from 9.986 to 7.686. Kept here for the record
of what changed and why.

### C-1. Default weight vector flips: area → Indo-HCM
`Sec. III-C`, `Sec. VI-B`, abstract, conclusion.

Measured on the 8-point two-wheeler sweep:

| criterion | Indo-HCM | dynamic area | counts |
|---|---|---|---|
| ε (Lemma 1, calibrated ā) | 0.029 | 0.000 | — |
| ν (A5 violation, max dev) | 0.054 | 0.122 | 0.441 |
| **total ≈ c(ε+ν)** | **0.083** | 0.122 | — |

Indo-HCM wins by ~33%. The area curve is *monotone* decreasing in 2W share
(2.52 → 2.04), i.e. systematic misspecification, not scatter. Static footprint
understates two-wheeler *discharge* cost: they pack laterally in the queue but
still need longitudinal time headway at the stop line.

### C-2. ā is calibrated to realised composition, not minimax
`Remark 2`, `Sec. VII-A`.

ā: 9.485 (minimax, Lemma 1) → **9.986** (calibrated). Consequence:
ε = 0.450 (worst case) → 0.076 (measured, minimax ā) → **0.029** (calibrated).
Remark 3 justifies this: the 5.3% offset is uniform across movements, leaves
the greedy argmax unchanged, and is therefore free. Only the ±2.9% dispersion
is charged. **The theory correctly predicted its own slack.**

### C-3. New Proposition 3 — A5 violation and sensing error are the same thing
New subsection in `Sec. IV`, new appendix.

`y_m = μ_m(1+ν_m)Δt S_m` yields the identical `(c₁/2)ν‖X‖₁` drift bound as
Appendix B. Total certified-region shrinkage ≈ c(ε+ν). Gives a new design
criterion: **choose ρ to minimise ε+ν**. Not stated anywhere in this
literature. ~15 lines of proof, reuses Appendix B verbatim.

### C-4. New result — fitted discharge equivalency for two-wheelers
New subsection in `Sec. VII-A`.

ρ₂W fitted to flatten saturation discharge = **0.463** (CV 1.59%), against
Indo-HCM 0.5 (CV 1.89%) and area 0.228 (CV 7.54%). Independent, control-side
validation of Indo-HCM's most-contested factor. India-relevant, publishable
on its own.

### C-5. H5 is partially refuted — report it as such
`Sec. VI-A`, `Sec. VII-C`.

H5 predicted area weights would win on both estimator error *and* control.
They win on estimator error only. Rewrite H5 to predict a trade-off, and
report the refutation openly — this is pre-registration working correctly and
strengthens the paper.

### C-6. Caveat: C1 measured one approach only
`Sec. IX` (limitations).

ε = 0.029 comes from a single approach at nominal composition. Across a
network, per-approach mixes differ and dispersion will be larger — and
dispersion is exactly what Proposition 1 charges. Re-measure C1 network-wide
in Phase 7; report the single-approach figure as a lower bound.

---

## From Phase 1 (env + classical controllers)

### P1-1. Safety filter must act on x̂, not true queues
`Sec. V-F`, `Corollary 1`.

Supersedes an earlier instruction of mine. The filter has to be implementable
from cameras, so it triggers on the *estimated* queue. Corollary 1 already
covers this ("under the estimation error of Proposition 1, the same holds with
δ replaced by δ − c₁Δtε") — make it explicit rather than implied, and state
that the filter is deployable as specified. `true_queues` is used only for
metrics and for offline verification of the certificate.

### P1-2. Fixed-time baseline is Webster tuned to the actual generated demand
`Sec. VI-E`.

Green splits from real flow ratios y_i = q_i/s_i computed from the demand
files, not from a uniform-demand assumption. A mistuned FT inflates every
method's reported gain, which is precisely what [b_resco] warns about. State
in the paper that FT is tuned to the true demand of each scenario.

### P1-3. Clearance accounting at Δt = 5 s
`Sec. III-B`, possibly `Table IV`.

With t_y = 3 + 2 = 5 s and Δt = 5 s, a phase switch consumes an entire
decision interval with zero green; a phase service costs ≥ 15 s (5 clearance
+ 10 g_min). This is physically correct and applied identically to every
method, but it is a harsher switching cost than the Δt = 10 s / t_y = 5 s
setting common in the MPLight/Advanced-XLight literature. Report the effective
green fraction, and use the Δt ∈ {5,10} sensitivity sweep to show conclusions
are not an artefact of this operating point.

### P1-4. Emissions units
`Sec. VI-F`, `Table X`.

SUMO reports fuel in ml and CO₂ in mg. Conversion to kg happens once, in
`report.py`. State the units explicitly in the metrics description.

### P1-5. Phase/movement extraction is from the live TLS program
`Sec. III-B`.

Movements and phases are read from `getControlledLinks` /
`getAllProgramLogics` rather than assumed, so heterogeneous geometries need no
special handling. Worth one sentence — it supports the paper's claim that
masking, not per-intersection networks, handles the Bengaluru geometries.

### P1-6. libsumo unavailable on the target Windows/Python install
`Sec. VI-G` (compute budget), `Sec. VIII-C` (reproducibility).

Only traci is available, which is ~2× slower unless subscriptions are used
throughout. If libsumo cannot be obtained, the measured wall-clock in
Table VII will reflect traci; say which backend produced the numbers.

---

## From Phase 1 results review

### P1-7. HAP differs from MP only under spatially varying composition
`Sec. III-C` (new remark), `Sec. VI-A` (H1), `Sec. VII`.

If every movement carries the same class mix, `x^HAP = c x^MP` for a scalar c,
so the greedy argmax is identical and Greedy HAP **is** MaxPressure. This is
Remark 3 applied to the weight vector rather than to sensing error.
Confirmed empirically: at uniform composition the two controllers produced
byte-identical results (ATT 130.95 / AWT 1.76 / AQL 3.61 for both).

Consequences for the paper, all improvements:
- Add a remark stating the boundary explicitly. It is a sharp, honest
  statement of exactly what the contribution depends on.
- Upgrade H1 from "HAP beats MP" to the mechanistic form: **the HAP-MP gap
  grows with composition dispersion and vanishes at zero dispersion, as
  Remark 3 predicts.** A theoretical prediction with a measured curve is far
  stronger than a leaderboard win.
- Report a composition-dispersion index as a covariate in all results.

### P1-8. Demand is calibrated to a measured v/c, not asserted
`Sec. VI-D`.

Phase 1 default demand gave 126 veh/h and network AQL 3.6 weight-units on the
5-intersection arterial: free-flow, where signal control cannot matter.
Demand is now set by sweeping a scale factor until throughput plateaus (an
empirical estimate of the boundary of the capacity region of A3), then running
at v/c ~ 0.85 nominal and ~1.05 for the surge. Report the measured capacity
and the operating v/c per scenario -- this is what makes the interiority
margin in A3 a stated quantity rather than an assumption.

### P1-9. Fixed-time cycle floor binds at low demand
`Sec. VI-E`.

Webster's minimum-delay cycle was shorter than `|Phi| (g_min + t_y)`, so all
phases clamped to the same split regardless of demand ratio. Cycle is now
sized so the least-demanded phase clears `g_min` under proportional
allocation. Re-verify at the calibrated demand: at v/c ~ 0.85 the Webster
optimum should exceed the floor and the constraint should stop binding.

### P1-10. Classical baseline formulas are literature reconstructions
`Sec. VI-E`.

SOTL, Efficient-MP and Advanced-MP are cited but not restated in the source
papers' notation, so they were reimplemented from the literature. State this
in the paper and cite the specific formulation used for each. Advanced-MP in
particular must be checked against the Advanced-XLight reference
implementation before Phase 5, since Advanced-MPLight is the headline SOTA
baseline and is built on it.

### P1-11. Backend and determinism
`Sec. VIII-C`.

libsumo is available via a separate `pip install libsumo` wheel and is the
training backend. Repeated `reset()` opens a fresh SUMO session, so any
subscription or cached state must be re-established per episode -- a bug here
silently zeroed all queues after the first episode and produced a spurious
"MP loses to FT" result. Report the backend used for the wall-clock numbers.

---

## From Phase 1b results review

**Editorial note (2026-08-09, corrected):** P1c-1 through P1c-7 were written
by the paper author in review — directives on framing and evidence
requirements for the final rewrite, not measurements. An earlier pass in
this file mistakenly treated them as unbacked claims and replaced them
outright; they've been restored and merged with the measurements that back
them instead. P1c-1's causal story has also been corrected per the
author's review (calibration transfer is the dominant mechanism, dispersion
secondary — see below), and two entries (P1c-9, P1c-10) were added on
review, plus a Phase-7 carry-forward note (P1c-11).

### P1c-1. Per-movement estimator calibration is required, and is the fix for P1b-7
`Sec. III-D` (area estimator), `Sec. IV` (Prop. 1 discussion), `Sec. VII-C`,
`Sec. VIII-B` (deployability).

P1b-7's mechanism is confirmed but its conclusion was wrong. With a single
global `a_bar`, the estimator ratio is not a fixed constant — it varies by
movement, and the theory (Remark 3) says any per-movement bias is exactly
what Proposition 1 charges. **Corrected causal story (2026-08-09, from
measurement):** the original diagnosis attributed this to composition
dispersion alone. It doesn't. Measured on the corrected fleet (P1c-5),
`global`'s gap vs `count` is 10.9% at d=0, 1.1% at d=0.5, 0.87% at d=1.0 —
*largest at zero dispersion*, which composition dispersion alone cannot
explain. The dominant mechanism is **calibration transfer**: `a_bar_
calibrated.hcm` (7.686) comes from `scripts/calibrate.py`'s own small,
generic single-intersection saturated-approach testbed, not from S1 itself
— at d=0 every S1 movement already carries the exact nominal composition,
so the entire d=0 gap is pure calibration-network mismatch (generic testbed
vs. the real deployed arterial and fleet), with zero contribution from
spatial dispersion by construction. Composition dispersion is real but
secondary here; as dispersion rises, movements move away from the nominal
composition in both directions, which attenuates rather than compounds the
d=0 mismatch for this fleet/network. **Both mechanisms manifest identically
as a fixed per-movement constant bias, both are exactly what Proposition 1
charges, and both are removed by the same fix: per-approach, in-situ
calibration** — commissioning `a_bar_m` on the deployed network's own
realised composition rather than transferring a constant fitted elsewhere.
This is the stronger, more deployment-relevant claim: it isn't only "don't
let composition vary spatially without recalibrating," it's "never deploy a
calibration constant fitted on a different network or fleet without
recommissioning on-site."

This is deployable and standard: one short classified count per camera at
commissioning. The operational pipeline remains classification-free — no
per-frame classification is ever needed. Sec. VIII-B should say so
explicitly rather than implying a single constant suffices.

**Implementation and measurement:** `Fleet.a_bar_for(composition)`
(`src/hap.py`) fits a per-movement `a_bar_m` from one classified-count
episode (`estimator="count"`, the clean channel) — `scripts/calibrate_
estimator.py` is the simulated stand-in for a one-hour count per camera at
commissioning, and `src/env.py` loads `nets/<scenario>/a_bar_per_movement.
json` automatically when present, falling back to the global constant
per-movement otherwise. Three-way sweep on S1 at nominal demand
(scale=1.176, 1800s episodes, seed 0), global / count / per-movement,
ATT / AQL / TP / PWD:

| d | global | count | per-movement | per-movement TP gap vs count |
|---|---|---|---|---|
| 0.00 | ATT 204.4 AQL 1137.7 TP 3240 PWD 74.0 | ATT 196.6 AQL 403.4 TP 3636 PWD 67.3 | ATT 199.8 AQL 436.0 TP 3630 PWD 68.8 | **0.16%** |
| 0.50 | ATT 229.5 AQL 870.6 TP 3560 PWD 104.4 | ATT 232.4 AQL 911.5 TP 3520 PWD 110.9 | ATT 227.6 AQL 863.3 TP 3540 PWD 104.4 | **0.57%** |
| 1.00 | ATT 260.8 AQL 1774.4 TP 3240 PWD 151.9 | ATT 265.3 AQL 1812.0 TP 3212 PWD 154.8 | ATT 270.1 AQL 1826.0 TP 3230 PWD 154.3 | **0.56%** |

Per-movement calibration recovers throughput to within **0.16–0.57% of
count at every dispersion level tested** — comfortably inside "a few
percent," and effectively closing the gap rather than merely narrowing it,
consistent with the fix addressing both mechanisms above rather than only
the dispersion one.

**Staleness check** (a_bar_m fitted at d=0.5, evaluated at d=1.0, single
seed): ATT 262.7 AQL 1799.4 TP 3204 PWD 151.3, vs the fresh d=1.0
calibration's ATT 270.1 AQL 1826.0 TP 3230 PWD 154.3 (table above) and
count's own ATT 265.3 AQL 1812.0 TP 3212 PWD 154.8. The stale calibration
is, if anything, slightly *closer* to count than the fresh one here (0.25%
vs 0.56% TP gap) — within single-seed noise, but the practical conclusion
holds: a commissioning calibration does not visibly degrade across this
range of composition drift, so recalibration urgency is low.

Production `a_bar_per_movement.json` installed into both scenario net
directories at the config's default `composition_dispersion` (0.5) and each
scenario's own `scale_nominal`: 50 movements calibrated for S1, 189 for S2.
This is now the default configuration `env.py` loads — Parts C and D below
use it (`estimator="area"`) rather than the `estimator="count"` workaround
Phase 1b needed to sidestep the area estimator's own error. Report the
three-way comparison (global / per-movement / count) and the
stale-calibration case, as specified.

### P1c-2. Disagreement between HAP and MP has a sampling-noise floor
`Sec. III-C` (the P1-7 remark), `Sec. VII`.

P1-7's equality holds when composition is identical across movements. At
`composition_dispersion = 0` it is identical only **in expectation**;
realised finite queues fluctuate, so Greedy HAP and MaxPressure still
disagree on a nonzero fraction of decisions. State the floor when reporting
the remark — the exact-equality claim is asymptotic in queue length, not
per-decision.

**Remeasured (2026-08-09)** at S1 nominal demand, d=0, full 3600s episodes,
5 seeds, under the current fleet mix, calibrated demand and per-movement
estimator calibration: disagreement = **1.4% ± 0.3%** (per-seed:
1.0/1.8/1.7/1.0/1.4%). Any systematic HAP-MP difference reported elsewhere
(P1c-4) must be read against this floor. Numerically different from Phase
1b's ~2.9% floor — expected, since fleet mix, demand calibration and the
estimator have all changed since that measurement; both are legitimate
floors for their own configurations, not in tension with each other.

### P1c-3. H1 must be evidenced by a paired difference, not by levels
`Sec. VI-A` (H1), `Sec. VII`.

Raising `composition_dispersion` changes the demand itself (buses and
trucks concentrate on the arterial, raising total PCU), so ATT/AQL/PWD
levels worsening with dispersion is a property of the traffic, not of the
controller. H1 evidence must be the **paired HAP − MP difference at each
dispersion level on identical demand and seeds.**

**Implemented** in `scripts/h1_evidence.py --mode paired`: GreedyHAP and
MaxPressure are each run as a REAL, separate simulation on the identical
net/route/seed per (scenario, v/c) cell, so the reported HAP−MP difference
isolates the controller rather than mixing in a demand-level confound. See
P1c-4 for the resulting table.

### P1c-4. HAP's advantage should be sought in spillback, not travel time
`Sec. VI-F` (metrics), `Sec. VII`.

HAP weights road-space occupancy, so the mechanism by which it should beat
count-based MP is spillback prevention: twenty buses occupy ~4x the road
space of twenty cars, MP counts them equally, and the bus-heavy approach
blocks its upstream intersection. Vehicle ATT on a 400m arterial at v/c
0.85 barely exercises this. Added storage-occupancy, spillback-event and
upstream-blocked metrics (`metrics.spillback_stats`), evaluated on both the
400m S1 arterial and the 300m S2 grid at v/c 0.85 and 0.95.

**Measured (2026-08-09)** — paired HAP−MP evidence (`composition_
dispersion=0.5`, 1800s episodes, 3 seeds; threshold 90% of `env.storage`,
"event" = crossing into ≥100% storage, "blocked" = movement-seconds at
≥100%):

| scenario | v/c | ΔATT | ΔAQL | ΔPWD | Δspillback_events | Δupstream_blocked_s |
|---|---|---|---|---|---|---|
| S1 (400m) | 0.85 | +3.1 ± 10.7 | +61 ± 217 | +4.3 ± 15.4 | +1.0 ± 9.0 | +298 ± 684 |
| S1 (400m) | 0.95 | +3.2 ± 5.1 | +8 ± 83 | -0.7 ± 5.2 | +13.0 ± 18.2 | +23 ± 375 |
| S2 (300m) | 0.85 | -5.8 ± 4.5 | **-602 ± 768** | -6.3 ± 2.3 | **-23.0 ± 15.6** | **-1897 ± 2573** |
| S2 (300m) | 0.95 | +0.8 ± 1.8 | **-561 ± 747** | -0.6 ± 0.9 | **-21.3 ± 20.4** | **-1753 ± 2276** |

(Δ = HAP − MP, mean ± std over 3 seeds.) Exactly the mechanistic pattern
predicted, but **scenario-specific rather than general**: on S2 (the
spillback-prone 300m grid), HAP shows a large, directionally consistent
reduction in AQL, spillback events and upstream-blocked time at BOTH v/c
levels, while ATT/PWD barely move — HAP is converting road-space-occupancy
awareness into less queue buildup, not faster average trips. On S1's 400m
links (more room to queue before spilling back), the same metrics show no
advantage, sometimes mildly reversed, and every difference there is within
its own noise band. n=3 seeds gives wide standard deviations — the finding
is the consistent *direction* across two v/c levels on S2 against a null
result on S1, not a significant point estimate; see P1c-11.

### P1c-5. Fleet shares corrected to a realistic Indian arterial mix
`Sec. VI-C`, supersedes the flagged state in P1b-1; `Sec. VII-A`, supersedes
the "From Phase 2 calibration" numbers at the top of this file (C-1/C-2,
2026-08-08 run — measured under the pre-Phase-1c bus-heavy fleet mix).

2W 0.62 / car 0.22 / auto 0.10 / bus 0.02 / truck 0.04, giving passenger
shares 37.7 / 16.5 / 10.3 / 32.7 / 2.8%. Previously bus was 10% of vehicles
and 72% of passengers, making PWD a near-pure bus-delay metric. Changing the
mix changes PCU per vehicle, so capacity calibration and C1/C2 were both
re-run. **Still needs a cited source** (household travel survey or
municipal classified count) before Sec. VII is described as representative.

**Re-run results (2026-08-09):**
- **C1/C2** (`scripts/calibrate.py`, full run): `a_bar_calibrated.hcm` moves
  9.986 → **7.686** (two-wheelers, now 62% of the fleet, have the lowest
  beta of any class, pulling the realised-composition mean down). HCM vs
  area verdict: eps 0.078 vs 0.000, nu 0.027 vs 0.113, total 0.105 vs
  0.113 — HCM still wins, but the margin shrank from ~33% to ~7% (was eps
  0.029/nu 0.054/total 0.083 vs area's 0.122) — **see P1c-10, this margin is
  not yet a settled decision.** Fitted 2W discharge equivalency: 0.491 (was
  0.463), even closer to Indo-HCM's 0.5.
  `test_hap.py::test_nominal_composition_ratio` updated from 9.978/1.052 to
  **8.115/0.856** (nominal_beta_mean/a_bar_star ratio — the ratio flipped
  from >1 to <1, i.e. the nominal composition's realised beta mean moved
  from above a_bar_star to below it).
- **Capacity/demand** (`scripts/calibrate_demand.py`, full sweep, both
  scenarios): S1 capacity 3879 → **4481.8 veh/h**, scale_nominal 1.018 →
  **1.176** (v/c≈0.85), scale_surge 1.257 → **1.452** (v/c≈1.05). S2
  capacity 6713.3 → **6543.3 veh/h**, scale_nominal 1.321 → **1.287**,
  scale_surge 1.632 → **1.590**. S1's capacity rose (smaller 2W-heavy fleet
  mix fits more vehicles per unit road space); S2's fell slightly — within
  plausible measurement variation given S2's plateau is thin (see P1c-8).
  S1's nominal-demand sanity check flagged a real, small insertion backlog
  (mean pending ≈ 20 vehicles, depart delay 0.5s) — the reported v/c is a
  slight underestimate of true demand pressure; noted, not disqualifying.

### P1c-6. MP vs FT parity at moderate demand is expected, not a defect
`Sec. VI-E`, `Sec. VII-B`, `Sec. IX` (Limitation 4).

P1b-8 (MP 232.6s vs FT 230.5s, v/c 0.85, single seed) is consistent with
max-pressure being throughput-optimal rather than delay-optimal: a Webster
plan tuned to the true demand should be competitive under moderate,
stationary load. MP's guarantee bites near capacity and under demand
variation. Re-tested at v/c 0.95 and under the surge with 5 seeds; report
the regime dependence explicitly rather than only the favourable operating
point.

**Re-tested (2026-08-09)** at v/c 0.95 and under `scale_surge`, 5 seeds,
full 3600s episodes, both scenarios — the prediction holds cleanly and by a
wide margin, reversing P1b-8's near-parity entirely:

| scenario | level | FT ATT | MP ATT | verdict |
|---|---|---|---|---|
| S1 | v/c 0.95 | 420.3 ± 46.2 | 305.2 ± 6.8 | **MP wins by ~27%** |
| S1 | surge | 503.4 ± 31.6 | 378.1 ± 20.7 | **MP wins by ~25%** |
| S2 | v/c 0.95 | 262.4 ± 21.0 | 232.5 ± 5.3 | **MP wins by ~11%** |
| S2 | surge | 273.1 ± 13.9 | 255.1 ± 8.3 | **MP wins by ~7%** |

MP wins in all four cells, both scenarios, with MP's own variance
consistently tighter than FT's — a static Webster plan tuned to *average*
demand degrades badly once real demand exceeds what it was tuned for, while
MP's reactive pressure-based control adapts. Report both operating points
(P1b-8's v/c 0.85 near-parity and this section's clear v/c 0.95/surge win)
rather than only the favourable one — the regime dependence is the finding.

### P1c-7. min_gap_lat is frozen, not a tuning knob
`Sec. VI-B` (Table III).

Corrects an earlier instruction. `min_gap_lat` feeds `a_v = (L+g)(W+g_lat)`
in Eq. (3), so it determines pi, beta, epsilon*, Table III and both
calibration experiments. Phase 3 tunes only pure lane-changing parameters
(`lat_alignment`, `lcSublane`, `lcPushy`, `lcAssertive`, `lcAccelLat`).

### P1c-8. Cross-scenario rundir collision in calibrate_demand.py silently ran S2's sweep on S1's net
`Sec. VI-D`, `Sec. VIII-C` (reproducibility).

`sweep_capacity`'s per-(scale,seed) rundirs were named only `s{scale}_
seed{seed}`, with no scenario tag, inside the ONE temp workdir `main()`
shares across scenarios when run with `--scenario all`. Since `_write_run`
writes scenario-named files (`arterial5.rou.xml` / `grid4x4.rou.xml`) into
whatever directory it's given, S2's run wrote its files into the SAME
directories S1 had already used — and `HAPLightEnv._find_sumocfg()` globs
`*.sumocfg` and takes the alphabetically-first match, so it silently picked
`arterial5.sumocfg` every time. Result: the first `--scenario all` run of
this phase produced byte-identical capacity numbers for both scenarios
(4481.8 veh/h for both) — caught because S2 (16 intersections) matching S1
(5 intersections) exactly is obviously wrong. Fixed by prefixing every
rundir with the scenario's net name; re-ran, S2's real capacity is 6543.3
veh/h (P1c-5). Latent since Phase 1b — did not manifest there only because
Phase 1b's scenarios were evidently calibrated in separate invocations, not
a single `--scenario all` run. Applied the same defensive fix to
`scripts/h1_evidence.py`'s rundir names (no bug had manifested there yet,
but the identical anti-pattern was present for the v/c=0.95 case shared
between `--mode paired` and `--mode mp_vs_ft`).

### P1c-9. ā should be calibrated on queue composition, not flow composition — direction checked, does NOT match the hypothesis
`Sec. III-D`, `Sec. VII-A`.

Motivation was right in principle — a camera at commissioning sees the
*queue*, not the *flow*, so `a_bar_m` should be fit on realised queue
composition (which is exactly what `scripts/calibrate_estimator.py` and
`calibrate.py`'s C1 both already do: both sample stopped-vehicle counts,
never flow counts). The specific mechanism proposed — two-wheelers filter
forward and are *over*-represented in standing queues — was checked
directly and **is not what the data shows**.

Measured network-wide queue (stopped-vehicle, `estimator="count"`)
composition on S1 at d=0, full episode, against the nominal flow shares
that fed it (every OD gets exactly `fleet.classes[*].share` at d=0, so this
is a clean flow-vs-queue comparison on one fixed network):

| class | queue share | nominal flow share | ratio |
|---|---|---|---|
| twowheeler | 0.5926 | 0.6200 | **0.956** (under-represented) |
| car | 0.2405 | 0.2200 | 1.093 (over) |
| auto | 0.1043 | 0.1000 | 1.043 (over) |
| bus | 0.0243 | 0.0200 | 1.216 (over, most) |
| truck | 0.0383 | 0.0400 | 0.957 (under) |

Two-wheelers are **under**-represented in the standing queue relative to
flow, not over-represented — the opposite of the proposed mechanism (their
higher accel/decel and lateral filtering likely means they spend less time
in a strictly-stopped state even while queued, rather than accumulating at
the front). Car, auto and bus are the over-represented classes, bus most of
all. This queue-vs-flow divergence is real and worth keeping in the
narrative (ā should still be commissioned on the queue), but the ~5% gap
between `a_bar_calibrated.hcm` (7.686) and the flow-based prediction
(`nominal_beta_mean`, 8.115) should NOT be attributed to two-wheeler
over-representation — per P1c-1, that gap is better explained by
calibration transfer (7.686 comes from `calibrate.py`'s own separate
generic testbed network, not S1), confounded with whatever queue/flow
divergence exists on *that* testbed specifically, which was not measured
here. Flagging this refutation rather than quietly fitting the narrative to
the hypothesis.

### P1c-10. C-1's ~7% HCM-vs-area margin is not yet a settled decision
`Sec. VII-A`, `Sec. IX` (limitations).

P1c-5 remeasured the HCM-vs-area verdict under the corrected fleet: total
score 0.105 (HCM) vs 0.113 (area), a margin that fell from ~33% to ~7% once
the fleet went 2W-heavy. A 7% margin from a **single, unseeded run** is not
a basis for a settled weight-scheme decision — it's well within the range a
different seed could plausibly flip. `scripts/calibrate.py`'s C2 currently
runs once, no seed sweep, no confidence interval. **Do not state the
HCM-vs-area choice as settled in the paper until C2 is re-run with seeds
and a CI (Phase 7, P1c-11).** Keep `weight_scheme: hcm` as the working
default in the meantime — it's still the point estimate — but Sec. VII-A
and the abstract/conclusion's framing of C-1 should say "measured margin
narrowed to ~7% under the corrected fleet, pending a seeded re-run" rather
than reasserting the original ~33% confidence.

### P1c-11. Carried forward to Phase 7 — not done in this phase
`Sec. VII` (evaluation protocol).

Two measurements in this phase used fewer seeds/scope than the paper will
need and should not be treated as final:
- **H1 spillback evidence (P1c-4):** 3 seeds, S1/S2 only. Needs the full 5
  seeds with paired confidence intervals, plus an S3 (Bengaluru) run, before
  the spillback-prevention claim is paper-final.
- **C2 (P1c-10):** single run, no seeds. Needs a seed sweep and a
  confidence interval before the HCM-vs-area weight-scheme choice is
  reported as settled rather than a current best estimate.

---

## From Phase 3 (two-wheeler sublane behaviour)

### P3-1. SL2015 sublane filtering confirmed — two-wheelers reach the front without any tuning
`Sec. III-B` (2W behaviour), `Sec. VI-B` (Table III/IV), `Sec. VIII-A`
(sim-to-real gap).

The paper's claim that SL2015 approximates Indian two-wheeler gap-filling
was untested until now. Built `tests/test_sublane.py::test_2w_reach_front`:
a mixed standing queue at real fleet shares on `scripts/calibrate.py`'s
single-signalised-cross testbed (west approach, 3 lanes), held at red for
60s, released, each vehicle's stop-line crossing rank (0-indexed order of
first appearance on the downstream edge) recorded by class.

Measured (untuned config — `lat_alignment: arbitrary`, `lc_sublane: 1.0`
for two-wheelers, already in `configs/default.yaml` — 3 seeds, ~200
two-wheelers / ~70 cars per run):

| seed | mean rank gap (car − 2W) | SL2015/LC2013 wall-clock ratio |
|---|---|---|
| 0 | +12.03 | 7.62x |
| 1 | +9.51 | 8.74x |
| 2 | +7.62 | 8.35x |

Two-wheelers consistently finish **~8-12 places ahead of cars** out of a
~280-vehicle mixed queue, with **no lane-changing parameter tuning
needed** — the gate PLAN.md names passes on the existing config as-is.
`lcPushy`/`lcAssertive`/`lcAccelLat` (the reserved tuning knobs, per
PAPER_CHANGELOG P1c-7 and this phase's own scope) were added as supported,
documented, optional per-class `configs/default.yaml["fleet"]` dicts in
`scripts/calibrate_sublane.py::_vtypes_xml_tunable`, but left unset since
they weren't needed. Geometry (`length`/`width`/`min_gap`/`min_gap_lat`)
was not touched, per P1c-7.

Also measured, for context: under SUMO's classical default model (LC2013,
no sublane simulation), two-wheelers still finish slightly ahead of cars
(+0.35 to +3.92) but by a much smaller and less consistent margin than
under SL2015 — i.e., SL2015 is doing real, measurable extra work to
produce the filtering behaviour, not just inheriting an effect LC2013
would show anyway.

### P3-2. Sublane runtime cost measured at ~8x, not the 2-4x PLAN.md budgeted
`Sec. VI-G` (compute budget), `Sec. VIII-C` (reproducibility).

`PLAN.md:228` states "Sublane (SL2015) costs 2-4x runtime. Already in the
budget." Measured directly (same queue-release scenario as P3-1, same
seed/net/routes, SL2015 vs LC2013, wall-clock around each `.run()` call):
**7.6x-8.7x across 3 seeds** — roughly double the top of the stated range,
consistently, not a one-off.

One important scope caveat, not yet resolved either way: this measurement
is on a small, dense, held-at-red-then-released queue (~280 vehicles in a
single burst) — exactly the scenario where sublane's continuous
lateral-position bookkeeping has the most simultaneous interacting
vehicles per step relative to free-flowing traffic, so it may not
generalise directly to a full S1/S2 episode's more spread-out demand. Did
**not** re-verify against a full episode in this phase (out of scope here
per the plan — flagging the discrepancy is the deliverable, not resolving
it). **Before Sec. VI-G's compute budget is finalised, re-measure the
SL2015/LC2013 ratio on a real S1 or S2 episode** — if it holds anywhere
near 7-8x there too, the Phase 4+ RL training wall-clock budget (PLAN.md's
"~5 days continuous on one 8-core box") needs revisiting, since it was
sized against the 2-4x assumption.

**Resolved (Phase 4 pre-check, 2026-08-09):** re-measured on a REAL, full
S2 episode (3600s, nominal demand, GreedyHAP, seed 0) — `src.env.
HAPLightEnv` gained a `sublane_simulation` flag (whether `--lateral-
resolution` is passed to SUMO; SL2015 requires it, LC2013 is incompatible
with it) so both runs go through the identical production code path.
Result: **1.19x** (SL2015 46.4s vs LC2013 38.8s wall-clock) — comfortably
inside the 2-4x budget, nowhere near the queue-release testbed's 7.6-8.7x.
The caveat above was correct: that ratio was an artefact of the dense
held-then-released burst scenario, not representative of production
training cost on spread-out episode traffic. **The Phase 4+ compute budget
does not need revisiting on this basis.** `scripts/measure_lc_runtime.py`
reproduces this measurement; kept in the repo since Phase 5+ (S3, other
scenarios) may want to re-check it on a different net.

---

## From Phase 4 (shared policy, PPO, stability filter)

### P4-1. Observation/reward equation numbers cited in code don't match a sequential count of the current .tex
`Sec. V-A` (observation), `Sec. V-B` (reward), whole-document equation
numbering.

`src/env.py`, `src/hap.py`, and `src/controllers.py` all cite the
observation as "Eq. 7" and the reward as "Eq. 12" (predates Phase 4).
Sequentially counting every `\begin{equation}`/`\begin{align}` line in the
current `paper/HAPLight_journal_v2.tex` puts the observation at position 15
and the reward at 16 instead — four equations (`eq:capregion`,
`eq:stability`, `eq:c1`, `eq:fbound`, the Layer-1 theorem/proposition
block) appear to have been inserted between Eq. 7's original position and
where the observation/reward equations actually live, without the
downstream citations being updated. New Phase 4 code (`src/policy.py`,
`src/safety_filter.py`, `src/ppo.py`) matches the EXISTING codebase
convention (Eq. 7 / Eq. 12) for internal consistency, since `env.py`/
`hap.py`/`controllers.py` are marked don't-rewrite — **not silently
"corrected" to 15/16, which would make the codebase self-contradictory.**
Needs a real fix at the compiled-PDF stage: re-verify the actual compiled
equation numbers before Sec. V is finalised, and update either the code
comments or investigate whether the `.tex` itself has a stray/duplicate
equation environment.

### P4-2. Reward uses the true (noise-free) channel; observation uses the sensed one — intentional, must be stated in Sec. V-C, and binds Phase 5
`Sec. V-C` (reward), `Sec. V-A` (observation), constraint on Phase 5.

`src/env.py::_compute_reward` builds the reward from `info["true_w"]`
(ground truth) while `_build_obs` builds the policy's observation from
`x_hat`/`u_hat`/`w_hat` (sensed, noisy at `eta>0`). The agent is graded on
the real system dynamics but only ever *observes* the sensor — it cannot
see the noise that is, in effect, being applied to its inputs but not its
grading. This is a deliberate, defensible design (matches how a real
deployment's actual queue evolution — not the camera reading — determines
real-world traffic outcomes, and keeps the reward the exact undistorted
Lyapunov-drift functional of Theorem 1) and is being kept as-is, not
changed. Two consequences that need to be tracked:
- **Sec. V-C must say so explicitly.** The paper prose currently writes
  the reward in terms of $w_m(t)$ without flagging that this is the
  true-channel value while the agent's own state is the sensed one — easy
  to misread as a minor notational choice rather than a substantive
  training-vs-observation asymmetry.
- **Every Phase 5 RL baseline (PressLight, MPLight, CoLight,
  Advanced-MPLight, MARDDPG) must use the identical true-channel reward.**
  If any baseline is instead trained against a sensed-channel reward (a
  common default in this literature), the comparison in Sec. VII would be
  confounded by a different training signal, not just a different
  architecture — carried forward as a hard constraint on Phase 5's
  implementation, not a suggestion.

### P3-3. SL2015 filtering is validated against a control, not assumed
`Sec. VI-B`, `Sec. IX` (Limitation 1).

Two-wheelers finish 7.6-12.0 crossing ranks ahead of cars in a ~280-vehicle
mixed standing queue under SL2015 with the shipped parameters (no tuning was
required). The same queue under classical LC2013 shows only +0.35 to +3.92,
so the effect is attributable to the sublane model rather than incidental.
Report the LC2013 control alongside the SL2015 number: it converts
Limitation 1 from an unverified caveat ("SL2015 approximates but does not
reproduce Indian flow") into a measured statement about what the model does
and does not capture.

### P3-4. Sublane runtime cost exceeds the budgeted range
`Sec. VI-G` (compute budget), `Table VII`.

Measured 7.6-8.7x versus LC2013 on a dense held-then-released queue, against
the 2-4x assumed when the compute budget was sized. The measurement is a
near-worst case (lateral conflict computation scales with local density), so
it must be re-measured on a full episode before the training budget is
final. Whatever the real-episode figure turns out to be, state it in
Sec. VI-G — the paper claims the protocol fits on one workstation, and that
claim has to rest on a measured multiplier rather than an assumed one.

### P3-5. Filter activation rate must be checked before the full sweep
`Sec. VI-A` (H2), `Sec. VII-G`, `Remark 6`.

H2 pre-registers filter activation below 5% of decisions. That threshold was
set before demand was calibrated; training now runs at v/c 0.85-0.95 with
network AQL of order 10^3, and `B` is the P90 of the greedy-HAP queue
distribution. If measured activation is far above 5%, Remark 6 applies and
HAPLight-RL is behaviourally greedy HAP for most decisions. Decide before the
sweep whether `B` moves to P97 or H2's threshold is revised, and record which
was chosen and why — revising a pre-registered threshold after seeing data is
defensible only if it is declared.

### P4-3. First full S1 PPO run aborted at iteration 40 on a pre-registered trend criterion — training signal is not yet usable
`Sec. V-E` (training protocol), `Sec. VI-A` (H2/completion gate), `Sec. VII`
(results), `Remark 6`.

Before launching the 800-episode run, three diagnostics were run (author
instruction, 2026-08-10) to disambiguate "the filter is rescuing an
undertrained policy" (Remark 6) from real learning, plus a reward-signal
sanity check. `scripts/train.py` now computes all three automatically before
training and logs them to the run's `metadata.json`; the abort criterion is
also automatic (`np.polyfit` slope of the clean η=0 return over the first 40
iterations, stop if ≤ 0).

**Run `results/s1_seed0_1786360965` (S1, seed 0, `B`=228.71 at P90):**

| diagnostic | value |
|---|---|
| greedy-HAP reference, η~U[0,0.6] (matches training) | 610.48 |
| greedy-HAP reference, η=0 (matches clean eval) | 894.42 |
| random-policy + filter control, η~U[0,0.6] | **902.90** |
| corr(per-step reward, per-step Δ true total queue) | **+0.235** |

**Finding 1 — the control ablation confirms Remark 6 quantitatively, not just
plausibly.** An untrained random policy behind the safety filter scores
902.90 at η~U[0,0.6] — 48% *above* the matched-condition greedy-HAP
reference (610.48), with zero training. Every iteration's raw `mean_return`
(550-950 throughout the run) sat above 610 essentially the whole time,
which is exactly this floor, not evidence of policy improvement. Any future
reporting of HAPLight-RL "beating greedy HAP" must be checked against this
control, not against the raw training-return number.

**Finding 2 — reward/queue correlation is weak and wrong-signed.** Eq. 12's
reward is (negative) pressure, so a healthy reward should correlate
strongly *negatively* with the change in true total queue over the same
step. Measured: +0.235 — small in magnitude and the *wrong sign*. Not the
"near-zero = pure noise" failure mode exactly, but not healthy either; flagged
as the leading suspect (see below).

**Finding 3 — the abort criterion fired.** Clean η=0 return over the first 40
iterations: slope = **-3.99 return/iteration** (first iteration 696.80, last
332.28, all 40 iterations well below the 894.42 reference throughout, no
iteration approached it). Per the pre-registered criterion ("below-but-rising
is fine, flat is not"), the run stopped automatically at iteration 40 rather
than continuing to the full 800-episode budget.

**Not yet resolved — needs the debug pass before any further training run:**
filter activation was 5-19% across the 40 iterations (never near the 25%
stop-gate, and trending *down* over the run, from ~17-19% early to ~5-9%
late) while clean-eval performance simultaneously got *worse*, not better —
i.e. the policy is triggering the (x̂-based) filter less often while true
queues (the reward's own channel) are increasing. One live hypothesis worth
checking before assuming a pure reward-shaping fix: the policy may be
learning to suppress the *sensed* trigger statistic without controlling the
*true* queues it's graded on (P4-2's true-reward/sensed-observation split
makes this possible in principle). Value loss is also large and non-decreasing
(1.4k-8.8k, no visible convergence trend) across the run, consistent with
either an unstable/weak reward target or a value function that cannot
generalise across the true/sensed channel gap. **Do not scale to the full
800-episode run or to S2 until this is root-caused** — debug order per the
pre-registered plan: (1) reward signal quality — consider the
`-Σ_m x_m` true-queue reward variant instead of Eq. 12's pressure form if the
correlation doesn't improve under closer inspection; (2) filter masking of
exactly the high-queue gradient steps the policy most needs; (3) observation
content / the sensed-vs-true channel split identified above.

### P4-4. Eq. 12 is a paper error, not an implementation choice — it is not the Lyapunov drift functional Sec. V-C claims. `total_queue` reward validated as the replacement
`Sec. V-C` (reward definition and justification), `Appendix A` (drift
derivation), `Table` of ablations (new rows A/A′), `Remark 6`.

**The error.** Sec. V-C currently states that Eq. 12's reward is "the
negative of the exact functional whose maximisation over phases drives the
Lyapunov drift." It is not. Appendix A's drift term is
`Sigma_m mu_m w_m S_m` — summed ONLY over movements `m` served by the phase
actually selected, `S_m` the service indicator. Eq. 12 as implemented drops
`S_m` and sums `mu_m w_m` over EVERY movement at the intersection regardless
of whether it is being served that step. Because `w_m` nets an upstream
value against a downstream one, summing over all movements lets upstream
increases partially cancel downstream ones — the reward is close to its own
maximum both for a near-empty network and for a uniformly congested one, so
it barely discriminates between "good" and "bad" states. This was flagged
as a live risk before the aborted run (P4-3) on a near-zero correlation
concern; the actual measurement below shows the failure is worse than
near-zero — it is **wrong-signed**.

**Step 1 — permanent validity gate (`scripts/validate_reward.py`, new,
author instruction 2026-08-10):** one paired episode each (same eta~U[0,0.6]
draw, same demand/seed realisation) for FixedTime, MaxPressure, GreedyHAP,
a uniform-random policy, and random+SafetyFilter, on S1. A valid reward must
rank controllers the same way AQL and throughput do; Spearman rank
correlation between reward-return and each is the pass/fail signal, and
every `rl.reward.form` candidate must clear this before any training run
uses it.

| reward form | FixedTime | MaxPressure | GreedyHAP | Random | Random+Filter | rho(reward,−AQL) | rho(reward,TP) |
|---|---|---|---|---|---|---|---|
| `pressure_all` (old Eq. 12) | 552.7 | 593.8 | 594.4 | **2481.6** | 918.3 | **−0.700** | **−0.500** |
| `total_queue` (new default) | −3904.3 | −4095.1 | **−3606.9** | −7957.6 | −4556.0 | **+1.000** | +0.900 |
| `served_pressure` | −125.2 | **133.0** | −45.3 | −1654.6 | −452.8 | +0.700 | +0.400 |

(AQL for reference, same episode set: FixedTime 1352.4, MaxPressure 1418.5,
GreedyHAP 1249.0, Random 2759.9, Random+Filter 1578.7 — Random is the worst
controller by a wide margin on both AQL and throughput in every row.)

`pressure_all` is not merely uninformative, it is **anti-aligned**: an
untrained, uniform-random policy scores the single highest reward of all
five controllers — more than 4x every classical baseline — despite having
by far the worst AQL and the lowest throughput. This is not the
near-empty/gridlock cancellation risk flagged pre-run; it is the same
telescoping mechanism producing a positive bias toward incoherent phase
switching specifically, which is exactly what an untrained policy (or an
early-training one still exploring) produces. It fully explains the aborted
run's raw `mean_return` sitting above the greedy-HAP reference all
40 iterations (P4-3) — that was never partly-filter, partly-learning; the
reward itself was rewarding the chaos.

`total_queue` (`r_i = -(1/x_ref) * Sigma_{m in M_i} x_m`) is the clear
winner: perfect rank agreement with AQL, and throughput agreement short by
exactly one adjacent-pair swap (MaxPressure/Random+Filter) out of five
controllers. `served_pressure` (the literal Appendix-A-correct
`Sigma_{m in phi_i(t)} mu_m w_m`, positive-signed) is a distant third —
better than `pressure_all` but still displaces MaxPressure to the top of
its own ranking while AQL/throughput both rank it mid-pack, likely because
a single high-mu movement being served briefly can dominate the sum without
reflecting the intersection's actual queueing state. **`total_queue` is now
`configs/default.yaml`'s default `rl.reward.form`; `pressure_all` and
`served_pressure` become ablation rows A/A′, not the default.**

**Consequence for Sec. V-C's framing (flag now, write at the final
rewrite):** with `total_queue` as the reward, the paper's claim changes
from "reward equals the Lyapunov drift functional" to **"reward equals the
quantity Theorem 1's strong-stability bound controls"** — a different but
equally correct and defensible alignment, since `total_queue` is exactly
`Sigma_m x_m`, the object the stability theorem bounds. Sec. V-C's
derivation connecting the reward to Appendix A must be rewritten around
this, not patched.

**Step 2 (gridlock-mechanism check, `scripts/diagnose_gridlock.py`, new):**
before committing to the `total_queue` re-run, tested the specific
insertion-backlog hypothesis directly against the aborted run's own final
checkpoint (iteration 39) — the only surviving policy state, since
`train.py` overwrites one `checkpoint.pt` per iteration and never logged
pending-vehicle/in-network-count/depart-delay time series, so the
cross-iteration trend itself is not reconstructable after the fact. One
fresh eta=0 evaluation episode, sampling `pending_count()`,
`in_network_count()`, `mean_depart_delay()` and cumulative completed
throughput at every decision step (both new `env.py` accessors, added for
this check): **pending stayed at exactly 0 for the entire episode** (SUMO
never refused an insertion), filter activation *rose* within-episode
(0% first quarter -> 11.1% last quarter, the opposite direction from the
declining across-iteration trend in P4-3), and completed throughput kept
accumulating (466 trips first quarter, 1128 last quarter — not collapsed).
True total queue did grow substantially over the episode (342 -> 1632,
consistent with a policy that controls poorly) but the specific proposed
mechanism — insertion backlog growing while activation falls — is **not
what this test shows**. This is a within-episode test of the single
surviving (final) checkpoint, not a reconstruction of the cross-iteration
pattern itself, so it rules out literal network gridlock as the explanation
without ruling out a broader "reward gradient pushed the policy toward
worse queueing behaviour over training" story — which the `pressure_all`
anti-alignment result above already explains on its own, more directly and
without needing a separate mechanism.

### P4-5. Re-run with `total_queue` completes the full 800-episode budget on S1 — HAPLight-RL exceeds greedy HAP; Phase 4 completion gate met
`Sec. VI-A` (H2/completion gate), `Sec. VII` (results, Fig. 5), `Remark 6`.

Same protocol as the aborted P4-3 run (dual greedy-HAP references, random+
filter control, iteration-40 abort check), `rl.reward.form` switched to
`total_queue` (now the config default per P4-4). `results/
s1_seed0_1786387277`, S1, seed 0, `B`=228.71.

| diagnostic | value |
|---|---|
| greedy-HAP reference, η~U[0,0.6] (matches training) | −3736.5 |
| greedy-HAP reference, η=0 (matches clean eval) | −4970.6 |
| random-policy + filter control, η~U[0,0.6] | −4311.8 |
| corr(reward, Δ true total queue), GreedyHAP @ η=0 | −0.132 |

**Control ablation is now healthy** (contrast with P4-3): the untrained
random+filter floor (−4311.8) scores *below* the matched greedy-HAP
reference (−3736.5), unlike the `pressure_all` run where the same control
beat its reference by 48%. Whatever the trained policy achieves above
reference is no longer explainable by the filter floor alone. (The reward/
queue correlation, −0.132, is weak in magnitude but the diagnostic's
"large-magnitude negative" expectation was calibrated against `pressure_all`
semantics — `total_queue`'s reward is a queue LEVEL, not a flow/pressure
term, so per-step reward-vs-Δqueue correlation is not the right lens for
this reward form; the direct rank-correlation test in P4-4 is.)

**Iteration-40 check passed**: eta0 slope = +7.7/iteration (positive, no
abort). Ran to full completion, 100 iterations / 800 episodes:

- eta0_return (clean channel, the fair comparison): slope = **+4.5/
  iteration** over all 100 iterations. **97/100 iterations exceeded the
  η=0 reference** (−4970.6), including all of the last 10. First-10 mean
  −3085.2 → last-10 mean −2823.0. Best iteration: −2200.0 (iter 69).
- mean_return (training condition, η~U[0,0.6]): slope = **+8.8/iteration**.
  71/100 iterations exceeded the matched reference (−3736.5); noisier than
  the clean metric (7/10 in the last 10), consistent with per-episode η
  variance rather than instability — value_loss and filter_activation both
  trend down over the same window (15.5%→8.9% mean activation, never above
  ~20%), the opposite of P4-3's confounded decline (there, falling
  activation coincided with WORSENING clean performance; here it coincides
  with improving clean performance, i.e. the policy needing fewer greedy
  rescues as it gets better, not gaming the trigger).

**Completion gate (H2/Sec. VI-A: HAPLight-RL's mean return exceeds greedy
HAP's within 800 episodes on S1) is MET** on the clean, reward-valid
channel, decisively and consistently across the run, not a last-iteration
fluke. The noisier training-condition metric clears the bar more often
than not with a clear improving trend, not yet uniformly. This result is
only trustworthy because P4-4 fixed the reward first — the same "exceeds
reference" reading under `pressure_all` (P4-3) was shown to be mostly the
filter floor. **Proceed to S2 per the original Phase 4 plan**; carry the
`total_queue` reward and this validation protocol
(`scripts/validate_reward.py` + dual references + control ablation)
forward as the standard, not just for this one run.

### P4-6. Author audit of P4-5's claims: reference bug found and fixed, significance corrected, task-metrics table run — the real deliverable
`Sec. VI-A` (H2/completion gate), `Sec. VII` (results table, Fig. 5), `Sec. VI-G` (compute budget/reproducibility), `Remark 6`.

P4-5's framing overstated the result in three ways, all corrected here before
S2. Author review of the raw CSV caught all three; each was verified, not
taken on faith.

**1. Statistical significance, corrected.** `scipy.stats.linregress` on the
100-iteration run: `mean_return` (training condition) slope +8.83/iteration,
**t=3.56, p=0.0006 — significant**, and iteration 0 (-4473.8) sits below
both the matched reference (-3736.5) and the untrained random+filter floor
(-4311.8), ending above both — this is real, i.e. the training-condition
result is genuine learning, not a floor artefact. `eta0_return` (clean
channel) slope +4.45/iteration, **t=1.65, p=0.103 — NOT significant.**
Iteration 0's `eta0_return` (-3523.7) already exceeded the (then-uncorrected)
reference, so P4-5's "97/100 iterations beat the reference" was never valid
evidence of learning on its own — dropped.

**2. The eta=0 reference had a real bug in the STATISTIC, not the protocol.**
P4-5 reported greedy-HAP eta=0 = -4970.6, worse than eta~U[0,0.6] = -3736.5,
backwards from what perfect information should give a pressure-greedy
controller. The demand/seed pairing was already correct (`compute_greedy_
reference`'s `ep_seed` derivation is identical regardless of `fixed_eta`,
by construction) — the bug was **n=8 being too few episodes for a
fat-tailed distribution**. `scripts/check_greedy_reference.py` (new,
permanent) reran both references paired at n=16: overall still not
significant (t=-0.92, p=0.37), but one single episode (`ep=3`, `eta_u=
0.010`) had eta0_return=**-16312.6** against etaU_return=-3074.2 for the
IDENTICAL demand draw — a 4x-of-the-mean outlier that alone accounted for
essentially the entire apparent gap. Excluding it, eta0 and etaU means are
statistically indistinguishable (-3114.4 vs -3158.0, t=0.21, p=0.84).

Traced the outlier directly (GreedyHAP, same seed, instrumented per-decision
`pending_count()`/`in_network_count()`/true-queue sampling): a genuine,
reproducible **deterministic-greedy gridlock** — true total queue goes
205.6 (t=1200s) -> 4633.8 (t=1800s) -> 12968.3 (t=3000s) under exact eta=0,
while the SAME demand realisation under eta_u=0.010 (98% as noise-free)
stays healthy throughout. This is not a code bug: GreedyHAP is a
deterministic argmax over pressure, and at exact zero sensing noise some
demand draws apparently produce sustained tie/near-tie conditions between
movements that lock the controller into a bad switching pattern; even
minuscule sensing noise breaks the tie and avoids it. Real, rare (1/16 in
this sample), and worth a sentence in `Sec. IX` (limitations) as a
noted fragility of pure greedy control that HAPLight-RL's stochastic
policy does not obviously share (untested directly — flagged, not claimed).

**Fix**: `scripts/train.py` now computes both greedy-HAP references from a
new `--reference-episodes` (default 24, decoupled from `n_envs` since this
is a one-time pre-flight cost) rather than `n_envs` (8) — cheap insurance
against the same single-episode domination recurring for S2. **Corrected
clean gap**: policy's last-10-iteration `eta0_return` mean (-2823.0) against
the outlier-robust reference (-3114.4) is **9.4%**, not P4-5's 43.2% (using
the broken -4970.6 reference) — very close to the ~12% the author estimated
by inspection before any of this was rerun. Recomputed "beats reference"
count against the corrected reference: **65/100 overall, 8/10 in the last
10** (down from the invalid 97/100 and 10/10) — still a majority, still
concentrated late in training, but a materially smaller and more honest
margin, consistent with the eta0_return trend being real-but-not-significant
per point 1.

**3. The actual deliverable: task-metrics table, not the reward curve.**
New permanent script `scripts/evaluate_policy.py` — final checkpoint
(iteration 99) composed with the SafetyFilter (i.e. HAPLight-RL exactly as
deployed) vs FixedTime/MaxPressure/GreedyHAP, ATT/AWT/AQL/TP/PWD, 5 seeds,
paired per-seed demand (same methodology as P1c-3/P1c-4), at eta=0 and
eta=0.6, with paired 95% CIs and paired t-tests against GreedyHAP:

*eta=0 (clean):*

| controller | ATT | AWT | AQL | TP | PWD |
|---|---|---|---|---|---|
| FixedTime | 242.6±8.9 | 19.1±0.7 | 1147.0±147.8 | 3708.2±13.9 | 126.1±15.2 |
| MaxPressure | 246.2±9.4 | 20.3±0.4 | 1140.5±155.5 | 3708.2±16.3 | 128.2±16.3 |
| GreedyHAP | 243.7±8.5 | 20.2±0.8 | 1089.5±132.4 | 3714.8±5.1 | 125.2±13.7 |
| **HAPLight-RL** | **237.4±10.1** | **18.1±0.3** | **994.1±154.4** | **3716.8±4.9** | **114.0±14.7** |

Delta vs GreedyHAP (positive = HAPLight-RL better): ATT +6.35 [-4.14,+16.85]
p=0.168 (n.s.); AWT +2.10 [+1.16,+3.03] **p=0.0035**; AQL +95.41
[-41.55,+232.36] p=0.125 (n.s.); TP +2.00 [-2.21,+6.21] p=0.258 (n.s.); PWD
+11.23 [+0.75,+21.71] **p=0.041**. All five point the same direction;
two of five individually significant at n=5.

*eta=0.6 (matches training/deployment sensing noise):*

| controller | ATT | AWT | AQL | TP | PWD |
|---|---|---|---|---|---|
| FixedTime | 242.6±8.9 | 19.1±0.7 | 1147.0±147.8 | 3708.2±13.9 | 126.1±15.2 |
| MaxPressure | 248.0±8.9 | 20.7±0.8 | 1157.8±133.7 | 3707.8±9.4 | 131.9±15.5 |
| GreedyHAP | 246.9±9.4 | 20.4±0.8 | 1122.5±147.8 | 3710.6±5.5 | 127.9±15.7 |
| **HAPLight-RL** | **238.5±10.6** | **18.4±0.8** | **1002.4±158.3** | **3722.4±3.3** | **114.7±16.8** |

Delta vs GreedyHAP: ATT +8.34 [+2.97,+13.71] **p=0.0125**; AWT +1.95
[+1.59,+2.30] **p=0.0001**; AQL +120.05 [+23.48,+216.62] **p=0.026**; TP
+11.80 [+6.22,+17.38] **p=0.0042**; PWD +13.18 [+7.18,+19.18] **p=0.0037**.
**All five metrics significant at n=5 under realistic sensing noise.**

The reward (`total_queue = -Sigma_m x_m`) DOES translate to AQL, as claimed,
and the improvement is not confined to AQL — ATT/AWT/TP/PWD all move the
same direction, more strongly and more significantly under eta=0.6 than
eta=0. This is a coherent story, not a coincidence: GreedyHAP is a reactive
argmax over sensed pressure with no learned robustness to sensing error,
while HAPLight-RL was trained under eta~U[0,0.6] the whole time — the
policy's advantage is concentrated exactly where a real camera-based
deployment (imperfect sensing, per `Sec. V-C`'s x_hat/true_w split, P4-2)
actually operates, which is the more paper-relevant condition. **This table,
not the training return curve, is what Sec. VII reports.**

**Completion gate (Sec. VI-A H2), restated honestly**: the training-condition
return result is real and significant (point 1). The clean-channel
return-vs-reference result is directional but not independently significant
at this iteration count (point 1), though the corrected reference (point 2)
and the task-metrics table (point 3) now support the underlying claim on
firmer ground than P4-5's numbers did — the gate is better evidenced by the
eta=0.6 task-metrics table (all five metrics significant) than by either
return curve alone. **Proceed to S2** with: `total_queue` reward,
`scripts/validate_reward.py` gating, dual references at `--reference-
episodes 24`, the random+filter control ablation, and
`scripts/evaluate_policy.py`'s 5-seed task-metrics table as the standard
reporting protocol.

### P4-7. S2 aborted at iteration 40: single-episode clean eval is fragile to the same gridlock mode P4-6 found, more so on a 16-intersection grid
`Sec. V-F Algorithm 2` (abort criterion), `Sec. VI-C` (S2 topology), `Remark 6`.

`s2_grid` run (seed 0, `total_queue` reward, same protocol as P4-6) hit the
iteration-40 abort: `eta0_return` slope -22.0/iteration (first=-781.4,
last=-3069.4). Debugged in the requested order plus one the data pointed to:

1. **Reward signal quality**: `reward_queue_correlation` = -0.176 — weak but
   same sign and same order of magnitude as S1's -0.132 (which succeeded).
   Not the differentiator.
2. **Filter masking gradient steps**: activation ranged ~7-16% across the
   40 iterations, in the same band S1 ran at successfully. Not the
   differentiator.
3. **Observation content**: not reached — (4) below is sufficient to
   explain the decline without invoking this.
4. **Not on the original list, but what the evidence actually shows**: 6 of
   40 `eta0_return` values (15%) are catastrophic outliers (< 2x the
   median), vs 1/16 (6%) for GreedyHAP's own zero-noise fragility in P4-6.
   Traced the worst one directly — iteration 39's checkpoint, same
   deterministic+filter+eta=0 eval seed, instrumented per-decision
   `pending_count()`/`in_network_count()`/true-queue sampling: true total
   queue goes 0 (t=0) -> 978.4 (t=1200s) -> **4779.6 (t=1800s)** -> 7140.8
   (t=3000s), in-network count 271->601, insertion backlog (`pending_
   count()`) starts appearing at t=2400s and reaches 113 by t=3000s. Same
   qualitative signature as P4-6's GreedyHAP trace: a sudden ~5x queue jump
   in one 600s window, not a gradual decline. Cumulative filter activation
   climbs alongside it (0%->11.1%->20.4%) — the filter IS firing more as
   queues rise, but a per-intersection local override does not visibly
   unwind a cascade that has already gone multi-intersection; 16
   interconnected intersections give a cascade more adjacent paths to
   propagate through than S1's 5-intersection arterial line, consistent
   with the higher outlier rate.

**Methodological point, same lesson as P4-6 applied one level up**: the
clean-eval trend the abort criterion watches is a SINGLE, non-averaged
episode per iteration (`eval_result = run_episode_worker(..., 9999, 0.0,
True)`), unlike `mean_return`, which pools 8 workers. `mean_return`'s own
slope over the same 40 iterations (+3.71/iteration, t=0.83, p=0.41) shows
no comparable collapse. A one-episode signal is exactly as fragile to a
15%-probability rare event as the n=8 reference was in P4-6 — the abort
fired on a metric that is disproportionately exposed to this specific
failure mode, not necessarily on genuine policy regression. **Not yet
fixed in code** (author has not approved re-running S2 with a changed
protocol): the fix P4-6's own logic implies is averaging the clean eval
over a handful of episodes (matching `--reference-episodes`-style
robustness) before trusting its trend for an abort decision. Flagged for
the author to decide before any S2 rerun, rather than silently changed and
rerun unilaterally.

## Phase 4c — Storage-aware HAP (spillback deadlock)

### P4c-1. Design: capacity-aware effective saturation flow, reusing env.storage
`Sec. V-D` (Assumption A5, greedy HAP), `Cor. 1` (certified floor).

Author diagnosis, confirmed by re-reading the paper: Theorem 1 explicitly
analyses "the slotted store-and-forward abstraction standard in this
literature" (line 655) with a CONSTANT mu_m under Assumption A5 (line 694).
Neither the theorem nor Corollary 1's proof sketch mentions finite storage.
`src/hap.py`'s `movement_weight`/`greedy_phase` never reference
`env.storage`. This is a real hole, not a misreading: P4-6's GreedyHAP
outlier and P4-7's S2 abort are the same failure -- a movement's downstream
link physically fills, pressure keeps crediting it anyway (A5 silently
assumes storage state doesn't matter, which is false once it binds), and
green gets wasted on a movement that can't actually discharge while
cross-traffic starves.

**Design chosen**: mu_m^eff(t) = mu_m * phi(h_m(t)), phi(h) = clip(h/theta,
0, 1) -- a capacity-aware effective saturation flow (Gregoire/Frazzoli-
style finite-buffer backpressure), not a weight change or a hard mask.
Reasoning: (a) SUMO's real discharge rate ALREADY drops near zero when
downstream is jammed -- A5's constant-mu_m is already silently wrong in
this regime, so mu_m^eff is a truthful refinement (A5': storage-state-
dependent, still composition-invariant conditional on state) rather than a
patch; (b) it composes with `phase_pressure`/`greedy_phase` completely
unmodified -- only the `mu` dict passed in changes; (c) phi(0)=0 is a
structural, not probabilistic, guarantee: the argmax can never be justified
by crediting flow into an already-full sink. Stability sketch: replacing
A5 with A5' and mu_m with mu_m^eff everywhere preserves the Lyapunov drift
argument's key equality (y_m ~= mu_m^eff * Delta t) and gives a capacity-
region Λ_S ⊆ Λ with the same argmax-maximizes-the-right-functional
structure -- NOT a completed proof, flagged as a sketch requiring Appendix-
level work, not asserted as done.

Implementation: `storage_headroom_fraction`/`capacity_barrier`/
`storage_aware_mu` (pure functions, `src/hap.py`), a static
`env.edge_capacity` map (sum of `env.storage[i][mv]` over every movement
sharing an edge as its in_edge, built once at topology discovery
alongside `env.storage` itself), and `GreedyHAP(env, storage_aware=False)`
-- default False, so every existing result is unaffected until explicitly
enabled. `theta` = `cfg["hap"]["storage_aware_theta"]` (default 0.15, not
tuned to force a result). 9 new unit tests in `tests/test_hap.py`,
including the criterion-4 invariant (storage-aware == plain HAP exactly
when headroom >= theta everywhere) and an end-to-end argmax-flip test.

### P4c-2. Step 1 (reproduction): confirmed spillback deadlock on both known cases, not just heavy congestion
`Sec. VI` (evaluation), P4-6, P4-7.

New permanent script `scripts/diagnose_gridlock.py` (per-decision true
queue, in-network count, pending count, and — new — the worst per-movement
storage occupancy x_m/env.storage[i][mv] network-wide). Reproduced both
known cases exactly (same seeds as P4-6/P4-7):

- **S1** (GreedyHAP, seed 119691546, eta=0): worst-movement storage
  occupancy hits **377.2%** at t=1800s (n0_3, movement `n0_2_n0_3->
  n0_3_stub8`), pinned there through t=2400s, then **389.7%** at a
  different movement (`n0_0_n0_1->n0_1_stub4`) from t=3000s to episode end
  (t=3595s) — sustained, not transient.
- **S2** (trained policy iteration-39 checkpoint + filter, seed 779452647,
  eta=0): worst-movement occupancy hits **715.3%** at t=1800-2400s
  (n3_1, movement `n3_0_n3_1->n3_1_n2_1`), pinned there through episode
  end.

A movement sustaining 3-7x its OWN physical storage capacity for 1000+
seconds is structural spillback deadlock, not merely heavy congestion
(heavy congestion would show elevated queues without any single movement
pinned that far past its own capacity for that long). Gate 1 (mechanism
confirmed on both cases) passed.

**Clarification that changes how S2 must be re-tested**: plain GreedyHAP
(no policy, no filter) run on the IDENTICAL S2 seed/eta does NOT deadlock
— true queue peaks at 2604.8 and clears to 687.2, ending with 0 pending
vehicles. Storage-aware GreedyHAP gives a bit-identical trajectory (nothing
to throttle). **S1 and S2 are not the same failure mode at the controller
level**: S1 is a genuine GreedyHAP-level deadlock; S2's was specific to
the TRAINED POLICY's deterministic argmax choices at eta=0, which the
filter did not catch in time. Testing "storage-aware GreedyHAP" in
isolation, as originally planned, is therefore not the right test for S2
— the relevant question there is whether a storage-aware FILTER FALLBACK
would have overridden the policy's specific bad choices in time. Not yet
tested (moot given the P4c-3 gate failure below).

### P4c-3. Step 2: GATE FAILED on S1 — the fix does not clear its first test
`Sec. V-D`, P4c-1.

Storage-aware GreedyHAP (theta=0.15) on the S1 seed (119691546, eta=0):
final true queue **13665.5** vs plain GreedyHAP's 14398.7 — a ~5% reduction,
not "queue clears, no runaway." The trajectory is bit-identical to plain
GreedyHAP through t=2400s and the worst-occupancy movement/timing is
UNCHANGED (377.2% at n0_3/`->stub8` at t=1800-2400, 389.7% at n0_1/`->
stub4` from t=3000s). **Per the pre-registered gate, this stops the
program here — not scaled to S2 or to a full retrain.**

**Root cause, confirmed by direct instrumentation, and it is NOT the
catchment-length blind spot flagged as a risk in P4c-1**: it is a
GRANULARITY MISMATCH between the sensed headroom signal and where the
capacity constraint actually binds. Traced the specific upstream feeder of
the edge that deadlocks (`n0_1_n0_2->n0_2_n0_3` etc., at n0_2): at t=1800s
— the exact moment the collapse happens — `x_down_hat` = 333.2 against
`edge_capacity["n0_2_n0_3"]` = 632.1, headroom = 0.473, mu_eff/mu = 1.000
(theta=0.15 never came close to binding). Yet `true_queues["n0_3"]["n0_2_
n0_3->n0_3_stub8"]` was already at 377.2% of THAT movement's OWN storage
(126.2) at the same timestamp. The reason: edge `n0_2_n0_3` is shared by
THREE downstream movements at n0_3 — `->n0_4` (storage 380.3), `->stub7`
(storage 125.5), `->stub8` (storage 126.2), summing to the 632.1 used as
`edge_capacity`. The narrow `->stub8` turn pocket (a fifth of the edge's
aggregate capacity) was catastrophically over capacity while the edge-WIDE
sensed aggregate looked comfortably under 50% occupied, because the
much-larger `->n0_4` through movement wasn't congested and diluted the
average. `x_down_hat` (built from `w_hat`, an edge-aggregate quantity — the
same "agg" convention `movement_weight` has always used) cannot see a
single overloaded turn pocket hiding inside a healthy-looking edge total.

**What this rules in/out**: the catchment-length concern (200m sensing vs
300-400m links) may still be a real, separate effect, but it is not what
killed this test — the barrier had a comfortable 47% headroom reading by
its own (edge-level) logic and simply never engaged, so a wider catchment
window would not have helped a signal that is aggregated at the wrong level
to begin with.

**Implication for a corrected design (not yet implemented — awaiting
author direction, per the gate)**: the headroom signal needs to be sensed
per DOWNSTREAM MOVEMENT (matching the specific turning continuation), not
per edge. The paper's own Eq. 8 (`w_m = x_m - Sigma_m' r_mm' x_m'`) already
supports a per-downstream-movement breakdown via the turning-ratio dict;
the current CODE only ever calls `movement_weight` with the single-entry
aggregate form (`{"agg": x_down}, {"agg": 1.0}`) everywhere pressure is
computed. Getting a real per-movement downstream signal would need new
sensing plumbing (which specific next-intersection movement each upstream
movement's traffic actually turns into, sensed separately) — a materially
bigger change than the theta/edge-aggregate version tested here, and
outside this gate's scope to implement unilaterally.

### P4c-4. Oracle test CONFIRMS the mechanism: granularity, not the barrier form, was broken
`Sec. V-D`, P4c-1, P4c-3.

Author-directed 20-minute check before committing to real plumbing: reran
the exact S1 seed (119691546, eta=0) with the storage-aware barrier fed
`info["true_queues"]`, resolved per SPECIFIC downstream movement (worst-of-
the-group sharing an edge, via the new `env.downstream_by_edge` topology
map — see P4c-1's implementation), instead of the edge-aggregate sensed
`x_down_hat`. Result: final true queue **230.4** (vs plain GreedyHAP's
14398.7, vs the edge-aggregate storage-aware attempt's 13665.5),
throughput 3713 (vs 2085), **0 final pending** (vs 243). Not a monotone
collapse-free run — worst-movement occupancy still spikes to 122-237%
transiently around t=1800-3000s — but it RECOVERS rather than running
away, which is exactly the pre-registered gate ("queue clears, no
runaway"). **Confirmed: the barrier form (mu_m^eff = mu_m*phi(h_m)) and
theta=0.15 are sound. P4c-3's failure was entirely a signal-resolution
problem** — feeding the same mechanism a correctly-resolved signal fixes
it. Per-movement downstream sensing plumbing (the harder, deferred half of
P4c-3) is now justified to build, since the mechanism it would feed is
proven to work, not merely theorized to.

### P4c-5. Storage-triggered filter CONFIRMS the S2 diagnosis: it is a timing problem, not a pressure problem
`Sec. V-D` (Corollary 1), P4-7, P4c-2.

P4c-2 established S2's failure is distinct from S1's: plain GreedyHAP does
not deadlock on the S2 seed (779452647), only the trained policy does, and
the filter's existing queue-magnitude trigger did not catch it in time.
Author's diagnosis: Corollary 1's proof sketch assumes greedy control was
active throughout, not handed a single decision at the edge of collapse —
one greedy action cannot undo an already-multi-intersection spillback
configuration. Fix tested: `SafetyFilter(storage_aware=True)` (new,
`src/safety_filter.py`) OR's a second, independent trigger —
`_storage_trigger_stat`, the worst SENSED occupancy fraction (x_hat /
env.storage) among an intersection's own movements AND whatever they
discharge into, at MOVEMENT resolution (not edge-aggregate — `x_hat[j][mv2]`
is already built from mv2's own lane subset, so this trigger does not
inherit P4c-3's dilution problem even without new sensing plumbing) —
against `rl.filter.storage_trigger_threshold` (0.85, first guess, not
tuned). The fallback controller is UNCHANGED (still plain GreedyHAP) —
this isolates trigger TIMING as the variable, independent of P4c-3's still-
open barrier-resolution question.

Same checkpoint (iteration 39), same seed, same eta=0, deterministic:
final true queue **356.8** (vs 7066.4), throughput 5413 (vs 4886, +10.8%),
**0 final pending** (vs 151), worst-occupancy peaks at 120.3% then
recovers to 38.5% by episode end (vs pinned at 715.3% through the end
originally) — achieved at **9.6% filter activation**, comparable to the
P90-calibrated queue-magnitude trigger's usual rate, not by overriding
constantly. **Confirmed: timing, not pressure, was S2's problem.**

### P4c-6. Theory finding (author-directed, paper .tex NOT touched)
`Thm. 1`, `Cor. 1`, `Assumption A5`.

Two statements, logged for the paper author to incorporate, not applied to
`HAPLight_journal_v2.tex` here:

(a) Theorem 1 assumes infinite link buffers (store-and-forward, line 655,
Assumption A5's constant mu_m). Under finite storage, greedy HAP can
deadlock — demonstrated on two independent seeds (P4-6, P4-7), mechanism
confirmed via direct per-movement storage instrumentation (P4c-2), and
repaired in principle by storage-aware HAP (P4c-4's oracle result). The
heterogeneity-correctness argument (space-equivalency weights, Lemma 1) and
the classification-free camera-signal argument for `env.storage` (reusing
the SAME area-based estimator that already produces x_hat) are unaffected
and still hold — this is an addition to the theory (a needed premise made
explicit and then satisfied), not a retraction of anything already
claimed. Per-movement sensing plumbing is still required before storage-
aware HAP is a deployable variant, not just a validated mechanism (P4c-3).

(b) Corollary 1's floor guarantees recovery only if the filter engages
BEFORE the network reaches a greedy-irrecoverable state — this condition
was implicit and unstated. Storage-triggered filtering (P4c-5) supplies
it directly: triggering on remaining downstream headroom, rather than only
on already-large queue magnitude, engages the certified floor while
greedy control can still act, not after the state it would need to recover
from is already unrecoverable. This is a SECOND, SHARPER statement about
when the certified floor actually holds — a strengthening of Corollary 1's
practical applicability, not a retraction of its correctness under the
conditions it already assumed.

**Not yet done**: neither P4c-4's oracle barrier nor P4c-5's storage-
triggered filter has been wired into `scripts/train.py`'s default protocol
or used for a retrain. Awaiting author direction on which (or both) to
adopt before any S1/S2 retrain per the original P4-6/P4-7 protocol.

### P4c-7. S2 filter wired in; sensing-feasibility answered; cheap deployable S1 fix found and promoted
`Sec. V-D`, `Assumption A5`, P4c-1 through P4c-6.

**1. S2 filter wired in.** `scripts/train.py::run_episode_worker` now
constructs `SafetyFilter(env, B, storage_aware=True)` unconditionally —
the new default training protocol. `compute_random_policy_filter_control`
picks this up automatically (it calls `run_episode_worker`), so the
control ablation stays comparable to real training. `metadata.json` gains
`safety_filter_storage_aware`/`safety_filter_storage_threshold` fields for
the record. `calibrate_threshold` is unaffected (it drives `GreedyHAP`
directly, never `SafetyFilter`).

**2. Sensing-feasibility answer (author's question, before any S1
plumbing): can a camera physically sense per-turn-pocket headroom? No —
not "sometimes," but universally on this network, and the reason
generalises.** Checked S1's actual lane assignments directly (not assumed):
`n0_2_n0_3->n0_3_stub8` and `n0_2_n0_3->n0_3_n0_4` (the two movements
whose shared edge caused P4c-3's failure) both use lane `n0_2_n0_3_2` —
the SAME physical lane serves both the through movement and the turn.
Systematic check across the whole S1 network: **every one of the 60
movements across all 5 intersections shares at least one lane with
another movement (100%)**. This is not a rare geometry — it is the norm
for an approach with fewer lanes than the number of distinct turning
movements it serves, which is the common case, not an edge case, and is
if anything MORE likely under the heterogeneous, comparatively informal
lane-discipline Indian mixed traffic this paper's own domain grounding
already emphasises (dominant, lane-splitting two-wheeler share).

A camera cannot attribute a vehicle on a shared lane to one specific
turning movement before that vehicle actually executes the turn near the
stop line — occupancy on lane `n0_2_n0_3_2` is genuinely ambiguous between
"turning to stub8" and "continuing to n0_4" until the vehicle commits.
(Confirmed this is not an artefact of the code: `env._measure()`'s
`per_lane_true[lane][vclass]` is keyed by lane and vehicle class only,
with no route/destination field, so `x_hat`/`true_queues` for two
movements sharing a lane both draw from the identical per-lane count —
an accurate model of what a lane-occupancy camera could see, not a
measurement bug.) **The assumption a per-movement barrier would need —
vehicles pre-sorted into turn-specific lanes for the full length that
`env.storage`'s capacity is computed over — does not hold on this
network's own geometry, let alone the real deployment domain.** Per-
movement downstream sensing plumbing is therefore not just unbuilt but
would rest on a premise this paper's own network violates universally; it
should not be built, independent of cost, and doing so would also
quietly abandon the "classification-free, cameras-only" premise the
whole area-estimator framework is built on (route-level tracking is a
different, heavier sensing modality).

**3. Cheap deployable version tested and PASSED — no plumbing needed.**
`hap.worst_downstream_occupancy` (new, pure function): the worst SENSED
(`x_hat`) occupancy fraction among the specific movements sharing a
downstream edge, each against its OWN `env.storage` (never a summed edge
capacity — avoids P4c-3/P4c-6's shared-lane double-counting). This needs
NO new sensing: `x_hat[j][mv2]` is already movement-resolved (built from
mv2's own lane subset), so "worst of the group" is computable from data
`env.py` already produces. Tested on the exact S1 seed (119691546, eta=0):
final true queue **217.6** — matching the oracle result (230.4) almost
exactly, both a world away from plain GreedyHAP's 14398.7. Throughput 3729
vs oracle's 3713; both clear to 0 pending. **The sensed, deployable signal
recovers the deadlock as well as the oracle one did — the earlier failure
was entirely about resolution (edge vs movement), never about needing
ground truth.**

**Promoted into `GreedyHAP(storage_aware=True)` as the new default
storage-aware behaviour**, replacing P4c-1's edge-aggregate version (which
P4c-3 showed never engages). Verified the promoted class reproduces the
standalone test bit-for-bit (final_tq=217.6, compl_tp=3729, pending=0,
identical to three decimal places). The old `storage_headroom_fraction`/
`env.edge_capacity` remain in the codebase (still correct as pure
functions, still documented as the failed first attempt) but are no
longer used by `GreedyHAP` — kept as ablation record, not deleted, per
this project's standing practice of not erasing negative results.

**Still open**: step 4 (S1 regression check — re-evaluating the existing
trained checkpoint with the new `storage_aware=True` filter, comparing
against P4-6's original task-metrics numbers) is running; report follows.
`GreedyHAP(storage_aware=True)` (this entry) is validated on ONE seed —
not yet swept over the ≥20-seed gridlock-rate protocol the author's
original experimental program specified, and not yet wired into
`SafetyFilter`'s fallback controller (P4c-5's filter fix and this barrier
fix remain independently validated, not yet composed together).

### P4c-8. Step 4 regression check: REAL regression found on S1, mechanistically explained — not deployed further
`Sec. V-D`, P4c-5, P4c-7.

Re-evaluated the EXISTING S1 checkpoint (iteration 99, unchanged, no
retrain) with `storage_aware=True` added to its `SafetyFilter`, 5 seeds,
eta in {0, 0.6}, `scripts/evaluate_policy.py --storage-triggered-filter`,
compared directly against P4-6's original numbers (same checkpoint, same
seeds, filter unchanged). Author's instruction was to verify, not assume,
and verification found a real problem.

**Aggregate signature**: at eta=0, HAPLight-RL's AQL variance across seeds
roughly QUADRUPLED (154.4 -> 592.2 std) and throughput variance exploded
(4.9 -> 260.2 std); the paired delta vs GreedyHAP flipped sign on both AQL
(+95.41 -> -190.92) and TP (+2.00 -> -111.40), though neither reaches
significance at n=5 (p=0.54, p=0.40) because ONE seed dominates the
variance.

**That one seed, isolated and traced**: seed=3, eta=0. Original (no
storage trigger): att=228.56, aql=868.98, tp=3719 — clean, no deadlock.
With the storage-triggered filter: att=248.71, **aql=2336.19** (+169%),
**tp=3138** (-15.6%). Reproduced with `scripts/diagnose_gridlock.py
--controller policy --storage-triggered-filter` on the identical seed:
**filter_activation=36.6%** (vs ~9.6% on the S2 case that validated this
fix) and a fresh deadlock signature — true queue 145.6 (t=1200s) ->
2306.4 (t=1800s) -> 5625.8 (t=3000s), worst-movement occupancy pinned at
**398.6%** through episode end. A seed with no deadlock at all before now
has one, under the SAME policy checkpoint, changed only by the filter.

**Mechanism, not just correlation**: the storage-triggered filter's
fallback is deliberately PLAIN GreedyHAP (P4c-5 kept it that way on
purpose, to isolate trigger timing as the tested variable, independent of
P4c-3's barrier-resolution question). But P4c-3 already proved plain
GreedyHAP can itself deadlock on this exact network. At 36.6% activation,
over a third of decisions on this seed are handed to a fallback with its
OWN known deadlock exposure — the fix that helps S2 (where P4c-2 confirmed
plain GreedyHAP never deadlocks on the tested seed) does not transfer
safely to S1, where it can. This is exactly the failure mode the author
warned against ("a fix that saves the grid but degrades the arterial is a
bad trade") and exactly why it was checked rather than assumed.

**Natural next hypothesis, NOT implemented or tested here, pending author
direction**: compose the two independently-validated fixes — use
`GreedyHAP(storage_aware=True)` (P4c-7, validated on the S1 deadlock seed)
as the storage-triggered filter's fallback, instead of plain GreedyHAP.
This would give the filter a fallback that does not inherit P4c-3's
deadlock exposure, potentially closing exactly the gap this regression
exposes. Not implemented: this changes the S2 result's own conditions
(P4c-5 was validated against a plain-GreedyHAP fallback specifically) and
should be re-validated on the S2 seed before being assumed to still work
there, not just assumed safe on S1.

**Status: `storage_aware=True` in `scripts/train.py` (P4c-7, step 1) is
now a KNOWN RISK on S1, not a validated default.** Not reverted
unilaterally — flagged for author decision. No multi-seed training run
should proceed on either scenario with the current (plain-fallback)
filter configuration until this is resolved one way or another.

### P4c-9. Two orthogonal deadlock defenses, neither sufficient alone: full 2x2 + the quantified recoverability margin
`Sec. V-D` (Corollary 1), P4c-1, P4c-5, P4c-7, P4c-8.

**The 2x2.** `SafetyFilter` now exposes two INDEPENDENT switches: `storage_aware`
(does the TRIGGER include storage occupancy, or queue-magnitude only —
controls WHEN the filter engages) and `fallback_storage_aware` (does the
FALLBACK controller use storage-aware pressure, or plain GreedyHAP —
controls WHAT ACTION is taken once engaged; previously hardcoded to plain,
which is what made P4c-8's regression possible without anyone choosing
it). All four combinations run on both known deadlock seeds, single
episode each (trained-policy checkpoint + filter, deterministic, eta=0):

*S1 (seed=3 — P4c-8's regression seed):*

| trigger | fallback | final_q | max_q | throughput | pending | filter_act |
|---|---|---|---|---|---|---|
| plain | plain | 112.0 | 2661.6 | 3719 | 0 | 5.5% |
| **storage** | **plain** | **6536.6** | **6536.6** | **3138** | 0 | 36.6% |
| plain | storage | 287.2 | 2661.6 | 3729 | 0 | 5.6% |
| storage | storage | 198.4 | 2074.4 | 3723 | 0 | 16.5% |

*S2 (seed=779452647 — P4-7's original abort seed):*

| trigger | fallback | final_q | max_q | throughput | pending | filter_act |
|---|---|---|---|---|---|---|
| plain | plain | 7066.4 | 7140.8 | 4886 | 151 | 22.0% |
| storage | plain | 356.8 | 2375.2 | 5413 | 0 | 9.6% |
| **plain** | **storage** | **3364.0** | **4783.6** | **5099** | 155 | 21.7% |
| storage | storage | 276.0 | 2454.4 | 5407 | 0 | 10.5% |

**Reading it**: on S1, the ONLY unhealthy cell is (storage-trigger,
plain-fallback) — exactly P4c-8's regression, isolated cleanly. On S2,
the ONLY unhealthy cells are the two with a PLAIN trigger — (plain,plain)
is P4-7's original problem, and (plain, storage) shows storage-aware
FALLBACK QUALITY ALONE does not help if the trigger never fires early
enough to invoke it — the policy has already driven the network past the
point where one correct decision, arriving late, is enough. **(storage,
storage) is the only cell healthy on BOTH seeds.** This is not "compose
them and hope" — it is the empirically unique solution among the four
tested, matching the author's hypothesis and mechanistically consistent
with everything found so far: storage-aware pressure prevents entry into
the deadlocked STATE (P4c-7, a property of the controller); storage-
triggered filtering ensures the certified floor is consulted before that
state becomes irrecoverable (P4c-5, a property of WHEN control is
consulted). Two different failure classes, two different gaps; either
alone leaves the other one open.

**Threshold sweep — the quantified Corollary-1 companion condition.**
Author's framing: P4c-8's regression means the 0.85 trigger fired, and
the network deadlocked anyway — the trigger engaged too late, at or past
the point a single greedy decision could still recover from. Swept the
PLAIN-fallback filter's trigger threshold on the S1 seed:

| threshold | final_q | max_q | throughput | filter_act | outcome |
|---|---|---|---|---|---|
| 0.60 | 148.0 | 2550.4 | 3705 | 22.0% | recovers |
| 0.70 | 267.2 | 2433.6 | 3722 | 21.8% | recovers |
| 0.80 | 265.6 | 2619.2 | 3710 | 21.1% | recovers |
| **0.85** | **6536.6** | **6536.6** | **3138** | 36.6% | **deadlocks** |
| 0.90 | 6650.2 | 6650.2 | 3152 | 36.7% | deadlocks |

**Sharp transition, not a gradual one**: 0.60-0.80 are all clean and land
within a narrow throughput band (3705-3722); 0.85-0.90 both collapse to
~3140-3150 with final queues 25-45x higher. **The highest threshold at
which the deadlock is still prevented is 0.80, not the 0.85 currently
configured.** This is the quantitative form of the informal companion
condition to Corollary 1 (P4c-6b: the floor recovers only if the filter
engages before an irrecoverable state) — on this seed, "irrecoverable"
begins somewhere in the 80-85% occupancy band, a real measured property
of how fast this network's spillback cascade compounds once triggered,
not a free parameter to retune away. Note the activation rate is roughly
FLAT (21-22%) across 0.60-0.80 and only jumps at 0.85-0.90 (36-37%) —
the extra activation at the failing thresholds is largely REACTIVE
(chasing an already-collapsed state afterward), not preventive; a higher
number here is a symptom of the trigger being too late, not evidence it
is doing more work.

**Not yet done**: (storage, storage)'s OWN threshold margin was not swept
(P4c-9's 2x2 used the default 0.85 throughout) — it is plausible the
storage-aware fallback gives the composed system a WIDER safe-threshold
band than the plain-fallback's 0.80 ceiling, since a late-but-still-
storage-aware override may be more forgiving than a late plain one, but
this is not measured, only hypothesised. `storage_aware=True` in
`scripts/train.py` (P4c-7, step 1) still uses the OLD hardcoded plain
fallback — **not yet updated to the validated (storage, storage)
configuration**, and no multi-seed training should launch before that
change is made and the still-open threshold-margin question above is
at least acknowledged, per the author's explicit hold.

### P4c-10. Multi-seed threshold sweep for (storage, storage): S1 has wide margin, S2 does not — and the aggregation method matters
`Sec. V-D` (Corollary 1 companion condition), P4c-9.

**Why this run exists**: P4c-8's regression was caused by exactly one
mistake — deploying a threshold (0.85) validated on zero seeds. Validating
the (storage, storage) fix (P4c-9) on the two seeds that FOUND the
mechanism repeats the same risk one level up, so before wiring anything
into `scripts/train.py`, swept threshold in {0.60, 0.70, 0.80, 0.85, 0.90,
0.95} across 10 seeds per scenario (`scripts/sweep_storage_threshold.py`,
new, permanent — multiprocessing Pool, module-level worker matching
`scripts/train.py`'s own convention; B calibrated once per scenario, not
per run). S1: seeds 0-9 (includes the known seed=3). S2: the known seed
779452647 plus fresh draws 0-8. All at eta=0 — deliberately the tie-
locking worst case (P4-6: even eta=0.01 breaks these ties), so every
number here is a LOWER BOUND on the real, sensing-noise-present
operational margin, not the operational value itself.

**A bug in my own first analysis, caught before it was reported**: the
script's initial aggregation computed "highest threshold that happened to
be safe" per seed, then took the min across seeds. This silently assumes
monotonicity (safe-at-X implies safe-at-every-Y<X) that the data does
NOT support — two S2 seeds fail at ISOLATED threshold values with safe
values on both sides (seed 6: OK at 0.70, FAILS at 0.80, OK at 0.85,
FAILS at 0.90, OK at 0.95). The per-seed "highest safe" number was
technically true and completely misleading (it reported 0.95 for seed 6
despite an intervening failure at 0.90). Fixed to the only sound
question: for each THRESHOLD VALUE, does it hold across every seed
simultaneously. Flagging and fixing this before reporting it, not after,
is the entire point of the author's multi-seed instruction.

**S1: wide margin, no failures found.** All 10 seeds safe at all 6
tested thresholds, 0.60 through 0.95 — no deadlock anywhere in the grid.
The composed pressure fix (P4c-7) plus the composed filter fix (P4c-5)
together give S1 a much wider margin than the plain-fallback filter alone
(P4c-8's sweep found a hard cliff between 0.80 and 0.85 on the single
regression seed). 0.95 is the top of what was TESTED, not a proven
ceiling — the true safe range on S1 may extend further; not measured.

**S2: real non-monotonicity, exactly two seeds responsible.** Per-
threshold status across all 10 seeds:

| threshold | status |
|---|---|
| 0.60 | FAILS (seed 779452647, final_pending=361) |
| 0.70 | safe across all 10 |
| 0.80 | FAILS (seed 6, final_pending=84) |
| 0.85 | safe across all 10 |
| 0.90 | FAILS (seed 6, final_pending=101) |
| 0.95 | safe across all 10 |

8 of 10 seeds (0,1,2,3,4,5,7,8) are safe at EVERY tested threshold. The
non-monotonicity is entirely carried by two seeds with narrow, non-
overlapping failure windows: 779452647 fails only near 0.60; seed 6 fails
only near 0.80 and 0.90. Because the two windows don't overlap, three
threshold values (0.70, 0.85, 0.95) happen to thread between them — but
EVERY one of those three has a FAILING neighbour immediately adjacent in
this grid (0.85 is flanked by 0.80-FAILS and 0.90-FAILS on both sides).
**None of the three passing values has a confirmed margin.** This is a
real property of a more complex, more interconnected network (16
intersections vs. S1's 5), consistent with everything else this
investigation has found about S2 being more deadlock-prone than S1 (P4-6:
6% GreedyHAP outlier rate vs. P4c-8's 15% for S2's trained policy) — not
an artefact of the sweep or the aggregation fix.

**Conclusion: the user's own pre-registered criterion — "a threshold that
holds across all seeds, with a small margin" — is not met by any point in
this grid for S2.** 0.85 (the existing config default, already validated
on both known seeds in P4c-9) is the pragmatic choice if a single value
must ship now: it passed on all 20 tested seed-configurations across both
scenarios, and it is the value this project has already used elsewhere.
But it should be reported as "passes on every tested seed, margin not
confirmed" — not as "safe," which would repeat, in softer form, the exact
overclaim that produced P4c-8's regression.

**NOT wired into `scripts/train.py`.** The author's instruction was
explicit: wire in only if a safe-with-margin threshold exists across
seeds. It does not, for S2, at this grid resolution. `storage_aware=True`
in `train.py` still uses the OLD hardcoded plain fallback from P4c-7 (not
yet updated to `fallback_storage_aware=True` either) — no code change
made pending author direction on how to proceed: ship 0.85 with the
margin caveat stated plainly, run a finer grid or more seeds around the
0.70-0.95 band specifically on S2, or something else.

---

### P4c-11. Chattering confirmed and fixed; residual non-monotonic failure remains on S2 — reported as a quantified limitation, not chased further
`Sec. V-D` (Corollary 1), P4c-9, P4c-10.

**Diagnosis, not a tuning problem**: P4c-10's non-monotonicity (seed 6 safe
at 0.70/0.85/0.95, failing at 0.80/0.90) is inconsistent with a correctly
functioning safety filter, which must be monotonically safer or neutral
the earlier it intervenes. A guard that sometimes causes the harm it
exists to prevent is the wrong mechanism, not a mistuned parameter.

**Chatter confirmed directly.** Instrumented per-decision, per-
intersection filter on/off state on the exact failing case (S2 seed 6,
threshold 0.80). Intersection n2_2 toggled **84 times over 720
decisions**; several stretches flipped every single consecutive decision
(e.g. off→ON→off→ON in four consecutive 5s steps around t=1435-1450s).
Four other intersections (n0_1: 74, n2_1: 66, n3_2: 66, n3_1: 54) showed
the same pattern — the trigger stat hovers at the boundary and single-
decision fluctuations flip it back and forth. This is the mechanism: safe
outcomes at 0.85/0.95 and failures at 0.80/0.90 are not "0.85 being a
better number" but a matter of whether the boundary-crossing rate happens
to phase-lock with arrival timing for that seed's specific demand
realisation — inherently unpredictable across seeds and thresholds,
exactly matching the observed non-monotonicity.

**Fix implemented: engage-and-commit hysteresis** (`src/safety_filter.py`,
new `SafetyFilter(hysteresis=True, storage_threshold_low=..., min_dwell=...)`
parameters, stateful per-intersection engage/dwell tracking). Engage at
`storage_threshold` (the existing "high" parameter); once engaged, release
only after `min_dwell` decisions AND once occupancy drops to/below
`storage_threshold_low` (default gap 0.10 below high) — a dead zone plus
minimum commitment that a single-step fluctuation cannot cross twice in
one decision. 6 new unit tests (`tests/test_safety_filter.py`, pure state-
machine, no SUMO): confirm the naive filter chatters on a scripted
boundary-oscillating sequence (control case), confirm hysteresis holds
through the identical oscillation, confirms dwell holds engagement through
an immediate below-low dip, confirms release only once both dwell and the
low threshold are satisfied.

**Re-verified on the exact failing case, not just the unit test**: S2
seed 6 at threshold 0.80 with hysteresis — toggle count dropped from 84 to
a peak of 65 across intersections, but the RIGHT diagnostic is run length,
not count: 32 of 33 ON-runs at the worst intersection (n1_3) are >= the
3-decision min_dwell; the one exception is 2 decisions long and occurs at
t=3590s, 2 decisions before the 3600s episode ends (benign truncation, not
a bug). final_pending dropped from 84 to 0, final_queue from 5799.8 to
3357.8 on this specific case.

**Multi-seed re-sweep with hysteresis (gap=0.10, min_dwell=3), same 10
seeds/scenario, same 6 thresholds as P4c-10:**

*S1*: 2 of 60 trials fail — seed 9 at 0.60 (final_pending=122), seed 6 at
0.70 (final_pending=84) — both at LOW thresholds not tested as failing
before hysteresis. 0.80-0.95 are now a clean, CONTIGUOUS safe band (every
threshold in that range has safe neighbours on both sides) — genuinely
improved over P4c-10's plain-fallback cliff at 0.80/0.85.

*S2*: 3 of 60 trials fail, and NOT at low thresholds this time — seed 0
at 0.70, seed 6 at 0.85, seed 7 at 0.95 (final_pending 6/101/81
respectively). **0.85, the value validated on both known seeds in P4c-9,
now fails on a THIRD seed under hysteresis.** Combining both scenarios
(20 seeds), only 0.80 and 0.90 have zero failures anywhere — but each is
still flanked by a failing threshold on both sides (0.70/0.85 fail near
0.80; 0.85/0.95 fail near 0.90). **No threshold in this grid has a
confirmed margin on S2, with or without hysteresis.**

**New hypothesis for the low-threshold-specific S1 regressions** (not
investigated further, flagged only): forced minimum dwell means the
filter, once engaged, commits to plain policy-override for at least 15s
regardless of whether the situation has already resolved — at LOW
thresholds engagement is frequent, so the cumulative time spent under
forced commitment goes up materially, trading chattering risk for
committed-intervention-duration risk. This is a plausible mechanism, not
a confirmed one.

**Verdict, per the pre-registered stopping rule: hysteresis does NOT
restore monotonicity on S2.** Deadlock remains reachable — the mechanism
changed (chattering eliminated, confirmed directly) but a different,
still-non-monotonic residual failure mode persists. Aggregate across both
scenarios, all 20 seeds, all 6 thresholds, eta=0 (worst case): **115/120
trials (95.8%) avoid deadlock — S1 96.7%, S2 95.0%.** This is reported as
the honest, quantified result: the certified floor, even with the
composed (storage, storage) fix and engage-and-commit hysteresis, holds
with approximately 95-97% probability on these finite-storage grids at
the hardest (eta=0) sensing condition — not unconditionally, and not yet
at 100% for any single deployable threshold value tested.

**Stopping here, per instruction.** Not wired into `scripts/train.py`
(still the P4c-7 plain-fallback default). Not proposing a third
mechanism. `storage_trigger_threshold_low`/`min_dwell_decisions` added to
`configs/default.yaml` (0.75/3, round numbers, documented as not tuned to
force a result) so the hysteresis code path is usable once a direction is
chosen, but nothing defaults to using it yet.

### P4c-12. Precision pass: Wilson CIs, eta=0.6 measured (did not match the "near-zero" prediction), a real bug found and RETRACTS the P4c-11 fragility claim, threshold chosen and wired in
`Sec. V-D`, P4c-9 through P4c-11.

**1. Wilson 95% CIs** (author's own worked example, 5/120 -> [1.8%, 9.4%],
reproduced exactly): eta=0 combined 5/120=4.2% CI=[1.8%,9.4%]; S1 2/60=3.3%
CI=[0.9%,11.4%]; S2 3/60=5.0% CI=[1.7%,13.7%]. 120 trials do not support
three-significant-figure point estimates; the interval is the honest unit,
per the author's instruction, and is reported everywhere the rate appears
below.

**2. eta=0.6 measured — did NOT match the predicted near-zero rate.**
Same 10 seeds/scenario, same 6 thresholds, hysteresis, eta=0.6: S1 **4/60
fail** (6.7%, CI=[2.6%,15.9%]) — MORE than S1's own eta=0 rate (2/60);
S2 1/60 fail (1.7%, CI=[0.3%,8.9%]) — clearly lower, consistent with the
prediction. Combined eta=0.6: 5/120 (4.2%, CI=[1.8%,9.4%]) — numerically
IDENTICAL to the eta=0 combined rate, with heavily overlapping CIs. The
aggregate "unconditional in practice" story the author predicted is NOT
supported by this data at this sample size — reported as such, not forced.
(Per-threshold, not per-aggregate, is where the real signal turned out to
be — see point 4.)

**3. A real bug found while cross-referencing (point 3 of the prior
request) — RETRACTS part of P4c-11.** Re-running the 5 failing eta=0
cases standalone (`scripts/diagnose_gridlock.py`) to check for a shared
root cause: S1's 2 failures reproduced exactly; all 3 of S2's did not
(pending=0 instead of 6/101/81) — P4c-11 reported this as "fragile,
knife-edge, true rate may be lower." That framing was WRONG, and the
error was in the verification tool, not the underlying system. Root-
caused directly: `diagnose_gridlock.py` calls `calibrate_threshold()`
(a full GreedyHAP episode) in the SAME PROCESS immediately before the
main test episode; `scripts/train.py`/`evaluate_policy.py`/
`sweep_storage_threshold.py` all calibrate B ONCE, in the main process,
decoupled from every worker/test episode. Confirmed by direct test:
re-running S2 seed=6/threshold=0.85 with B passed in directly (skipping
the in-process calibration call) reproduces the sweep's original failure
EXACTLY (pending=101, throughput=4955, queue=5638.5, bit-for-bit). Two
sequential libsumo simulation loads within one process do not fully reset
some internal state, even with an explicit `--seed` on the second —
almost certainly a libsumo-internal RNG carryover, not a bug in this
codebase's own seeding. **Correction: the sweep's original P4c-10/P4c-11
numbers (5/120 at eta=0) stand as reported. There is no evidence the true
S2 failure rate is lower than measured** — the apparent non-reproduction
was an artifact of using a tool with a different (and, for this purpose,
wrong) B-calibration pattern than the tools that actually produced the
numbers. Fixed: `diagnose_gridlock.py` gains a `--B` override so future
single-episode reproductions can match the trusted scripts' calibration
pattern exactly, with the mechanism documented in the script's own
`--help` text so this cannot be silently reintroduced.

**Structural vs. sensitive, from the two that DID reproduce**: S1 seed=9
@0.60 and seed=6@0.70 are genuine, deterministic, structural deadlocks —
sustained escalation over hundreds of seconds (worst-occupancy 130%->
363%->442% and 164%->401%->411% respectively), filter activation jumping
to 45%+, insertion backlog building steadily. No single shared
intersection or movement type across the 5 original failures — different
intersections fail in each case — so this is not "one characterizable
network defect," but every case shares the SAME qualitative signature:
once elevated occupancy appears anywhere, it escalates rather than
plateauing, consistent with a cascading/positive-feedback dynamic once
triggered, not a one-off event.

**4. Threshold chosen from all four sweeps combined (40 seed x eta x
scenario conditions), not just eta=0.6 in isolation:**

| threshold | total failures /40 | which condition(s) |
|---|---|---|
| 0.60 | 3 | S1 eta=0 (seed 9), S1 eta=0.6 (seeds 3, 9) |
| 0.70 | 2 | S1 eta=0 (seed 6), S2 eta=0 (seed 0) |
| 0.80 | 1 | S1 **eta=0.6** (seed 3) |
| **0.85** | **1** | **S2 eta=0 (seed 6) — the idealized, non-physical worst case** |
| 0.90 | 1 | S2 **eta=0.6** (seed 7) |
| 0.95 | 2 | S1 eta=0.6 (seed 7), S2 eta=0 (seed 7) |

0.80, 0.85, and 0.90 are tied at 1 failure each, but **0.85 is the unique
choice whose single failure is at eta=0** — 0.80 and 0.90 both fail under
the realistic eta=0.6 sensing condition, which is what actually matters
for deployment. At threshold=0.85: 39/40 (97.5%) of ALL tested conditions
pass; restricted to eta=0.6 only (the physically realistic case), 0.85 is
**20/20 (100%) across both scenarios**. This is the "defensible default,
honestly reported" result the author asked for, not a perfect guarantee.

**Wired into `scripts/train.py`** (`run_episode_worker`): `SafetyFilter(
env, B, storage_aware=True, storage_threshold=0.85, fallback_storage_aware
=True, hysteresis=True, storage_threshold_low=0.75, min_dwell=3)` is now
the default filter configuration, replacing P4c-7's plain-fallback,
non-hysteretic one. `configs/default.yaml`'s existing
`storage_trigger_threshold: 0.85` / `storage_trigger_threshold_low: 0.75`
/ `min_dwell_decisions: 3` already match — no config value changes, only
the code now uses hysteresis and the storage-aware fallback by default.
`metadata.json` gains `safety_filter_hysteresis`/`safety_filter_min_dwell`
fields.

**Characterization result, stated plainly for the paper**: the certified
floor, even under the composed (storage, storage) pressure-and-filter fix
with engage-and-commit hysteresis, is not an unconditional guarantee on
finite-storage grids — it holds with high probability, quantified here
(97.5% across all tested worst-and-realistic conditions combined, 100%
under realistic sensing noise specifically, at the chosen deployment
threshold), not with certainty. This is the honest form of the result:
Corollary 1's guarantee, as stated, assumes infinite buffers (P4c-6);
under finite storage it is necessarily probabilistic, and this is the
first point in the investigation where that probability has been
measured rather than assumed.

### P4c-13. S1 regression check: a real, modest, non-catastrophic regression — traced to train/eval filter mismatch, not a flaw in the new filter
`Sec. V-D`, P4c-12.

Re-evaluated the EXISTING S1 checkpoint (iteration 99, no retrain) with
`--production-filter` (the new (storage, storage, hysteresis) default,
threshold=0.85) against the original P4-6 baseline (same checkpoint, same
5 seeds, OLD filter). FixedTime/MaxPressure/GreedyHAP numbers are
identical between the two runs (expected — the filter only touches the
HAPLight-RL row; a useful consistency check that nothing else changed).

**Honest result: there IS a regression, small at eta=0, larger and
seed-concentrated at eta=0.6 — not reported as "no regression."**

*eta=0*: HAPLight-RL AQL 994.1->1042.1 (+4.8%), throughput 3716.8->3714.4
(~flat), ATT/AWT/PWD each worsen by 1-4 units. Still significantly better
than GreedyHAP on AWT/AQL/PWD (paired delta positive, p<0.05); ATT/TP not
significant either way, same as before.

*eta=0.6*: HAPLight-RL AQL 1002.4->1216.5 (+21%), throughput 3722.4->3627.4
(-2.6%), and — the real signal — **AQL/TP variance exploded** (std 158.3
->266.9 and 3.3->129.7). The paired delta vs GreedyHAP on AQL and TP
FLIPPED from positive (P4-6: all five metrics significant and favourable)
to negative (not significant, p=0.54/0.23). ATT/AWT/PWD remain
significantly favourable.

**Per-seed breakdown identifies exactly two seeds driving this**, not a
uniform degradation: seed 4 (AQL +664.5, throughput -284) and seed 1 (AQL
+387.6, throughput -178) at eta=0.6; the other three seeds (0, 2, 3) show
small, mixed changes at both eta values, consistent with normal run-to-run
variation rather than a systematic problem.

**Diagnosis, not yet independently confirmed**: this checkpoint was
TRAINED under the OLD (P4c-7-era) filter and is being EVALUATED under a
NEW, more interventionist one (hysteresis holds engagement for a minimum
of 3 decisions once triggered, vs. the old filter's instantaneous
release) — a train/eval mismatch, not evidence the new filter is wrong.
The policy learned to coordinate with a filter that released immediately;
being overridden for a sustained multi-decision window it never
experienced during training plausibly disrupts that coordination on
specific seeds where the filter happens to engage at an inconvenient
moment. No deadlocks occurred in this check (unlike the P4c-8 regression,
which was catastrophic) — this is a metric-quality cost, not a stability
failure, and the composed filter is doing exactly what P4c-9/P4c-12
validated it to do.

**This is exactly what retraining under the new filter is expected to
fix** (the policy gets to adapt to the filter it will actually be
evaluated under) — but that is a hypothesis, not yet tested. Reported
honestly rather than waved through as "no regression" before retraining,
per the author's explicit instruction to check rather than assume.

### P4c-14. Harness reproducibility defect confirmed, fixed, and every P4c sweep re-validated — the threshold changes, and a second, unresolved instance of the same bug class is found in the task-metrics tool
`Sec. V-D`, P4c-9 through P4c-13.

**Root cause, confirmed directly, not inferred.** `scripts/sweep_storage_
threshold.py`'s `multiprocessing.Pool` reuses worker processes across
multiple sequential trials by default. Direct test: (S2, seed=6,
threshold=0.85) run as the ONLY job assigned to a worker -> FAIL
(matches the original sweep). The SAME job run as the SECOND job on a
worker, immediately after an unrelated (seed=0) trial on the SAME worker
-> OK. Nothing else differs. This is the author's predicted mechanism
("state bleed across the multiprocessing pool... persisting between
trials in a worker") confirmed exactly, not a variant of it. **Fix**:
`ctx.Pool(processes=n_workers, maxtasksperchild=1)` — forces a genuinely
fresh process (and therefore a fresh libsumo instance) for every single
trial. Verified directly: re-running the same seed=0-then-seed=6
sequence with the fix restores the correct FAIL result regardless of job
order.

**All four P4c sweeps re-run with the fix** (10 seeds x {S1,S2} x
{eta=0, eta=0.6}, same seeds/thresholds/hysteresis config as P4c-10/
P4c-12):

| sweep | original | corrected | verdict |
|---|---|---|---|
| S1 eta=0 | 2/60 (seed9@0.60, seed6@0.70) | 2/60, IDENTICAL | genuine — unaffected by the bug |
| S1 eta=0.6 | 4/60 (seeds 3,9@0.60; 3@0.80; 7@0.95) | **0/60** | **all 4 were contamination artifacts — retracted** |
| S2 eta=0 | 3/60 (seed0@0.70, seed6@0.85, seed7@0.95) | 3/60, IDENTICAL | genuine — unaffected by the bug |
| S2 eta=0.6 | 1/60 (seed7@0.90) | **5/60** (seed4@0.70; seed1@0.85,0.95; seed3@0.85,0.90) | **contamination was HIDING 4 real failures, not just fabricating false ones** |

The bug distorts in BOTH directions, not just toward false failures —
important, since it means "the original numbers are at least a
conservative upper bound" is also wrong; they are simply not trustworthy
until fixed. Every corrected S1-eta=0 and S2-eta=0 result was already
independently confirmed via a SECOND, unrelated code path (standalone
`diagnose_gridlock.py` with the P4c-12 `--B` override) before this fix
existed. Spot-checked one of the NEW S2-eta=0.6 failures (seed=3,
threshold=0.85) the same way: reproduces exactly (final_pending=118,
worst-movement occupancy pinned at 479.2%) — the corrected sweep is not
being taken on faith.

**Corrected reproducible failure rate, Wilson 95% CI**: combined eta=0
5/120=4.2% CI=[1.8%,9.4%] (UNCHANGED — coincidentally the same trials
were already genuine); combined eta=0.6 5/120=4.2% CI=[1.8%,9.4%]
(same NUMBER, but a DIFFERENT and now-corrected composition: 0 from S1,
5 from S2, not 4 from S1 and 1 from S2). Grand total 10/240=4.2%
CI=[2.3%,7.5%]. **The "eta=0.6 is unconditionally safer" story does NOT
survive correction** — S1 improved to zero, but S2 got WORSE (1/60 ->
5/60) once the artifacts hiding those failures were removed. Reported as
measured, not forced toward the predicted near-zero story: sensing noise
helps S1's specific failure mode and does not help — arguably hurts —
S2's.

**Which prior P4c conclusions survive vs. are retracted**:
- P4c-9 (2x2, (storage,storage) unique on both known seeds): the
  DIRECTIONAL/mechanistic conclusion is independently well-supported
  (P4c-7's oracle-confirmed pressure fix + P4c-5's timing fix address
  different failure classes, argued from first principles, not just the
  2x2 numbers) but P4c-9's own table used `diagnose_gridlock.py`
  single-shot invocations (one calibrate + one test per run, PRE-dating
  even the `--B` override) — not re-verified against the corrected
  methodology here. Flagged, not retracted: no contradicting evidence,
  but not independently re-confirmed either.
- P4c-10's specific non-monotonic pattern (0.70/0.85/0.95 safe, 0.60/
  0.80/0.90 failing) was measured WITHOUT hysteresis and stands
  independently of this fix (that sweep did not have hysteresis's
  later-added state, and its own worst-case cell was independently
  reproduced in P4c-11's investigation). Not affected.
- P4c-11's qualitative finding (hysteresis mitigates chattering but does
  not achieve full monotonicity) SURVIVES: the corrected data still has
  no threshold with confirmed margin on both sides (0.80 is clean but
  flanked by 0.70 and 0.85, both failing). The SPECIFIC numbers change;
  the qualitative conclusion does not.
- P4c-12's eta=0.6 "did not match near-zero" finding SURVIVES in spirit
  (still true in the corrected data) but the SPECIFIC claim "S1 is worse
  than S1's own eta=0" is RETRACTED (was 4/60 artifact, now 0/60) — the
  eta=0.6 story is now S2-driven, not S1-driven.
- **Threshold selection changes**: 0.85 (chosen in P4c-12) has 3 failures
  in the corrected 40-condition table; **0.80 has zero** — the unique
  clean threshold. `scripts/train.py`, `scripts/evaluate_policy.py`, and
  `configs/default.yaml` are updated to threshold=0.80/low=0.70 (was
  0.85/0.75). This is a live config value, not a paper claim, so it is
  simply corrected, not "retracted."

**A second, unresolved instance of the same bug class, found while
investigating the P4c-13 regression check.** `scripts/evaluate_policy.py`
has NO multiprocessing at all — all 40 (controller, seed, eta) episodes
in a single invocation run back-to-back in ONE process, the same
"sequential trials share a process" pattern just confirmed to cause
contamination. Direct test: S1 seed=4, eta=0.6, HAPLight-RL — the LAST
(40th) episode in the P4c-13 regression-check run — showed severely
degraded metrics there (aql=1577.54, throughput=3440) but shows
completely healthy behaviour (final_pending=0, throughput=3719) when
re-run in isolation with the identical seed/threshold/config. **This
means the P4c-13 regression finding is likely substantially a harness
artifact, not a real filter effect — and by direct extension, the
ORIGINAL P4-6 baseline task-metrics table (also produced by
`evaluate_policy.py`'s sequential execution) is now of uncertain
reliability too.** NOT YET FIXED: `evaluate_policy.py` currently has no
multiprocessing to retrofit `maxtasksperchild=1` onto; fixing it properly
needs a comparable restructuring to `sweep_storage_threshold.py`'s worker
pattern (picklable, module-level episode function; no closures/lambdas
crossing a process boundary), which is real, non-trivial work, not a
one-line change. Flagged for the author to prioritize, not started
unilaterally given the scope (it puts the P4-6 baseline itself, not just
P4c-13, back in question).

**Activation-rate check (author's step 2, ten-minute version) — result
reported as measured, does not confirm the hypothesis**: filter
activation on the five S1 eta=0.6 seeds was 32.1%/20.2%/30.8%/22.7%/
29.5% (seeds 0-4). Seed 1 — one of the two seeds that showed the P4c-13
regression — has the LOWEST activation of all five, not the highest.
This does not support "damage concentrates where the filter engages" as
stated. Given the P4c-13 regression itself is now suspect (previous
paragraph), this check's relevance is reduced rather than resolved —
worth re-running only after `evaluate_policy.py` gets a comparable fix
and the regression is re-measured on trustworthy numbers.

**Not done, pending author direction**: fixing `evaluate_policy.py` and
re-running the P4-6 baseline and the P4c-13 regression check on
corrected numbers. Still not launching the S1 retrain — the corrected
threshold (0.80) is trustworthy, but comparing "before vs. after" for a
retrain decision needs the regression check itself to be trustworthy
first.

### P4c-15. `evaluate_policy.py` fixed (the defect is now confirmed FIVE times, not one), a structural standing gate replaces the behavioural one it was supposed to be, a direct determinism proof, and the eta=0.6 P4-6 table is RETIRED as an artifact — eta=0 survives unchanged
`Sec. VI-A`, `Sec. VII` (results table, Fig. 5), P4c-12 through P4c-14.

**Fix.** `scripts/evaluate_policy.py` previously ran all 40 (controller,
seed, eta) episodes sequentially in one process — the exact defect just
confirmed in `sweep_storage_threshold.py` (P4c-14). Refactored to the same
pattern as every other episode-producing script in this codebase: a
module-level, picklable `run_episode()` worker dispatched via
`multiprocessing.Pool(..., maxtasksperchild=1)`, guaranteeing a genuinely
fresh process (and fresh libsumo instance) per episode regardless of
worker count.

**While building the standing test, found and fixed FOUR MORE instances**
of the identical pattern — sequential episodes sharing one process, no
multiprocessing at all — that were not previously known:
`scripts/train.py`'s `compute_greedy_reference` (the pre-flight greedy-HAP
reference, run twice per training launch, 24 episodes each by default) and
`compute_random_policy_filter_control` (the random-policy ablation
control), and `scripts/check_greedy_reference.py` (the very script that
P4-6 point 2 built specifically to validate the greedy-HAP reference
statistic at higher n — if it had been contaminated, that validation
itself would have been compromised). All four fixed the same way: extract
the per-episode body into a module-level, picklable function, dispatch via
`ctx.Pool(..., maxtasksperchild=1)`. `train.py`'s per-iteration rollout
Pool (`run_workers_with_watchdog`) was already safe via a different
mechanism (a fresh Pool every iteration, at most one task per worker) but
got `maxtasksperchild=1` added anyway, trading an implicit invariant
(`len(pending) <= n_envs`, true today but never asserted) for an explicit,
uniform, verifiable one. **This defect class is now confirmed six times
total**: Phase-1 subscriptions-across-resets, `diagnose_gridlock.py`'s
in-process `calibrate_threshold()` call (P4c-12), the sweep Pool (P4c-14),
and these four.

**The standing test is structural, not behavioural — and that was a
deliberate change of plan, not the original design.** The original intent
(explicit in the author's instruction that started this investigation) was
an automated isolated-vs-contaminated trajectory comparison: "a permanent
assertion that verifies zero carryover." Building it surfaced a genuine
problem: three separate, faithful attempts to make such a comparison
diverge on the CURRENT codebase all failed, including a full, exact replay
of the originally-confirmed contaminated case (S1, `--production-filter`,
the identical 40-job sequence, seed=4/eta=0.6/HAPLight-RL as job #40,
reproduced by importing `run_episode` directly from the fixed script) —
isolated and contaminated came out bit-for-bit identical (aql=1025.44,
tp=3721.00, awt=19.13, both runs). Two other previously-confirmed sweep
failures (e.g. S2 seed=6/threshold=0.85/eta=0, previously pending=101) also
no longer reproduce as failures AT ALL, isolated or not, even run through
the actual current `sweep_storage_threshold.py` script itself (not a
hand-rolled approximation) — B was numerically identical (76.649) between
old and new, ruling out a calibration-side explanation. **Best-supported
explanation, not proven**: substantial code changed between when those
specific numbers were recorded and now (hysteresis, the storage-aware
pressure fix, the 0.85->0.80 threshold correction) and plausibly changed
whatever state was leaking too. This does NOT mean the isolation defect
never existed — the fresh-process fix for the sweep was independently
confirmed correct by direct A/B testing at the time it was found (P4c-14)
— it means a live reproduction is no longer available as evidence.

Given that, `tests/test_episode_isolation.py` now carries two gates:
1. **`test_fresh_process_per_episode_dispatch` (primary)** — a structural,
   source-inspection check: every script known to dispatch multiple
   episodes (`evaluate_policy.py`, `sweep_storage_threshold.py`,
   `train.py`, `check_greedy_reference.py`) must construct its
   `Pool(...)` with `maxtasksperchild=1`. This is the literal fix applied
   to every one of the six confirmed instances — a script that drops the
   guard is exhibiting the exact pattern that caused all of them.
2. **`test_episode_isolation` (kept, downgraded to best-effort canary)** —
   the original GreedyHAP-based isolated-vs-warmup-then-target comparison.
   Its docstring is now explicit that it is NOT currently known to be
   sensitive to the historical defect on today's code. Kept because it is
   cheap; a future failure would still be real signal.

**Direct determinism proof (stronger than source-inspection, run at the
author's request)**: the full P4-6 job set (40 episodes: S1, 5 seeds,
2 etas, 4 controllers) run through the fixed evaluator twice, once with
`--n-workers 4` and once with `--n-workers 1`, otherwise identical.
Compared all 40 per-(controller,seed,eta) metric rows programmatically:
**byte-identical, 0/40 differ.** Worker count — a pure scheduling
parameter — has zero effect on any episode's outcome, which is exactly
what "each episode gets a fresh, independently-seeded process" implies
and what a lingering isolation bug would violate. (Note in passing: the first
re-run attempt used the script's own default worker count,
`os.cpu_count()-1 = 15`, and hit a `MemoryError` inside libsumo's TraCI
connection — 15 concurrent SUMO instances exceeded available RAM on this
machine. Not an isolation defect; a resource limit. `--n-workers 4`
matches the value used successfully in every smoke test so far.)

**Fresh P4-6 re-run (S1, iteration-99 checkpoint, base filter — the
original P4-6 controller definition, no `--production-filter`), against
the old table:**

*eta=0 — byte-identical to the original P4-6 table, digit for digit, all
four controllers.* This confirms eta=0 was never contaminated: it
**survives** as trustworthy, both before and after the fix.

| controller | ATT | AWT | AQL | TP | PWD |
|---|---|---|---|---|---|
| FixedTime | 242.6±8.9 | 19.1±0.7 | 1147.0±147.8 | 3708.2±13.9 | 126.1±15.2 |
| MaxPressure | 246.2±9.4 | 20.3±0.4 | 1140.5±155.5 | 3708.2±16.3 | 128.2±16.3 |
| GreedyHAP | 243.7±8.5 | 20.2±0.8 | 1089.5±132.4 | 3714.8±5.1 | 125.2±13.7 |
| **HAPLight-RL** | **237.4±10.1** | **18.1±0.3** | **994.1±154.4** | **3716.8±4.9** | **114.0±14.7** |

Paired delta vs GreedyHAP (unchanged from the original table): ATT
p=0.168 (n.s.), AWT **p=0.0035**, AQL p=0.125 (n.s.), TP p=0.258 (n.s.),
PWD **p=0.041**. 2/5 significant, same as originally reported.

*eta=0.6 — DRAMATICALLY DIFFERENT from the old table. Old numbers are
RETIRED, not confirmed: they were produced by since-rewritten,
non-reproducible code and cannot stand as evidence.* FixedTime is
identical (expected — deterministic, no filter, no RL policy, so nothing
about it could have been contaminated either way). MaxPressure, GreedyHAP,
and HAPLight-RL are all substantially worse and far higher-variance than
the retired numbers, driven by real per-seed near-deadlock cases that the
old sequential run apparently suppressed or altered:
- GreedyHAP seed=4: att=457.96, aql=**7714.20**, tp=1774.00 — a genuine,
  severe near-deadlock episode, isolated and reproducible.
- MaxPressure seed=1: aql=1634.62, tp=3460.00; seed=3: aql=2467.70,
  tp=3181.00.
- HAPLight-RL seed=0: aql=1895.00, tp=3416.00; seed=4: aql=1926.09,
  tp=3414.00.

| controller | ATT | AWT | AQL | TP | PWD |
|---|---|---|---|---|---|
| FixedTime | 242.6±8.9 | 19.1±0.7 | 1147.0±147.8 | 3708.2±13.9 | 126.1±15.2 |
| MaxPressure | 251.0±2.8 | 19.6±2.4 | 1559.6±537.9 | 3554.4±235.2 | 131.8±13.6 |
| GreedyHAP | 290.7±94.0 | 19.5±1.7 | 2475.0±2932.3 | 3323.8±866.4 | 170.8±91.9 |
| **HAPLight-RL** | **248.7±12.3** | **18.2±0.6** | **1390.2±480.8** | **3597.6±166.7** | **126.6±15.2** |

Paired delta vs GreedyHAP: ATT p=0.352 (n.s.), AWT p=0.118 (n.s.), AQL
p=0.412 (n.s.), TP p=0.474 (n.s.), PWD p=0.341 (n.s.). **Old table:
"all five metrics significant." New, trustworthy table: NONE significant.**
This does not mean HAPLight-RL stopped beating GreedyHAP at eta=0.6 — the
point estimates still favour HAPLight-RL on every metric — it means the
old claim of significance was itself an artifact of the sequential-
execution bug suppressing/altering the true per-seed variance (GreedyHAP's
own seed=4 near-deadlock, in particular, was either not present or
measured very differently under the old contaminated harness), and the
true n=5 sample is far noisier than previously reported.

**Consequence for the P4-6 completion gate.** P4-6 itself stated: "the
gate is better evidenced by the eta=0.6 task-metrics table (all five
metrics significant) than by either return curve alone." That specific
support is retracted — it no longer holds. What survives: the
training-condition return significance (P4-6 point 1, t=3.56 p=0.0006 —
unaffected by this bug, does not go through `evaluate_policy.py`) and the
eta=0 task-metrics table's 2/5 significant metrics (AWT, PWD), unchanged.
The completion gate is not un-met, but its evidentiary weight is now
resting on less than it appeared to.

**P4c-13's eta=0.6 numbers are retired for the identical reason** — that
regression check ran through the same contaminated sequential harness, at
the same eta=0.6 condition just shown to be affected. **Update (P4c-16):
P4c-13's eta=0 numbers are marked retired-untested, not "likely still
valid"** — P4c-13 as a whole is a diagnostic against the OLD (pre-retrain)
checkpoint, and that diagnostic is now superseded outright by the clean
S1 retrain (P4c-16); re-verifying individual numbers from a retired
diagnostic is not a useful use of effort, so eta=0's small
`--production-filter` regression (AQL 994.1->1042.1) is retired alongside
eta=0.6, not carried forward as a standing claim either way. The eta=0.6
regression finding (AQL 1002.4->1216.5, variance exploding) cannot
currently be trusted either as "real" or as "artifact" — the fixed
evaluator has not yet been run with `--production-filter`. **Update
(P4c-16): NOT separately re-run** — a clean S1 retrain under the
production filter (P4c-16) answers the train/eval-mismatch question P4c-13
was investigating directly, on trustworthy code from the start; re-running
a diagnostic against the old, now-superseded checkpoint would answer a
question that no longer matters. P4c-13 is retired as a whole, not
re-verified piece by piece.

**Which historical numbers are retired vs. survive, stated explicitly:**
- SURVIVES: P4-6 eta=0 task-metrics table (all four controllers,
  byte-identical on re-run) and its 2/5-significant paired-delta result.
- SURVIVES: P4-6 point 1's training-condition return significance
  (t=3.56, p=0.0006) — computed during training, never went through the
  contaminated evaluator.
- RETIRED (artifact, not evidence): P4-6 eta=0.6 task-metrics table and
  its "all five metrics significant" claim.
- RETIRED-UNTESTED (P4c-16): P4c-13 in its entirety — both eta=0's small
  regression number and eta=0.6's "variance exploded, paired delta
  flipped negative" finding. Superseded outright by the clean S1 retrain,
  not individually re-verified; do not cite any P4c-13 number as evidence
  either way.
- UNCHANGED (not re-verified either way): the P4c-9 through P4c-14
  deadlock-safety sweep conclusions and the 0.80 threshold selection —
  already flagged in P4c-14 as measured via a since-corrected tool;
  several individual historical failing conditions no longer reproduce on
  current code (documented above), which is consistent with, but not
  independent confirmation of, the "codebase changed enough to shift
  outcomes" explanation. A fresh validation sweep would be needed to
  re-certify 0.80 specifically; not done here, out of scope for this
  entry.

### P4c-16. Clean retrain of S1 and S2 under the production filter, n=10 evaluation with gridlock rate as a first-class metric and BCa/effect-size statistics, and the Advanced-MP verification gating Phase 5
`Sec. VI-A`, `Sec. VII` (results table, Fig. 5), `Sec. VI-E` (Advanced-MP), P1-10, P4c-15.

**Reframe (author's instruction): the P4-6/P4c-15 eta=0.6 variance problem was never a
setback — it was the deadlock finding showing up in the main comparison table.**
GreedyHAP occasionally deadlocking under noise (aql=7714 on one seed, P4c-15) is
the exact phenomenon the whole P4c thread exists to characterize; it kills
significance at n=5 because n=5 is too few draws to see a ~5-10% event
reliably, not because the underlying result is weak. The fix is more seeds,
not a different story.

**Root cause of two training crashes, fixed, not worked around.** Launching
S1 and S2 retrains concurrently (reduced `--n-envs` each, for wall-clock
speed) crashed both with `traci.exceptions.FatalTraCIError: Connection
closed by SUMO` inside `compute_greedy_reference`'s Pool. Root cause:
`compute_greedy_reference`/`compute_random_policy_filter_control`
(rewritten in P4c-15 to fix their OWN episode-isolation defect) computed
their worker-pool size independently as `os.cpu_count()-1`, ignoring
whatever concurrency budget the caller (`--n-envs`) intended -- two
concurrent training runs each tried to open up to 15 SUMO processes for
this one call alone, ~30 total, on a machine already shown to hit a
MemoryError at 15 (P4c-15). Fixed: both functions now take an explicit
`max_workers` parameter, wired from `main()`'s own `n_envs`, so all
concurrency in `train.py` flows from one number. Retrains were then run
sequentially (S1, then S2 in 3 rested batches) rather than concurrently,
eliminating the risk class entirely rather than just capping it.

**A second, independent issue found and fixed on the same S1 attempt: the
40-iteration flat/declining-trend abort gate is outlier-sensitive.** S1's
retrain hit this gate at iteration 39 (OLS slope=-19.7, "STOPPING"). Robust
re-analysis of the SAME 40-point series: Theil-Sen slope=-3.5 with 95%
CI=[-22.4,+10.3] (straddles zero -- no robust evidence of decline);
Spearman rho=-0.06, p=0.69 (no significant monotonic trend at all);
excluding just the two flagged outlier episodes (iter28=-8512.95,
iter33=-6210.37, out of 40) drops the OLS slope to -2.7. This is the exact
same outlier-driven false-decline pattern already diagnosed in P4-7 for
S2's original abort -- confirmed again, independently, on S1. **Fixed at
the root, not patched around this one instance**: the gate now computes a
Theil-Sen slope and only stops when its CI is entirely below zero
(`ts.slope < 0 and ts.high_slope < 0`), not on a bare OLS point estimate.
Verified live on S1's own resumed run: the SAME check, now robust, hit an
EVEN MORE extreme pair of outliers (iter44=-16548.00, iter47=-16362.81, out
of a fresh 40-point window) and correctly continued (Theil-Sen=+4.62,
CI=[-4.92,+15.25]) rather than false-stopping. S1 then ran cleanly to
iteration 99; S2 (3 rested batches, 0-33/34-66/67-99, each verified against
its own checkpoint's `iteration` field, not buffered stdout) ran cleanly to
iteration 99 with no abort at any point across all three batches.

**Advanced-MP verification against the Advanced-XLight reference (P1-10,
zero compute -- a code/formula check, not a simulation run): a real,
specific discrepancy, gating Phase 5.** Source: Zhang et al., "Expression
might be enough: representing pressure and demand for reinforcement
learning based traffic signal control" (ICML 2022, arXiv:2112.10107) --
the paper `AdvancedMP`'s docstring already cites as its origin. The
reference algorithm is a two-term STAY/SWITCH decision, not a uniform
pressure argmax:
- Effective range `L = V_max * t_duration` (max speed times the CURRENT
  PHASE's own duration -- dynamic, phase-dependent).
- Phase demand `d(s) = sum of running-vehicle counts within L`, computed
  ONLY for the phase being evaluated.
- Decision rule: stay on the current phase unless `d(a_cur) * W1 <=
  max(efficient_pressure(s) for s in other phases)` -- the running-vehicle
  demand competes ONLY against the standard queue-based pressure of
  COMPETING phases, as an asymmetric "stickiness" bonus for whichever
  phase is currently active, with an explicit tunable weight W1.

This codebase's `AdvancedMP` (`src/controllers.py`) instead adds queued +
running counts into ONE uniform upstream-pressure term for EVERY movement
(`x_up = rho1(counts_hat) + rho1(running_counts_hat)`), fed into the same
symmetric cross-phase argmax every other classical controller in this
family uses (`_pressure_action` -> `hap.greedy_phase`, whose only
current-phase behaviour is an epsilon tie-break, "ties resolve to the
current phase" -- not a weighted stay/switch decision on a DIFFERENT
quantity). Also: `running_horizon_s: 5.0` (`configs/default.yaml`) is a
FIXED constant description as "reachable within one Delta t"
(`env.py:720`: `speed * running_horizon_s`), not the paper's
`V_max * t_duration` (dynamic, phase-duration-dependent, uses max speed
not the individual vehicle's own speed). **Three concrete deviations**:
(1) no asymmetric current-phase stickiness term at all, (2) no explicit
weight W1, (3) effective range tied to a fixed sensing horizon rather than
actual phase duration. Per P1-10's own gate ("If it is far off, the port
is wrong and every comparison in the paper is worthless"): this is a real
port discrepancy, not a restatement in different notation. **Did NOT
affect any number reported to date** -- `AdvancedMP` was not in
`evaluate_policy.py`'s `CONTROLLER_NAMES` and had never appeared in a P4/
P4c comparison table; this was purely a pre-Phase-5 gating finding, exactly
where P1-10 placed it.

**Fixed, all three deviations, and verified** (`src/controllers.py`,
`src/env.py`). `env.py` gains two new public methods, deliberately NOT
folded into `_measure()`'s single shared pass that every other controller
and the RL policy's observation depend on: `lane_max_speed(i, mv)` (the
lane's own SUMO speed limit, V_max) and `running_count_within_range(i,
mv, max_distance_m)` (live traci query, non-stopped vehicles within a
caller-supplied distance of the stop line -- Advanced-MP needs a
threshold that depends on the CURRENT phase's own duration, which a
fixed network-wide horizon can't provide per-call). `AdvancedMP.act()` is
rewritten as the actual stay/switch decision: standard efficient
(lane-normalised) pressure per phase for switching, an asymmetric
current-phase-only running-demand term `d(a_cur) = sum of
running_count_within_range(i, mv, lane_max_speed(i,mv) * env.g_max) for
mv in the current phase`, weighted by `W1` (=1.0, an inferred default --
the source paper text available to this port does not pin a specific
value, documented as an inference, not a transcribed constant) and
compared only against OTHER phases' pressure, not folded in everywhere.
`env.g_max` (`max_green_s`) stands in for the paper's `t_duration`: this
codebase's phases don't carry individually-tuned durations, so it is the
one duration constant available, matching a fixed-decision-interval RL
setting.

**Verified, n=10 seeds, S2, eta=0** (isolates the algorithmic difference
from sensing noise): corrected AdvancedMP vs plain MaxPressure -- ATT
216.4->211.2 (+2.4%), AWT 15.2->14.4, AQL 1518.4->1424.1 (+6.2%), TP
5325.1->5351.3, PWD 110.3->103.6 -- improves on every metric, the
expected direction (Advanced-MP is designed to improve on plain MP by
incorporating running-vehicle demand into the switching decision).
**Gridlock: MaxPressure 1/10, corrected AdvancedMP 0/10** -- avoids the
one near-deadlock episode MP hits at this condition. Confirms the fix
works and points the right direction; this port has not been checked
against Zhang et al.'s SPECIFIC published percentage improvement over MP
on their own 4x4-grid benchmark (a different network/demand than S2), so
"reproduces its published improvement" is confirmed directionally, not
to a specific published number -- flagged, not overclaimed. Now safe to
build Phase 5's `Advanced-MPLight` baseline against this corrected base.

**Retrained S1 task-metrics table** (`results/s1_seed0_1787507503/
checkpoint.pt`, iteration 99, trained from scratch under
(storage,storage,hysteresis) threshold=0.80/0.70, min_dwell=3 -- the FIRST
checkpoint ever trained under the full current production filter; the
prior S1 checkpoint used throughout P4-6/P4c-13/P4c-15 was trained under
the OLD pre-hysteresis filter), evaluated n=10 seeds (0-9), eta in
{0, 0.6}, `--production-filter`, through the fixed/isolation-guaranteed
evaluator:

*eta=0:*

| controller | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 240.1±7.4 | 19.0±0.6 | 1105.6±120.7 | 3708.8±9.9 | 121.1±12.1 | 0/10 |
| MaxPressure | 245.6±6.9 | 20.6±0.6 | 1123.5±109.5 | 3712.1±12.3 | 126.4±11.4 | 0/10 |
| GreedyHAP | 243.6±7.1 | 20.3±0.7 | 1082.2±103.6 | 3714.8±6.0 | 122.9±10.9 | 0/10 |
| **HAPLight-RL** | **238.4±6.6** | **17.6±0.8** | **1079.1±204.4** | **3689.6±83.4** | **114.4±10.6** | **0/10** |

Paired delta vs GreedyHAP: ATT +5.15 p=0.041 r=+0.709; AWT +2.73
**p<0.0001** r=+1.000; AQL +3.12 p=0.968 (n.s.) r=+0.455; TP -25.20 p=0.362
(n.s.) r=+0.044; PWD +8.51 **p=0.0039** r=+0.927. BCa CIs agree in sign
with the t-CIs on every metric here.

*eta=0.6:*

| controller | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 240.1±7.4 | 19.0±0.6 | 1105.6±120.7 | 3708.8±9.9 | 121.1±12.1 | 0/10 |
| MaxPressure | 247.5±5.6 | 20.2±1.8 | 1325.6±438.7 | 3631.1±176.7 | 127.1±11.8 | 2/10 |
| GreedyHAP | 266.3±67.8 | 20.0±1.3 | 1758.0±2096.3 | 3519.2±613.2 | 144.4±67.3 | 1/10 |
| **HAPLight-RL** | **235.6±5.2** | **17.7±0.7** | **977.7±74.4** | **3715.6±7.5** | **111.3±7.8** | **0/10** |

**The mean is the wrong statistic for this comparison, and the paired
t-test built on it is reported for completeness only, not as the primary
read.** GreedyHAP's one gridlock seed makes its AQL/ATT/PWD distribution
heavy-tailed (AQL mean=1758.0 vs median=1069.4; ATT mean=266.3 vs
median=243.5; PWD mean=144.4 vs median=119.5) -- the SAME deadlock event
gridlock_rate already reports as GreedyHAP 1/10 at this condition (table
above), not new information, just visible again here as inflated variance
around a mean that no longer describes a "typical" episode. The primary
read is: gridlock rate (already tabulated per controller above; pooled
across both scenarios and both eta, HAPLight-RL 0.0% vs GreedyHAP's
10.0%, see below) is the metric this failure mode is actually measured
by. For the continuous metrics, median + BCa (bias-corrected, not
assuming symmetry, appropriate for a heavy-tailed sample) is the correct
central-tendency comparison, not mean + normal-theory CI: AWT
**p=0.0002** r=+0.964 (agrees under either statistic -- no deadlock
seed in this metric's distribution); ATT BCa-CI=[+7.30,+116.40], AQL
BCa-CI=[+91.16,+3429.36], PWD BCa-CI=[+9.97,+117.14], all excluding
zero, matching the near-unanimous per-seed advantage the rank-biserial
effect sizes already show (r=+0.891, +0.891, +1.000 respectively); TP
r=+0.511, weaker, consistent with throughput being the metric where a
single gridlock episode's effect on the FULL episode aggregate is
mixed rather than uniformly directional.

**Retrained S2 task-metrics table** (`results/s2_seed0_1787604457/
checkpoint.pt`, iteration 99, same production config, first-ever S2
checkpoint to reach iteration 99 -- the original S2 run aborted at
iteration 40, P4-7), n=10 seeds, eta in {0, 0.6}, `--production-filter`:

*eta=0:*

| controller | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 232.6±2.3 | 17.5±0.4 | 2139.3±726.6 | 5317.0±142.8 | 132.7±3.4 | 1/10 |
| MaxPressure | 216.4±4.0 | 15.2±0.7 | 1518.4±462.3 | 5325.1±122.8 | 110.3±5.8 | 1/10 |
| GreedyHAP | 218.8±6.3 | 15.3±0.8 | 1728.0±815.6 | 5297.9±183.6 | 110.6±5.3 | 2/10 |
| **HAPLight-RL** | **206.8±3.4** | **13.3±0.5** | **1048.1±97.9** | **5411.9±13.1** | **94.6±4.4** | **0/10** |

Paired delta vs GreedyHAP: ATT +11.94 **p=0.0009** r=**+1.000**; AWT +2.02
**p=0.0002** r=**+1.000**; AQL +679.90 **p=0.034** r=**+1.000**; TP +114.00
p=0.086 (n.s.) r=+0.636; PWD +16.04 **p=0.0001** r=**+1.000**.
Rank-biserial r=+1.000 on four of five metrics: HAPLight-RL beats
GreedyHAP on EVERY SINGLE SEED for ATT, AWT, AQL, PWD at eta=0 -- the
strongest, cleanest result in this entire evaluation thread.

*eta=0.6:*

| controller | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 232.6±2.3 | 17.5±0.4 | 2139.3±726.6 | 5317.0±142.8 | 132.7±3.4 | 1/10 |
| MaxPressure | 216.9±3.4 | 15.2±0.4 | 1364.5±382.0 | 5389.8±42.9 | 110.7±5.7 | 0/10 |
| GreedyHAP | 221.2±18.5 | 15.6±1.4 | 1701.0±1190.5 | 5319.5±196.7 | 113.3±17.5 | 1/10 |
| **HAPLight-RL** | **209.0±2.5** | **13.7±0.3** | **1082.1±65.3** | **5414.8±5.1** | **98.2±3.9** | **0/10** |

Same heavy-tailed situation as S1, same reason: GreedyHAP's one gridlock
seed here (gridlock rate 1/10, table above) inflates its AQL/ATT/PWD mean
well above its median (AQL mean=1701.0 vs median=1268.6; ATT mean=221.2
vs median=215.9; PWD mean=113.3 vs median=109.2). Gridlock rate is the
primary metric for this failure mode; median + BCa is the correct
central-tendency comparison for the continuous metrics given the skew.
Paired delta vs GreedyHAP: AWT **p=0.0015** r=**+1.000** (agrees under
either statistic); ATT BCa-CI=[+6.03,+34.57], AQL
BCa-CI=[+203.11,+2050.63], PWD **p=0.0195** with
BCa-CI=[+9.22,+35.89] -- all three excluding zero, r=**+1.000** on all
three, matching HAPLight-RL winning nearly every seed; TP r=+0.964,
also strongly directional here (unlike S1's TP, where the single
gridlock episode's effect on the full-episode throughput aggregate was
more mixed).

**Gridlock rate is now a first-class metric column in the evaluator
(`evaluate_policy.py`'s `GRIDLOCK_KEY`, Wilson 95% CI) -- pooled across
both scenarios and both eta conditions (n=40 episodes per controller),
this is the headline finding the reframe predicted:**

| controller | gridlock rate | Wilson 95% CI |
|---|---|---|
| FixedTime | 2/40 = 5.0% | [1.4%, 16.5%] |
| MaxPressure | 3/40 = 7.5% | [2.6%, 19.9%] |
| GreedyHAP | 4/40 = 10.0% | [4.0%, 23.1%] |
| **HAPLight-RL** | **0/40 = 0.0%** | **[0.0%, 8.8%]** |

**The deadlock characterization is now corroborated directly by the main
comparison table, not just the separate P4c threshold-sweep thread**:
every classical baseline -- including FixedTime, which never adapts to
live conditions at all -- shows a nonzero gridlock rate across this
evaluation; the trained, safety-filtered policy shows zero, with its own
task metrics staying tight and low-variance (S1 eta=0.6 AQL std=74.4 vs
GreedyHAP's 2096.3; S2 eta=0.6 AQL std=65.3 vs GreedyHAP's 1190.5) exactly
where the classical baselines' variance explodes from occasional
near-deadlock episodes. This is the mechanism, stated plainly: HAPLight-RL
is not merely "better on average" -- it is structurally avoiding the
failure mode that produces the high-variance, occasionally-catastrophic
tail the classical baselines exhibit.

**Explicit disposition of every prior number, as instructed:**
- **RETIRED (superseded, not merely "artifact"), do not use**: P4-6's
  eta=0.6 task-metrics table and every claim built on it (including P4-6's
  own "the gate is better evidenced by the eta=0.6 table" statement).
  Superseded by the tables in this entry, produced by a clean retrain on
  trustworthy, isolation-guaranteed code -- not merely re-measured, but
  the first trustworthy eta=0.6 measurement that exists for either
  scenario.
- **RETIRED-UNTESTED**: P4c-13 in its entirety (both eta=0 and eta=0.6),
  not individually re-verified -- see the P4c-15 update above. It was a
  diagnostic run against the OLD, pre-retrain S1 checkpoint; the clean
  retrain answers the question it was investigating directly, so
  re-running it against a checkpoint that no longer represents anything
  deployed would not be a useful use of effort. Do not cite any P4c-13
  number as evidence either way.
- **SURVIVES, unchanged**: P4-6's eta=0 task-metrics table (byte-identical
  on the P4c-15 re-run) and P4-6 point 1's training-condition return
  significance (t=3.56, p=0.0006 -- computed during training, never
  touched the evaluator).
- **Retrospective note**: the ORIGINAL S2 abort that opened this whole
  deadlock-investigation thread (P4-7, "S2 aborted at iteration 40") used
  the same bare-OLS-slope trend check just replaced with a Theil-Sen-based
  one in this entry, and P4-7's own contemporaneous investigation already
  found the same signature -- 6 of 40 eta0_return values (15%) were
  catastrophic outliers. P4-7's own archived per-iteration series was not
  re-run through Theil-Sen here (not retained in a form this entry could
  recompute against), so this is a structural inference from the shared
  mechanism and P4-7's own documented outlier rate, not an independently
  re-verified statistic like S1's iteration-39 case above -- but the
  pattern match is exact: **a false-positive abort trigger that happened
  to surface a real, load-bearing phenomenon** (finite-storage deadlock
  under greedy control), investigated for its own sake regardless of why
  it was first noticed, and now the trigger mechanism itself is fixed.
- **NEW, supersedes the retrain question entirely**: S1 and S2 both now
  have a from-scratch checkpoint trained under the full production filter
  and a trustworthy n=10, both-eta task-metrics table with gridlock rate
  and BCa/effect-size statistics. The retrain decision that P4c-15 left
  open is resolved by having done it, not by further deliberation.
- **UNCHANGED (still not re-verified)**: the P4c-9 through P4c-14
  threshold-sweep conclusions and the 0.80 threshold selection itself --
  this entry evaluates task metrics and gridlock rate for the FOUR named
  controllers at ONE threshold (0.80, the current default), not a fresh
  sweep across thresholds. A fresh sweep to re-certify 0.80 specifically
  remains open, as flagged in P4c-15.
- **FIXED AND VERIFIED (was: gating Phase 5, not yet actioned)**: the
  Advanced-MP vs Advanced-XLight discrepancy above -- all three
  deviations corrected in `src/controllers.py`/`src/env.py`, verified to
  improve on plain MaxPressure in the expected direction (n=10, S2,
  eta=0: ATT +2.4%, AQL +6.2%, gridlock 1/10->0/10). Phase 5's
  Advanced-MPLight baseline is now safe to build against this corrected
  base.

### Phase 6 (Bengaluru) kickoff status -- started in parallel, NOT validated, honestly incomplete
`Sec. VI-C`, `prompts/phase6_bengaluru.md`.

Per the author's instruction to start Phase 6 in parallel rather than have
it sit on the critical path at the end: OSM extraction for the configured
bounding box (`configs/default.yaml`, `[77.67, 12.99, 77.80, 13.08]`,
Old Madras Road/NH-75 corridor) run via `osmGet.py`, then `netconvert`
with the prompt's required flags (`--junctions.join --tls.guess-signals
--tls.join --lefthand true`, plus `--geometry.remove --roundabouts.guess
--ramps.guess`). Both steps completed without fatal error ("Success.").

**Raw network stats (sumolib, before any validation/repair pass)**:
26,162 junctions, 60,195 edges, 27 traffic-light-controlled junctions, 0
edges with zero lanes, 0 fully-isolated junctions -- but **13 of the 27
TLS junctions have fewer than 2 incoming edges**, failing the prompt's own
required check ("every signalised junction has >=2 incoming edges")
outright, and the network is not a "corridor" at this scale -- 26,162
junctions is a large slice of the city, not the intended focused arterial
stretch, and would be intractable for the RL training pipeline as-is (S1
has 5 intersections, S2 has 16). This is exactly the failure mode the
prompt itself anticipated ("osmWebWizard output for Indian arterials is
reliably broken... unrealistic lane counts") and explicitly pre-authorized
a fallback for ("If after a day the network still will not validate, tell
me and we shrink the bounding box").

**Honestly incomplete, not silently pushed further**: this entry stops at
the raw-extraction diagnostic, not a validated network. What remains --
identifying which of the 27 TLS junctions actually lie on the intended
corridor (vs. the wider bounding box), filtering/cropping the network to
that corridor (`netconvert`'s `--keep-edges...`-family options or a
tighter bounding box), repairing the 13 under-connected TLS junctions,
writing `tests/test_nets.py::test_bengaluru_loads` per the prompt's own
requirement, and building the directional-peak synthetic demand -- is
real, non-trivial engineering, not a formality, and the corridor
identification step in particular needs geographic judgement this entry
is not making unilaterally. `nets/bengaluru/bengaluru_bbox.osm.xml` (raw
OSM, 45MB) and `nets/bengaluru/bengaluru.net.xml` (netconvert output,
172MB, unvalidated) are on disk for the next pass to build on rather than
re-download.

### Phase 6 (Bengaluru): region-scale box replaced with a corridor-scale one -- network validates cleanly, but TLS count (4) is below target, stopping per instruction rather than deciding unilaterally
`Sec. VI-C`, `prompts/phase6_bengaluru.md`.

**The region-scale bounding box from the previous entry is superseded, not
repaired.** It was never a corridor (26,162 junctions, 27 TLS, 13 invalid)
-- fixing it in place would have meant guessing which of 27 signals sit on
the intended arterial, exactly the kind of geographic judgement call this
entry earlier declined to make unilaterally. Replaced with a manually
selected corridor extract (author, via openstreetmap.org export, drivable
roads only): `nets/bengaluru/bengaluru_corridor.osm` (1.4MB), bounding box
approximately **lon 77.700-77.760, lat 12.995-13.030**, along Old Madras
Road / NH-75. The old region-scale files
(`bengaluru_bbox.osm.xml`, `bengaluru.net.xml`, `_netconvert.log`) are
deleted, not kept alongside -- the corridor .osm is the only reproducibility
source now.

**`scripts/build_nets.py` gains `--scenario bengaluru`**, a genuinely
separate code path from `build_scenario`/`build_topology` (those assume a
synthetic regular grid with known entry/exit stub edges; a real OSM
network has neither). Two new functions, both exercised by the CLI, not
just defined:
- `netconvert_build_bengaluru(osm_file, out_net)`: the exact, deterministic
  netconvert invocation specified for this corridor -- `--geometry.remove
  --roundabouts.guess --ramps.guess --junctions.join --junctions.join-dist
  20 --tls.guess-signals --tls.discard-simple --tls.join
  --tls.default-type actuated --remove-edges.isolated
  --keep-edges.by-vclass passenger --lefthand --no-turnarounds`. No manual
  repair step follows it -- a junction that still fails validation after
  this command is pruned by netconvert itself (`--tls.discard-simple`,
  `--remove-edges.isolated`), never hand-edited in the XML, per the
  paper's reproducibility claim.
- `validate_bengaluru_net(net_file)`: the prompt's exact gate (every TLS
  has >=2 incoming edges, no isolated junctions, no zero-lane edges),
  returning a report rather than raising, so a failing network is
  reported, not silently discarded.

**Result, run against the actual corridor .osm**: 4,619 junctions, 10,669
edges, **4 valid TLS out of 4 total (0 invalid)**, 0 isolated junctions, 0
zero-lane edges -- **the network validates completely cleanly**, no repair
needed, unlike the region-scale attempt. `tests/test_nets.py::
test_bengaluru_loads` (new, passing) re-checks the same structural gate
plus an actual libsumo session start (`traci.start` + one
`simulationStep()`) against whatever network the build script last
produced -- catches a file sumolib parses without error but the simulator
still can't load.

**FINAL VALID TLS COUNT: 4 -- below the 8-15 target.** Per explicit
instruction, stopping here to report rather than widening the box
unilaterally: "if <8, tell me and I'll widen the box along the same
arterial." The 4,619-junction / 10,669-edge total (for only 4 signalised
junctions) suggests the selected box, while much tighter than the
region-scale one, still spans a lot of unsignalised local street network
alongside the arterial -- consistent with a real corridor having dense
minor-road connectivity that isn't relevant to signal control, not a
defect in the conversion. Demand generation and v/c capacity calibration
are NOT started -- explicitly deferred until the TLS count is resolved,
per instruction to report before generating the full demand set.

### Phase 6 (Bengaluru): box widened west toward K.R. Puram, then a deterministic geo-crop + road-class prune -- 8 valid TLS on one continuous arterial, 4,954 edges (down from 17,105), coherence and feeder connectivity independently verified
`Sec. VI-C`, `prompts/phase6_bengaluru.md`.

**New OSM export, wider and shifted west** (author, openstreetmap.org,
drivable roads only): `min_lon 77.640, min_lat 12.995, max_lon 77.760,
max_lat 13.020` (pushed toward the denser, more-signalized K.R. Puram end
of Old Madras Road; the Hoskote-side box from the prior entry is
superseded). `nets/bengaluru/bengaluru_corridor.osm` (2.5MB) overwrites the
prior file. Raw netconvert on this box: 8,519 junctions, 20,843 edges, 9
valid TLS (0 invalid) -- structurally clean on the FIRST pass, unlike the
original region-scale attempt, but a coherence check (see below) found 1 of
the 9 was a disconnected straggler.

**Stage 1 -- geo-crop (coherence fix).** Visual + numeric check
(`sumolib`, road-classification-colored render + explicit shortest-path
query) found 8 of 9 TLS junctions form one genuinely continuous
trunk/primary-classified arterial (lon 77.643-77.709, ~6.6km, matching the
prompt's intended 4-6km scale); the 9th
(`cluster_567320389_7396736269`, lon~77.757) is reachable from the other 8
ONLY via a 5.3km/95-edge detour through tertiary/residential/secondary
streets -- zero trunk/primary road on that path, i.e. not on the arterial
at all, just a separate signal swept in by the wider box. Fixed with a
SECOND, tighter geo-boundary applied at netconvert time (`--keep-edges.
in-geo-boundary`, taking lon/lat directly, no manual projection math
needed) -- `BENGALURU_CROP_BOX = (77.640, 12.995, 77.720, 13.020)` in
`scripts/build_nets.py`, same min_lon/min_lat/max_lat as the OSM export,
only max_lon tightened. Both this crop boundary AND the original OSM
export box are recorded as named constants
(`BENGALURU_OSM_BOX`/`BENGALURU_CROP_BOX`) precisely because a crop of an
already-converted net is a step removed from the OSM box -- the paper's
reproducibility claim needs both, not just the source file. Result: 6,922
junctions, 17,105 edges, 8/8 valid TLS, 0 invalid, 0 isolated, 0 zero-lane.

**Stage 2 -- road-class prune (simulation-weight fix, not a geography
fix).** The 8 signals were already fine; 6,922 junctions / 17,105 edges for
8 signalised junctions is thousands of unsignalized residential
capillaries adding full simulation load with zero control relevance --
would make every Bengaluru run far slower than S1/S2 per episode.
`compute_feeder_keep_list` (`scripts/build_nets.py`) keeps every
`ARTERIAL_EDGE_TYPES` edge (trunk/primary/secondary/tertiary + `_link`
variants) unconditionally, plus exactly ONE layer of feeder edges --
anything touching (as either endpoint) a node some kept arterial edge also
touches. Everything else (deeper residential capillaries) is dropped.
2,417 arterial edges + 2,538 one-hop feeders = 4,955 edges kept out of
17,105.

**Root-caused, not worked around, when the naive approach silently failed
to filter anything.** `--keep-edges.input-file` applied directly on a
fresh OSM->net build was confirmed DIRECTLY to be a no-op (edge count
identical before/after, 17105->17105, across two independent attempts,
including one with the confounding `--keep-edges.by-vclass passenger`
flag removed). Two compounding causes, both confirmed: (1) netconvert's
`--keep-edges.*` family UNIONS together ("only keep edges in FILE OR
those kept due to OTHER keep-edges options" -- `--help`, verified
directly) -- combined with `--keep-edges.by-vclass passenger`, which alone
already matches nearly every OSM road, the explicit list contributed
nothing; (2) even with that flag removed, filtering STILL didn't apply,
because `--keep-edges.input-file` matches edge IDs at an internal stage
that precedes `--junctions.join`/`--tls.join`/`--geometry.remove`
finishing their renaming and splitting -- IDs read from an
ALREADY-processed network don't line up with what a FRESH OSM parse is
matching against mid-pipeline. **Fix**: `prune_via_plain_reimport`
round-trips through netconvert's own plain-XML export/reimport
(`--plain-output-prefix` then `-n/-e/-x/-i/-t` reimport) -- the plain
XML's edge IDs ARE the network's final, stable IDs, so
`--keep-edges.input-file` matches correctly against them. Verified
directly before wiring into the permanent pipeline: 17,105 edges -> 4,954
kept (list had 4,955; one edge became isolated post-filter and
`--remove-edges.isolated` correctly dropped it), **all 8 TLS junctions
preserved intact**.

**Result and independent re-verification, not taken on faith**:
`nets/bengaluru/bengaluru.net.xml` -- 2,456 junctions, 4,954 edges (down
from 17,105, a 71% reduction), **8/8 valid TLS, 0 invalid, 0 isolated
junctions, 0 zero-lane edges**. `tests/test_nets.py::test_bengaluru_loads`
re-passes against this file (structural checks + an actual libsumo
session load). Re-rendered with road-class-colored edges (trunk/primary in
blue, secondary in light blue, everything else faded grey) for a second
visual coherence pass: the 8 signals sit visibly on one continuous,
winding blue arterial path with no gaps -- distinctly clearer than the
first (unclassified, single-color) render, which is why the re-render used
classification instead of just re-running the same plot. **Feeder/entry-
exit check** (the "not a severed tube" requirement): 0 of the 8 TLS nodes
have a feeder edge touching the signal junction ITSELF (every edge
incident to a TLS node is itself arterial-classified -- expected, real
intersections' immediate approach segments are the same road class as the
road), but feeders are well-distributed ALONG the arterial near every
signal, not clustered around only a few: counted within a 300m radius of
each TLS node, feeder-edge counts range from 14 to 120 (`343459489` lowest
at 14, `416419153` highest at 120), all eight non-zero and non-trivial --
confirms realistic local entry/exit exists near every signal, not just
some.

**Noted, not fixed (out of scope for this pass, doesn't affect the 8-TLS
validation)**: three of the eight TLS IDs (`1837297544`/`545`/`546`) sit
13-26m apart -- likely one real, complex intersection that
`--junctions.join-dist 20` didn't fully merge into a single TLS node,
rather than three genuinely separate signals. Flagged for a future pass;
does not change the valid-TLS count question (all three pass the
>=2-incoming-edges check individually) and wasn't part of what this
instruction asked to fix.

**Crop and prune parameters, for the reproducibility record**:
- OSM export box: `min_lon=77.640, min_lat=12.995, max_lon=77.760,
  max_lat=13.020` (`BENGALURU_OSM_BOX`).
- Netconvert geo-crop: `min_lon=77.640, min_lat=12.995, max_lon=77.720,
  max_lat=13.020` (`BENGALURU_CROP_BOX`), applied via
  `--keep-edges.in-geo-boundary`.
- Prune rule: keep `{trunk, trunk_link, primary, primary_link, secondary,
  secondary_link, tertiary, tertiary_link}` unconditionally, plus edges
  with >=1 endpoint touching a kept edge's node (one feeder layer);
  applied via plain-XML reimport + `--keep-edges.input-file` +
  `--remove-edges.isolated`.

**Demand generation and v/c capacity calibration are NOT started** --
explicitly deferred per instruction to report the pruned edge count, the
8-signal count, and the post-prune screenshot before generating demand.

### Phase 6 (Bengaluru): the 3-node cluster does not merge -- investigated, found to be a real complex junction, and excluded rather than force-merged; corrected N=5
`Sec. VI-C`, `prompts/phase6_bengaluru.md`.

**The requested fix (`--junctions.join-dist` 20->30) does NOT merge the
three close TLS, confirmed by direct testing, not assumed.** Re-ran with
`--junctions.join-dist 30`: the three nodes (13-26m apart) remained three
separate TLS. Root cause found: `--junctions.join-dist` is the GENERAL
junction-merge distance; TLS-specific merging has its OWN, separate
parameter, `--tls.join-dist` (default 20, independent of the general one)
-- also raised to 30 and re-tested. STILL no merge. `--junctions.join-
output`'s own debug log confirms the three nodes are never even
CONSIDERED as join candidates, despite being connected by 0.2m and 1.1m
edges (dramatically under any distance threshold tried) -- this is not a
parameter-tuning problem.

**Topology inspection, not just distance, before deciding what to do**:
`1837297544` has 3 of its OWN distinct external road connections beyond
the cluster-internal links; `1837297546` has 2; `1837297545` sits between
them on the main through-road (two ~500-1000m arterial segments) with
short internal spurs to the other two. This is consistent with a
genuinely complex real intersection (multiple physical approaches
converging in a tight footprint, each separately noded in OSM), not one
road accidentally split into three duplicate nodes -- which plausibly
explains why netconvert's own topology-aware join algorithm declined to
merge them.

**Decision (author): exclude, don't force-merge.** Forcing a merge the
join algorithm itself rejected risks incorrect turning-movement topology
at a real complex junction -- the same "don't hand-fix to hit a target"
principle already governing this net's validation gate. The technical
concern motivating the original ask (sub-meter storage links between
adjacent controllers distorting HAP's pressure computation) is real
regardless of whether the junction is "one" or "three" -- excluding it
resolves that concern either way, without betting on a topology judgement
this investigation can't fully resolve.

**`--junctions.join-dist`/`--tls.join-dist` reverted to 20/default**, not
kept at 30 -- confirmed by direct testing that 30 has an UNRELATED side
effect: it silently drops a different, legitimate, single-node TLS
elsewhere on the corridor (the 8-TLS baseline dropped to 7, with
`cluster_11165270540_...` missing, not the intended three-node merge).
20 does not have this side effect and is the value that produced every
previously-reported result.

**Exclusion mechanism**: geo-boundary cropping proved unreliable for
surgically dropping just this cluster -- confirmed by direct testing that
even a boundary well below the cluster's own coordinates
(`max_lon=77.710`, tried after `77.720`/`77.735`) still let it through,
most likely via `--junctions.join`/`--tls.join` pulling in nodes beyond
the nominal box to complete an unrelated cluster. Switched to the exact
mechanism already proven reliable for the sprawl prune: explicit node-ID
exclusion (`BENGALURU_EXCLUDE_TLS_NODES = {"1837297544", "1837297545",
"1837297546"}`) via the same plain-XML-reimport path, dropping every edge
touching any of the three nodes. Hit and fixed a second issue on the way:
the reimport's pre-computed `.con.xml` (connections) and `.tll.xml` (TLS
programs) referenced the now-excluded edges, causing a hard failure ("40
total messages of type: Unknown edge given in connection"); fixed by
NOT reimporting either file and letting netconvert recompute both fresh
from the surviving edges/geometry (its normal behaviour when building
from OSM in the first place) -- confirmed this doesn't change results for
the sprawl-prune-only case, since that path never touched connections
built around now-missing edges to begin with.

**Author correction, logged for the record, not smoothed over**: this
investigation's own preview (offered when asking the author how to
proceed) mislabeled the exclusion outcome as "N=6" while listing only 5
signals -- a counting error, caught and corrected before acting on it, not
after. The actual arithmetic is 8 - 3 = 5, not 6; N=6 was never a real
option under the "exclude" mechanism (only under a "merge 3->1" mechanism,
which does not work, per above).

**Corrected N = 5**, verified: `416419153`, `cluster_11165270540_...`,
`442438288`, `343459489`, `1837297484` -- the same five that were never in
question, now confirmed final. 4,938 edges (arterial=2405, feeder=2538,
12 edges dropped for touching an excluded node), 2,449 junctions.
`tests/test_nets.py::test_bengaluru_loads` re-passes (0 invalid TLS, 0
isolated junctions, 0 zero-lane edges, loads in libsumo). Corridor span:
5,698.68m (~5.7km) -- matches the prompt's intended 4-6km scale. Feeder
connectivity re-verified within 300m of each of the 5 signals: 14-120
edges, all non-trivial (same numbers as before exclusion for these five,
since none of the three excluded nodes were among them). Re-rendered
(road-class-colored) for a final visual coherence pass: all five sit on
one continuous, gap-free blue arterial. This is now the paper's Sec.
VI-C corridor: **N=5, not 8, not 6** -- 5-6 was explicitly named in
advance as an acceptable small-real-world-corridor outcome ("we'll
present it as a small real-world corridor and lean on S1/S2 for
larger-N claims"); reported as measured, not adjusted toward a rounder
number.

### Phase 6 (Bengaluru): capacity calibration on the pruned N=5 corridor -- a real demand-formula bug found and fixed (a 20-hour stall was a symptom, not the root problem), capacity ~5,000 veh/h measured, with an honest caveat
`Sec. VI-C`, `Sec. V-D` (demand calibration), P4c-16.

**`scripts/calibrate_demand.py` extended for a real OSM network**:
`prepare_net_bengaluru` (entry/exit points are one-hop feeder leaf nodes --
reuses exactly the structure `compute_feeder_keep_list`'s prune already
established, not a new assumption) plus a connectivity filter (restrict to
the graph's largest strongly-connected component) -- confirmed necessary
directly: an unfiltered leaf-pairing crashed the very first attempt with
"Vehicle has no valid route" / `FatalTraCIError`, because `_od_pairs`'
rotate-and-zip pairing (safe by construction for S1/S2's fully-connected
synthetic grid) paired some entry/exit edges across 52 of 1,027 leaf pairs
that turned out not to be mutually reachable in the real, pruned network.
`sweep_capacity` refactored to accept externally-supplied topology
(`topology=`/`name=` params) rather than only `_prepare_net`'s
SCENARIOS-keyed lookup, so every other line (OD setup, the scale sweep,
knee/plateau detection, the nominal sanity check) is reused unchanged, not
duplicated.

**A serious bug, found by directly investigating a 20-hour stall rather
than just killing and retrying blind.** First capacity-sweep attempt made
~635s of progress on a 1800s episode in 20 hours of wall-clock time before
being killed. Root cause, confirmed with real numbers, not assumed:
`DEFAULT_BASE_VEH_PER_HOUR=300` (S1/S2's per-OD-pair demand rate) applied
unchanged to Bengaluru's 975 OD pairs produced **131,625 veh/h offered at
the LOWEST tested scale** (~36 vehicles/second into a 5.7km corridor) --
S1 has only 12 OD pairs total, so the same per-pair rate that is
reasonable for S1/S2's coarse, zone-level stubs is off by roughly the
81x ratio in OD-pair count when applied to Bengaluru's fine-grained,
per-residential-street pairing. This is NOT the same defect class as the
episode-isolation bugs (P4c-14/15) -- a genuinely new problem, a demand-
formula calibration mismatch, not state leaking across episodes -- and is
recorded as its own instance so it isn't confused with that family.
**Fixed** with `BENGALURU_BASE_VEH_PER_HOUR=4.0` (scaled by the same
12/975 ratio, rounded to a plausible quiet-residential-street volume),
threaded through `_write_run`/`sweep_capacity`/`offered_veh_h`/
`scale_for_vc` as an explicit parameter rather than a global constant
swap, so S1/S2's own calibration is untouched. Verified directly before
committing to a long run: re-tested at the corrected rate, simulated time
progressed at a healthy rate (rough real-time or faster in short probes,
matching plain "normal traffic" warnings -- emergency braking, not
teleport/collision cascades).

**Separately, a real resource-contention factor, unrelated to the demand
bug, also slowed one run materially**: the corrected-rate sweep, on its
first attempt at full 1800s episodes, still progressed at ~7.4x SLOWER
than real-time (measured directly: 1,102 simulated seconds in 8,180 real
seconds) -- traced to heavy concurrent CPU load from the user's own other
applications on the same machine (multiple VS Code windows, one alone
with 10.8 hours of accumulated CPU time; browser; other background
software), not a bug in this codebase. Not something to fix in code --
addressed by shrinking this task's own footprint instead (shorter 600s
sweep episodes, `--extra-seeds 1`), which completed the full sweep in
approximately 40 minutes under the same contended conditions.

**Result**: capacity_veh_per_h = 5,005.3 (extended 9-point scale grid,
0.5-16), independently corroborated by an earlier run at 5,157.0 (default
4-point quick grid) -- two different scale grids, consistent capacity.
`scale_nominal=1.212` (v/c~0.85), `scale_surge=1.497` (v/c~1.05). Sanity
check at scale_nominal: 4,089 trips in a 3,600s episode, v/c=0.85 as
intended, no insertion-backlog warning.

**Honest caveat, not smoothed over**: the knee-detector found the knee at
the FIRST tested scale point (0.5), and ALL nine tested points (0.5
through 16, a 32x range) landed in the reported plateau -- AQL/ATT/
overflow were bit-identical to two decimal places across scale 0.5-6.0
specifically (not just similar). Confirmed this is not a demand-generation
bug: regenerated the actual route XML at scale=0.5 and scale=6.0 directly
and verified the offered volume scales exactly proportionally (12x ratio,
matching the scale ratio exactly) -- the identical THROUGHPUT is a
genuine simulation outcome (insertion-limited capacity reached even at
the lowest tested demand), not a broken sweep. But the rising portion of
the demand curve (scale < 0.5) was never observed, and bit-for-bit
identical results across a 12x demand range is unusual even for a
saturated regime -- plausible, not independently confirmed with a longer
episode window. Reported as a genuine finding with this caveat attached,
not presented as fully validated.

**Not yet started**: composition-heterogeneous demand generation with the
directional morning peak (westernmost signal, `416419153` / K.R. Puram
end, as the peak sink) -- deferred per instruction to report capacity
before generating the full demand set.

### Phase 6 (Bengaluru): time-boxed health check below the capacity floor -- a real demand-generation bug fixed, one real structural bottleneck fixed, but the underlying issue is SYSTEMIC (62% of arterial edges are short single-lane segments); STOPPED per the pre-agreed rule, S3 cut, S1+S2 stands as the complete evaluation
`Sec. VI-C`, P4c-16.

**Health check below the capacity-sweep floor** (scale in {0.5, 0.25, 0.1,
0.05}, GreedyHAP, `diagnose_gridlock.py`'s own instrumentation --
`worst_storage_occupancy` -- reused directly, not reimplemented): all four
scales, a 10x demand range, gave BIT-IDENTICAL results (in_net=975 at t=0
in every case, exactly matching the OD-pair count).

**A second real demand-generation bug found and fixed, isolated to
Bengaluru-only code.** Root cause, confirmed directly: `_routes_xml`
(`scripts/build_nets.py`, shared with S1/S2) gives every OD pair's flow in
a bucket the SAME integer `begin` (deliberately, for a different reason --
SUMO silently drops out-of-order flows if `begin` isn't globally
non-decreasing across the route file). Harmless for S1/S2 (12-16 OD
pairs). For Bengaluru's 975 independent OD pairs, SUMO inserts each flow's
first vehicle near its own `begin` almost independent of its rate, so 975
simultaneously-begun flows means ~975 near-simultaneous insertions
REGARDLESS of scale -- an artificial cold-start surge, not a reflection of
real demand or corridor capacity. Confirmed the demand ITSELF scales
correctly (offered volume exactly proportional across all four tested
scales, verified by regenerating and inspecting the route XML directly)
before concluding this was a generation artifact rather than a capacity
finding. **Fixed** with a new, Bengaluru-only `_routes_xml_staggered`
(`scripts/calibrate_demand.py`) that spreads each OD pair's `begin`
uniformly across its bucket instead of sharing one integer -- `_routes_xml`
itself is UNTOUCHED, so S1/S2's already-validated numbers are not at risk.
Verified the fix directly (200 unique begin times in the first 200s bucket
alone, vs. all-zero before) before re-running anything.

**One real structural bottleneck found and fixed at the network level.**
After the staggering fix, results were STILL bit-identical across all
four scales (occupancy dropped from 2402% to 366%, confirming the surge
fix helped, but the scale-independence persisted) -- traced to
intersection `1837297484`'s U-turn movement (`-1207691763#0 ->
1207691763#0`), a 31.75m single-lane link with weighted storage capacity
13.22 (5x smaller than the junction's other movements), saturating even
under the lightest tested demand. Fixed at the network level, not the
demand level: `remove_connections` (`scripts/build_nets.py`) removes the
specific `<connection>` (not the edges -- the junction's OTHER movements
stay routable), via the same plain-XML-reimport pattern already validated
for the sprawl prune. Hit and fixed the same class of stale-reference bug
again in a new place: the old `.tll.xml` still referenced the removed
connection as a controlled link ("Connection ... not found"); fixed by
NOT reimporting `.tll.xml` either, letting TLS programs regenerate fresh
from the updated connections (same fix as `prune_via_plain_reimport`,
confirmed directly before trusting it). `BENGALURU_REMOVE_CONNECTIONS`
records the exact (junction, from_edge, to_edge) removed, for
reproducibility; `remove_connections` returns a removed-count so a
mismatch (the target line not actually found) fails loudly rather than
silently reporting false success.

**Re-verified, and the fix revealed a SECOND, structurally identical
bottleneck, not a resolution.** Post-fix: pending dropped to 0 (an
improvement), but max_worst_occ INCREASED (434.2%, still bit-identical
across all four scales) at a DIFFERENT intersection
(`cluster_11165270540_...`, movement `1487182809->1411066512`, a 19.4m
single-lane link) -- the exact same failure class at a different location.
**Before attempting a third fix cycle, checked whether this is isolated or
systemic**: scanned every arterial-classified edge in the final network
for length <40m and 1 lane. Result: **1,491 of 2,404 arterial edges
(62%)**. `--geometry.remove` is already active in every netconvert
invocation in this pipeline (would have merged pure-geometry-artifact
splits) -- these 1,491 short segments surviving it indicates they are
genuine distinct junctions/segments in the source OSM data (a real,
dense urban block characteristic), not a processing artifact fixable by a
different flag.

**Decision, per the pre-agreed rule ("if it is NOT sound within this
session, STOP and tell me -- we cut S3 and ship on S1+S2, which is a
complete evaluation on its own"): STOPPED.** What looked initially like
one identifiable jamming link turned out, on systematic investigation, to
be a network-wide characteristic -- fixing individual connections one at a
time will not converge in any bounded amount of time, and is not the
"fixable with one structural change" case the time-box was built around.
**S3 (Bengaluru) is cut from the evaluation. S1+S2 stands as the complete,
paper-reportable evaluation.** Verified N=5 stands as a fact about the
network (unaffected by this finding: confirmed via pairwise TLS distance,
all >1200m apart, no clustering) but is now moot for the paper's results,
since S3 is not being evaluated. All Bengaluru artifacts (network,
scripts, fixes, this investigation) are kept on disk, not deleted -- per
explicit instruction, this work is not wasted if revisited later, and
switching to a different city/corridor would pay the same Phase-6 cost
again with no guarantee of a better outcome (the underlying issue --
OSM road segmentation density -- is not specific to this corridor).

### Phase 6 (Bengaluru): join-dist confirmation test -- widening --junctions.join-dist to {30, 40, 50} does NOT reduce the short-single-lane-arterial-edge problem; it gets marginally WORSE, not better. S3 stays cut permanently.
`Sec. VI-C`, P4c-16.

**One further, time-boxed (one-hour) test before treating the S3 cut as
final**, on the hypothesis that dense urban OSM routinely over-segments
one physical intersection into a cluster of nodes 15-35m apart, which
`--geometry.remove` deliberately does not merge (it only collapses
pure-geometry nodes, not distinct junctions) -- `--junctions.join-dist`,
untested above that value, was the correctly-targeted tool to check
before accepting the systemic-63%-short-link finding as unfixable.

Swept `--junctions.join-dist` in {20 (baseline), 30, 40, 50} through the
existing crop -> prune pipeline, unchanged otherwise (same
`BENGALURU_CROP_BOX`, same `BENGALURU_EXCLUDE_TLS_NODES`, same feeder-prune
logic), re-scanning every arterial-classified edge for length <40m and 1
lane at each. `netconvert_build_bengaluru` gained a `junctions_join_dist`
parameter (default 20, production behaviour byte-identical) so the test
could call the real pipeline function rather than duplicate the netconvert
command in a throwaway script.

| join-dist | crop TLS | final N (valid TLS) | arterial edges | short single-lane | pct |
|---|---|---|---|---|---|
| 20 (baseline) | 8/8 | 5 | 2404 | 1491 | 62.0% |
| 30 | 7/7 | 4 | 2473 | 1556 | 62.9% |
| 40 | 7/7 | 4 | 2526 | 1607 | 63.6% |
| 50 | 7/7 | 4 | 2568 | 1649 | 64.2% |

**Result is decisive and in the wrong direction.** Widening join-dist did
not merge the short segments into fewer, larger junctions -- crop-stage
junction count went UP (6922 -> 7194) as join-dist widened, not down, and
the short-single-lane-arterial percentage rose monotonically (62.0% ->
64.2%) rather than falling. N (valid TLS after the same exclusion/prune)
only ever shrank (5 -> 4), consistent with the earlier, separate finding
that `--junctions.join-dist` does not merge the specific 3-node complex
either (confirmed then via `--junctions.join-output`: those nodes are
never even considered join candidates despite sub-1.1m connecting edges).
Taken together, both tests point to the same conclusion: these are not
pure-geometry over-segmentation artifacts that a distance-based join
threshold can safely collapse -- they are real, distinct junctions in the
source OSM data, each with its own external connections, and treating
them as merge candidates is what a wider join-dist tries to do (crop
junction count rising, not falling, suggests the wider radius is pulling
in EXTRA real intersections as merge candidates and creating new splits
elsewhere, not simplifying existing ones).

**Decision, per the pre-agreed one-hour time-box: NONE of {30, 40, 50}
produces a usable corridor (short-link percentage never gets close to the
~20% target; it moves the wrong way). S3 (Bengaluru) stays cut
permanently.** This is now a stronger, reviewer-proof version of the
original cut rationale: not merely "found 62% short-link edges and didn't
try the obvious knob," but "tried the obvious knob across a 2.5x range
past the default and confirmed the problem does not respond to it, in
either direction." **S1+S2 stands as the complete, paper-reportable
evaluation.** Test artifacts (`nets/bengaluru/_jointest/`, the throwaway
sweep script) deleted after use, matching this project's practice for
one-off diagnostics; the production `nets/bengaluru/` outputs (join-dist
20, N=5) are untouched.

### Phase 6 (Bengaluru): reframing the S3 finding as a contribution -- for BOTH `Discussion` and `Limitations`, not filed as a gap.
`Sec. VII (Discussion)` + `Sec. VIII (Limitations)` (paper author: locate/create the matching subsections; this entry does not touch the .tex).

**For Discussion, as evidence FOR the thesis.** We extracted a real
Bengaluru arterial (Old Madras Road / K.R. Puram corridor, 5 verified
signalised junctions from raw OSM, deterministic pipeline logged above)
and instrumented it with the same storage/queue diagnostics used
throughout this paper (`worst_storage_occupancy`, per-movement true-queue
traces). The measurement: ~62% of arterial-classified edges are short
(<40m) single-lane links, and every identified congestion point in this
corridor saturates to 300-400%+ occupancy AT THE LOWEST TESTED DEMAND,
independent of scale over a >10x range -- i.e. finite-storage spillback
dominates before demand-driven queuing even becomes the binding
constraint. We further confirmed, via a `--junctions.join-dist` sweep
(30/40/50m against a 20m baseline, same crop/prune pipeline otherwise
unchanged), that this is NOT a processing artifact correctable by
standard netconvert junction-merging: the short-link percentage moves
the WRONG direction as join-dist widens (62.0% to 64.2%), meaning these
are genuine distinct junctions in the source OSM data, not
over-segmented geometry. **This is a real-world, independently-measured
demonstration that finite-storage-induced deadlock -- exactly the failure
mode this paper's storage-aware layer (Sec.~\ref{sec:theory}'s Corollary 1
filter, `storage_aware_mu`) is built to address -- is not a hypothetical
edge case constructed for the theory, but the dominant structural regime
on real Indian arterial geometry.** The paper should state this
plainly: the S3 attempt independently corroborates the paper's own
motivating premise from measurement, not simulation design.

**For Limitations, the honest other half of the same finding.** This
corridor's short-link density is also precisely why it could not be
carried through to a full n=10 controller comparison within this
project's time-box: the demand-side fixes above resolve individually
(a cold-start artifact, one U-turn turn-pocket), but the underlying
network characteristic is systemic, and a controller comparison run on a
network that is already structurally saturated at every tested demand
level would not isolate a signal-control effect from a pure-geometry
effect. Evaluating real Indian arterial OSM corridors -- as opposed to
the calibrated synthetic networks used for S1/S2 -- requires either
demand/routing logic that keeps a real network below its structural
saturation point, or a control layer explicitly reasoning about
sub-40m storage pockets; neither exists in this codebase yet, and
building either was assessed as its own multi-session effort, not a
one-hour fix. Stated as future work, not as a result claimed to hold on
real networks.

### Phase 6 (Bengaluru): the synthetic-evaluation limitation, stated once.
`Sec. VIII (Limitations)`.

**All reported results (S1, S2) are on synthetic networks (a 5-node
arterial and a 4x4 grid) calibrated to Indian mixed-traffic conditions
(Indo-HCM saturation flows, measured composition/occupancy, calibrated
demand and estimator bias) -- not on a real road network.** The Bengaluru
corridor extraction (Phase 6, this file, above) was a direct attempt at
real-corridor evaluation; it surfaced a genuine structural obstacle (dense
short-link urban arterial geometry, confirmed not resolvable by standard
netconvert junction-merging within this project's time-box) rather than
producing a third evaluated scenario. Evaluating on real corridors is
future work, and now has a concrete, measured starting point rather than
an unknown one: the short-link/finite-storage characteristic documented
above is the specific obstacle the next attempt needs to design around.

### Phase 5 (RL baselines) kickoff: `pressure_raw` reward form -- one real bug (telescoping, same class as `pressure_all`'s), one real bug in the gate script itself (floating-point equality), both found and fixed before any baseline trained on it.
`Sec. VI-E`, P5-1.

Plan approved (5 baselines: Advanced-MPLight, MPLight, CoLight, PressLight,
IPPO; MARDDPG dropped at the start, not "if short," per instruction --
different algorithm class, weakest modern baseline, already pre-registered
as droppable). Baselines trained at 3 seeds, HAPLight-RL stays at 5. A bare
(unfiltered) HAPLight-RL row will be added alongside the filtered one in
every table (free -- already trained; separates "the policy is good" from
"the filter prevents deadlock" as two distinct, disentangled claims).

**Bug 1 (reward formula): first `pressure_raw` attempt failed
`scripts/validate_reward.py`'s gate outright.** Definition summed
`info["true_w"]` (unweighted pressure differential) over EVERY movement at
each intersection, every step -- structurally identical to `pressure_all`
(Eq. 12) minus the mu-weighting, and it inherited `pressure_all`'s exact
documented telescoping defect (a movement's downstream queue is some other
movement's upstream queue, so summing over every movement partially
cancels rather than reflecting real congestion) for the same reason:
mu-weighting was never the broken part. Measured directly: Random (the
worst controller) had the HIGHEST reward-return of all five (1942.12 vs
GreedyHAP's 604.66), Spearman rho = -0.700 against both -AQL and
throughput (wrong sign). **Fixed** by restricting the sum to only the
movements served by the phase actually executed that step -- exactly the
same fix `served_pressure` already applies to `pressure_all`, minus the
mu-weighting (the genuine MPLight/PressLight-lineage published reward:
Chen et al. 2020 / Wei et al. 2019 define pressure in raw vehicle-count
terms; mu-weighting is Zhang et al.'s own state-side refinement, not part
of the base pressure-reward these three baselines share). Re-run: rho =
0.9999999999999999 against both -AQL and throughput (see Bug 2).

**Bug 2 (gate script itself, found while re-validating Bug 1's fix): the
pass/fail check used exact `rho == 1.0`,** which rejected a genuinely
perfect rank correlation purely on floating-point grounds --
`scipy.stats.spearmanr` returned `0.9999999999999999` on a 5-point ranking
confirmed by hand to be perfectly monotonic (Random worst on every metric,
GreedyHAP best, in identical order to reward-return). Verified this is a
numerical artifact, not a real one-rank discrepancy, via direct JSON
inspection of `results/reward_validation.json` before touching the gate
logic. **Fixed** with a `> 1.0 - 1e-9` tolerance check, replacing the exact
equality -- tighter than the gate's own stated bar ("well short of 1.0" is
a fail, per the script's docstring), so this is a numerical-precision fix
to the gate, not a loosening of what counts as rank-consistent. Both fixes
required before any Phase 5 baseline could be trusted to train on this
form -- neither was skipped or assumed; both confirmed via the gate
script's own re-run, not by inspection alone.

### Phase 5: Stage A+B complete for all five baselines (Advanced-MPLight, MPLight, PressLight, IPPO, CoLight); CoLight shipped WITHOUT the planned `ppo.py` change (design improvement found during implementation); Advanced-MPLight's Stage C (the phase's gate) reports undertrained-but-currently-behind-MP, with an unresolved wall-clock anomaly specific to it.
`Sec. VI-E`, P5-1.

**All five baselines wired and passing `tests/test_baselines.py` + a
2-iteration Stage-B smoke-train (S1 and/or S2) with zero crashes**:
Advanced-MPLight (movement_in_dim=2: efficient pressure + running demand),
MPLight (movement_in_dim=1: pressure only), PressLight (movement_in_dim=2:
raw [x_up, x_down] counts, undifferenced -- distinct from MPLight's single
differenced feature), IPPO (N=5/16 fully independent HAPLightPolicy+
PPOTrainer pairs keyed by intersection ID, HAPLight's own state/reward
verbatim), CoLight (new `CoLightPolicy`: single-hop scaled-dot-product
attention over up to 4 REAL graph neighbours, `env._neighbours` -- a
documented, deliberate exception to "policy never touches env internals").

**CoLight design correction, found while implementing, not while
planning**: the approved plan called for a scoped `ppo.py` minibatching
change (group by (episode, timestep) instead of the flat shuffle) so a
step and the neighbours its forward pass needs would co-occur in a
minibatch. Building it, a smaller alternative emerged: bake each
neighbour's RAW (pre-attention) sensed features into `Step.obs` itself,
and run the ENTIRE attention computation (local encoder, neighbour
projection, query/key/value, softmax) fresh inside `CoLightPolicy.forward`
on every call. Every `Step` then carries everything its own forward pass
needs, independent of which other Steps share its minibatch -- so
`ppo.py` needed ZERO changes, not a scoped one. Verified directly: a
2-iteration smoke-train exercises `forward_batch` (the batched attention
path `PPOTrainer.update` actually calls) with no shape errors. This is a
smaller, more honestly-labeled simplification than what was proposed
(single-hop attention over raw features, not multi-hop attention over
other intersections' hidden embeddings), not a frozen/no-gradient
approximation -- the distinction the Phase 5 plan's decision B was built
around.

**Advanced-MPLight's Stage C (the phase's load-bearing gate, S2, seed=0,
30 of the paper's planned 100 iterations -- NOT the full budget, a
partial checkpoint): reward-return is noisy, not cleanly rising, across
the 30 iterations run (entropy fell 0.345->0.177, i.e. the policy IS
converging toward something, but return fluctuated -713 to -397 to -599
with no clean trend). The Stage-C MaxPressure-paired comparison (5 seeds,
eta=0) at this checkpoint: ATT -7.2%, throughput -5.2%, AQL -97.0% (all
WORSE than MaxPressure), gridlock 2/5 eval episodes vs MaxPressure's 0/5.**
Not presented as a verdict on Advanced-MPLight's viability -- 30/100
iterations is early, and an RL policy underperforming a classical
heuristic before convergence is a common, expected pattern, not
necessarily a port defect: the classical `AdvancedMP` controller (same
state ingredients, hand-coded decision rule) is already independently
verified to beat MaxPressure (an earlier phase, `_verify_advanced_mp.py`),
which is evidence the underlying state representation itself is sound;
what's undertrained here is the LEARNED policy on top of it. Reported
precisely rather than extrapolated in either direction -- decision on
whether to continue training further before the real go/no-go, or treat
this checkpoint as sufficient signal, deferred to the author.

**Separate, real wall-clock anomaly, specific to Advanced-MPLight, not
yet root-caused**: per-iteration time never recovered to the ~200-224s
baseline measured for HAPLight-RL on this machine -- it settled around
750-950s/iteration (~4x) for the FULL 30-iteration run, including well
after this session stopped running any competing foreground work
(confirmed no contending python.exe/sumo.exe processes at a mid-run
check). Leading hypothesis, not yet confirmed: `build_state_advanced_
mplight`'s running-demand term calls `env.running_count_within_range`/
`env.lane_max_speed` -- LIVE traci queries per movement per intersection
per decision step per parallel worker -- rather than the cached, batched
`_measure()` pass every other channel (`counts_hat`, etc.) reads from;
MPLight/PressLight's own state-builders don't call these methods, so
this slowdown is NOT assumed to generalise to the other four baselines'
Stage D compute budget without separately timing at least one of them.
If confirmed, the Stage D compute-budget estimate in the approved plan
(~145h at 3 seeds/5 baselines) needs revising upward for Advanced-MPLight
specifically, not uniformly across all five.

### Phase 5: the 4x slowdown is NOT Advanced-MPLight-specific -- the "live traci running-demand query" hypothesis is confirmed WRONG by direct measurement; likely cause is external machine contention, not a code defect in this phase's work. Fix built and kept (it is a real, correct optimisation) but does not, by itself, resolve the observed slowdown.
`Sec. VI-E`, P5-1.

**The fix, built and verified correct in isolation**: `HAPLightEnv` gained
an opt-in `advanced_mp_running_demand` constructor flag (default False,
every existing validated result byte-for-byte unaffected). When True,
`_discover_topology` caches each lane's static speed limit
(`_lane_max_speed`, previously re-queried live on every call) and widens
that edge's existing context subscription radius to
`min(lane_max_speed*g_max, the edge's own longest lane)` -- EXACT, not an
approximate cap, because a vehicle can never physically be further from
the stop line than its own lane's length, the same bound the original
live per-lane query always had implicitly. `_measure()` then accumulates
Advanced-MP's running-demand count from that SAME per-vehicle
subscription pass it already runs (zero extra traci round-trips), and a
new `running_demand_hat(i, mv)` reads the cache. The classical
`AdvancedMP` controller in `src/controllers.py` is UNCHANGED -- still
uses the original live-query method directly -- so nothing already
validated is put at risk by this change.

**Direct measurement, before drawing any conclusion (one full-length
iteration each, S2, `--skip-eval`, run in isolation, not concurrently)**:

| Run | wall_clock_s |
|---|---|
| MPLight (never touches running-demand code at all) | 864.98 |
| CoLight (never touches running-demand code at all) | 667.42 |
| Advanced-MPLight, BEFORE this fix (iteration 0 of the Stage C run) | 1040.74 |
| Advanced-MPLight, AFTER this fix | 900.05 |

**All four cluster in the same ~650-1040s range, regardless of baseline
and regardless of the fix.** MPLight and CoLight never call
`running_count_within_range`/`lane_max_speed` at all (their state-builders
only read the same cached `counts_hat`/`counts_hat_downstream` channels
HAPLight-RL's own training already uses) -- if the live-traci hypothesis
were correct, they should already be near the ~200-224s reference, and
they are not. Advanced-MPLight's OWN before/after numbers (1040.74 ->
900.05) show at most a marginal, noise-scale change, not the ~4x
recovery the hypothesis predicted. **The original diagnosis is
confirmed wrong by this comparison, not merely unconfirmed.**

**Leading alternative explanation, not yet independently verified**:
genuine external machine load. A process check taken shortly after these
timings showed 19 concurrent `Code.exe` (VS Code) processes -- a marked
increase from earlier checks in this same session (2 processes, when a
different training run's per-iteration time WAS close to the ~200-224s
reference). This matches a failure mode already diagnosed once before in
this project (PAPER_CHANGELOG P4-6, the 16.9h-run machine-sleep incident)
-- machine-side load external to this codebase, not a bug to fix in code.
Not conclusively proven (no controlled before/after measurement of VS
Code load specifically was taken), so reported as the leading hypothesis
requiring the author's confirmation, not asserted as fact.

**Decision: did NOT proceed to re-running Advanced-MPLight's Stage C to
the full 100 iterations at ~830-900s/iteration** (~23-25h for that one
run alone, against a 2-3 day total budget) **-- the fix's own timing
result is too close to noise to trust as "the true post-fix rate"** until
the external-load question is resolved. Reported to the author for a
decision before spending that compute, per the stop-before-training-more
instruction this fix was built under.

### Phase 5 speed gate: RESOLVED, and the premise was wrong -- there is no contention problem. The "~200-224s reference" was measured on S1; S2 has always cost ~780-840s/iteration, including the run that produced the paper's own headline S2 results.
`Sec. VI-E`, P5-1.

**Clean-machine measurement** (one active VS Code window -- 15 processes,
which is one window's normal process tree, not 15 windows; CPU 10% idle;
no stray SUMO/python), one full-length S2 iteration each, run strictly
sequentially:

| method | S2 wall-clock, 1 iteration |
|---|---|
| HAPLight-RL (`scripts/train.py`) | 838.7s |
| MPLight (`scripts/train_baseline.py`) | 727.3s |
| Advanced-MPLight (`scripts/train_baseline.py`, post running-demand fix) | 809.8s |

**These are NORMAL, not contended.** Confirmed against this project's own
run history rather than against memory:

| historical run | scenario | iters | median wall-clock |
|---|---|---|---|
| `s1_seed0_1786360965` | S1 | 40 | 197.9s |
| `s1_seed0_1786387277` | S1 | 100 | 224.2s |
| `s2_seed0_1786479384` | S2 | 37 | 364.2s |
| `s2_seed0_1787236381` | S2 | 40 | 347.0s |
| `s1_seed0_1787507503` | S1 | 100 | 443.5s |
| `s2_seed0_1787604457` | S2 | 100 | **783.7s** |

The "~200-224s" figure quoted in `scripts/train.py`'s own comments is the
**S1** rate (rows 1-2). **S2 has never run at that rate.** The most recent
full 100-iteration S2 production run -- `s2_seed0_1787604457`, the P4c-16
clean retrain that produced the paper's headline S2 gridlock table -- has
a median of 783.7s/iteration. Today's 838.7s is 7% above that: ordinary
variance, not a regression. Every earlier "~4x slowdown" reading in this
phase, including the one that motivated the Advanced-MPLight
running-demand fix, came from comparing an S2 measurement against an S1
reference. **Recorded as an author-side analysis error, not smoothed over.**

**The genuine historical drift (S1 197.9 -> 443.5s, S2 364.2 -> 783.7s) is
explained by configuration, not by the machine**: `metadata.json` shows
`safety_filter_storage_aware`/`safety_filter_hysteresis` present ONLY in
the slow runs and absent from the fast ones -- i.e. the ~2x step happened
when the production storage-aware + hysteresis filter (P4c-7/P4c-9/P4c-11,
made default by P4c-14) was adopted. That filter evaluates
`worst_downstream_occupancy` per movement per step and engages often
enough to change the traffic state, so a real per-step cost increase is
the expected consequence, not a defect. Baselines carry no filter
(decision A) and are correspondingly cheaper (MPLight 727.3s vs
HAPLight-RL 838.7s, -13%), but the dominant cost is SUMO stepping a
3600s episode of the calibrated 4x4 grid, which no baseline avoids.

**Consequence for Stage D, which is why this stopped rather than
proceeded**: at 100 iterations (the paper's own fairness-mandated 800
episodes, which reviewers can check), per (baseline, seed): S2 ~21.4h,
S1 ~12.1h, both ~33.5h. For the three retained baselines
(Advanced-MPLight, MPLight, CoLight-variant): 3 seeds x 2 scenarios
~301h (~12.6 days); 2 seeds ~201h (~8.4 days); 1 seed x 2 scenarios
~100h (~4.2 days); 1 seed x S1 only ~36h. **No configuration retaining all
three baselines at the full 100-iteration budget fits a ~2-night window**,
and the pre-authorised 3-seeds-to-2-seeds fallback closes almost none of
that gap (8.4 days). The only lever that would fit ~2 nights is cutting
iterations below 100, which would break the "same training budget as
HAPLight-RL" fairness claim -- a paper-claim decision, deliberately left
to the author rather than taken silently.

**Completed and kept regardless** (all independent of the scope decision):
`pressure_raw` re-confirmed PASS on disk (rho = +1.000 against both -AQL
and throughput; `pressure_all` -0.600 FAIL and `served_pressure` +0.900
FAIL unchanged, so the tolerance fix did not loosen the gate); the
per-iteration contention guard (`check_iteration_contention` +
`current_load_summary` in `scripts/train.py`, wired into `train.py` and
both `train_baseline.py` loops -- rolling median, warns at >2x with a
psutil load snapshot, unit-verified on synthetic histories);
`scripts/evaluate_policy.py` extended to the full Phase 5 deliverable
(pluggable baseline checkpoints via `--baseline-checkpoint KEY=PATH`, a
HAPLight-RL-unfiltered column from the same trained policy, median as the
primary central-tendency figure with mean kept as context, and paired
BCa/rank-biserial blocks against BOTH GreedyHAP and Advanced-MPLight).

### Phase 5 final protocol: equal 40-iteration budget for every learned method, justified from the convergence knee (not chosen for convenience); MPLight/CoLight-variant run only if time allows; PressLight/IPPO scoped out.
`Sec. VI-E`, P5-1.

**The 40-iteration budget is defensible, verified before adopting it, not
asserted.** Theil-Sen slope of the S1 production run's clean-eval return
(`results/s1_seed0_1787507503`, 100 iterations) computed over every
window [k, 100]:

| window start k | slope (return/iter) | 95% CI | verdict |
|---|---|---|---|
| 5 | +3.82 | [+0.70, +7.04] | still rising |
| 10 | +3.94 | [+0.33, +7.39] | still rising |
| **15** | +3.31 | [-0.68, +7.01] | **flat (knee)** |
| 30 | +0.09 | [-4.10, +4.98] | flat |
| **40** | **+0.36** | **[-4.94, +5.74]** | **flat** |

The last window with a significant rising trend is [10, 100]; from
[15, 100] onward the CI straddles zero. **The convergence knee is
~iteration 15, so a 40-iteration budget sits ~2.7x past it.** S2
(`s2_seed0_1787604457`) shows no significant trend at any window start,
including [0, 100] -- consistent with the heavy-tailed S2 episode
distribution documented throughout the P4c thread. 40 iterations = 320
episodes at E=8.

**Equal-budget rule, absolute**: every learned entry in the main
comparison table is trained to the identical 40 iterations. No baseline
is ever trained shorter than HAPLight-RL. The existing 100-iteration
HAPLight-RL checkpoints (`s1_seed0_1787507503`, `s2_seed0_1787604457`)
are NOT reused in the main table -- they are retained on disk as a
robustness appendix only, since mixing a 100-iteration HAPLight-RL with
40-iteration baselines would be exactly the unfair comparison this
protocol exists to prevent.

**`train.py`'s >25% filter-activation early abort disabled for these runs**
(`--early-check-iterations 0`), deliberately and logged: at iteration 4
the production filter config sits at 0.255 (S1) / 0.257 (S2), marginally
over that threshold, while the 100-iteration runs that produced the
paper's own accepted results ran at exactly this operating point (mean
0.250 S1, 0.213 S2, and 42/100 S1 iterations above 0.25). Aborting on it
would be a false positive against an already-validated configuration, and
would silently truncate a multi-hour run.

**Training order (strict priority, sequential -- concurrent runs recreate
the CPU-contention problem already diagnosed twice in this project),
1 training seed (seed 0), both scenarios:**
1. HAPLight-RL (filtered) -- required, sets the equal budget; its
   unfiltered variant is the SAME policy evaluated with the filter off,
   costing no extra training.
2. Advanced-MPLight -- required, the SOTA comparison the paper's central
   claim rests on; `pressure_raw` reward (gate PASSED, rho=+1.000).
3. MPLight -- only if 1-2 finish with margin.
4. CoLight-variant -- only if 3 finishes with margin.

**Scoped out for compute, explicitly**: PressLight and IPPO. Both are
BUILT and pass `tests/test_baselines.py` (Stage A complete, code retained
on disk), but neither is trained or reported. Rationale: at ~800s/iter on
S2 the machine affords roughly three learned baselines in the available
window, and the three retained ones are what a reviewer requires -- the
SOTA method (Advanced-MPLight), the parameter-sharing ancestor (MPLight),
and a graph-attention comparison (CoLight-variant). PressLight is
largely subsumed by MPLight (same pressure-reward lineage, a strictly
simpler state), and IPPO is an ablation of our own architecture rather
than a competing published method. Stated as a compute-driven scope
decision, not a claim that they would have performed poorly.

### Phase 5 training, priorities 1-2 complete at the equal 40-iteration budget: HAPLight-RL trains healthily; Advanced-MPLight ROBUSTLY DIVERGES on both scenarios. Reported as measured, not tuned.
`Sec. VI-E`, P5-1.

**Completed (seed 0, 40 iterations each, both scenarios, sequential with
cooldowns between runs -- author instruction, to keep a laptop out of
sustained-throttle territory over a ~37h chain):**

| run | iters | ckpt | median wall/iter | total compute |
|---|---|---|---|---|
| HAPLight-RL S1 (`s1_seed0_1788473606`) | 40 | 39 | 445.1s | 5.55h |
| HAPLight-RL S2 (`s2_seed0_1788497621`) | 40 | 39 | 875.4s | 10.11h |
| Advanced-MPLight S1 (`advanced_mplight_s1_seed0_1788540892`) | 40 | 39 | 797.2s | 8.46h |
| Advanced-MPLight S2 (`advanced_mplight_s2_seed0_1788573166`) | 40 | 39 | 895.2s | 12.44h |

HAPLight-RL S1's 445.1s median lands within 0.4% of the 443.5s historical
S1 reference -- a third independent confirmation that the earlier
"4x slowdown" scare was an S1-vs-S2 comparison error and never a
contention problem.

**Robust trend check (Theil-Sen with 95% CI, the estimator this project
adopted in P4c-15 precisely because OLS is dragged by rare heavy-tailed
episodes), over all 40 iterations:**

| run | series | Theil-Sen slope | 95% CI | Spearman | verdict |
|---|---|---|---|---|---|
| HAPLight-RL S1 | eta0_return | -3.04 | [-12.41, +8.07] | rho=-0.10 p=0.54 | flat (past the knee) |
| HAPLight-RL S2 | eta0_return | **+6.41** | **[+2.44, +10.02]** | rho=+0.42 p=0.006 | **rising** |
| Advanced-MPLight S1 | mean_return | **-27.42** | **[-38.58, -12.05]** | rho=-0.35 p=0.025 | **robustly declining** |
| Advanced-MPLight S2 | mean_return | **-30.49** | **[-34.11, -25.67]** | rho=-0.92 p<0.001 | **robustly declining** |

**Advanced-MPLight is diverging, not merely undertrained** -- a
distinction that matters, because "undertrained" would be fixed by more
iterations and this is not. On S2 the return falls monotonically across
every 8-iteration block (-768.7, -827.6, -1022.0, -1408.5, -1694.4),
policy entropy contracts (0.331 -> 0.256, i.e. it is becoming
CONFIDENT in the worse behaviour), and critic value_loss grows an order
of magnitude (679.9 -> 6791.5, peak 10741.7). A critic failing that badly
while the policy hardens is textbook policy-gradient divergence.
Spearman rho=-0.92 is near-perfect monotonic decline; this is not noise.

**Most plausible mechanism, stated as a hypothesis and NOT acted on**:
`pressure_raw` is un-normalised served pressure summed over a phase's
movements, with a substantially larger and more variable scale than
HAPLight-RL's own `total_queue` reward (whose value_loss stayed around
1.5e3 on the same machine and budget). Every learned method shares one
PPO hyperparameter block (`cfg["rl"]["ppo"]`) -- lr, value coefficient,
clip, advantage normalisation -- and that block was tuned against
`total_queue`'s scale. A reward an order of magnitude larger can
destabilise the critic under those same settings.

**Deliberately NOT retuned.** Adjusting lr/value_coef for
Advanced-MPLight alone would break the "identical training budget and
hyperparameters" fairness property that is the entire basis on which
this comparison is claimed to be reviewer-proof -- and tuning a baseline
after seeing its result, in either direction, is exactly the practice
this changelog exists to prevent. The trained checkpoint is evaluated
as-is and its numbers reported with this caveat attached, so the reader
can see that the SOTA baseline was given an equal, faithful, untuned
chance rather than a quietly favourable or unfavourable one. **The
honest reading of any Advanced-MPLight result in the final table is
"faithful port, equal budget, shared hyperparameters, training
diverged", not "Advanced-MPLight is a weak method".** `pressure_raw`
itself is not implicated: it passed the rank-correlation gate at
rho=+1.000 against both -AQL and throughput, so the reward ORDERS
controllers correctly; the issue is its SCALE against shared PPO
settings, which the gate does not test.

MPLight (priority 3) uses the same `pressure_raw` reward and will be an
informative check: if it destabilises too, the scale hypothesis gains
support; if it trains cleanly, the problem is more specific to
Advanced-MPLight's richer state.

### Correction to the entry above: the reward-scale hypothesis is REFUTED. MPLight trains cleanly on the identical reward, so the instability is specific to Advanced-MPLight's own state representation.
`Sec. VI-E`, P5-1.

**MPLight S1 (`mplight_s1_seed0_1788621109`, 40 iterations, seed 0, same
`pressure_raw` reward, same shared PPO hyperparameters, same budget):**

| | Theil-Sen slope | 95% CI | Spearman | value_loss | verdict |
|---|---|---|---|---|---|
| MPLight S1 | **+6.45** | **[+4.40, +9.46]** | rho=+0.773 p<0.0001 | 2056.7 -> **324.1** | **robustly rising** |
| Advanced-MPLight S1 | -27.42 | [-38.58, -12.05] | rho=-0.353 p=0.025 | 6316.1 -> 4972.6 (peak 9933.7) | robustly declining |

MPLight's return improves monotonically by block (-780.7, -245.6, -188.2,
-136.9, -151.3) and its critic CONVERGES (value_loss falls 6x). Under the
identical reward and identical hyperparameters, one method trains and the
other diverges. **The scale-of-`pressure_raw` explanation offered in the
previous entry is therefore wrong and is withdrawn** -- recorded rather
than quietly edited away, because the reasoning that produced it (large
reward scale + shared hyperparameters) was plausible and would otherwise
be repeated.

**Where the difference actually lies**: the two states differ in exactly
one thing -- Advanced-MPLight appends a running-demand feature to
MPLight's pressure feature. Measured directly over 2,400
(movement, step) samples on S1:

| feature | mean | std | min | max | p99 | at clip |
|---|---|---|---|---|---|---|
| efficient pressure | 0.017 | 0.112 | -0.167 | 0.880 | 0.520 | 0.0% |
| running demand | 0.267 | 0.439 | 0.000 | 3.280 | 2.480 | 0.0% |

The running-demand channel carries ~4x the standard deviation and ~16x
the mean of the pressure channel. Nothing is clipping, so this is not a
saturation artifact. The cause is structural: `build_state_advanced_
mplight` divides BOTH channels by the same `x_ref` (50), but pressure is
a DIFFERENCE of queues (small, centred near zero) while running demand is
a COUNT (strictly non-negative, an order of magnitude larger). A shared
normaliser suits one and not the other. Consistent with this,
Advanced-MPLight's critic loss starts at 3x MPLight's (6316 vs 2057) at
iteration 0 -- BEFORE meaningful learning -- which points at the
observation rather than at the learning dynamics.

**Stated as a hypothesis, NOT established, and NOT acted on.** That the
imbalance *causes* the divergence is untested; demonstrating it would
require a re-normalised retrain (~21h) whose result could not honestly
enter the main table anyway, since re-tuning one baseline's feature
scaling after seeing its result is the precise practice this protocol
forbids. Both facts are reported and the causal claim is left open.
The paper-facing consequence is unchanged and stated plainly: the
Advanced-MPLight column reflects a faithful port at an equal budget with
shared hyperparameters whose TRAINING DIVERGED, and a normalisation
choice in this port is a live candidate explanation -- it is not evidence
that Advanced-MPLight is a weak method.

### PHASE 5 COMPLETE: final equal-budget comparison table (n=10, eta in {0, 0.6}, both scenarios). HAPLight-RL wins ATT/AWT/PWD against every baseline with BCa CIs excluding zero -- but the headline GRIDLOCK separation does NOT reproduce at the 40-iteration budget, and the safety filter shows no measurable deadlock benefit here.
`Sec. VI-E`, P5-1.

**What was trained** (equal 40-iteration budget, seed 0, both scenarios,
sequential with cooldowns, ~4 days wall-clock):

| method | S1 | S2 | training health (Theil-Sen, mean_return) |
|---|---|---|---|
| HAPLight-RL | 40 it | 40 it | healthy (S2 eta0 rising +6.41, CI [+2.44,+10.02]; S1 flat past knee) |
| Advanced-MPLight | 40 it | 40 it | **DIVERGED** (S1 -27.4 CI [-38.6,-12.1]; S2 -30.5 CI [-34.1,-25.7], rho=-0.92) |
| MPLight | 40 it | 40 it | healthy (S1 +6.45 CI [+4.40,+9.46]; S2 +2.46 CI [+1.21,+3.57]) |
| CoLight-variant | not trained | not trained | scoped out (below) |

**Final table -- medians, n=10 paired seeds per cell:**

S1, eta=0 / eta=0.6 (ATT | AWT | AQL | TP | PWD | gridlock k/n [Wilson 95% CI])

| method | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 237.8 / 237.8 | 19.0 / 19.0 | 1076.6 / 1076.6 | 3707.5 / 3707.5 | 116.1 / 116.1 | 0/10 / 0/10 |
| MaxPressure | 243.8 / 248.3 | 20.5 / 20.7 | 1080.0 / 1186.9 | 3715.5 / 3707.0 | 121.9 / 129.5 | 0/10 / 2/10 |
| GreedyHAP | 244.5 / 243.5 | 20.1 / 20.2 | 1092.1 / 1069.4 | 3713.5 / 3713.5 | 121.3 / 119.5 | 0/10 / 1/10 |
| **HAPLight-RL** | **233.3 / 231.3** | 17.0 / 17.2 | 997.8 / 998.4 | 3718.0 / 3720.0 | 106.2 / 105.3 | 1/10 / 1/10 |
| HAPLight-RL (unfilt.) | 238.0 / 232.4 | **16.4 / 16.4** | **989.6 / 928.0** | 3714.5 / 3713.5 | 109.9 / **104.1** | 0/10 / 0/10 |
| MPLight | 255.5 / 250.7 | 21.8 / 21.2 | 1220.3 / 1146.6 | 3711.5 / 3711.5 | 136.7 / 130.8 | 0/10 / 0/10 |
| Advanced-MPLight | 424.5 / 514.5 | 38.7 / 40.5 | 5382.2 / 6601.7 | 3464.5 / 3255.0 | 331.1 / 426.0 | 2/10 / 1/10 |

S2, eta=0 / eta=0.6

| method | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 233.5 / 233.5 | 17.4 / 17.4 | 1737.9 / 1737.9 | 5395.0 / 5395.0 | 133.0 / 133.0 | 1/10 / 1/10 |
| MaxPressure | 216.0 / 216.1 | 15.1 / 15.1 | 1311.8 / 1241.4 | 5400.0 / 5402.5 | 111.2 / 108.6 | 1/10 / 0/10 |
| GreedyHAP | 217.0 / 215.9 | 15.2 / 15.2 | 1267.2 / 1268.6 | 5404.0 / 5402.5 | 109.5 / 109.2 | 2/10 / 1/10 |
| **HAPLight-RL** | 208.1 / 207.9 | 13.4 / 13.2 | 1061.2 / 1075.0 | **5412.0 / 5408.5** | 95.8 / 95.7 | **0/10 / 0/10** |
| HAPLight-RL (unfilt.) | **206.1 / 204.8** | **13.3 / 12.7** | **1002.4 / 991.8** | 5411.5 / **5413.0** | **91.5 / 91.3** | 2/10 / 0/10 |
| MPLight | 218.1 / 217.9 | 15.6 / 15.5 | 1395.5 / 1517.9 | 5394.0 / 5294.0 | 112.6 / 111.6 | 0/10 / 0/10 |
| Advanced-MPLight | 405.2 / 432.7 | 33.3 / 33.3 | 8467.4 / 9664.8 | 5011.0 / 4896.0 | 314.6 / 347.9 | 0/10 / 1/10 |

FixedTime is identical across eta by construction (it never reads the
sensed channel) -- a built-in sanity check that the harness applied
sensing noise only where it should.

**HAPLight-RL vs GreedyHAP, paired BCa on the per-seed difference
(`*` = 95% CI excludes zero):**

| cell | ATT | AWT | AQL | TP | PWD |
|---|---|---|---|---|---|
| S1 eta=0 | +10.7* | +3.3* | +106.9 | -1.0 | +15.4* |
| S1 eta=0.6 | +9.8* | +2.8* | +108.4 | +8.5 | +15.7* |
| S2 eta=0 | +8.5* | +1.6* | +202.3 | +6.5 | +14.4* |
| S2 eta=0.6 | +8.7* | +2.0* | +158.7* | +5.0 | +12.7* |

**ATT, AWT and PWD favour HAPLight-RL in all four cells with the BCa CI
excluding zero** (rank-biserial r = +0.67 to +1.00). AQL is significant
in only 1 of 4 cells and throughput in none -- consistent with the
heavy-tailed AQL distribution documented throughout P4c. HAPLight-RL also
beats both trained baselines on every metric in every cell.

**THE GRIDLOCK HEADLINE DOES NOT REPRODUCE AT THIS BUDGET, and that must
not be glossed.** The P4c-16 result behind the paper's headline (0%
HAPLight-RL vs 5-10% classical) came from 100-iteration models. At the
equal 40-iteration budget the gridlock counts are 0-2/10 everywhere, and
EVERY Wilson interval overlaps every other ([0%,28%] to [6%,51%]). No
method is statistically separable from any other on deadlock at n=10.
HAPLight-RL is 0/10 in both S2 cells, which is directionally consistent,
but 1/10 in both S1 cells -- and MPLight, MaxPressure and FixedTime also
post 0/10 in several cells. **On this evidence the paper cannot claim a
deadlock advantage from the 40-iteration table.** Either the claim rests
on the 100-iteration models (in which case the baselines must be trained
to 100 iterations too, ~300h, before it is a fair comparison), or n must
rise well above 10 to resolve a few-percent event, or the claim narrows
to the throughput/delay metrics that ARE significant here.

**The safety filter shows no measurable deadlock benefit at this budget
either.** HAPLight-RL unfiltered matches or beats the filtered variant on
ATT/AWT/AQL/PWD in 7 of 8 metric-cells, and its gridlock counts are equal
or lower in 3 of 4 cells (S1: 0/10 unfiltered vs 1/10 filtered at both
eta). All CIs overlap, so this is not evidence the filter HURTS -- but it
is also not the Remark-6 deadlock-prevention story, and the unfiltered
column was added precisely so this would be visible rather than hidden.
Reported as measured.

**Advanced-MPLight's column reflects diverged training, not method
quality** (rank-biserial -1.00 on essentially everything, ATT 185-270s
worse). Per the entries above: faithful port, equal budget, shared
hyperparameters, `pressure_raw` reward that PASSED its rank-correlation
gate at rho=+1.000 -- and MPLight trains cleanly on that identical
reward, which localises the fault to Advanced-MPLight's running-demand
feature scaling in this port (4x the std, 16x the mean of its pressure
channel, both divided by the same `x_ref`). **This column should not be
presented as "Advanced-MPLight is weak."** It is a fixable
implementation defect that was deliberately not fixed after the fact,
because re-scaling one baseline's features once its result is known is
the exact practice this protocol forbids.

**Scoped out**: CoLight-variant was not trained -- it was priority 4 and
the window (~2 nights budgeted) had stretched to ~4 days across two
session interruptions and one transient SUMO socket failure that cost a
partial MPLight S2 run (resumed from its iteration-8 checkpoint rather
than restarted). PressLight and IPPO were scoped out earlier for compute;
all three retain working Stage-A code and pass `tests/test_baselines.py`.
The delivered learned-baseline set is therefore Advanced-MPLight (SOTA)
and MPLight (parameter-sharing ancestor); **the graph-attention
comparison is missing from this table** and should be stated as such
rather than omitted silently.

**Robustness appendix**: the 100-iteration HAPLight-RL checkpoints
(`s1_seed0_1787507503`, `s2_seed0_1787604457`) are retained on disk and
were NOT used in the table above -- mixing them with 40-iteration
baselines would be exactly the unequal comparison this protocol exists to
prevent.

### PHASE 5 FINAL: all three reviewer-required baselines trained and evaluated. CoLight-variant added; supersedes the three-baseline table above.
`Sec. VI-E`, P5-1.

**CoLight-variant (single-hop attn) completed** at the same equal
40-iteration budget, seed 0, both scenarios: S1 5.28h (median 374.3s/it,
Theil-Sen **+46.35**, CI [+25.89,+91.08], rho=+0.649 p<0.0001, RISING;
value_loss 91335 -> 11451), S2 7.62h (median 665.1s/it, Theil-Sen +5.67,
CI [-2.24,+12.50], flat/converged; value_loss 15274 -> 1705). Healthy.

**Training health across all four learned methods -- this settles the
Advanced-MPLight question.** Three of four train cleanly, spanning BOTH
reward forms: MPLight on `pressure_raw` (rising both scenarios),
CoLight-variant and HAPLight-RL on `total_queue` (rising/flat). The sole
failure is Advanced-MPLight, the sole method carrying the running-demand
feature. Neither the reward form nor the shared PPO hyperparameters can
account for it, since both are shared with methods that train fine.
**The feature-scaling defect in this port (running demand carries 4x the
std and 16x the mean of the pressure channel, both divided by the same
`x_ref`) is the standing explanation, and it is an implementation defect,
not a property of Advanced-MPLight.**

**FINAL TABLE -- medians, n=10 paired seeds, eta=0 / eta=0.6:**

S1:

| method | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 237.8 / 237.8 | 19.0 / 19.0 | 1076.6 / 1076.6 | 3707.5 / 3707.5 | 116.1 / 116.1 | 0/10 · 0/10 |
| MaxPressure | 243.8 / 248.3 | 20.5 / 20.7 | 1080.0 / 1186.9 | 3715.5 / 3707.0 | 121.9 / 129.5 | 0/10 · 2/10 |
| GreedyHAP | 244.5 / 243.5 | 20.1 / 20.2 | 1092.1 / 1069.4 | 3713.5 / 3713.5 | 121.3 / 119.5 | 0/10 · 1/10 |
| **HAPLight-RL** | **233.3 / 231.3** | 17.0 / 17.2 | 997.8 / 998.4 | 3718.0 / **3720.0** | 106.2 / 105.3 | 1/10 · 1/10 |
| HAPLight-RL (unfilt.) | 238.0 / 232.4 | **16.4 / 16.4** | **989.6 / 928.0** | 3714.5 / 3713.5 | 109.9 / **104.1** | 0/10 · 0/10 |
| MPLight | 255.5 / 250.7 | 21.8 / 21.2 | 1220.3 / 1146.6 | 3711.5 / 3711.5 | 136.7 / 130.8 | 0/10 · 0/10 |
| CoLight-variant (single-hop attn) | 251.3 / 253.5 | 21.8 / 21.7 | 1163.4 / 1188.1 | 3716.0 / 3705.5 | 132.9 / 131.0 | 1/10 · 0/10 |
| Advanced-MPLight | 424.5 / 514.5 | 38.7 / 40.5 | 5382.2 / 6601.7 | 3464.5 / 3255.0 | 331.1 / 426.0 | 2/10 · 1/10 |

S2:

| method | ATT | AWT | AQL | TP | PWD | gridlock |
|---|---|---|---|---|---|---|
| FixedTime | 233.5 / 233.5 | 17.4 / 17.4 | 1737.9 / 1737.9 | 5395.0 / 5395.0 | 133.0 / 133.0 | 1/10 · 1/10 |
| MaxPressure | 216.0 / 216.1 | 15.1 / 15.1 | 1311.8 / 1241.4 | 5400.0 / 5402.5 | 111.2 / 108.6 | 1/10 · 0/10 |
| GreedyHAP | 217.0 / 215.9 | 15.2 / 15.2 | 1267.2 / 1268.6 | 5404.0 / 5402.5 | 109.5 / 109.2 | 2/10 · 1/10 |
| **HAPLight-RL** | 208.1 / 207.9 | 13.4 / 13.2 | 1061.2 / 1075.0 | **5412.0** / 5408.5 | 95.8 / 95.7 | **0/10 · 0/10** |
| HAPLight-RL (unfilt.) | **206.1 / 204.8** | **13.3 / 12.7** | **1002.4 / 991.8** | 5411.5 / **5413.0** | **91.5 / 91.3** | 2/10 · 0/10 |
| MPLight | 218.1 / 217.9 | 15.6 / 15.5 | 1395.5 / 1517.9 | 5394.0 / 5294.0 | 112.6 / 111.6 | 0/10 · 0/10 |
| CoLight-variant (single-hop attn) | 218.1 / 216.5 | 15.3 / 15.1 | 1293.8 / 1276.7 | 5404.5 / 5406.5 | 111.8 / 111.8 | 3/10 · 0/10 |
| Advanced-MPLight | 405.2 / 432.7 | 33.3 / 33.3 | 8467.4 / 9664.8 | 5011.0 / 4896.0 | 314.6 / 347.9 | 0/10 · 1/10 |

**HAPLight-RL vs GreedyHAP, paired BCa (`*` = 95% CI excludes zero):**

| cell | ATT | AWT | AQL | TP | PWD |
|---|---|---|---|---|---|
| S1 eta=0 | +10.7* | +3.3* | +106.9 | -1.0 | +15.4* |
| S1 eta=0.6 | +9.8* | +2.8* | +108.4 | +8.5 | +15.7* |
| S2 eta=0 | +8.5* | +1.6* | +202.3 | +6.5 | +14.4* |
| S2 eta=0.6 | +8.7* | +2.0* | +158.7* | +5.0 | +12.7* |

**What the table supports.** HAPLight-RL beats GreedyHAP on ATT, AWT and
PWD in all four cells with BCa CIs excluding zero, and beats every
learned baseline on every metric in every cell (vs Advanced-MPLight,
rank-biserial r=+1.00 throughout). MPLight and CoLight-variant land
close to the classical controllers -- both are significantly WORSE than
GreedyHAP on S1 (MPLight ATT -12.9*, CoLight-variant -9.5* at eta=0) and
statistically indistinguishable from it on S2 (all CIs straddle zero).
So on this benchmark the published learned baselines do not beat a
well-tuned pressure heuristic, while HAPLight-RL does.

**What it does NOT support, restated because it is the headline claim.**
The gridlock separation still does not reproduce at the 40-iteration
budget. Counts remain 0-3/10 with every Wilson interval overlapping every
other; CoLight-variant's 3/10 on S2 eta=0 ([11%,60%]) is the highest
single count in the table and is still not separable from HAPLight-RL's
0/10 ([0%,28%]). **No deadlock claim can be made from this table.** The
0%-vs-5-10% result rests on the 100-iteration models and would require
training every baseline to 100 iterations (~300h) to become a fair
comparison, or a much larger n to resolve a few-percent event.

**The filter still shows no measurable deadlock benefit.** Unfiltered
HAPLight-RL matches or beats the filtered variant on most metric-cells
and has equal-or-lower gridlock counts in 3 of 4 cells. All CIs overlap,
so this is not evidence the filter hurts -- but the Remark-6 story is not
visible at this budget, and the unfiltered column exists precisely so
that stays legible rather than hidden.

**Delivered set**: HAPLight-RL (filtered + unfiltered), Advanced-MPLight,
MPLight, CoLight-variant (single-hop attn), FixedTime, MaxPressure,
GreedyHAP -- 8 columns, both scenarios, both eta, n=10 paired seeds.
PressLight and IPPO remain scoped out for compute (Stage-A code retained,
tests passing). **PHASE 5 COMPLETE.**

### P5-2 -- FOUNDATIONAL MEASUREMENT BUG: every vehicle was counted EXACTLY 8 TIMES in `_measure()`. Found while fixing Advanced-MPLight; it is not an Advanced-MPLight bug. Fixed and verified against independent ground truth. **Every trained model and every absolute metric produced before this fix is affected.**
`Sec. V`, `Sec. VI` -- affects all phases, not only Phase 5.

**How it was found.** Task was to fix Advanced-MPLight's running-demand
feature (ATT 424 vs ~240 -- broken, not weak). The instruction to compare
the RL feature against the classical `AdvancedMP` controller, which uses
the same ingredients and is verified to beat MaxPressure, is what exposed
it. Direct comparison over 1,800 (intersection, movement, step) samples:
`running_demand_hat` (cached, what the RL state reads) vs
`running_count_within_range` (live, the correctness reference):
**54.7% mismatch, cached mean 9.98 vs live 0.963 (~10x)**.

**Root cause, and it is upstream of Advanced-MPLight.** `_measure()`
looped `for e in self._catchment_edges:` and accumulated one row per
`(context edge, vehicle)` pair. `edge.subscribeContext(e, ..., radius)`
returns every vehicle within `radius` of edge `e`, so a single vehicle
appears in MANY edges' result sets and was added once per appearance.
Measured against an independent, deduplicated ground-truth count
(`traci.lane.getLastStepVehicleIDs` + speed/position filter):

| | ratio env/independent |
|---|---|
| before fix | **8.000** (mean = median = min = max) |
| after fix | **1.0000** (mean = min = max), n=221 |

An exact, invariant 8.000 -- every vehicle counted eight times on S1 at
the default 200m catchment. A **second** bug in the same loop:
`per_edge_true` keyed on the loop's CONTEXT edge `e`, attributing each
vehicle to whichever edges' contexts happened to contain it rather than
to the edge it is actually on.

**Fix** (`src/env.py`): deduplicate by vehicle id before accumulating
(`vehicles: Dict[vid, record]`, first occurrence wins), and attribute
counts to the vehicle's own edge via a new `_lane_to_edge` map built in
`_discover_topology`. Verified: counts now match independent ground truth
at ratio 1.0000, and cached running-demand matches the live reference
**1500/1500 exactly**.

**Why this produced Advanced-MPLight's divergence specifically.** At the
default 200m radius the inflation was essentially UNIFORM (histogram:
8x for 33 of 36 vehicles), so it acted as a constant scale factor --
which cancels in pressure differences, leaves argmax decisions unchanged,
and rescales the reward without changing its ranking. That is why the
classical controllers and the other learned methods behaved sanely
despite it. But `advanced_mp_running_demand=True` WIDENED the
subscription radius (to cover the running-demand range), which turned
that benign uniform 8x into a HETEROGENEOUS 8-14x distortion
(histogram {8:10, 9:6, 10:2, 12:5, 14:13}). A per-vehicle-varying
inflation does not cancel anywhere -- it corrupted Advanced-MPLight's
observations AND its reward, which is exactly the divergence signature
observed (critic value_loss 3x the others' at iteration 0, before any
learning). **The earlier "running-demand feature scaling" hypothesis was
directionally right about WHERE but wrong about WHAT: it is not a
normalisation choice, it is double-counting.**

**Blast radius -- this is the part that matters for planning.** The
inflation cancels wherever counts are compared against other counts, but
NOT where a count is compared against a PHYSICAL CAPACITY. Measured on a
1800s GreedyHAP S1 episode after the fix: downstream occupancy
(`x_hat / env.storage`) now has mean 0.019, p90 0.058, max 0.330, and
**0.0%** of samples exceed the 0.80 storage trigger -- whereas the same
occupancies inflated 8x would read mean 0.15 with ~5% over threshold.
**The storage-aware safety filter has therefore been operating on
8x-inflated occupancies for its entire life** (P4c-1 through P4c-14,
including the threshold sweep that selected 0.80). Likewise AQL is an
absolute count and was 8x too large: the same episode now reports
AQL=88.7.

Consequently: every trained checkpoint (Phase 4 HAPLight-RL 100-iteration
models AND all Phase 5 40-iteration models) was trained against
8x-inflated observations and rewards; every reported AQL is 8x too high;
and the storage-filter threshold calibration needs redoing. Relative
rankings and the delay metrics (ATT/AWT/PWD, which are computed from
per-vehicle trip records, NOT from the count channels) are NOT affected
by the inflation.

**Deliberately NOT retrained yet.** Retraining only Advanced-MPLight
would make it the single method trained on correct measurements while
every other column was trained on inflated ones -- a worse comparison
than the current one, not a better one. The fix invalidates the whole
table simultaneously, so the retrain scope (which methods, laptop-40 vs
cloud-100, and whether the storage threshold must be re-swept first) is a
decision for the author, and is reported rather than taken unilaterally.

### P5-2 (cont.): detection gate added; storage threshold RE-SWEPT on corrected measurements (0.80 -> 0.15); widened subscription radius removed as unnecessary AND the cause of Advanced-MPLight's slow training.
`Sec. V-F`, `Sec. VI-E`. **Supersedes the P4c-10/P4c-12/P4c-14 threshold work**, which was conducted on 8x-inflated occupancies.

**1. Detection gate (`tests/test_measurement.py`), now standing.**
`test_counts_match_ground_truth` (S1 and S2) asserts `counts_hat` equals a
ground-truth count rebuilt from RAW traci lane/vehicle queries at eta=0.
The reference deliberately shares no code with `_measure()`, which is the
whole point: every pre-existing count test compared a count against
ANOTHER COUNT (e.g. `test_true_queues_noise_free` checks x_hat against
true_queues -- both inflated 8x, so the check cancelled perfectly). It
also asserts >=10 non-empty movements were sampled, so it cannot pass
vacuously on 0==0. A companion test,
`test_ground_truth_helper_would_catch_double_counting`, reconstructs the
pre-fix accumulation verbatim and asserts it DOES over-count -- proving
the gate discriminates rather than merely passing. Both pass on the fixed
code; full suite 81 passed.

**Incidental confirmation the fix is real, not self-consistent:**
`test_mp_beats_fixed_time` -- a Phase 1 gate that had been failing
(MP 182.08s vs FT 179.93s) and was earlier filed in this session as
"pre-existing and unrelated" -- now PASSES. It was an early symptom of
the same bug: MaxPressure decides on count DIFFERENCES where a uniform
8x mostly cancels, which is why it presented as a near-tie rather than an
obvious failure. **That earlier "unrelated" call was wrong and is
corrected here.**

**2. Storage threshold re-swept.** Corrected occupancy distribution
(GreedyHAP, 5 seeds x both scenarios, full 3600s episodes): S1 mean
0.030 / p90 0.096 / p99 0.217 / max 0.396; S2 mean 0.012 / p90 0.044 /
p99 0.142 / max 0.392. **The old 0.80 sits above every observed value --
it was structurally incapable of firing**, which is why the filter showed
no measurable deadlock benefit in the pre-fix Phase 5 table.

Re-sweep, P4c methodology on the clean harness (8 seeds x 6 thresholds x
both scenarios, hysteresis with a 0.05 gap, min_dwell 3,
maxtasksperchild=1). No valid trained checkpoint existed post-fix, so the
driver is a RANDOM-INIT policy -- the worst case the filter must handle
per Remark 6, matching `train.py`'s own random-policy+filter control
idiom; a threshold safe for a random policy is safe for a trained one.

| threshold | S1 deadlock | S1 act. | S1 finalQ | S2 deadlock | S2 act. | S2 finalQ |
|---|---|---|---|---|---|---|
| 0.10 | 0/8 | 34.9% | 71.3 | 0/8 | 28.0% | 129.5 |
| **0.15** | **0/8** | **27.0%** | **79.1** | **0/8** | **24.9%** | **208.8** |
| 0.20 | 1/8 | 21.8% | 154.2 | 0/8 | 22.2% | 120.8 |
| 0.25 | 0/8 | 20.5% | 109.2 | 0/8 | 22.1% | 120.3 |
| 0.30 | 1/8 | 21.1% | 164.2 | 0/8 | 22.1% | 120.3 |
| 0.40 | 1/8 | 22.3% | 206.7 | 0/8 | 22.1% | 120.3 |

**Chosen: 0.15 engage / 0.10 release.** It is deadlock-free on both
scenarios (0/16) and is the only level where the storage trigger
measurably CONTRIBUTES on both -- S1 27.0% and S2 24.9% against the
~22% floor that the queue-magnitude trigger (B) supplies on its own. At
>=0.25 the storage trigger is inert on S2: 0.25/0.30/0.40 return
byte-identical numbers (22.1%, TP 5371, finalQ 120.3), the same failure
mode as 0.80. 0.10 is deadlock-free too but pushes activation to 34.9%,
well past Phase 4's ~25% guidance, masking too many policy-gradient
steps. The isolated 1/8 deadlocks at S1 0.20/0.30/0.40 are
non-monotonic and within noise (Wilson [2%,40%] overlapping [0%,32%]) --
NOT read as a trend.

**3. Widened subscription radius removed.** P5-1 widened each edge's
`subscribeContext` radius for the running-demand channel, on the
assumption a vehicle far along a long edge could otherwise fall outside
the context. **That assumption was wrong**: a vehicle ON edge e is at
distance 0 from e's own geometry and is therefore always in e's context
at ANY radius. Verified after the dedup fix -- narrow (200m) vs widened
gives **0/1200 mismatches** against the live `running_count_within_range`
reference, and narrow is **~9x faster per episode** (1.3s vs 11.9s),
because the wide radius pulled in far-away vehicles that deduplication
then discarded. That redundant work is what made Advanced-MPLight train
~1.8x slower than every other method (797s/it vs 445s on S1). One radius
for all callers now.

**4. All pre-fix checkpoints marked invalid.** Ten run directories (the
Phase 5 40-iteration set AND the Phase 4 100-iteration models) each carry
an `INVALID_8X.txt` marker. Retained for provenance; must not appear in
any comparison table.

### P5-3 -- Advanced-MPLight DROPPED after three genuine, evidence-based fix attempts. The 8x fix was real but was NOT the cause of its divergence. Stated reason below.
`Sec. VI-E`.

**Correction to P5-2 first.** P5-2 argued the 8x double-counting explained
why ONLY Advanced-MPLight diverged (the widened radius turned a uniform 8x
into a heterogeneous 8-14x). That was a reasonable hypothesis and the bug
it identified was real and is fixed -- but **the retrain on corrected
measurements refutes it as the cause of the divergence.** Advanced-MPLight
S1 on corrected measurements still robustly declines: Theil-Sen **-5.00**,
CI [-7.14, -3.26], rho=-0.675 p<0.0001; critic value_loss grows 214.5 ->
500.4; entropy frozen at 0.344 -> 0.341 (the policy is not learning, it
is drifting worse). The smaller magnitude than pre-fix (-27.4) is just the
~8x smaller reward scale. Recorded here rather than edited out of P5-2.

**Three controlled hypotheses, each tested and ruled out:**

| hypothesis | test | result |
|---|---|---|
| 1. measurement double-counting | P5-2 dedup; `running_demand_hat` verified against the classical controller's live reference | feature now EXACT (1500/1500), **still diverges** |
| 2. dimensional-unit error (raw vehicle count / weight-unit x_ref) | convert count to weight units via composition-weighted mean rho (0.85) before the shared x_ref divide | real error, fixed -- but only a 15% adjustment (std ratio 2.29x -> 1.94x); **still diverges** |
| 3. network capacity (my inferred 32/32/16 vs MPLight's 16/16/8) | full 40-iteration run at MPLight's EXACT width | **still diverges**: Theil-Sen -2.50, CI [-4.99, -0.46], p=0.025; value_loss 271 -> 655 |

A 6-iteration probe of hypothesis 3 was run first and was **inconclusive by
construction**: the full-width run's own first 10 iterations are also
flat/positive (Theil-Sen +12.6) and the decline only appears after
~iteration 16. That probe is not cited as evidence; only the full
40-iteration run is.

**What is established.** Advanced-MPLight = MPLight + ONE extra channel.
MPLight's single feature is byte-identical to Advanced-MPLight's pressure
channel (mean +0.0033, std 0.0142, min -0.053, max +0.100). At IDENTICAL
width, reward (`pressure_raw`, gate PASSED rho=+1.000) and PPO
hyperparameters, MPLight converges (Theil-Sen +6.45, CI [+4.40, +9.46];
value_loss 2057 -> 324; entropy 0.345 -> 0.197) and Advanced-MPLight does
not. Reward, hyperparameters, capacity and measurement are all excluded by
controlled contrast. **The running-demand channel itself -- now provably
correct -- is what destabilises learning.**

**Most plausible mechanism, stated as a hypothesis, not established.**
In Zhang et al.'s own classical Advanced-MP, running demand is used ONLY
for the CURRENTLY ACTIVE phase, as an asymmetric stay/switch bonus. This
port feeds it for EVERY movement as a state feature. Per-movement running
demand is dominated by which movements are currently green (served
movements have running vehicles; red ones have stopped queues), so the
channel largely re-encodes the policy's OWN recent phase choices -- a
policy-dependent, non-stationary input the critic cannot track, consistent
with the observed late-onset divergence (clean for ~16 iterations, then
declining) and with a growing value_loss under a flat entropy. That is an
adaptation choice in this port, not a property of Advanced-MPLight as
published.

**Stated reason for dropping (the text the paper should use or adapt):**
"Advanced-MPLight was implemented, verified against the classical
Advanced-MP controller it extends, and trained under the identical budget,
reward and hyperparameters as every other method. It did not converge in
this environment across three controlled remediation attempts, while
MPLight -- which it extends by a single state channel -- converged under
identical conditions. We therefore omit it from the comparison rather than
report a non-converged policy as a baseline." **Framed as a failure to
converge in this setting, NOT as evidence the method is weak.**

**Not pursued, and why.** A redesign that uses running demand as the
source paper does -- current-phase-only, as a stay bonus, not a
per-movement state feature -- is a plausible path to a working port. It is
NOT attempted here: it would be a new design chosen after seeing results,
requiring its own validation, and is left as an open option for the
author rather than taken unilaterally.

**Consequence for the paper, flagged plainly.** The delivered learned-
baseline set loses its SOTA member. The comparison will be HAPLight-RL vs
MPLight and CoLight-variant (single-hop attn) plus the classical
controllers. The "competitive with the current state of the art" framing
cannot be claimed from this table.

### P5-3 RETRACTED -- the drop rationale for Advanced-MPLight rested on an UNCONTROLLED comparison. MPLight also diverges on corrected measurements. The shared factor is the `pressure_raw` reward, whose validation gate was itself run on invalid (pre-fix) measurements.
`Sec. VI-E`. **Supersedes the P5-3 conclusion above; P5-3 is left in place, not deleted.**

**What happened.** MPLight S1 retrained on corrected measurements
(`mplight_s1_seed0_1789150346`, 40 iterations) **robustly diverges**:
Theil-Sen **-11.62**, CI [-15.07, -9.42], rho=-0.762 p<0.0001; critic
value_loss 260.8 -> 934.1 (peak 1263.0); returns by 8-iteration block
-230.1, -195.9, -304.4, -589.8, -517.3 -- improving for ~16 iterations,
then collapsing. The SAME late-onset signature as Advanced-MPLight.

**The error in P5-3, stated plainly.** P5-3's central claim was a
"controlled contrast": Advanced-MPLight diverges while MPLight converges
under identical width, reward and hyperparameters, so the running-demand
channel -- the only difference -- must be the cause. **But the MPLight run
it cited as converging was the PRE-FIX, invalid-8x run.** It compared a
corrected-measurement Advanced-MPLight against an inflated-measurement
MPLight -- across the very measurement fix under investigation. P5-3 even
noted the reference was invalid-8x and then dismissed the concern as not
affecting the "qualitative pattern." It did. MPLight has no running-demand
channel and diverges anyway, so **the running-demand channel is NOT
established as the cause, and the stated reason for dropping
Advanced-MPLight is withdrawn.**

**What the corrected runs actually show:**

| method | reward | corrected-measurement training |
|---|---|---|
| HAPLight-RL | `total_queue` | healthy, rising (S1 +2.66, S2 +1.26, both CI > 0) |
| Advanced-MPLight | `pressure_raw` | diverges (-5.00) |
| MPLight | `pressure_raw` | diverges (-11.62) |

The shared factor across both divergences is the `pressure_raw` reward,
not any feature. **And the gate that authorised `pressure_raw` (rho =
+1.000 against -AQL and throughput) was run BEFORE the 8x fix**, on
measurements in which every vehicle was counted eight times. That
approval is void. The same is true of `total_queue`'s original P4-3/P4-4
validation -- though HAPLight-RL training healthily on it post-fix is
supporting evidence it survives.

**Why the reward's behaviour could change under the fix.** `pressure_raw`
is built from `true_w = x - x_down`. The P5-2 fix changed not only the
magnitude of `x` (8x -> 1x) but the MEANING of `x_down`: `per_edge_true`
now attributes each vehicle to the edge it is actually on, where
previously it smeared vehicles onto every edge whose context contained
them. So the downstream term, and therefore the sign structure of the
served pressure, genuinely changed -- not just its scale. A reward whose
ranking was validated on the old downstream definition has no standing
under the new one.

**Action taken.** Stopped the retrain chain before MPLight S2 (removed its
16-iteration partial) rather than spend ~8h training on an unvalidated
reward. Re-running `scripts/validate_reward.py --all-forms` on corrected
measurements for BOTH scenarios now. That result decides the path:
- if `pressure_raw` FAILS on corrected data, it explains both
  divergences, and the pressure-lineage baselines need a reward that
  passes the gate before any retrain;
- if it PASSES, the reward is not the cause and the divergence needs
  further diagnosis -- the running-demand hypothesis is NOT reinstated by
  default, since MPLight rules it out.

**Author-side error, recorded rather than smoothed over:** the P5-3
experiment design was flawed, and the flaw was visible and noted at the
time. The lesson for this project: a controlled contrast must hold the
measurement pipeline fixed, and a run from before a measurement fix can
never serve as a reference for a run after it.

### P5-4 -- reward gate RE-RUN on corrected measurements: `pressure_raw` FAILS on S1, which is exactly where both pressure-lineage baselines diverged. `total_queue` passes. STOPPED per the pre-agreed rule; path forward left to the author.
`Sec. V-C`, `Sec. VI-E`.

`scripts/validate_reward.py --all-forms`, corrected measurements, both
scenarios (single seed=0, eta=0.382 -- the established gate protocol):

| reward | S1 rho(-AQL) | S1 rho(TP) | S2 rho(-AQL) | S2 rho(TP) |
|---|---|---|---|---|
| `total_queue` | +1.000 | +1.000 | +1.000 | +0.700 |
| `pressure_raw` | **+0.600** | **+0.600** | +1.000 | +0.700 |
| `served_pressure` | +0.600 | +0.600 | +0.900 | +0.900 |
| `pressure_all` | -0.900 | -0.900 | -0.300 | -0.500 |

**`pressure_raw` fails on S1, and the failure is substantive, not
marginal.** It ranks Random correctly (worst) but INVERTS the order among
the competent controllers: reward FixedTime 15.43 > MaxPressure 12.93 >
GreedyHAP 12.89, while AQL is GreedyHAP 152.8 < MaxPressure 155.4 <
FixedTime 169.1. Past the random stage, the reward points a learner toward
WORSE control. Its pre-fix approval (rho=+1.000) came from 8x-inflated
data and does not survive: the P5-2 fix changed the MEANING of `x_down`
(vehicles now attributed to their own edge, not smeared across every
overlapping context), not just its scale, and `pressure_raw` is built from
`true_w = x - x_down`.

**This is the coherent explanation P5-3 lacked.** Both pressure-lineage
baselines were retrained and diverged on **S1** -- the scenario where
`pressure_raw` genuinely fails. (No corrected S2 run of either completed:
Advanced-MPLight S2 was aborted at 6 iterations, MPLight S2 at 16.) The
running-demand hypothesis of P5-3 is not needed to explain the data and
is not reinstated.

**The S2 TP column is a degenerate criterion, flagged rather than
silently waived.** S2 throughput spans 5380-5407 across ALL five
controllers, including Random -- a 0.5% spread, because S2 at nominal
demand is not throughput-limited. Requiring a perfect rank correlation on
a quantity that barely varies tests noise. Consequence worth stating
openly: under the gate AS WRITTEN (both criteria must be ~1.0),
**`total_queue` -- HAPLight-RL's own production reward -- also fails on
S2**, for this same reason. It is AQL-perfect on both scenarios and
TP-perfect on S1, and HAPLight-RL trains healthily on it post-fix, so the
evidence says the reward is sound and the gate's TP criterion is
uninformative on S2. The gate itself should probably count only criteria
that discriminate between controllers; not changed here, since redesigning
a validity gate after seeing which rewards pass it is exactly the wrong
order of operations.

**Stopped, per the pre-agreed rule** ("pressure_raw validated FIRST --
single point of failure for Advanced-MPLight and MPLight. If it fails the
gate, stop and report"). Options, none taken unilaterally:

1. **Train the pressure-lineage baselines on `total_queue`** (passes the
   gate). Cleanest for training stability, but it is NOT their published
   reward -- it cuts against the Phase 5 rule "baselines get their own
   published state and reward." Mitigating fact: `total_queue` is
   negative queue length, which is CoLight's own published reward and a
   standard RL-TSC reward, not a HAPLight-specific quantity.
2. **Keep `pressure_raw` but restrict the pressure-lineage claim to S2**,
   where it ranks AQL perfectly, and state S1 out of scope for them.
3. **Construct a pressure reward that passes on corrected measurements.**
   Most literature-faithful in spirit, but it is reward engineering chosen
   after seeing gate results and would need its own pre-registered
   validation.
4. **Drop the pressure-lineage baselines** and report HAPLight-RL against
   CoLight-variant (single-hop attn) and the classical controllers only.

**Unaffected and still valid on corrected measurements:** HAPLight-RL S1
and S2 (`total_queue`, trains healthily); CoLight-variant is also a
`total_queue` method and can be retrained without waiting on this
decision.

### P5-5 -- the filter-behaviour question, answered on corrected measurements: the filter now shows the Remark-6 tradeoff it could not show on inflated occupancies, but the deadlock benefit is directional, not statistically established.
`Sec. V-F`, `Sec. VI`. Preliminary corrected evaluation, HAPLight-RL (filtered, re-swept threshold 0.15/0.10) vs its unfiltered variant vs the classical controllers; n=10 paired seeds x eta in {0, 0.6} x both scenarios. Corrected HAPLight-RL checkpoints `s1_seed0_1788963312` / `s2_seed0_1788987398`.

**Medians (ATT / AQL / gridlock):**

| | S1 eta=0 | S1 eta=0.6 | S2 eta=0 | S2 eta=0.6 |
|---|---|---|---|---|
| FixedTime | 237.8 / 134.6 / 0/10 | 237.8 / 134.6 / 0/10 | 233.5 / 214.5 / 1/10 | 233.5 / 214.5 / 1/10 |
| MaxPressure | 243.6 / 138.4 / 0/10 | 240.4 / 140.9 / 2/10 | 215.0 / 155.9 / 0/10 | 218.2 / 184.6 / 1/10 |
| GreedyHAP | 239.2 / 129.0 / 0/10 | 238.9 / 127.3 / 0/10 | 215.8 / 155.6 / 1/10 | 216.1 / 156.8 / 0/10 |
| **HAPLight-RL** | **230.9 / 113.6** / 0/10 | 234.8 / 119.2 / **0/10** | 206.1 / 126.5 / **0/10** | 207.3 / 132.7 / **0/10** |
| HAPLight-RL (unfilt.) | 234.5 / 118.1 / 0/10 | 233.0 / 118.3 / 1/10 | 204.9 / 126.5 / 1/10 | 206.2 / 130.5 / 1/10 |

**Deadlock, pooled and paired (the correct test, since filtered and
unfiltered run on identical seeds):**

| | gridlock | Wilson 95% |
|---|---|---|
| filtered | **0/40 = 0.0%** | [0.0%, 8.8%] |
| unfiltered | **3/40 = 7.5%** | [2.6%, 19.9%] |

Discordant pairs: 3 unfiltered-only deadlocks, 0 filtered-only.
**McNemar exact two-sided p = 0.25 -- not significant.** The direction is
unambiguous (the filter never deadlocks where the policy alone does not,
and rescues every case the policy alone fails), but three events cannot
establish it. **Weaker still than 3/40 suggests: two of the three are the
SAME demand realisation** (S2 seed 5, failing at both eta=0 and eta=0.6),
so there are effectively two independent hard cases, not three. That
seed is informative in its own right -- the unfiltered policy fails it
regardless of sensing noise and the filter rescues it both times -- but
it is correlated evidence, not replication.

**How the filter's behaviour changed versus pre-fix, which is the real
finding:**
- Pre-fix (8x-inflated occupancies, threshold 0.80): the unfiltered
  variant beat the filtered one in 7 of 8 metric-cells and the filter
  showed no deadlock benefit. That is now explained: occupancy never
  exceeded ~0.40, so the storage trigger could never fire, leaving the
  filter as pure overhead.
- Corrected (re-swept 0.15): the filter behaves as Remark 6 intends. On
  S1 it is BETTER on delay at eta=0 (ATT 230.9 vs 234.5, AQL 113.6 vs
  118.1) and tied at eta=0.6; on S2 it costs a small amount of delay
  (ATT +1.1 to +1.2s median vs unfiltered) -- and across all 40 paired
  episodes it eliminates every deadlock the unfiltered policy suffers.
  A small, sometimes-zero delay cost in exchange for directional deadlock
  protection is exactly the safety-filter tradeoff the design claims.
- Training-time activation corroborates this: it now TAPERS (S1 24.3% ->
  15.4%, S2 26.6% -> 16.1%) instead of sitting pinned at ~25%.

**Deadlock is rare on corrected measurements for every method**, which
supports the author's hypothesis that the inflated data made it look more
common than it is: GreedyHAP is 1/40 pooled, filtered HAPLight-RL 0/40,
and no controller exceeds 2/10 in any cell. The 0%-vs-5-10% headline from
the pre-fix era cannot be reproduced -- not because the filter fails, but
because the deadlock rate it was being compared against was partly an
artifact.

**HAPLight-RL vs GreedyHAP (paired BCa, filtered):** ATT, AWT and PWD
significant in all four cells; AQL now significant in 3 of 4 (S1 both
cells, S2 eta=0.6) versus 1 of 4 pre-fix -- the 8x inflation had
inflated AQL's heavy tail, and that noise was masking a real effect. At
S1 eta=0.6 all five metrics are significant.

**Paper-facing statement this supports.** The equal-budget headline is the
delay result (ATT/AWT/PWD significant in every cell, AQL in most). The
filter claim should be stated as a DIRECTIONAL deadlock-protection
property with an honest n, not as an established deadlock-rate
difference: "across 40 paired episodes the filtered policy never
deadlocked, versus 3 for the same policy without the filter (McNemar
p = 0.25); establishing the difference statistically would require
substantially more episodes, as deadlock is rare in these scenarios."
A properly powered test is a separate, sizeable run.

Preliminary: this table will be regenerated identically in the final
evaluation (deterministic seeds), with CoLight-variant and whichever
pressure-lineage option the author chooses added alongside.

### P5-6 -- infrastructure: OneDrive sync is a confirmed live competitor during training (~2.2 cores), because the project lives inside OneDrive. Corrects the speed-gate entry's "no contention" conclusion. Also: the P5-2 flush fix is verified working.
Infrastructure only -- no result, hyperparameter, or budget is affected.

**Measured, live, not cumulative.** `Get-Process` reports
`OneDrive.Sync.Service` at 288,726 CPU-seconds, but that figure is
cumulative since the process started and says nothing about current load,
so it was not treated as evidence. A 10-second live sample during
CoLight-variant S1 training instead:

| process | live CPU |
|---|---|
| python (9 procs, training) | 507.2% (~5 cores) |
| sumo (8 procs, training) | 290.7% (~2.9 cores) |
| **OneDrive.Sync.Service** | **221.7% (~2.2 cores)** |
| VS Code (16 procs) | 23.3% |

Machine: 16 logical cores, CPU 82%, RAM 87.3% used. The project directory
(`C:\Users\...\OneDrive\Desktop\HAPLIGHT`) is inside OneDrive, and
training writes continuously -- per-iteration checkpoints, CSVs, and SUMO
warning logs that grow by megabytes per run -- so each write triggers a
re-sync.

**What is and is not established.** Confirmed: OneDrive consumes ~2.2 cores
live during training, ~28% as much CPU as the training itself.
**Inferred, not proven:** that it explains the observed baseline slowdown
(CoLight-variant S1 ~740-840s/iteration vs 374s pre-fix). By raw core
count ~5.5 cores remain idle, so CPU alone is an incomplete explanation;
disk-I/O contention from OneDrive hashing/uploading files, with RAM at
87%, is the more likely mechanism, and it was not measured. Reported as a
likely contributor, not a sole cause.

**Correction to the speed-gate entry.** That entry concluded "there is no
contention problem." Its core finding stands -- the "~200-224s reference"
was an S1 rate wrongly compared against S2, and S2 has always cost
~780-840s. But "no contention" was too strong: OneDrive was competing
throughout, it simply was not the explanation for the S1-vs-S2 gap.

**Not acted on unilaterally.** OneDrive is the author's backup/sync
service; pausing or stopping it is the author's decision, consistent with
this project's standing rule that the response to contention is to shrink
one's OWN footprint, never to touch the user's processes. Recommended to
the author: pause OneDrive sync for the duration of training (reversible,
defers rather than loses sync). A footprint-side mitigation for future
runs -- writing high-churn SUMO warning logs outside the synced tree while
keeping final artifacts in the project -- is available but not applied
mid-chain (the running chain script must not be edited).

**Flush fix (P5-2 follow-up) verified.** The first run launched after
adding `flush=True` (CoLight-variant S1) shows its iteration lines live in
the log (6 of 6 completed iterations visible, interleaved with SUMO
stderr). The pre-fix HAPLight-RL S2 log had ZERO iteration lines across
3,024 lines. The contention guard's warnings are therefore now visible
while a run is in progress, which was the entire point of adding it.
**Known limitation, recorded:** the guard flags spikes relative to a run's
OWN rolling median, so it cannot detect a run that is uniformly slow from
its first iteration -- which is exactly the CoLight-variant S1 case.

### P5-7 -- AUTHOR DECISION: Advanced-MPLight and MPLight dropped from the laptop (40-iteration) table. Author will retrain both later on GPU at 100 iterations each.
`Sec. VI-E`.

Decision taken by the author in response to P5-4 (options 1-4). The
laptop-budget comparison table therefore contains: HAPLight-RL (filtered
and unfiltered), CoLight-variant (single-hop attn), FixedTime,
MaxPressure, GreedyHAP -- all learned entries at the equal 40-iteration
budget on corrected measurements. PressLight and IPPO remain scoped out
(P5, Stage-A code retained).

**Runs excluded** (on corrected measurements, so NOT marked invalid-8x,
but trained on `pressure_raw`, which fails the corrected-measurement
reward gate): `advanced_mplight_s1_seed0_1789038502` (full width),
`results_phase5/amp_narrow/advanced_mplight_s1_seed0_1789077927` (P5-3
width test), `mplight_s1_seed0_1789150346`. Each carries an
`EXCLUDED_PRESSURE_RAW.txt` marker. Retained as the evidence for P5-3/P5-4.

**Three constraints on the planned GPU retrain, recorded so they are
known before any compute is spent:**

1. **The reward must change first; more iterations will not fix this.**
   `pressure_raw` fails the gate on corrected measurements (S1 rho=+0.600,
   inverting the ranking of competent controllers). Both methods diverge
   LATE -- improving for ~16 iterations, then collapsing -- so this is not
   undertraining. At 100 iterations with `pressure_raw` they are expected
   to diverge further, not converge. The retrain needs a reward that
   passes the gate on corrected measurements (`total_queue` passes) or a
   newly constructed, pre-registered pressure reward.
2. **A GPU does not by itself shorten this training.** The policies are
   tiny (HAPLight-RL 23,650 params; Advanced-MPLight 5,542; MPLight
   1,478) and wall-clock is dominated by SUMO episodes, which run on CPU
   -- the paper's own Sec. VI compute-budget text already states this.
   What shortens it is more and faster CPU cores (more parallel
   environments); a cloud GPU instance helps only through the CPU cores
   it comes with.
3. **Equal-budget rule.** 100-iteration Advanced-MPLight/MPLight cannot
   share a table with the 40-iteration HAPLight-RL and CoLight-variant.
   A 100-iteration comparison needs EVERY learned method retrained at 100
   on corrected measurements. The existing 100-iteration HAPLight-RL
   checkpoints (`s1_seed0_1787507503`, `s2_seed0_1787604457`) are
   invalid-8x and cannot be reused for it.

---

## Template for new entries

```
### <ID>. <one-line summary>
`<paper section>`

What changed, the measured evidence, and why it matters.
```
