# Fresh-world force and recovery-budget factorial

**Development simulation only; `GATE_B_NOT_AUTHORIZED`.** No Holdout/reserved seed contents, production tickets, frozen artifacts or V9-M4 statistical rules were used or changed. AI-agent review is engineering assistance, not independent statistical approval.

## Predeclared experiment and implementation

`V9_M5_FRESH_FACTORIAL_PLAN_2026-10-31.md` was saved before running seeds2256000/2256001, whose outcomes had not been inspected. Both vector biases and both recovery arms were crossed with force methods AXIS_CLIP/DIRECTION_PRESERVING_PEAK and recovery budgets100/300; nominal range, overall800/postSTOP50 fixed. Four ledgers each contain8 assignments,32 total. All executions completed without errors. The design contains only two distinct world realizations, with multiple correlated conditions; it is not32 independent worlds or a basis for confirmatory risk claims.

The new `scripts/research/summarize_recovery_factorial.py` validates all four ledgers, requires the full factorial grid and exact matching assignments/runtime/source/horizons except force/budget, preserves ERROR/INCOMPLETE denominator counts, and separates decision-time measurements from post-STOP samples. Output creation is exclusive. Eight tests cover the full grid, missing/duplicate cells, unpaired settings and failure-state handling.

## Outcomes

| Force | Recovery budget | Assigned/completed | True STOP | False STOP | Abstain | Timeout |
|---|---:|---:|---:|---:|---:|---:|
| AXIS_CLIP | 100 | 8/8 | 1 | 0 | 7 | 0 |
| AXIS_CLIP | 300 | 8/8 | 1 | 0 | 7 | 0 |
| DIRECTION_PRESERVING_PEAK | 100 | 8/8 | 1 | 0 | 7 | 0 |
| DIRECTION_PRESERVING_PEAK | 300 | 8/8 | 1 | 0 | 7 | 0 |

No decision-horizon collision flag was recorded. In each cell terminal reasons were four ANCHOR_OUTSIDE_CONFIRMATION_MARGIN, two POSTPROPOSAL_MONITOR_ALARM, one POSTPROPOSAL_RANGE_UNAVAILABLE and one EXPLORATORY_STABILIZED_ANCHOR_CONFIRMED. One repeated scientific condition (seed2256000, heavy bias, anchor-recovery arm) supplies the STOP in each cell; these are not four independent successful worlds.

The budget pairs have unchanged outcomes and observed trajectories within each force method because all runs exited before reaching the100-update limit; the largest recorded recovery counter was50. There is no demonstrated budget benefit on this fresh grid. In contrast, previous selected failure cases had budget-sensitive timeouts; that result should not be generalized from its diagnostic selection.

Direction-preserving guidance changed356 recorded requests in each of its ledgers (difference greater than1e-12 per component for this descriptive diagnostic). Thus the force ablation was engaged, even though aggregate outcome labels matched. This1e-12 comparison is a numerical diagnostic, not a scientific acceptance threshold. Equal outcome counts do not imply equal force trajectories or performance in all worlds.

## Physical observations

The STOP cases each retained50 post-STOP samples under the existing simulator-truth braking/CBF path. With AXIS_CLIP, decision distance was .15306m, speed .06968m/s, maximum post distance .15280m and final sampled speed .00905m/s. With direction guidance, decision distance was .15626m, speed .08263m/s, maximum post distance .15902m and final sampled speed .01073m/s. Budget100/300 repetitions within each force have the same measurements. No post-sample collision was recorded. Motion remains nonzero; no rest/stability threshold or safety pass is inferred. Only STOP cases have this horizon, so it says nothing about post-abstention dynamics.

## Integrity and regression

Raw files under `results/research_development/dev/`:

| Filename | SHA-256 |
|---|---|
| team_fresh_factorial_axis_100_v1.jsonl | 18a8acd28a80e354cadf336bc1ace425750a55346629d8813ffff2978e1be6db |
| team_fresh_factorial_axis_300_v1.jsonl | eb2280addca946bb57557d4ab8a69682af0d22b266e5dce5e953969ac61266e6 |
| team_fresh_factorial_direction_100_v1.jsonl | c5fb46c66d412b8b2f73a58e992571e05fbfc69c2418876b7da819b43adce8e3 |
| team_fresh_factorial_direction_300_v1.jsonl | 09ef447ce954aba20f9d1d3da01484ca8560097eb5605a8b13ec3057ccc09281 |

Summary: `results/research_development/analysis/team_fresh_recovery_factorial_v2_summary.json`. Before/after source and runtime maps match across cells. These local hashes are not signed authentication or rollback protection. Sources/default controllers were not changed for this experiment. Existing changes/history were preserved; no commit/push or release decision was made.

Final targeted tests:155 passed; `git diff --check` passed.

## Evidence-backed next work

Prioritize the anchor-confirmation failures and phase-specific monitor alarms on these fresh worlds rather than increasing time indiscriminately. Inspect anchor/range consistency, measured speed, calibration, stopping distance and re-confirmation transitions without weakening existing checks. Add separate incremental post-action/post-abstention physical observations before claiming safe fallback. More fresh worlds, fault coverage, estimated-state control, hardware and independently reviewed scientific/security rules remain necessary for broader claims. Gate B remains unauthorized.

Additional audit: `V9_M5_POST_STOP_MEASUREMENT_AUDIT_2026-10-31.md` confirms top-level collision/CBF counters exclude the post-STOP horizon; consumers must inspect its separate samples. The latest comparator also compares selected recorded decision state/action digests: budget pairs match in all8 conditions within each force, while force pairs differ in all8. Those digest comparisons are not proof of complete post-physics equivalence.
