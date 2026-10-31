# Team recovery diagnostics and targeted sensor-loss follow-on

**Development simulation only; `GATE_B_NOT_AUTHORIZED`.** No Holdout/reserved seed contents, production tickets, frozen artifacts or V9-M4 statistical logic were accessed or changed. These AI engineering reviews are not independent statistical approval.

## Engineering work completed

Three agents investigated recovery transitions, hardened the evidence analyzer, and traced range availability. The coordinator added trace-only telemetry and ran the predeclared fault follow-on. The benchmark now records raw range sample/transport validity, controller-visible distance, semantic validation status, recovery step counter, stabilization wait and missing-velocity count. These additions do not change observations, random draws, controller decisions or STOP criteria. An actual MuJoCo regression fixture preserves abstention on the known negative-range case.

The range investigation found all three nominal-smoke POSTPROPOSAL_RANGE_UNAVAILABLE events had valid/fresh transport flags but negative Gaussian-noise distances. This was not injected dropout or demonstrated scheduling failure. See `V9_M5_RANGE_AVAILABILITY_INVESTIGATION_2026-10-31.md`. No clipping, retry rule, or threshold relaxation was introduced.

Transition diagnostics show existing RECOVERY_TIMEOUT episodes execute 100 bounded recovery NAVIGATE updates then time out on the next update. Progress during those updates does not imply the unchanged confirmation rule was satisfied. Example selected2252000 direction/nominal-bias trajectory moved from approximately .79884 to .41342 m during recovery while observed speed increased. The bounded horizon/gain is a plausible contributor, not proven causal evidence or justification to increase it silently. Legacy unrecorded counters are marked unavailable rather than filled with zero.

The recovery analyzer now checks manifest-wide force method consistency, paired source/runtime/horizons, numerical types and trace transformation semantics, including rejecting claimed changes to recovery/braking/VERIFY forces. It retains legacy compatibility and distinct execution ERROR/INCOMPLETE states.

## Predeclared targeted vector-loss batch

Both previously used development seeds2252000/2254000, both vector biases, both recovery controllers and both force methods, vector-loss-after-proposal case only, max600/postSTOP50: sixteen assignments in two ledgers. These are diagnostic repeats of the nominal-smoke worlds, not new independent worlds. All sixteen executions completed without errors.

| Force method | Assigned | Fault triggered | Untriggered timeouts | Abstain after triggered loss | STOP after triggered loss |
|---|---:|---:|---:|---:|---:|
| AXIS_CLIP | 8 | 4 | 4 | 4 | 0 |
| DIRECTION_PRESERVING_PEAK | 8 | 8 | 0 | 8 | 0 |

Every triggered monitor-arm assignment recorded one vector-loss step before abstention with POSTPROPOSAL_VECTOR_UNAVAILABLE. Original anchor-recovery assignments retained 79 or88 injected-loss steps before RECOVERY_SENSOR_INVALID abstention. These counts measure injected pre-physics decision observations, not certified physical stopping time. Differences in trigger counts reflect different trajectories and opportunities, not a detection-rate improvement. Four baseline assignments never reached injection and cannot support sensor-loss response claims. No recorded false arrival or collision occurred; the tiny dependent set cannot establish safety.

Recorded counters clarify those 79/88 observations: the original arm continues stabilization, then rejects invalid vectors at its first RECOVERY update (recovery_steps1, stabilization wait78 or87). The monitor rejects at its first post-proposal update (recovery_steps0/wait0). Thus the long interval is mainly stabilization before recovery validation, not 79/88 recovery navigation commands.

No STOP occurred, so there is no post-STOP horizon evidence in this batch. Abstention applies the benchmark's existing truth-state CBF braking step; it is not evidence of a real-system fail-safe or stable physical stop.

## Preserved evidence and checks

- `results/research_development/dev/team_recovery_fault_axis_v1.jsonl`, SHA-256 `0313735d0916e1b856f37ed17f2f7d24ba8d8affb9ea0c519f054a8c710e73e3`.
- `results/research_development/dev/team_recovery_fault_direction_v1.jsonl`, SHA-256 `7bbbfae9c0de94b3ba3cbbf811cd127b224c4d4cc6bd85b438aece280ba9b53e`.
- Exclusive summaries: `results/research_development/analysis/team_recovery_fault_axis_v1_summary.json` and `team_recovery_fault_direction_v1_summary.json`.
- Read-only diagnostic tool: `scripts/research/diagnose_recovery_transitions.py`; synthetic tests preserve incomplete/error distinctions and missing counter evidence.

Final targeted regression: **152 passed**; `git diff --check` passed. Four team ledgers and four historical recovery ledgers remain readable under the strengthened analyzer. Hash chains and source maps are local/self-reported, not signed trust anchors. Existing history/results were preserved. No commit/push or release decision was performed.

## Next decisions for development

Compare recovery duration/guidance as separately named experimental settings rather than changing the current candidate silently. First declare outcomes to observe (distance, speed, anchor/range validity, terminal reasons), isolate guidance from horizon, retain the baseline and all denominators, then execute a fresh matched development grid. Preserve negative-range evidence and model it explicitly when considering alternative physical sensor noise models. Physical post-abstention settling still needs a separate measured horizon. Gate B and all V9-M4 owner/statistical/security blockers remain unchanged.
