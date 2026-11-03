# Phase 1b — Demand calibration and heterogeneous composition

Read `PLAN.md`, `PAPER_CHANGELOG.md`, and `src/hap.py`.

Phase 1 works, but the 600 s smoke test completed only 19 trips at
126 veh/h with a network-wide AQL of 3.6 weight-units. That is free-flow:
signal control cannot matter, n=19 is not a measurement, and per-class Gini is
impossible. Separately, class shares are drawn i.i.d. from one global vector,
so composition is spatially uniform and Greedy HAP is *provably identical* to
MaxPressure (see below). Both must be fixed before any RL work.

## Part A — locate network capacity, then set demand relative to it

Add `scripts/calibrate_demand.py`.

Sweep a global demand scale factor under **Greedy HAP** and record, per scale:
completed trips, throughput, network AQL, mean travel time, and the fraction
of decisions where any movement queue exceeds its storage.

Throughput rises with demand and then plateaus. That plateau is the network
capacity, i.e. an empirical estimate of the boundary of the capacity region
`Λ` in Assumption A3 — say so in the docstring, it is not a coincidence.

Write back into `configs/default.yaml` under `demand`:
- `scale_nominal` — the scale giving **v/c ≈ 0.85** (congested, control matters,
  still inside `Λ` with a real interiority margin)
- `scale_surge` — **v/c ≈ 1.05** for the surge stress test (briefly outside `Λ`,
  which is exactly what the certified floor is for)
- `capacity_veh_per_h` — the measured plateau, per scenario

Sanity floor: the nominal 3600 s episode should complete on the order of
10^3 trips on Scenario 1, not 10^2. If it does not, the demand generator has a
bug — do not just scale the number up until it looks right.

## Part B — spatially heterogeneous composition (this is the important half)

Right now `x^HAP = c · x^MP` componentwise for a scalar `c`, so the two
controllers have the same argmax by construction. Proof: if every movement has
the same mix `f_v` then `n_mv = f_v N_m`, hence
`x^HAP_m = N_m Σ_v ρ_v f_v = c N_m` while `x^MP_m = N_m`. This is Remark 3 of
the paper applied to the weight vector instead of to sensing error.

So HAP differs from MP **only to the extent that composition varies across
movements**. Make that variation real, and make it a controlled variable.

Extend the demand generator so class shares are **per-OD**, not global,
reflecting documented Indian patterns:
- minor/side approaches two-wheeler-dominated (the paper's own claim)
- buses concentrated on designated arterial routes, near-absent on side streets
- trucks concentrated on the through-arterial, suppressed in the town core
- cars over-represented on the main arterial

Add a `composition_dispersion` knob in `[0, 1]`: 0 reproduces today's uniform
shares exactly (must give HAP ≡ MP bit-for-bit — assert this in a test), 1 is
the full heterogeneous pattern. Nominal runs use a documented mid value.

Add `src/metrics.py::composition_dispersion(queue_composition)` returning a
scalar index — mean pairwise total-variation distance between per-movement
composition vectors, weighted by queue mass. Log it every episode. It becomes a
reported covariate, not an unexamined assumption.

## Tests

- `test_uniform_composition_makes_hap_equal_mp` — at dispersion 0, Greedy HAP
  and MaxPressure select the identical phase at every decision. This is
  Remark 3 as an executable check; if it ever fails, something is wrong.
- `test_heterogeneous_composition_separates_hap_from_mp` — at dispersion 1 the
  two disagree on a non-trivial fraction of decisions.
- `test_nominal_demand_is_congested` — nominal scale gives network AQL above a
  threshold and v/c in [0.8, 0.9].

## Determinism (fold in here)

The subscription-across-resets bug means state can leak between episodes. Add:
- `test_reset_determinism` — two consecutive episodes in one process, same
  seed, identical metrics.
- `test_seed_changes_outcome` — different seeds give different metrics.

If libsumo cannot support repeated clean resets in one process, say so
explicitly and document that training uses one process per environment.

## Deliverable

The capacity sweep curve (throughput vs demand scale) for S1 and S2, the
chosen nominal/surge scales with their v/c, and a table of Greedy HAP vs
MaxPressure ATT at composition dispersion 0, 0.5 and 1.0 on Scenario 1 at
nominal demand.
