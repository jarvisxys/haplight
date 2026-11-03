# Working rules for this repository

Read `docs/STATUS.md` first, then the relevant section of
`docs/plan/HAPLight_v3_Research_Plan.pdf`. Update `docs/STATUS.md` before ending a session.

## Commits
- The author is the repository owner (the git config identity). Never add a
  `Co-Authored-By` trailer or any AI attribution to commits or PRs.
- Simple, plain commit messages: one short summary line, optional short body.
- Commit and push at the end of each piece of work so a lost session loses nothing.

## Authorship
- Single author for now: Aditya Kumar. Do not add other authors to the paper,
  README, plan or citation files unless asked.

## Research rules (carried over from v2, see docs/history/)
- Do not edit `paper/*.tex` content while experiments run. Record paper-affecting
  findings as decision records in `docs/decisions/`.
- `configs/default.yaml` is the only place numbers live. No hand-typed result numbers.
- Every phase or experiment has an acceptance test or a pre-registration file
  (`experiments/EXX/prereg.md`) committed before launch.
- Never compare runs produced by different measurement pipelines or SUMO backends.
- One fresh process per episode (`maxtasksperchild=1`).
- Runs before 2026-09-09 (the 8x double-counting fix) are invalid.

## Environment
- `uv run ...` for everything; Python 3.12, SUMO 1.27.1 via pip, libsumo backend.
- Set `SUMO_HOME` to the installed `sumo` package (see README). An older user-level
  `SUMO_HOME` may point into the v2 OneDrive folder and must not be used.
- In any process that uses both libsumo and pyarrow, import pyarrow first; the
  reverse order fails with a DLL error on Windows.
- Laptop: 7.7 GB RAM, so use at most 6 parallel SUMO workers. Heavy sweeps run on the
  college GPU server.
- Outputs go to `results/` and `results_baselines/`, which are junctions to
  `D:\haplight-data\runs`. Never write large files into the repository.
