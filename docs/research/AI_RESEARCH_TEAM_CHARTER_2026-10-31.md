# NEXVIA AEGIS AI research team — kickoff

**Date:** 2026-10-31 (Asia/Bangkok). This is a collaboration record, not an approval, release decision, safety claim, or permanent autonomous service. Agents are task-scoped and do not continue running after their work ends. The project owner remains responsible for project decisions; independent statistical and security review are not supplied by assigning AI roles.

## Team and remit

| Role | Initial assignment | Current outcome |
|---|---|---|
| Research and statistics agent | Review V9-M5 development design, dependence, endpoints and proposed next experiment | Read-only review completed; actionable issues below. |
| Simulation and control agent | Investigate controller, simulation and synthetic failure behavior | Read-only review and synthetic reproductions completed; actionable issues below. |
| Evidence and reproducibility agent | Audit development artifacts, analysis and retention | Read-only review and synthetic reproductions completed; actionable issues below. |
| Integrating research agent | Coordinate findings, implement scoped fixes, test and preserve evidence | Implemented the two evidence-accounting fixes described below. |

## Governance and boundaries

The work is exploratory V9-M5 development. Preserve historical artifacts and existing user changes. Do not access reserved V9-M4 Holdout seeds or outcomes, create or sign a production ticket, run Holdout, alter frozen artifacts or unapproved scientific decision logic, or authorize Gate B. The repository contains a published V9-M4 report and an audit noting unresolved authorization/protocol/evidence discrepancies; no new conclusion about the validity of a confirmatory claim follows from this kickoff. Do not represent simulated results as real-robot validation. Gate B remains `GATE_B_NOT_AUTHORIZED` under the owner's standing instruction.

## Kickoff findings and actions

1. **Evidence accounting fixed locally:** `analyze_dual_velocity.py` previously accepted the self-reported `sources_unchanged` flag without comparing the before/after SHA-256 maps. `dwell_diagnostics.py` could classify a STOP as passing dwell even when `false_arrival` conflicted with the unrounded decision distance. Both now reject or mark inconsistent evidence unevaluable, with synthetic tests. A matching self-reported hash map is not an independent attestation and does not establish the identity of all dependencies.
2. **Historical development log not tracked:** `results/research_development/dev/3d_probe_ablation_v2.log` exists locally and its SHA-256 matches the historical handoff, `0fa9386909d052d9a939b242f2de683231221e5e047a8baa4eb1a4be17965787`. It is ignored by Git and absent from the committed repository; a clean checkout therefore cannot retrieve it. Do not rewrite it or claim GitHub preserves it. Decide separately how to retain and publish evidence without changing historical bytes.
3. **Controller input validation:** A synthetic `RangeReading` with a nonnumeric distance can raise `TypeError` during confirmation rather than return abstention. Other invalid range/anchor values and recovery pathways need a scoped fail-closed input-validation fix and meaningful synthetic regression tests. No scientific threshold or registered evaluator rule should be altered to do this.
4. **Monitoring gaps:** The base monitor is not updated throughout experimental braking, confirmation and anchor-guided recovery. A synthetic observation also shows that loss of both vector sensors at confirmation can still permit STOP if other inputs appear valid. The appropriate failure behavior must be specified and tested; do not infer a violation of an unapproved protocol or a real-world guarantee.
5. **Simulation oracle:** Existing harness damping and simulated CBF braking use simulator ground-truth velocity, even when candidate decisions receive noisy measurements. Results cannot establish performance without this oracle. Add a separately identified non-oracle development arm with matched fault scenarios, and document every intentionally shared or unshared input before comparing.
6. **Evidence persistence:** Development runners collect records in memory before writing at the end. Interruptions can lose progress or leave incomplete files. A future append-only, crash-aware development ledger should preserve assignments and errors without silently rerunning episodes; synthetic failure and interrupted-write tests are required. Current selected-file hashes and self-declared manifests do not provide independent provenance.
7. **Statistics:** D0 simulation episodes sharing seeds across arms and scenarios, and time steps within an episode, are dependent. Do not interpret raw step counts as independent trials. Before any new confirmatory V9-M5 study, separately specify and obtain appropriate review of the independent unit, endpoint, denominator, missingness, baselines, sample size and multiplicity. Previously inspected development seeds are not confirmatory just because their numerical range differs.

## First prioritized work packages

1. Harden malformed sensor input handling in the experimental controller wrappers and test invalid/missing input and terminal behavior.
2. Design and test continuous monitoring throughout braking and recovery, with a clear sensor-loss policy, keeping the change in a separate exploratory arm until its behavior is evaluated.
3. Add a no-oracle simulation comparison and record control inputs, fault provenance, coverage, false arrivals, sampled dwell, collisions, abstentions and runtime costs. Do not reclassify old runs.
4. Add durable per-assignment records and test interruption/recovery and incomplete evidence; keep all raw outputs immutable and identified by their actual source state.
5. Investigate why the dual-velocity gate times out using pre-specified development scenarios and noise diagnostics. The 20-consecutive-sample rule can be restrictive under the simulated noise model, but a stationary analytical calculation is not an episode success probability.

## Verification at kickoff

The selected adjacent regression suite passed **146 tests** after the evidence fixes. The updated analyzers processed the retained dual-velocity development dataset into new temporary output paths; the input hash and summaries matched the historical analysis. The earlier outputs were not overwritten. This verifies those fixtures and this dataset only; it does not independently verify the simulator, underlying design, actual sensor behavior, V9-M4 claims, or all repository tests.
