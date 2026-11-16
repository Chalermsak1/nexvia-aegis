# Incremental physical-step evidence — development implementation

Gate B remains `GATE_B_NOT_AUTHORIZED`. This is development simulation/tooling only; no Holdout, reserved seed contents, production ticket, frozen artifact or V9-M4 statistical rule is involved. No real-robot or safe-stop claim is made.

## Scope and declared diagnostic

Add an optional observational `on_physics` sink to the two exploratory recovery benchmark arms. Persist actual post-physics state, velocity, target, projected force, CBF residual/feasibility, collision flag, physical-step index and linked decision index. Label MAIN, ABSTAIN_BRAKE and POST_STOP_BRAKE separately. Preserve original decision-time outcome/counters and post-STOP terminal data; do not feed observations back into decisions.

Use a separate runner/study/schema interpretation, not mixed events in the existing recovery-ledger study. Old readers/artifacts and the previously prepared comprehensive report/index remain unchanged snapshots. Parent commit:74b0bfab8e57cd450293e49de881207074df3141; source maps record the uncommitted implementation actually executed, not an assertion of a new release commit.

Predeclared diagnostic repeat: development seed2256000, both vector biases and both recovery arms, direction-preserving guidance, recovery budget100, maximum400 decision steps, post-STOP50 physical steps. Four assignments, selected to exercise existing STOP/abstention paths rather than estimate efficacy. No post-abstention extension is added: the existing one-step brake is recorded only.

## Failure and interpretation boundaries

A callback runs after physics. Interruption before persistence can still leave an unrecorded physical step. If the evidence sink fails, execution propagates its error rather than silently continuing. A local fsync/hash chain is not power-loss durability, authentication, antirollback or independent approval. Post-STOP remains active truth-state CBF braking. Projected force is not independently measured actuator force; gravity compensation is applied separately in the simulator.

Synthetic/short-MuJoCo checks compare callback-enabled and default results/traces for STOP, ABSTAIN and timeout, check stage/index/count semantics, propagate sink errors, reject unsupported sinks, and reject physically contradictory but correctly hash-chained records. A real child-process exit after two persisted physics observations must preserve the incomplete assignment, not relabel it complete.

## Recorded diagnostic results

All four declared diagnostic assignments completed without execution errors. The visible ledger is FINALIZED and its chronology/physical-distance/terminal-post-STOP checks pass. It retains699 decision observations and748 physical observations:695 MAIN,3 ABSTAIN_BRAKE and50 POST_STOP_BRAKE. One selected heavy-bias anchor-recovery assignment issues the existing STOP; the other three abstain. These repeated cases verify instrumentation paths, not efficacy or risk probability.

Raw: `results/research_development/dev/recovery_incremental_physics_v1.jsonl`, SHA-256 `359ae6f7e6f1de3fd99609c21cf9cdfa3d440f39a5234d8cfb45addeaafeaa2f`.

Summary: `results/research_development/analysis/recovery_incremental_physics_v1_summary.json`.

Tests:169 targeted checks passed, including14 new physical-evidence checks; `git diff --check` passed. The process-exit test records two decision and two physical events then terminates the child with exit41; the assignment remains STARTED/INCOMPLETE. This is an intentional failure fixture in a temporary test directory, not an automatically retried research episode or power-loss experiment.

The new physical-study analyzer validates recorded chronology/stage, vectors/distance, collision/residual syntax and terminal post-STOP consistency. It does not authenticate sensors, independently register the assignment grid, validate every scientific outcome, measure actual actuator force, or close signed-root/runtime/rollback blockers. A COMPLETED assignment remains execution status, not scientific acceptance.

The existing recovery-ledger study/analyzers continue reading their original PRE_PHYSICS_DECISION-only schema; the new mixed decision/physics records have a separate study identity and analyzer. Existing reports, evidence inventory and all historical results are untouched snapshots. No commit, push, external publication or Gate B authorization was performed.

Next: add separately specified post-abstention and NO_COMMAND horizons, full actuator/uncertainty evidence and stronger externally authenticated manifests. Preserve the difference between an observation after one braking step and demonstrated stable physical stopping.

AI evidence review identified two analyzer false-acceptance gaps: decisions after a terminal decision, and contradictory/nonexclusive terminal outcome metadata. Both were fixed with synthetic correctly-hash-chained counterexamples; method/budget/horizon, decision-time post-STOP measurements and strict integer indices are additionally checked. The preserved actual diagnostic summary still matches the strengthened analysis in memory. This review is not independent scientific or security approval.
