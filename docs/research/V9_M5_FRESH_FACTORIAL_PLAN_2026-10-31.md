# Predeclared fresh development factorial

**Development simulation only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** This plan is saved before execution or inspection of outcomes for seeds2256000 and2256001. The seeds are selected now for this development grid; no reserved Holdout seeds or outcomes are needed. No production ticket, frozen evaluation artifact, V9-M4 statistical rule or release authorization is changed.

## Question and declared assignments

Describe how force saturation and RECOVERY duration interact in two newly selected development worlds, while retaining the existing noisy-sensor recovery/confirmation logic and CBF. Earlier selected diagnostic worlds motivated the settings; they are not included as new independent evidence in this factorial.

| Dimension | Fixed declaration |
|---|---|
| New development seeds |2256000;2256001, outcomes not inspected when selected|
| Force methods |AXIS_CLIP;DIRECTION_PRESERVING_PEAK|
| Recovery update budgets |100;300|
| Recovery controllers |AEGIS_3D_ANCHOR_RECOVERY;AEGIS_3D_RECOVERY_MONITOR|
| Vector biases |[0,0,0];[0.8,0.8,-0.3]|
| Case |nominal range, bias0/dropout0; no post-proposal vector-loss injection|
| Whole-episode decision horizon |800 steps|
| Post-STOP diagnostic horizon |50 steps wherever an actual STOP occurs|

Execute the full Cartesian grid,32 assignments total. Use four new exclusive ledgers, one for each force-method/budget combination, each containing the same8 seed/controller/bias assignments. Write the assignments before running them. No favorable-seed substitution, automatic retry, overwrite, horizon change or optional early exclusion based on interim results is part of this plan. Execution errors and interrupted assignments remain evidence to report.

All settings other than the explicitly crossed force method and recovery budget remain identical: world/seed split, sensor distributions and fault defaults, geometry, proportional gain, damping, force limits, CBF, anchor schedule, range/anchor/velocity confirmation thresholds, monitor behavior, stabilization wait and missing-velocity limits. Record full assignment configuration, runtime and before/after source hashes. Stabilize code before executing all four batches, and investigate any source change rather than silently treating batches as comparable.

Within each world/controller/bias, the four cells form the intended factorial comparison. Matching seed/noise streams does not imply identical observations after trajectories diverge. These are **two worlds, not32 independent trials**. Repeated biases, controllers, force methods and budgets share world/random structure and are correlated. No hypothesis test, p-value, multiplicity correction, effect-size acceptance threshold or population-risk claim is declared here.

## Intervention boundaries and budget meaning

Direction-preserving force scaling applies only to inherited BASE guidance when both pre-update and post-update phases are BASE and the decision is NAVIGATE or PROBE. Preserve BRAKING, ANCHOR, RECOVERY, TERMINAL and VERIFY/STOP/ABSTAIN behavior. RECOVERY NAVIGATE retains its separate anchor-guided0.3 force bound. Do not alter an acceptance threshold or monitor wealth to improve a cell.

The recovery budget counts RECOVERY update attempts; the update increments the counter and times out when it exceeds its configured limit. It does not grant100/300 additional steps after any proposal irrespective of state. The800-step horizon independently bounds the whole episode, and stabilization wait remains a separate limit. A late recovery entry may never exercise the full budget. Log actual recovery phase occupancy/counter and reason for termination; label an unexercised intervention as such.

## Diagnostics and complete denominators

For each declared cell and aggregate, report assigned, completed, execution ERROR, STARTED/incomplete and never-started counts with clear denominators. Among completed executions retain all existing raw decision-time categories: true_success/true STOP, false_arrival/false STOP, abstained and timeout. Keep collision/contact or simulator safety-violation evidence and CBF residual/unchecked/infeasible diagnostics. Do not drop adverse or missing executions, combine abstention with success, or infer a pass from terminal execution COMPLETED.

Record full-trace distance progression, initial/final/minimum distance,50-observation tail reduction, phase/decision occupancy, original/effective guidance, transformation count, recovery attempts, anchor requests, stabilization waits, missing velocity and range-validation/monitor reasons. Metrics describe observed behavior; no new utility or stall threshold is approved.

For every actual STOP retain the entire50-step post-STOP speed, distance and collision/contact sequence, and report final/max speed and final/max distance descriptively. A true STOP flag reflects the benchmark's decision-time geometry. It does not establish stable arrival, zero velocity or subsequent safe behavior. No new pass criterion, zero-speed threshold or post-STOP tolerance is introduced. Where no STOP occurred, show post-STOP evidence as unavailable rather than zero violations. If evidence is interrupted or incomplete, preserve that state.

Validate ledger lifecycle/hash chains, declared paired grids and cell identities, force/budget metadata, source consistency, event counts/order, finite vectors and diagnostic fields, terminal trace agreement and outcome/post-STOP contradictions before interpreting differences. Local hash chains and fsync are not independent authentication, rollback protection or power-loss guarantees.

## Limits and subsequent work

This small factorial can expose interaction patterns and regressions but cannot confirm broad safety, reliability or practical utility. Sensors are synthesized from simulator truth; geometry and parts of damping/braking/CBF remain simulator-known. Nominal range does not cover dropout, replay, delay, intermittent/correlated faults, hardware noise, dynamic obstacles or unknown maps. Negative near-zero Gaussian range samples retain existing semantic invalidation and raw values; no clamp or resampling is authorized.

A larger recovery budget increases exposure as well as opportunity: more physical steps, noise, anchor requests and potential alarms/failures. Lower timeout count alone is not improvement if replaced by false STOP, collision or another adverse reason. Review complete cell outcomes and trajectories before proposing a separately named development change or wider grid. Do not promote any setting to a default, scientific acceptance rule or release merely from these two worlds. Gate B remains `GATE_B_NOT_AUTHORIZED`.
