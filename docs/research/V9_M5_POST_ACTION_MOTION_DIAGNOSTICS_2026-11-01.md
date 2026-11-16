# Post-action motion diagnostics — development tooling

**Governance: `GATE_B_NOT_AUTHORIZED`.** This run created a descriptive analyzer, synthetic regression fixtures and new summaries of existing development ledgers. It did not execute Holdout, read reserved seeds/outcomes, modify any V9-M4 rule or frozen artifact, create tickets, change a release candidate, commit, push or validate a real robot.

## Starting state and selected task

Inspected `codex/research-hardening` at parent `74b0bfab8e57cd450293e49de881207074df3141`, the working-tree status and `AI_RESEARCH_TEAM_CHARTER_2026-10-31.md`. Existing uncommitted benchmark instrumentation, reports, source files, tests and development evidence were preserved. No claim that this parent contains the uncommitted work is intended.

The previous post-abstention diagnostic already established residual simulated motion. The next scoped task was to make retained motion quantitatively reviewable without inventing an acceptable stopping speed, dwell interval or a scientific pass criterion. In particular, an absent post-action window must not be represented as evidence that no collision occurred, and target-distance change must not be substituted for travel along the observed path.

## Added capability and exact semantics

New CLI: `scripts/research/summarize_recovery_motion.py`. It first uses the existing physical-ledger chronology/source-map validator, verifies that the byte snapshot matches the validator's input SHA-256, then calculates a separate descriptive output. The underlying runner, controller, prior analyzer and historical summaries were not changed by this task.

- Each assignment retains its execution status independently of its observation-window status. A full set of observations in an interrupted assignment does not make the assignment COMPLETED.
- Window states distinguish NOT_REACHED, NOT_REQUESTED, MISSING, PARTIAL and COMPLETE_OBSERVATION_WINDOW. “Complete” refers to the requested sample count only.
- No samples produces `collision_observed: null`, null motion metrics and no positive collision-free evidence. With samples, false means only that no collision flag is present in those persisted samples; missing remainder remains missing.
- STOP uses its decision-time position/velocity/distance as the anchor. ABSTAIN uses the state **after the original first brake**, matching the previously retained extension scope. The two anchors cannot be treated as the same physical instant.
- Reports anchor and last speeds, minimum/maximum sampled speeds, last target distance, signed target-distance change, and the sum of Euclidean chords from anchor through persisted positions. Chord sum is a sampled polyline, not exact continuous travel or an independent actuator measurement.
- Reports how many CBF residuals were actually available and their observed minimum. Missing residuals remain missing; this does not independently verify the CBF model or solver.
- Rejects malformed anchors, changing targets within an anchored horizon, contradictory chronology and horizon overruns even when the hash chain is structurally valid.
- Elapsed seconds remains null: these assignment records do not record the simulation timestep. Reading the current implementation's timestep would not independently establish the runtime value used in an old ledger.
- Physical-rest classification is always `NOT_EVALUATED_NO_APPROVED_CRITERION`. No threshold, accepted-rest label, safety guarantee, aggregate reliability estimate or revised policy outcome was introduced.

The input hash check is a consistency check, not authentication or rollback protection. It does not certify all dependencies or a trustworthy execution environment. Persisted observations also cannot reveal a physics step lost between simulation execution and logging.

## Reanalysis of retained development evidence

No new research-study episodes were run. The adjacent regression suite includes development-only simulation fixtures; those runs are tests, not a new study or confirmatory evaluation. Both retained v1 and v2 ledgers were analyzed into **new**, exclusive-create output files; existing raw files and summaries were not overwritten.

| Retained condition | Window | Samples | Last speed (m/s) | Target-distance change (m) | Sampled polyline (m) |
|---|---|---:|---:|---:|---:|
| Nominal bias, anchor recovery | ABSTAIN extension | 25 | 0.020553 | +0.018232 | 0.018238 |
| Nominal bias, recovery monitor | ABSTAIN extension | 25 | 0.179194 | +0.121794 | 0.159009 |
| Heavy bias, anchor recovery | STOP extension | 50 | 0.010733 | +0.002758 | 0.035950 |
| Heavy bias, recovery monitor | ABSTAIN extension | 25 | 0.097289 | -0.028471 | 0.086330 |

The STOP condition illustrates the distinction: target distance changed only about **2.8 mm**, while its sampled polyline was about **35.9 mm**. The nominal-bias monitor continued roughly **159 mm** along its sampled polyline after the original abstention brake, ending with approximately **0.179 m/s** residual speed. These describe already recorded active truth-state braking in one repeated development world, not independent reliability trials or new experimental discoveries. They do not show passive stopping, indefinite stability, acceptable dwell or real-world safety. No collision flag was present in these recorded extension samples; that does not establish zero risk.

## Tests, failures and incomplete evidence

Initial targeted verification: 37 passed. Added an out-and-back trajectory test to distinguish polyline from radial change and exercise rising speed and partially missing residuals; final verification: **38 passed in 3.16 seconds**. This comprises 12 new synthetic tests and 26 adjacent physical-event, ledger and post-abstention regression tests, not the full repository suite. `git diff --check` passed.

Command:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_recovery_motion_summary.py tests/test_recovery_physics_events.py tests/test_recovery_physics_ledger.py tests/test_recovery_post_abstention.py
```

New synthetic cases cover interrupted assignments with partial or complete observation counts, no samples, an untouched assignment, original-brake anchoring, a collision flag, invalid anchors, changing targets, horizon overruns, input replacement, unknown residuals, out-and-back motion and exclusive-create output protection. Expected invalid cases reject rather than producing a statistical failure/pass. Missing and interrupted windows are retained as such. There were no unexpected test or analysis failures in this run. Existing prior interruption/sink-failure tests remain included in the adjacent suite.

## Evidence and identities

- New analyzer: `scripts/research/summarize_recovery_motion.py`.
- New tests: `tests/test_recovery_motion_summary.py`.
- New v1 summary: `results/research_development/analysis/recovery_motion_observations_2026-11-01_v1.json`.
- New v2 summary: `results/research_development/analysis/recovery_motion_observations_2026-11-01_v2.json`.
- Selected source/input/output hashes, command, parent identity and limitations: `results/research_development/analysis/recovery_motion_verification_2026-11-01.json`.
- Retained v1 raw SHA-256: `359ae6f7e6f1de3fd99609c21cf9cdfa3d440f39a5234d8cfb45addeaafeaa2f`.
- Retained v2 raw SHA-256: `48136174812afb4e852732d314b88bbd1b8e87dd4f860cec98c85902dd72fecf`, agreeing with the earlier post-abstention report.

## Next work and unresolved decisions

1. Record immutable runtime timestep/actuator-model metadata in a separately versioned future development runner before computing elapsed-time or stopping-time endpoints. Do not backfill old ledgers from current source.
2. Specify a development-only estimated-state fallback arm and its measured versus truth-only inputs, including actuator lag, sensor-loss response and continuous monitoring. Current braking still relies on simulator truth and idealized compensation.
3. Before any physical-stop acceptance or confirmatory claim, document application-specific speed, spatial envelope, dwell, sensor freshness, collision observation, incomplete-data and failure handling; obtain the owner's decision and appropriate independent control/safety/statistical review. This tooling does not choose or approve those criteria.
4. Keep independent units, paired development conditions and partial observation coverage explicit. Do not count physics samples as independent reliability episodes.

Existing scientific/security/release blockers remain open. **Gate B remains `GATE_B_NOT_AUTHORIZED`.**
