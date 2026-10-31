# Post-STOP measurement and accounting audit

**Read-only audit of exploratory development evidence. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No STOP rule, threshold, controller, runtime, ledger or frozen artifact was modified. No Holdout outcomes or reserved seeds were accessed. This report makes no safety or stable-arrival claim.

## Evidence identity

Only `results/research_development/dev/team_recovery_budget_300_v1.jsonl` was examined for experimental outcomes. SHA-256: `22f1b9236434f89b64322f5afd70c8d60dc69582163d83c9b6bb922d058e4d2d`. It declares 8 assignments: development seeds 2252000 and 2254000, two vector biases, both recovery arms, nominal range, direction-preserving navigation, max 800 decision steps, recovery limit 300 and 50 post-STOP physics steps. Runtime is declared as Python 3.12.14, NumPy 2.5.3, MuJoCo 3.14.0.

References below describe the inspected checkout on 2026-10-31. The ledger records benchmark SHA-256 `5274c20dd8f8615b554f4a96dd0ffbf669326e1526a2aef03381d262c8a901ea` and stabilized-arrival source SHA-256 `3f93b0c736a924296c949466fbec502040ce1c65a19912a64564ff7ec5928cb8`. These self-reported source references are not independent authentication or a complete runtime snapshot.

## Why the measured gate can pass above 0.08 m/s truth speed

`src/aegis/v9/stabilized_arrival_candidate.py:16` sets an exploratory observed-speed limit of 0.08 m/s. Lines 74–84 compare the supplied vector norm with that cutoff. Lines 85–88 request an anchor after a qualifying reading; lines 90–98 confirm a valid anchor/range and issue STOP on the subsequent update, which also passes through the velocity check. The code does not compute a confidence bound on physical speed or require a sustained low-speed dwell. Its docstring at lines 10–14 assigns freshness and application of the VERIFY brake to the caller and describes these as development parameters.

`experiments/benchmark_physical_3d_cbf.py:438`–447 synthesizes velocity as scaled truth plus configured bias plus independent per-component Gaussian noise of standard deviation 0.02 m/s, with delivery/dropout/replay support. A noisy vector can understate the norm even with current delivery. Gaussian noise has unbounded support, so an unadjusted observed cutoff cannot certify the same bound on truth speed. No error probability is estimated here.

The recovery arm delegates to this gate outside RECOVERY (`src/aegis/v9/anchor_recovery_candidate.py:54`). In recovery a sufficiently near anchor transitions back to BRAKING (`:44`–48). Its anchor displacement margin is not a velocity uncertainty bound.

### Observed instance

Assignment `nominal:2254000:0.0:AEGIS_3D_ANCHOR_RECOVERY` issued STOP at decision index 402 (403 observations):

| Index | Phase transition | Decision | Truth speed m/s | Observed speed m/s |
|---|---|---|---:|---:|
| 399 | BRAKING → BRAKING | VERIFY | 0.102116 | 0.101493 |
| 400 | BRAKING → BRAKING | VERIFY | 0.098031 | 0.089406 |
| 401 | BRAKING → ANCHOR | VERIFY | 0.094110 | 0.048919 |
| 402 | ANCHOR → TERMINAL | STOP | **0.090345** | **0.071993** |

At STOP the truth vector is `[-0.08964668125, 0.01056137916, -0.00377251772]`; the observation is `[-0.06131160527, -0.01599117909, 0.03417822367]`. Their difference norm is 0.0542971 m/s. Sequence 402 was acquired at 8.04 simulator seconds and delivered at step 402. Thus sampled noise explains the under-reporting without requiring stale delivery or a configured bias. The decision follows the implemented observed-speed rule; it does not establish the same truth-speed bound.

Decision distance is 0.0605008 m. `experiments/benchmark_physical_3d_cbf.py:542`–546 labels `true_success=1` from decision-time truth distance alone. That field does not include truth speed or subsequent persistence and must not be described as physical stopping certification.

There are five STOP assignments in this ledger. Their decision truth speeds are 0.0721102, 0.0721102, 0.0694863, 0.0903455 and 0.0655038 m/s. Only the identified one exceeds 0.08. Repeated-world and paired-arm outcomes are correlated; these five are not independent estimates of a failure probability.

