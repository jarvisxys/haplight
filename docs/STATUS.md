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
- libsumo backend: 82 passed, 1 skipped (Bengaluru net moved to D:), 1 failed, in 4 min
  (v2 environment with traci: 84 passed in 16 min).
- Failure: `test_counts_match_ground_truth[s1]` fails only when another simulation ran
  earlier in the same process. Cause: libsumo keeps context-subscription results across
  simulations in one process, so the first observation after `env.reset()` carries stale
  counts from the previous run. Every count from the first `step()` onward matches ground
  truth. Same bug class as v2 changelog P4c-12.
- Production training/evaluation is unaffected (one fresh process per episode). Tests and
  any code that reuses a process are affected.

## Next steps (plan Sec. 15)
1. Fix the stale first observation after `reset()` under libsumo (refresh subscriptions or
   measure only after the first simulation step), and add a regression test that runs two
   simulations in one process.
2. Backend parity test (traci vs libsumo) and per-episode speed benchmark.
3. Confirm the college server's CPU cores, RAM, OS and access method.
4. E0 re-validation (C1/C2 seeded, capacity, a_bar, filter B).
5. Download UVH-26 to `D:\haplight-data\datasets`.
6. Implement `control/cas.py` with tests, and the store-and-forward theorem checker.
