# Status

Last updated: 2026-11-04

## Where things stand
- v3 plan approved: `docs/plan/HAPLight_v3_Research_Plan.pdf`.
- Repository migrated from the v2 OneDrive folder without code changes.
  The full v2 snapshot is `D:\haplight-data\archive\HAPLIGHT_v2_2026-11-04.zip` (+ `.sha256`).
- v2 history: `docs/history/PAPER_CHANGELOG_v2.md` (evidence log), `PLAN_v2.md`, prompts, chain scripts.
- Last valid v2 checkpoints (40 iterations, seed 0, post-8x-fix):
  `D:\haplight-data\runs\v2_valid\s1_seed0_1788963312`, `...\s2_seed0_1788987398`;
  their evaluation (changelog P5-5) is in `...\v2_valid\eval\`.
- The Bengaluru v2 networks were moved to `D:\haplight-data\nets\bengaluru_v2`,
  so `tests/test_nets.py` skips until S3 is rebuilt.

## Decisions (2026-11-04)
- Code in `C:\dev\haplight`, data in `D:\haplight-data`, remote `github.com/jarvisxys/haplight`.
- No RAM upgrade. Heavy compute on the college server (RTX PRO 6000 Blackwell, 96 GB).
- Certified Action Set replaces the safety filter as the main contribution.
- Single author (Aditya Kumar) for now.

## Test suite on the new environment (2026-11-04)
- libsumo backend: **87 passed, 1 skipped** (Bengaluru net moved to D:), in 5.6 min
  (v2 environment with traci: 84 passed in 16 min). 84 ported tests + 2 reset
  regression tests + 2 backend parity tests.
- Fixed (commit `ea2807f`): stale first observation after `env.reset()` under libsumo.
  libsumo keeps context-subscription results in a process-wide cache that survives
  `close()`/`start()`; `subscribeContext()` and `unsubscribeContext()` do not clear it,
  only `simulationStep()` does. So the `reset()` observation of a second simulation in
  one process read the previous run's last-step vehicles (966 cached rows at t=0 with
  0 vehicles in a probe). `_measure()` now ignores context results until the first
  `simulationStep()` and raises if vehicles exist before it. Same bug class as v2
  changelog P4c-12.
- Regression test: `test_reset_observation_not_stale_after_previous_simulation`
  (`tests/test_measurement.py`), two simulations in one process (same env re-reset, and
  a new env); checks ground truth and equality with a fresh-process reset observation.
  Fails on the old code, passes now.
- Behaviour-neutral for production: fresh-process episodes are bit-identical with and
  without the fix (S1 and S2, GreedyHAP, eta=0.6, 60 decisions, SHA-256 of obs, rewards,
  true queues and x_hat). Valid v2 checkpoints and evaluations are unaffected.
- Side finding: before the fix, a second episode in the same process diverged for its
  whole length at eta=0.6, not only at the first observation (probably through the
  sensing-noise RNG stream; not yet confirmed). `test_episode_isolation` passed on the
  old code; its canary runs at eta=0 and records only post-`step()` observations,
  which is the likely reason. Worth extending it to eta>0 later.
- Lint: ruff reports 130 pre-existing findings in `src/env.py` and
  `tests/test_measurement.py` (v2 code); this change adds none.

## Backend parity and speed (2026-11-04, step 2)
- Parity holds exactly. `tests/test_backend_parity.py` (commit `2c90af4`) runs the same
  seeded GreedyHAP episode (600 s, eta=0.6) on traci and libsumo in fresh processes and
  requires identical per-step observations, rewards, true and sensed queues, actions,
  completed trips and metrics. Passes on S1 and S2. It also asserts the backend actually
  used, because `bootstrap_sumo()` silently falls back to traci when libsumo cannot be
  imported.
- At full length (3600 s) the benchmark found identical trajectory digests for every
  (scenario, seed) pair: 4/4 serial and 12/12 at 6 workers, seeds 0-5.
- Speed, `scripts/benchmark_backend.py`, GreedyHAP, eta=0.6, full 3600 s episodes, laptop,
  median wall-clock per episode (outputs in `results/benchmarks/`):

  | run | S1 traci | S1 libsumo | S2 traci | S2 libsumo |
  |---|---|---|---|---|
  | 1 worker, seeds 0-1 (`backend_w1_20261104_061233`) | 110 s | 35.5 s | 166 s | 48 s |
  | 6 workers, mixed, seeds 0-5 (`backend_w6_20261104_062502`) | 217 s | 66 s | 318 s | 103 s |
  | 6 workers, libsumo only, seeds 0-5 (`backend_w6_20261104_063900`) | - | 70 s | - | 104 s |

  libsumo is 3.1-3.4x faster per episode than traci in the same environment, above the
  plan's assumed 1.5-2.5x (the compute table used 2x). Under 6 workers each episode takes
  about 2x its serial time on both backends (machine contention, not traci's extra
  processes: the libsumo-only run matches the mixed run). The traci times at 6 workers
  match the v2 measurements (220-250 s S1, 340 s S2), so v2's cost was mostly the backend.
- Peak memory per episode: libsumo worker about 125-135 MB; traci worker about 95 MB plus
  about 35-40 MB for the sumo process. 6 libsumo workers need about 0.8 GB. Free RAM was
  only 1.6-1.7 GB of 7.7 GB during these runs.
- Caveats: GreedyHAP stands in for the policy (PPO adds a small forward pass and the
  update step); laptop numbers only, the college server still needs its own run.
- Open for the author: (a) whether to re-lock the compute budget with the measured 3x
  instead of 2x; (b) whether parity justifies comparing v2 (traci) results with v3
  (libsumo) results; CLAUDE.md still forbids it and was not changed; (c) whether to make
  `bootstrap_sumo()` raise instead of silently falling back to traci (a `src/` change,
  not made).

## Tools
- `scripts/system_check.py` prints hardware, package versions, whether PyTorch can use
  CUDA (laptop: no, CPU-only torch build; GTX 1650 detected but unused) and the latest
  benchmark results. Run it first on the college server.
- CPU training smoke test (2026-11-07, about 2 min): `uv run python -m scripts.train
  --scenario s1 --quick --iterations 3 --n-envs 6 --out results/smoke`.

## Next steps (plan Sec. 15)
1. ~~Fix the stale first observation after `reset()` under libsumo~~ (done 2026-11-04).
2. ~~Backend parity test and per-episode speed benchmark~~ (done 2026-11-04).
3. Confirm the college server's CPU cores, RAM, OS and access method.
4. E0 re-validation (C1/C2 seeded, capacity, a_bar, filter B).
5. Download UVH-26 to `D:\haplight-data\datasets`.
6. Implement `control/cas.py` with tests, and the store-and-forward theorem checker.
