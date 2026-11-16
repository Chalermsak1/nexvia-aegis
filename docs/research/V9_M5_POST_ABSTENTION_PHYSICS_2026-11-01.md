# Post-abstention physical evidence — development diagnostic

**Gate B: `GATE_B_NOT_AUTHORIZED`.** Simulation/tooling only, no Holdout, reserved seed contents, production ticket, frozen artifact, registered V9-M4 decision rule or real robot involved. No push/commit/publication is authorized by this run.

## Predeclared scope

Optional `post_abstain_steps=0` retains the existing benchmark default. A positive value is allowed only for the two exploratory recovery arms. The original ABSTAIN brake, decision-time result, first-brake `final_distance` and counters remain unchanged. Extra active truth-state CBF braking steps are diagnostics stored separately and emitted incrementally as POST_ABSTAIN_BRAKE, linked to the same terminal decision. They do not become new policy decisions or accepted outcomes.

The physical-evidence runner uses study v2 when the horizon is explicitly positive, keeps v1 for zero, records the requested count in assignments, and persists each physical sample through the development ledger. v1 historical bytes/readers remain supported without treating absent metadata as positive evidence. Old reports and the comprehensive report/index are preserved snapshots, not overwritten to imply they already included this capability.

Declared diagnostic before execution: repeated development seed2256000, both vector biases, both recovery arms, direction-preserving guidance, budget100, overall400 decision steps, post-STOP50 and post-abstention25 additional steps. Four assignments, deliberately reusing known STOP/ABSTAIN paths to test instrumentation. No estimate of generalization, failure probability or optimal horizon is intended. At timestep.02, the extension observes.5 simulated seconds after the original brake.

## Validation expectations

Compare enabled/disabled decisions, original result fields and traces, requiring exact equality apart from the new diagnostic field. Check one initial ABSTAIN_BRAKE followed by exactly25 POST_ABSTAIN_BRAKE events when completed, no post-abstention data on STOP/timeout, strict nonnegative-integer validation and scope restriction. Reject malformed/missing/duplicate/stage-mismatched events even with a valid hash chain. Preserve ERROR/INCOMPLETE assignments and no automatic retry after evidence failures. Test legacy v1 reading separately.

Limits: extra steps use simulator-truth position/velocity and idealized gravity compensation. Projected force is not an independent actuator measurement. A callback after physics still leaves a possible interruption window before persistence. Unkeyed hashes/self-reported source/runtime are not authentication, rollback protection or independent approval. Observation of a short active-braking horizon cannot establish a safe fallback, rest or indefinite stability.

## Completed diagnostic and finding

All four declared assignments completed with no recorded execution errors. The v2 ledger is structurally FINALIZED, with699 decision events and823 physical events:695 MAIN,3 initial ABSTAIN_BRAKE,75 additional POST_ABSTAIN_BRAKE and50 POST_STOP_BRAKE. Decisions/outcomes remain three abstentions and one existing decision-time STOP. These are repeated diagnostic conditions in one world, not four independent reliability trials.

| Abstaining condition | Speed after original brake(m/s) | Speed after25 extra active-braking steps(m/s) | Distance after original brake(m) | Distance after extension(m) |
|---|---:|---:|---:|---:|
| nominal vector bias, anchor recovery | .057028 | .020553 | .201797 | .220030 |
| nominal vector bias, recovery monitor | .497212 | .179194 | .019011 | .140805 |
| heavy vector bias, recovery monitor | .269950 | .097289 | .185182 | .156711 |

No collision flag was observed in these75 extra samples. Nonzero residual motion is directly observed: in the nominal-bias monitor case speed remains approximately.179m/s after the extra.5seconds, despite active truth-state braking. Thus ABSTAIN plus the original single braking step must not be described as immediate physical rest. A small initial distance can also increase substantially while braking. These data do not establish a population risk, acceptable speed threshold, safe fallback or a real robot result.

The original decision-time/first-brake fields intentionally retain their prior meanings. The new horizon's samples and initial-brake anchor are separate; its collision/CBF evidence must not be confused with pre-existing top-level counters.

## Evidence, review and verification

Parent research commit:`74b0bfab8e57cd450293e49de881207074df3141`; executed modified source maps/runtime metadata are embedded before/after each assignment. This parent identity is not a claim that the uncommitted changes are a new release candidate.

- Raw:`results/research_development/dev/recovery_post_abstention_physics_v2.jsonl`.
- SHA-256:`48136174812afb4e852732d314b88bbd1b8e87dd4f860cec98c85902dd72fecf`.
- Summary:`results/research_development/analysis/recovery_post_abstention_physics_v2_summary.json`.
- Final targeted regression:**181 passed**; `git diff --check` passed. This is not the full repository test suite.
- Historical v1 raw ledger remains readable with four assignments; historical bytes/summaries were not rewritten.
- Synthetic sink failure inside the new horizon propagates once, preserving STARTED with3 assignments still ASSIGNED and no silent retry. The unlogged actual step is not invented in analysis.
- Actual child-process exit after two persisted extra-horizon samples leaves the assignment STARTED/INCOMPLETE with one initial brake plus two extra samples. No claim of completion or power-loss durability follows.
- AI evidence reviewer found no material blocker in the scoped implementation and recommended the two extra failure tests above; they were added. This is not independent statistical, security or hardware approval.

Existing user documents, prior evidence and published history remain preserved. No commit/push/release authorization was made. Next investigate an explicitly specified estimated-state/fallback response and operational stopping/dwell endpoints; the present active truth-braking diagnostic only makes post-abstention motion observable.
