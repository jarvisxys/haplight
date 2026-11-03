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
- libsumo backend: **85 passed, 1 skipped** (Bengaluru net moved to D:), in 4 min
  (v2 environment with traci: 84 passed in 16 min). 84 ported tests + 2 new ones.
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

## Next steps (plan Sec. 15)
1. ~~Fix the stale first observation after `reset()` under libsumo~~ (done 2026-11-04).
2. Backend parity test (traci vs libsumo) and per-episode speed benchmark.
3. Confirm the college server's CPU cores, RAM, OS and access method.
4. E0 re-validation (C1/C2 seeded, capacity, a_bar, filter B).
5. Download UVH-26 to `D:\haplight-data\datasets`.
6. Implement `control/cas.py` with tests, and the store-and-forward theorem checker.
