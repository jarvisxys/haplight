# Phase 4 — Shared policy, PPO, stability filter

Read `PLAN.md`, `src/hap.py`, `src/env.py`, and Section V of
`paper/HAPLight_journal_v2.tex`.

Build `src/policy.py`, `src/safety_filter.py`, `src/ppo.py`, `scripts/train.py`,
`tests/test_policy.py`, `tests/test_ppo.py`.

**src/policy.py** — the architecture in Table V of the paper, exactly:

| Component | Spec | Params |
|---|---|---|
| Movement encoder | MLP 8→64→64, ReLU | 4,736 |
| Phase pooling | sum over movements in phase | 0 |
| Phase MLP | 64→64, ReLU | 4,160 |
| Neighbour encoder | MLP 4→32, ReLU | 160 |
| Phase + context | concat 96→64, ReLU | 6,208 |
| Competition head | pair 128→32→1 | 4,161 |
| Value head | mean-pool 64→64→1 | 4,225 |
| **Total** | | **23,650** |

`tests/test_policy.py::test_param_count` asserts exactly 23,650. If your count
differs, the architecture differs from the paper — fix the code, not the test,
and tell me.

One shared network for all intersections. Permutation-invariant over
movements, indifferent to phase count (masking handles geometry). Masked
logits set to −1e9 before softmax.

**src/safety_filter.py** — override with `hap.greedy_phase` when any queue
entering intersection *i*'s pressure computation exceeds `B`. `B` = the P90 of
the per-movement weighted queue distribution under greedy HAP on the same
scenario at nominal demand, so it must be *measured* first — add a
`calibrate_threshold()` that runs greedy HAP and returns the percentile.

**The filter triggers on `x_hat`, not on true queues** (changelog P1-1). It
has to be implementable from cameras, so it sees exactly what the controller
sees. Corollary 1 already covers the noisy case: the guarantee holds with
`delta` replaced by `delta - c1*dt*eps`. `true_queues` is used only for
metrics and for offline verification of the certificate. (This supersedes an
earlier instruction of mine that said the opposite.)

**Report filter activation rate after the FIRST S1 training run, not at the
end.** H2 pre-registers activation below 5% of decisions, but training now
runs at v/c 0.85-0.95 with network AQL of order 10^3, and Remark 6 says
HAPLight-RL converges behaviourally to greedy HAP wherever the filter fires.
If activation exceeds ~20%, stop and report: the learner has almost no room,
and we decide whether `B` moves to P97 or H2's threshold is revised. That
decision must be made before the full sweep is launched.

**src/ppo.py** — three things here are subtle and matter more than the rest:

1. **Filtered steps carry no policy gradient.** When the filter overrides
   intersection *i* at time *t*, the executed action was not the policy's.
   Mask those steps out of the policy-gradient and entropy terms, but keep
   them in the trajectory for GAE and value regression. The value head learns
   the value of the *composed* policy; the policy gradient is formed only from
   decisions the policy actually made. `test_filtered_steps_no_gradient`
   asserts the policy gradient is zero on overridden steps.
2. **Time-limit bootstrapping.** Episode end is truncation. Bootstrap
   `V(s_T)`. Omitting this biases values downward and is the usual cause of
   flat learning curves in this task. `test_truncation_bootstraps` covers it.
3. **Normalise advantages across the pooled batch**, not per intersection.
   Rewards use the fixed scaling in Eq. (12), not running statistics.

**Load `nets/<scenario>/a_bar_per_movement.json` during training.** Phase 1c
made per-movement estimator calibration the default; a global constant costs
~11% throughput (changelog P1c-1/P1c-9). Training against a biased estimator
wastes the entire run. Assert the file is present and used, and log which
calibration is active in the run metadata.

**First task of this phase, before any training:** measure the real
SL2015-vs-LC2013 runtime ratio on a full S2 episode at nominal demand.
Phase 3 measured 7.6-8.7x on a dense held-then-released queue, against the
2-4x that PLAN.md's compute budget assumed. If the real-episode ratio is >= 6x,
stop and report before launching runs; the levers, in order, are: restrict the
robustness grid to S2 only, cut training 800 -> 500 episodes with convergence
curves shown, then drop MARDDPG. Do **not** coarsen `lateral_resolution`
(0.8 m) — that would undo the two-wheeler gap-filling Phase 3 validated, and
it is a reported value in Table IV.

Hyperparameters from `configs/default.yaml` under `rl.ppo`. Parallel envs via
`multiprocessing` (Windows spawn — guard with `if __name__ == "__main__":`),
one libsumo instance per process, `n_envs = physical_cores − 1`.

**scripts/train.py** — trains on one scenario/seed, writes checkpoints and a
per-iteration CSV (return, filter activation rate, entropy, value loss,
wall-clock) into `results/`.

Get the pipeline learning on Scenario 1 first — smallest and fastest. The gate
is that HAPLight-RL's mean episode return exceeds greedy HAP's within 800
episodes. If it does not, do not scale up; tell me and we debug the reward or
the observation.
