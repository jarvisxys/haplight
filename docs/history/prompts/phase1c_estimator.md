# Phase 1c — Per-movement estimator calibration, fleet realism, paired H1 evidence

Read `PAPER_CHANGELOG.md` entries P1b-1, P1b-3, P1b-7, P1b-8 first.

Three problems from Phase 1b, in priority order. (1) is the important one and
turns a negative result into a positive one.

## Part A — per-movement calibration of the area estimator (the big one)

P1b-7 found Greedy HAP collapses under `estimator="area"` (AQL 3452 vs 848,
throughput 2256 vs 3220). The diagnosis is right but the conclusion is wrong.
Here is the mechanism, and it is fixable.

The area estimator divides by a **single global** `a_bar` (9.986, fitted to
the nominal fleet mix). Once composition varies by movement, the resulting
ratio does not:

    side street (75% 2W)      x_hat/x ~ 0.79
    arterial (20% bus, 14% truck)  x_hat/x ~ 1.12

That is a 1.41x systematic distortion, **fixed per movement and constant in
time**. Side streets look 21% smaller than they are, get underserved, spill
back, gridlock. This is exactly the per-movement bias that Remark 3 identifies
as the error Proposition 1 charges — and the theory prescribes the fix.

**Implement per-movement calibration.** Give each movement its own `a_bar_m`,
fitted once from a short classified count at that approach, mirroring how a
camera would be commissioned in the field:

- Add `Fleet.a_bar_for(composition)` returning the composition-weighted mean
  of `beta_v` — the same computation as `nominal_beta_mean()` but for an
  arbitrary mix rather than the fleet-wide shares.
- Add `scripts/calibrate_estimator.py`: run one Greedy HAP episode with the
  **count** estimator, log per-movement queue composition, and write
  `nets/<scenario>/a_bar_per_movement.json` mapping movement id -> `a_bar_m`.
  This is the simulated stand-in for a one-hour classified count per camera at
  commissioning.
- `env.py` loads that file when present and uses `a_bar_m` per movement;
  falls back to the global constant with a printed note when absent.

Deployment framing matters and should be documented inline: this is a
**one-time, install-time** calibration. The operational pipeline stays
classification-free — no per-frame classification is ever required. It is the
same practice as calibrating any traffic sensor at commissioning.

**Re-run the P1b-7 comparison** with per-movement calibration on. Prediction:
area recovers to within a few percent of count. Report the three-way table
(global a_bar / per-movement a_bar / count estimator) at
`composition_dispersion` 0, 0.5, 1.0.

**Also report the staleness risk:** rerun with `a_bar_m` calibrated at
dispersion 0.5 but evaluated at dispersion 1.0, i.e. a calibration that has
gone out of date as composition drifted. That bounds how often recalibration
would be needed in the field.

## Part B — realistic fleet composition, then recalibrate

P1b-1: bus at 10% of vehicles is 72% of all passengers, which makes PWD
essentially a bus-delay metric. Use:

| class | 2W | car | auto | bus | truck |
|---|---|---|---|---|---|
| vehicle share | 0.62 | 0.22 | 0.10 | 0.02 | 0.04 |
| -> passenger share | 37.7% | 16.5% | 10.3% | 32.7% | 2.8% |

Representative of an Indian metro arterial (2W 60-70%, buses 1-3% of vehicles
but a large passenger share on bus-served corridors). Flag in
`PAPER_CHANGELOG.md` that these still need a cited source — a household travel
survey or municipal classified count — before Sec. VII is called
representative.

This changes PCU per vehicle, so **re-run `calibrate_demand.py` for both
scenarios** and regenerate the nets. Also re-run `scripts/calibrate.py`
(C1/C2) — the C1 realised-error distribution depends on the fleet mix, and its
result feeds `a_bar_calibrated` in the config.

## Part C — paired H1 evidence

The Phase 1b sweep cannot support H1 as reported, for three reasons.

1. **Disagreement at d=0 is 2.9%, not 0%.** The theorem holds when composition
   is identical across movements; at d=0 it is identical only in expectation,
   and realised finite queues fluctuate. So ~3% is a sampling-noise floor, and
   disagreement never rises above it (2.9, 2.5, 3.1, 2.6, 3.2 — flat).
   Report this noise floor explicitly and separate it from the systematic
   component: estimate it by running d=0 across seeds.
2. **The table is confounded.** Raising d changes the demand itself (more
   buses and trucks on the arterial = more PCU to move), so ATT/AQL/PWD
   worsening with d says nothing about the controller. Report the **paired
   HAP - MP difference at each d, on identical demand and identical seeds.**
   That difference is the H1 evidence; the level is not.
3. **Wrong metric.** HAP optimises road-space occupancy, so its advantage
   should show as **spillback prevention**, not vehicle travel time. Add
   metrics: fraction of decision steps with any movement above 90% of
   `env.storage`, count of spillback events (a queue reaching the upstream
   intersection), and total upstream-blocked time. Then run the sweep on
   **S2 (300 m links, spillback-prone)** as well as S1, at **v/c 0.85 and
   0.95**, 3 seeds.

## Part D — MP vs FT, properly

P1b-8 (MP 232.6 vs FT 230.5, single seed) is not alarming: max-pressure is
throughput-optimal, not delay-optimal, so a well-tuned Webster plan should be
competitive at moderate stationary demand. Re-test at v/c 0.95 and under the
surge profile, 5 seeds, both scenarios. If MP still loses there, that is a
genuine finding and goes in the changelog — do not adjust FT to fix it.

## Deliverable

1. Three-way estimator table (global / per-movement / count) x dispersion
   {0, 0.5, 1.0}, plus the stale-calibration row.
2. Recalibrated capacity and C1/C2 under the new fleet shares.
3. Paired HAP - MP table with spillback metrics, S1 and S2, v/c
   {0.85, 0.95}, 3 seeds, with the d=0 noise floor stated.
4. MP vs FT at v/c 0.95 and under surge, 5 seeds.
