# NEXVIA research implementation and development results — 2026-11-16

**Development evidence only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No reserved Holdout outcomes/seeds, confirmatory episodes, production tickets, frozen statistical decision changes, published-history rewrite, commit, push, merge or hardware validation occurred. Current local branch: `codex/research-hardening`, parent `74b0bfab8e57cd450293e49de881207074df3141`, with pre-existing user changes preserved. All repository additions are new files/directories; previous versioned components remain intact.

## What was implemented and executed

1. New **v3 bridge and reader** record/check geometry, contacts, compiled obstacle mappings, CBF configuration, actual runtime versions, temporal phase and terminal-horizon coverage. Collision/contact fields are checked against recorded geometry; this is internal consistency, not independent physical truth.
2. New **paired development runner/reader** declares all eight assignments before execution, binds child digests/configurations/source identities to the batch, retains errors/incomplete assignments, checks reset equality and matches noise innovations over decision prefixes and anchor-query ordinals. Missing counterparts are not substituted. Exclusive new directories prevent implicit retries or overwrites.
3. Executed the previously proposed eight-case diagnostic: one known development seed 2256000, two controllers, two bias conditions and two environment versions; maximum 400 decisions, recovery budget 100, 50 post-STOP and 25 extra post-ABSTAIN steps, direction-preserving navigation and explicit no-fault/latency/replay settings. The manifest contains every actual benchmark argument.
4. Completed mathematical review of the **separate public aerodynamic benchmark** at commit `936fbdfeb516cf8b77ba6107c57f9f796293a525`, and packaged an isolated conditional e-process reference. It is not integrated into any controller/evaluator.
5. Packaged a separate **one-dimensional static-boundary braking-envelope reference** with analytical assumptions and tests. It is not a flight-recovery controller or a verified physical envelope.

## Actual paired-study results

All eight assignments completed; batch FINALIZED. All four reset pairs match, all four recorded runtime snapshots match, and all four pairs have matching common-prefix vector/range/velocity innovations and anchor-query innovations. Their common decision lengths are 139, 252, 86 and 222; anchor-query counts are 15, 11, 10 and 10. In this dataset request steps also coincide. No unmatched tail was observed. The source map still matches executed bytes and read-only analysis exactly reproduces the saved summary.

|Controller / bias|Environment|Recorded outcome|Decisions|Physics samples|Final sampled speed (m/s)|
|---|---|---|---:|---:|---:|
|anchor_recovery_nominal|legacy|abstained|139|164|0.020553|
|anchor_recovery_nominal|synchronized|abstained|139|164|0.020290|
|anchor_recovery_heavy|legacy|true_success|252|301|0.010733|
|anchor_recovery_heavy|synchronized|true_success|252|301|0.008797|
|recovery_monitor_nominal|legacy|abstained|86|111|0.179194|
|recovery_monitor_nominal|synchronized|abstained|86|111|0.176621|
|recovery_monitor_heavy|legacy|abstained|222|247|0.097289|
|recovery_monitor_heavy|synchronized|abstained|222|247|0.079744|

Recorded labels are unchanged by synchronization in these four environment pairs: six abstentions and two decision-time successes. This does not establish that synchronization never changes decisions. Residual motion differs, and the synchronized nominal monitor still has approximately **0.1766 m/s** after 25 extra active truth-state braking steps (0.5 simulated seconds at the recorded timestep). No approved operational rest criterion is asserted. No collision flag occurs in persisted PHYSICS samples; reset geometry is separately clear. Neither observation establishes zero risk or safe stopping.

These are eight dependent trajectories from **one already inspected world**, not eight independent reliability trials. No population confidence interval, p-value, generalization rate, V9-M4 finding or real-robot conclusion is derived. Synchronization changes control-state inputs and solver-derived state as well as observation timing; the comparison is not a pure reporting-only intervention.

## Tests and evidence

- Integration/batch/configuration/noise suite: **48 passed in 6.58 s**. Includes full eight-case fixture execution, omitted/wrong assignments, missing/tampered children, source inconsistency, preserved failed launch and exclusive output retention.
- V3 geometry/terminal suite: **44 passed in 3.19 s** (13 new, 31 adjacent; overlaps other suites). Includes actual 50-step legacy STOP and initial-plus-25-step legacy/synchronized ABSTAIN fixtures, rehashed geometry contradictions and persistence failure.
- Packaged mathematical reference suites: **73 passed in 0.06 s** (26 monitor, 47 braking-envelope tests).
- Counts are per suite and **must not be added as a distinct-test total**. This is not the full repository suite. Ordinary engineering tests deliberately create ERROR/INCOMPLETE/contradictory artifacts; those bytes are retained separately. No unexpected pytest failures or actual-study errors occurred in the reported runs. An initial helper-tool launch for the monitor reference used a not-yet-created work directory and did not execute; the successful test runs followed directory creation.

