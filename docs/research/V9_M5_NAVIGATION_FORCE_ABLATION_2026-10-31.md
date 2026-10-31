# Direction-preserving force ablation

**Development simulation only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No reserved outcomes/seeds, production tickets, frozen artifacts or V9-M4 statistical rules were used or changed.

## Implemented candidate and design

`scripts/research/navigation_force_candidate.py` implements two explicit methods: componentwise AXIS_CLIP and DIRECTION_PRESERVING_PEAK, which scales the complete vector by one factor to keep the same maximum absolute component limit. Unsaturated vectors are identical. Saturated vectors differ in both heading and component magnitudes; this ablation does not isolate heading from force magnitude or prove a globally sufficient navigation policy.

`scripts/research/study_navigation_force.py` is a separate ideal-state micro-study. Both arms use exact simulator target, position and velocity, the same proportional gain 1.2, velocity damping 0.5, CBF, static known obstacle geometry, gravity compensation, initial condition and seed/world mapping. It bypasses arrival-monitor/sensor logic entirely, not the CBF. It applies all 800 steps without STOP classification; final closeness is not evidence of stationary or certified arrival. No baseline controller implementation was replaced.

The declared grid was seeds 2252000, 2253000, 2253001 crossed with both arms, 800 steps each. Seed 2252000 was intentionally selected from the prior failure, and is a diagnostic repeat. The other two development seeds were selected before this run without inspecting their outcomes. Six paired-arm episodes are not six independent worlds; there are only three worlds. A `/2` development ledger persists 4,800 post-physics observations, including requested/projected force, state, CBF residual and feasibility, and collision/safety flags. A crash after physics but before persistence can still leave unrecorded physical steps. No automatic retry is performed.

## Observed results

Distances in meters at step 800:

| Development seed | AXIS_CLIP | DIRECTION_PRESERVING_PEAK |
|---|---:|---:|
| 2252000, selected prior failure | 3.445450 | 0.055826 |
| 2253000 | 0.048694 | 0.048805 |
| 2253001 | 0.008466 | 0.008466 |

All six executions completed. No safety violation or residual above 1e-8 was recorded in this small idealized grid; this is not a safety guarantee. That numerical residual tolerance is an engineering diagnostic, not a new hypothesis acceptance threshold. Both methods can overshoot/oscillate and there is no arrival or stable-stop judgment in this study.

The selected-failure result supports force saturation geometry as a contributor to the previously reproduced stall. It does not show that this candidate fixes noisy-sensor recovery, every obstacle configuration, or seed 2252001. The next experiment must integrate the change only as a separately named development arm and retain matched sensor streams and full failure denominators. Route planning remains a separate candidate if this simple change fails in broader geometry.

## Evidence and verification

Raw: `results/research_development/dev/navigation_force_ablation_v1.jsonl`.

SHA-256: `6169d85eebfa1bb0dcf5ab0b4c95261f967dfe40d3a503b56ea9a182972e196d`.

Summary: `results/research_development/analysis/navigation_force_ablation_v1_summary.json`.

The analyzer reads one byte snapshot, verifies its hash chain, paired assignment grid, identity, step count, numeric state observations, state-derived distances, recorded collision flags/residuals and terminal summaries. Source maps are checked for before/after consistency, not independent authentication. Runtime metadata and source hashes are embedded in each assignment. Source snapshots are hash references, not bundled reproducible wheels or independent attestations.

Targeted tests passed 33 checks across candidate forces, real short MuJoCo integration, intentionally contradictory summaries/residuals, shared ledger behavior and progress diagnostics. `git diff --check` passed. These tests verify the described implementation/evidence properties; they do not establish scientific success.

Reproduce only into new output paths:

```bash
.venv/bin/python scripts/research/study_navigation_force.py --seeds 2252000 2253000 2253001 --steps 800 --output NEW_DEVELOPMENT_LEDGER.jsonl
.venv/bin/python scripts/research/analyze_navigation_force.py NEW_DEVELOPMENT_LEDGER.jsonl --output NEW_SUMMARY.json
```

## Next bounded development step

Add an opt-in force-guidance hook to a separately named recovery-study arm, without changing monitor/STOP rules or CBF constraints. Validate that only NAVIGATE/PROBE force requests are transformed, never VERIFY/STOP/ABSTAIN or recovery braking. Compare with the current noisy-sensor baseline under a declared matched development grid, preserving all timeouts, abstentions, false arrivals, collisions, missing-data events and execution errors. Include post-STOP speed and persistence diagnostics. Any broader claim still requires the applicable scientific/security approvals and a separately reviewed protocol.