## What the diagnostic horizon measures

At STOP, `experiments/benchmark_physical_3d_cbf.py:547`–560 executes 50 `env.step(zero, force_braking=True)` calls, storing distance, speed, collision and CBF residual. With the configured default timestep 0.02 s (`src/aegis/env/mujoco_3d_cbf.py:35`), this is one second of diagnostic physics.

This is active truth-state braking: `src/aegis/env/mujoco_3d_cbf.py:418`–427 passes simulator truth velocity to the CBF; lines 147–155 construct the braking request from it. Lines 430–436 add ideal gravity compensation and advance physics. It is not an independent implementation of a deployed emergency stop.

For the identified case, the first post-STOP speed is 0.0867316 m/s; two of the 50 stored speeds exceed 0.08. The final stored speed is 0.0117346 m/s and distance 0.0450989 m. All 50 recorded collision flags are false and residuals zero. These describe one truth-braked diagnostic trajectory only.

## Accounting gap confirmed

`observe_step` at `experiments/benchmark_physical_3d_cbf.py:202`–214 updates episode collision, CBF violation, unchecked, exact-fallback and infeasibility counters. Navigation/VERIFY calls it at lines 565–566 and ABSTAIN at lines 538–539. **The post-STOP loop at lines 552–557 does not call it.** Top-level counters therefore exclude the diagnostic horizon. Separate post-STOP samples must be checked; a top-level zero does not establish a zero over that horizon. The inspected post-STOP samples do not show a collision/residual violation, so this is an accounting-scope gap, not a discovered hidden collision in this ledger.

Incremental `PRE_PHYSICS_DECISION` callbacks run at `experiments/benchmark_physical_3d_cbf.py:532`–535. The post-STOP loop has no incremental callback and holds samples in a local list. `scripts/research/study_recovery_monitor_ledger.py:88` persists the decision callback; lines 89 and 102 persist the terminal episode only after return. An interruption during the diagnostic horizon can lose its in-memory samples, leaving an incomplete assignment and a STOP proposal event. A recorded proposal does not prove the horizon executed.

The post-STOP local variable `observed` does not replace `state`; episode `final_distance` (`experiments/benchmark_physical_3d_cbf.py:577`) is consequently decision-time distance. The final diagnostic sample is `post_stop.steps[-1]`. Reporting must retain this distinction.

The analyzer (`scripts/research/analyze_recovery_monitor_ledger.py:202`–219 in this checkout) verifies post-STOP presence, sample count, numeric values and collision booleans. It does not reconcile those samples with top-level counters, independently establish execution, or apply a stable-stop rule.

## Proposed engineering evidence improvements — not implemented criteria

1. Persist typed POST_PHYSICS events during the diagnostic horizon with parent decision index, diagnostic step index, simulation timestamp, before/after state, requested/projected/applied control, gravity-compensation labeling, CBF feasibility/method/residual and contacts/clearance. Reconcile terminal summaries against these events. A crash between physics and persistence must remain explicitly observable as incomplete evidence.
2. Report separate pre-decision and post-STOP counters, preserving historical field meanings. Any combined diagnostic summary must declare its horizon and must not redefine positional success.
3. Record measured speed norm, declared measurement model, freshness sequence, configured cutoff, truth speed for scoring, and the qualification sequence leading to anchor request/STOP. Do not introduce a truth-based controller override while studying measurement limitations.
4. Evaluate a separately specified uncertainty-aware velocity candidate only after justifying its error model, dependence treatment and freshness assumptions. Repeated low readings alone do not justify independence or an error guarantee.
5. Synthetic tests should cover truth speed above cutoff with a noisy passing observation; post-STOP collision/residual faults absent from pre-decision counters; interruption after the Nth diagnostic step; persistence failure; and terminal/event disagreement. Preserve ERROR/incomplete status and never silently retry or assume a completed horizon.

Scientific review is required before selecting a velocity confidence rule, dwell, persistence horizon or stable-arrival endpoint. This audit approves none. Gate B remains unauthorized and V9-M4 remains unexecuted.