The integration tests themselves repeat development cases; test executions and the actual study are not additional independent replication worlds. Sources, exact commands, runtime versions, test XML and raw-output hashes are in `integrated_research_execution_verification_2026-11-16.json`. Test fixtures and actual-study raw outputs are retained separately. Source/runtime maps and AI reviews are not independent authentication or statistician/security approval.

## Statistical monitor: established defects versus proposed repair

The public aerodynamic benchmark raises the negative tail of its residual score by lower clipping, and separately floors wealth at .01. The mathematical review supplies exact counterexamples: expected multiplier **1.01875 > 1** under a stated-null distribution; and expected wealth **.010625 > .01** at the wealth floor. These disprove the generic supermartingale argument from the asserted residual-mean bound, not the empirical simulator distribution itself.

`research_references/conditional_monitor_v1/` implements an **upper-only clipped**, unfloored log-wealth reference with strict order/input checks. Validity remains conditional on an unverified predictable bound `E[Z_t | past] <= tau_t`; the code does not supply aerodynamic calibration, handle arbitrary missingness/resets/multiplicity, or certify floating-point inference. No current monitor, registered evaluator or published artifact was replaced. Independent statistical review and a justified null/calibration design remain required before claiming physical-system anytime validity.

## Recoverability reference and assumptions

`research_references/braking_envelope_v1/` implements the one-dimensional static-boundary bound

`travel <= v*t + 0.5*a*t^2 + (v+a*t)^2 / (2*(b-d))`, for `b>d`.

Inputs are asserted upper approach speed, lower clearance after footprint/reserve, bounded total delay, TOTAL outward acceleration during delay, guaranteed braking and opposing braking-phase disturbance. It rejects unsupported inputs and returns unknown when positive net braking cannot be established. Boundary equality has zero reserve and is not a physical safety claim. The module does not establish those bounds, flight dynamics, lateral escape, jerk/rotor behavior, changing obstacles or actual sensor uncertainty. It is ordinary floating-point reference arithmetic, not an interval-certified implementation.

## Execution register for the broader proposal

| Workstream | Current state | Next concrete evidence required |
|---|---|---|
| Integrated development evidence | Eight-case diagnostic completed | Independent reproduction from an isolated snapshot; broaden development worlds without relabeling them confirmatory |
| Valid statistical monitoring | Two defects proved; isolated conditional reference implemented | Derive/calibrate a conditional null with untouched evaluation worlds; review dependence, missingness, restarts and multiplicity |
| Estimation-aware control | Not yet implemented by this change | Separate simulated truth from estimated state/uncertainty/timestamps; define estimator failure interfaces and common-mode fault cases |
| Recoverability supervisor | 1D analytical reference implemented; no robot integration | Validate platform-specific delay/braking/disturbance/clearance bounds and extend to appropriate dynamics |
| Active verification | Design work remains | Constrained probe/measurement actions with information, delay and motion budgets; compare passive versus immediate fallback |
| Assurance-layer fault tolerance | Selected evidence/runtime failure tests implemented | Deadline/watchdog/callback/common-dependency faults and fallback execution checks |
| Controlled independent evaluation | Not executed | Freeze a narrowly scoped design and obtain required owner/independent review before reserved evaluation |
| Hardware progression | Pending; no hardware available | Identify platform, ground truth, transport, actuator model and controlled physical-test plan |

## Next implementation sequence

First build an estimated-state-only control interface and sensor uncertainty/age records in a new experimental arm. Preserve simulator truth only for evaluation. Specify how unavailable or unjustified bounds make recoverability UNEVALUABLE rather than favorable. Extend the bounded recovery analysis to the chosen dynamics and validate its inputs. Then compare active verification and immediate fallback under matched, recorded faults across multiple development worlds. Plan independent evaluation only after the method and metrics stabilize.

Keep the local 3D recovery study separate from the public tunnel-aerodynamics benchmark: they are different experimental systems. Do not combine their successes, test counts or figures as one validation claim. Public README/paper guarantee reconciliation, V9-M4 scientific/security blockers, operational stopping criteria and independent review remain unresolved. No Final Release Commit has been created. **Gate B remains `GATE_B_NOT_AUTHORIZED`.**
