# Predeclared recovery-duration diagnostic comparison

**Development simulation plan only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** This plan is saved before inspecting the new experiment's results. No protected Holdout data, production ticket, frozen artifact or V9-M4 scientific/statistical acceptance rule is involved. Longer recovery is an explicitly varied development parameter, not a new approved stopping criterion.

## Question and fixed design

Does extending the existing anchor-guided RECOVERY budget from100 to300 update attempts change descriptive outcomes in the previously used development worlds, with direction-preserving BASE guidance fixed?

Create two exclusive new ledgers, one for each budget, containing the following full matched grid. No automatic retry, overwrite, or favorable-seed substitution is permitted.

| Dimension | Declared values |
|---|---|
| Recovery update budget |100;300|
| Force guidance |DIRECTION_PRESERVING_PEAK fixed in both budgets|
| Recovery controller |AEGIS_3D_ANCHOR_RECOVERY;AEGIS_3D_RECOVERY_MONITOR|
| Development seeds |2252000;2254000|
| Seed roles |Both are repeated prior diagnostic worlds with known previous behavior; neither is fresh replication|
| Vector biases |[0,0,0];[0.8,0.8,-0.3]|
| Fault case |nominal range: bias0/dropout0; targeted post-proposal vector-loss injection disabled|
| Whole-episode decision horizon |800 steps, identical for both budgets|
| Post-STOP observation horizon |50 steps whenever an actual STOP occurs|

The grid has8 assignments per budget and16 total. Within each seed/controller/bias pair, budget100 and300 must have identical defaults, world mapping, sensor/noise streams, guidance gain and scaling, damping, CBF settings, geometry, anchor behavior, speed/range/confirmation thresholds, maximum missing-velocity count, stabilization wait limit, monitor assumptions and terminal logic. The budget and its explicit identity/metadata are the only experimental configuration changes. Source hashes/runtime metadata must be recorded, and source files must remain stable during execution.

The previous force-integration smoke used600 whole-episode steps. This comparison uses800 for **both** budgets. Interpret the new100-versus300 pair directly; comparing a new300/800 result against an older100/600 result cannot isolate the recovery budget because both overall horizon and recovery duration differ.

## Budget semantics from source

`src/aegis/v9/anchor_recovery_candidate.py:12`–16 initializes `recovery_limit` from the explicit positive integer. Its update at lines24–27 increments `recovery_steps` only when entering the RECOVERY branch, then abstains with RECOVERY_TIMEOUT when that counter exceeds the limit. Thus limit100 allows up to100 RECOVERY update attempts to continue through their sensor/anchor checks; the next attempt produces timeout. This is not100 additional whole-episode steps guaranteed after a proposal. At the configured0.02s simulation timestep,100/300 potential recovery steps correspond nominally to2/6 simulated seconds, but earlier exits, monitor checks and the overall horizon can shorten exposure.

The RECOVERY law remains `clip(0.5*anchor,-0.3,0.3)` at lines49–52. Anchor/range corroboration can return to BRAKING and reset stabilization wait at lines44–48. The once-only recovery entry is at lines54–60. Keep all of these unchanged. Increasing the update budget does not authorize additional recovery restarts or a different anchor acceptance margin.

`src/aegis/v9/stabilized_arrival_candidate.py:62`–64 separately maintains stabilization `wait_steps` and its120 default maximum; RECOVERY updates use the subclass branch and are not equivalent to these stabilization waits. Its speed, anchor and range checks at lines81–97 remain fixed. The monitor subclass checks observations in monitored phases before delegating (`src/aegis/v9/recovery_monitor_candidate.py:93`–103), so it can abstain before the recovery counter is incremented. Do not infer sensor exposure solely from `recovery_steps`.

The800-step assignment horizon bounds the entire preterminal episode, including BASE navigation, braking, anchor requests and recovery. A late RECOVERY entry may never use its full300 budget. Report both elapsed episode steps and actual recovery attempts/phase occupancy, not the configured budget alone. If a whole-episode timeout occurs first, preserve it as timeout rather than RECOVERY_TIMEOUT or evidence the full recovery budget failed.

Source references describe inspected working files; each executed ledger's source-map hashes identify the versions actually used.

## Required checks before execution

1. Reject nonpositive/noninteger/bool budgets. Restrict a nondefault budget to the two exploratory recovery arms; default behavior remains100.
2. Test budget boundary exactly: continuing eligible attempts through the declared limit and RECOVERY_TIMEOUT on the next; preserve sensor-invalid/anchor-conflict/monitor exits before that boundary.
3. Verify both controller constructors receive the explicit budget and metadata/result/assignment identity agree.
4. Confirm BASE navigation, BRAKING/ANCHOR confirmation and the separately bounded RECOVERY force law are unchanged. The alternate BASE guidance must never rescale RECOVERY NAVIGATE.
5. At identical configuration and random streams, paired traces must agree before the100-budget cutoff or any earlier terminal divergence. A300-budget run that differs before budget can affect behavior indicates a configuration or implementation confound requiring investigation.
6. Verify exclusive outputs, assignment recording before execution, per-step trace retention, hash/source identity validation, and explicit execution ERROR/incomplete handling. Do not silently rerun a failed assignment.

## Descriptive outputs and failure denominators

Report assigned8 per budget, completed/error/incomplete/never-started counts, and all existing outcome categories with explicitly named assigned/completed denominators. Do not drop monitor alarms, sensor invalidity, abstentions, timeouts or execution errors when comparing budgets. Each repeated seed is a world; multiple biases/controllers/budgets are correlated variants, not16 independent samples.

For each assignment retain actual RECOVERY phase entry/count, counter maximum, budget exhaustion versus whole-episode timeout, reason and phase of early termination, anchor queries/valid responses, stabilization waits, missing-velocity observations, monitor observation count/reason, and range semantic-validity diagnostics. For assignments that never enter RECOVERY, mark the budget contrast unexercised; they do not show that a larger budget improved recovery.

Keep full-trace initial/final/minimum distance,50-observation tail reduction, phase/decision counts, original/effective requested force and transformation status. Report actual post-action CBF force/residual/contact evidence only where logged; pre-physics intent alone does not prove actuation. Preserve safety violations, unchecked/infeasible steps and engineering residual diagnostics. For any STOP, preserve all50 post-STOP distance/speed/contact samples and explicitly mark absent/incomplete evidence. No new arrival, safety, utility, stall or statistical acceptance threshold is declared here.

## Risks, interpretation and next decision

Longer recovery permits more noisy sensor draws, anchor requests, force applications and monitoring opportunities. It can increase exposure to collision, invalid samples, correlated faults, drift, alarms, oscillation and storage loss. It may also allow more approach time. A lower RECOVERY_TIMEOUT count can simply move failures to another reason; report the complete outcome distribution and trajectories rather than treating timeout reduction as success.

The300 budget gives no guarantee of STOP, stable stopping or reaching an anchor margin. The scalar range model can produce negative measurements near zero; retain those raw values and fail-closed behavior. Do not resample/clamp or adjust validator/confirmation thresholds to obtain a desired result. Simulator truth remains involved in damping/braking/CBF and known geometry, so no hardware or estimate-only robustness claim is supported.

This is a deliberately selected diagnostic comparison, not independent confirmation. After complete evidence review, decide whether there is a mechanism worth testing in a separately declared broader development grid; do not promote the larger budget to a default or scientific acceptance rule merely because one repeated case improves. Gate B remains `GATE_B_NOT_AUTHORIZED` throughout.
