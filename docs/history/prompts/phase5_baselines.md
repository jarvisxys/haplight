# Phase 5 — RL baselines

Read `PLAN.md` and Section VI-E of the paper.

Build `src/rl_baselines.py`: IPPO (independent PPO, no parameter sharing),
PressLight, MPLight, CoLight, Advanced-MPLight, and MARDDPG (last, drop it if
time is short).

Reuse `src/ppo.py` and `src/env.py`. What differs between these methods is
the state, the reward and the network — not the training loop. Structure them
as configs over a shared trainer rather than six copies of PPO.

Critical for fairness, and reviewers will check:
- Same training budget (800 episodes), same demand distribution, same seeds,
  same evaluation protocol as HAPLight-RL.
- Baselines get their **own** state and reward as published — do not give
  MPLight the HAP reward, and do not give PressLight the µ weighting. The
  point of the comparison is that our representation is better, which is only
  a claim if theirs is faithful.
- In robustness runs, classical and learned baselines receive the *same*
  corrupted observations as HAPLight-RL.

Sanity gate: Advanced-MPLight should land in the neighbourhood of its
published relative improvement over MP on the 4×4 grid. If it is far off, the
port is wrong and every comparison in the paper is worthless. Report the
number before moving on.

`tests/test_baselines.py::test_all_baselines_run` — each baseline completes a
short episode on S1 and S2 without error.
