# Team development plan: noisy-sensor force integration

**Status: development experiment plan, not owner scientific approval. Gate B remains `GATE_B_NOT_AUTHORIZED`.** This document declares a bounded comparison before its results are inspected. No V9-M4 Holdout outcomes or reserved seed contents are required. No production ticket, frozen evaluation change, or release decision is part of this work.

## Question and source basis

Does direction-preserving peak force scaling change descriptive navigation/arrival outcomes when integrated into the existing noisy-sensor recovery benchmark, while keeping all recovery/confirmation decisions and CBF constraints unchanged?

The prior ideal-state experiment is recorded in `docs/research/V9_M5_NAVIGATION_FORCE_ABLATION_2026-10-31.md`: seed2252000 stalled with axis clipping and approached the target with peak scaling at800 steps. It used simulator-truth guidance and bypassed sensor/arrival-monitor logic. Its other two seeds produced similar final distances between methods. These observations motivate this development comparison, not a general performance claim.

The inherited proportional guidance uses gain1.2 and axis clipping in `src/aegis/v9/controller_3d.py:371`. BASE delegation and transition to BRAKING after the base proposes STOP are defined in `src/aegis/v9/stabilized_arrival_candidate.py:51`. RECOVERY has a separate anchor-guided, low-force law (`clip(0.5*anchor,-0.3,0.3)`) in `src/aegis/v9/anchor_recovery_candidate.py:23` and line49 onward. The monitor observes BRAKING/ANCHOR/RECOVERY before delegating at `src/aegis/v9/recovery_monitor_candidate.py:93`. Source line references describe the inspected working files; executed ledgers must record their own source hashes.

## Current predeclared nominal smoke

Create two exclusive new ledgers, one per force method, with the following identical grid. Record all assignments before execution. Root coordinates source stabilization and execution; no agent should change tracked runner/controller sources while the batch is running.

| Dimension | Declared values |
|---|---|
| Force method | AXIS_CLIP; DIRECTION_PRESERVING_PEAK |
| Recovery controller | AEGIS_3D_ANCHOR_RECOVERY; AEGIS_3D_RECOVERY_MONITOR |
| Explicit development seeds | 2252000;2254000 |
| Seed roles | 2252000 selected prior-stall diagnostic repeat;2254000 fresh preselected development seed, outcomes not inspected when selected |
| Vector bias | [0,0,0];[0.8,0.8,-0.3] |
| Case | nominal range only: bias0, dropout0 |
| Decision horizon | 600 steps |
| Post-STOP diagnostic horizon | 50 steps wherever STOP actually occurs |
| Other controls | Existing default sensor-noise, anchor, velocity, latency/replay, world, gain, damping, CBF and terminal rules |

There are8 assignments per force ledger and16 total. The force pair for each seed/controller/bias must match every configuration field except force method, output location and any identity field that explicitly distinguishes the method. Preserve a force-method field in assignment identity/configuration and results; the same seed/controller/bias appearing in separate ledgers is an intended pair, not an independent replicate. Do not compare this600-step study directly with the prior800-step ideal-state study as if only force scaling changed.

Seed/world draws and sensor-noise streams must use the existing benchmark split. Sensor values and trajectories cease to be identical after force methods diverge: matching random seeds/noise streams is not the same as supplying identical physical observations. The two bias settings and two controllers within a seed share a world and are correlated. This is two worlds, including one deliberately selected failure, not16 independent deployment trials.

## Transformation guard and synthetic prerequisites

Apply the alternative force law only when the controller's phase is BASE both immediately before and immediately after update, and its effective decision is NAVIGATE or PROBE. This selects the inherited gain1.2 navigation law. It must not change anchor-guided RECOVERY NAVIGATE, BRAKING, ANCHOR, TERMINAL, VERIFY, STOP, ABSTAIN, query scheduling, sensor validity, monitor wealth/restarts, confirmation rules, or CBF/braking behavior.

Required tests before simulation:

1. Default AXIS_CLIP preserves prior action/result behavior; unsupported force/controller combinations fail explicitly.
2. Saturated BASE guidance preserves vector direction with the same per-axis peak limit; unsaturated/zero vectors are unchanged.
3. Both BASE NAVIGATE and BASE PROBE can be transformed, while all non-BASE phases and nonnavigation decisions remain unchanged.
4. BASE-to-BRAKING VERIFY is not transformed even though the pre-update phase was BASE. RECOVERY NAVIGATE retains its0.3 force bound; RECOVERY-to-BRAKING VERIFY remains untouched.
5. Invalid/nonfinite alternate vectors fail explicitly; an execution error remains an ERROR assignment with retained prior ledger events, not an omitted or automatically rerun episode.
6. Trace original request, effective request, force method, whether transformation was applied, and phases before/after. Do not label a pre-physics record as evidence of applied actuation.

The controller's `prev_action_3d` field currently is assigned but not read in its own implementation; audit again if future consumers are added. Avoid silently allowing an internal history field to claim an action different from the one used downstream.

## Descriptive outputs and denominators

Preserve assignments and terminal state separately from scientific outcomes. Report assigned, completed, execution ERROR, STARTED/incomplete and never-started counts for every cell and aggregate; do not drop failed executions or replace missing outcomes with a false pass. For each completed cell report counts of existing decision-time true_success, false_arrival, abstained and timeout, with their actual assigned/completed denominators explicitly named. A STOP is a decision-time event, not demonstrated stable arrival.

Retain initial/final/minimum observed target distance; reduction over the complete trace and a declared50-observation tail; decision/phase/mode counts; whether/how many times the transformation was applied; anchor requests; vector availability; monitor steps/reasons; and terminal reason. Do not invent a stall, improvement or statistical acceptance threshold from these measurements. A timeout at600 means no terminal decision within that horizon, not proof of permanent inability to progress.

Report safety/contact flags, CBF residual violations under the existing engineering diagnostic tolerance, unchecked and infeasible steps, and projected force whenever actually recorded. For STOP episodes preserve all50 post-STOP distance/speed/contact observations. Show post-STOP data as unavailable when no STOP occurred, not as zero violations or successful stopping. The maximum/minimum post-STOP distance and maximum/final speed are descriptive; no new acceptance threshold is approved here.

Before interpreting results, validate hash chains, one-shot assignment lifecycle, method/configuration/seed identity, paired grids, source-map consistency, per-episode event sequence/count, terminal trace agreement, finite values, and contradictions between outcome flags and post-STOP records. Preserve raw ledgers and summaries with hashes in new paths. A chain/hash is not an independent trust anchor or antirollback mechanism.

## Limitations that remain after the smoke

Noise is simulator-generated from truth; static obstacle geometry, velocity-based damping, braking and parts of CBF control remain simulator-known/truth-dependent. This is neither perception validation nor a fully estimate-only controller. Anchor requests and fault timing are trajectory-dependent. The postproposal monitor starts a fresh e-process and lacks independent error-guarantee validation. Missing command, abstention, simulated braking and physically demonstrated stopping remain different observations. Local fsync does not establish power-loss durability or authenticated external retention.

Nominal range does not test range dropouts, missing/stale velocity, intermittent/correlated vectors, dynamic obstacles, replanning, reachable-goal guarantees or hardware response. Two worlds cannot support broad safety/performance probability claims. No multiple-testing/significance claim is specified or implied.

## Follow-on experiment, not part of the current execution

After reviewing the complete nominal smoke, a separately documented fault batch may reuse exactly the same grid with `fail_vectors_after_stop_proposal=True`. Preserve the distinction between untriggered episodes and episodes with actual injected loss. Report assignment denominator, trigger denominator, then STOP/abstain/timeout after trigger. Do not label an episode whose fault never triggered as evidence of fault resilience. Declare any new seeds/horizon/configuration before inspecting their outcomes; keep repeat diagnostic seeds separate from newly selected development worlds.

A wider geometry study, direction-scaling versus route-planning factorial, and estimated-state control integration are later designs. Failure of this smoke does not authorize adjusting arrival thresholds, increasing favorable seeds or changing the frozen protocol. Engineering can implement separately named candidates and synthetic tests within development scope; V9-M4 scientific/statistical/security release decisions remain governed by their owner/reviewer approval requirements.
