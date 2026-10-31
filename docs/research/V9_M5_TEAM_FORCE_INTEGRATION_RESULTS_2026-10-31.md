# Team force-integration development results

**Exploratory simulation only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No production tickets, reserved Holdout contents, frozen evaluation artifacts or V9-M4 statistical rules were used or changed. AI engineering review is not independent statistical approval.

## Team contributions

The integration agent added an opt-in benchmark hook and phase-specific tests. The evidence-review agent strengthened the separate ideal-state analyzer against unpaired settings, nonfinite/boolean inputs, inconsistent initial worlds, targets, and state discontinuity. The design agent prepared `V9_M5_TEAM_FORCE_INTEGRATION_PLAN_2026-10-31.md`. The coordinator integrated the runner CLI, manifest method checks and explicit seed-list support, ran simulations and reviewed evidence.

The benchmark default remains AXIS_CLIP. DIRECTION_PRESERVING_PEAK is limited to the two exploratory recovery arms and BASE→BASE NAVIGATE/PROBE. RECOVERY anchor guidance, VERIFY, braking, STOP and ABSTAIN are unchanged. Trace fields include original/effective action, method, transformation status, and phases. Both methods are separately identified in assignment and episode records.

## Declared smoke experiment and results

Nominal range case, seeds 2252000 (prior-stall diagnostic repeat) and 2254000 (fresh development seed selected before outcomes), two vector biases, two recovery arms, both force methods, 600-step horizon and 50 post-STOP diagnostic steps. Two separate ledgers each contain eight assignments. All sixteen executions completed with no recorded execution errors. They represent only two matched worlds and must not be counted as sixteen independent worlds.

| Method | Assigned/completed | Decision-time true STOP | False STOP | Abstain | Timeout | Collision observed |
|---|---:|---:|---:|---:|---:|---:|
| AXIS_CLIP | 8/8 | 0 | 0 | 4 | 4 | 0 |
| DIRECTION_PRESERVING_PEAK | 8/8 | 0 | 0 | 8 | 0 | 0 |

For selected seed 2252000 all four baseline configurations timed out at final distance 3.4455 m. The alternate ended by abstention, with distances 0.4064, 0.4064, 0.4063 and 0.2374 m depending on bias/arm. This supports removal of that local stall, but no assignment reached an accepted STOP under the existing rules. The fresh seed also abstained in all eight comparisons. Close distance alone does not satisfy the existing arrival decision.

Terminal reasons for AXIS_CLIP: four ACTIVE timeouts, three RECOVERY_TIMEOUT, one POSTPROPOSAL_RANGE_UNAVAILABLE. Alternate: five RECOVERY_TIMEOUT, two POSTPROPOSAL_RANGE_UNAVAILABLE, one POSTPROPOSAL_MONITOR_ALARM. These counts describe different trajectories and phases, not estimates of failure or alarm probabilities. No post-STOP horizon was triggered because no STOP occurred. No collision was observed in this tiny grid; this is not a safety guarantee.

## Evidence validation

The eight assignment pairs match in seed, bias, controller, horizons, runtime and source maps, differing only in declared force method. Candidate ledger retains 2,343 pre-physics events, of which 1,380 used the alternate guidance. Every transformed event was BASE→BASE NAVIGATE/PROBE; every untransformed event retained its original action. This verifies transformation scope in these traces, not actual completion of the subsequent physical action.

Both ledgers passed the recovery analyzer's chain, assignment, source-map consistency, episode identity, event-count/tail/order, outcome and post-STOP consistency checks. Self-reported source hashes and local chains are not independently authenticated. Truth velocity remains in benchmark damping/braking and CBF; geometry and sensor noise are simulator generated. These are not no-oracle or real-robot results.

- Baseline raw: `results/research_development/dev/team_force_axis_smoke_v1.jsonl`; SHA-256 `a8a96233912157c48d4cf35f54d1fb0dcaa94f025867f53239fae4121aa51ad6`.
- Alternate raw: `results/research_development/dev/team_force_direction_smoke_v1.jsonl`; SHA-256 `34cf9601f56d7be643f6960f4016acdf6e01243f27dc04c40f15f490999afe2e`.
- Summaries: `results/research_development/analysis/team_force_axis_smoke_v1_summary.json` and `team_force_direction_smoke_v1_summary.json`.

The combined targeted integration/evidence suite passed 64 tests before execution; final verification including shared-ledger and vector-fault tests passed 81 tests, and `git diff --check` passed. The ideal-state historical six-episode ledger still passes its strengthened analyzer. Existing files and historical results were preserved; no commit or push was made.

## Remaining work

Investigate RECOVERY_TIMEOUT and POSTPROPOSAL_RANGE_UNAVAILABLE without relaxing STOP criteria. Trace acquisition/freshness and recovery transition history, separating real dropout from an observation not requested during a phase. Study post-STOP physical settling only when such events actually occur. Execute the predeclared fault follow-on as its own batch, retaining untriggered fault assignments and all failures in the denominator. Broader geometry/routing, measurement authenticity, real sensors, and independent statistical/security review remain unresolved. No release blocker is closed by this experiment.
