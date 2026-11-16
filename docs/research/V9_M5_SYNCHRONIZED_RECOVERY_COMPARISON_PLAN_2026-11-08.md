# Synchronized recovery comparison — implementation-ready development plan

**Status: PROPOSED DEVELOPMENT DESIGN; NOT EXECUTED. `GATE_B_NOT_AUTHORIZED`.** This is a source-backed engineering plan and a closeout check of retained fixture evidence. It does not change scientific acceptance criteria, authorize a confirmatory study, establish safe stopping or supply independent statistical approval.

## Current evidence checked in this run

Inspected branch `codex/research-hardening`, parent `74b0bfab8e57cd450293e49de881207074df3141`, uncommitted changes and `AI_RESEARCH_TEAM_CHARTER_2026-10-31.md`. Existing changes and evidence were preserved.

The prior fixture-development turn stopped after exporting artifacts. This run checked their presence, source/input/output hashes, test XML and semantic analysis from the retained raw ledger:

- `synchronized_fixtures_v1_2026-11-07.jsonl`: FINALIZED, six COMPLETED engineering assignments and 14 persisted integration steps.
- Recomputed semantic output exactly equals the retained summary.
- The retained 78-test XML has zero failures, errors or skips. **These tests ran on 7 November; they were not rerun in this turn.**
- All selected current source and retained-input hashes still match the prior verification record; prior raw/summary/XML hashes match the exported artifacts.
- `git diff --check` passed. This is a consistency/retention check, not an independent attestation or full-suite rerun.

References: `V9_M5_SYNCHRONIZED_FIXTURE_LEDGER_2026-11-07.md` and `results/research_development/analysis/synchronized_fixture_verification_2026-11-07.json`. No new recovery episodes, research simulations or confirmatory evaluations were executed in this turn.

## Scientific question and scope

Proposed question: in one deliberately reused development world, how do the two existing recovery controllers' trajectories, decisions and post-action observations differ between legacy mixed-phase simulation and the opt-in synchronized environment?

This is an implementation diagnostic. It does not estimate population risk, generalization, statistical significance or power. The experimental intervention includes refreshed CBF inputs, refreshed physical observations and possible derived solver-state effects. It cannot isolate a pure reporting-only correction.

The next runner must use a **new study identity**, separately versioned reader and explicit environment labels. Do not reuse the fixed-fixture study identity: its validator requires exactly its own six fixtures. Do not make the old physical-evidence reader infer new phase semantics from an environment name.

## Proposed exact assignment plan

Reuse known development seed **2256000** only; record that it has already been inspected and is not a confirmatory seed. Cross:

- Environment: legacy `AegisMuJoCo3DEnvironment` versus `SynchronizedAegisMuJoCo3DEnvironment`.
- Controller: `AEGIS_3D_ANCHOR_RECOVERY` versus `AEGIS_3D_RECOVERY_MONITOR`.
- Vector bias: `[0,0,0]` versus `[0.8,0.8,-0.3]`.

This creates **eight declared assignments**, forming four environment pairs. They are dependent trajectories in one reused world, not eight independent reliability trials.

Proposed execution settings, reused from prior exploratory diagnostics: maximum 400 decision steps, recovery budget 100, `DIRECTION_PRESERVING_PEAK` navigation, 50 post-STOP steps and 25 extra post-ABSTAIN steps. These are development observation horizons/budgets, not acceptance thresholds. Explicitly set and record all remaining function arguments, including zero range/anchor/velocity biases where applicable, zero dropout/latency/replay, unit velocity scales and `fail_vectors_after_stop_proposal=False`; do not rely on future-changing defaults. Pin the actual argument map and source hashes before execution.

Evidence: `scripts/research/study_recovery_physics_evidence.py` defines the existing two controllers, biases, method and budgets; `experiments/benchmark_physical_3d_cbf.py:80` onward defines the sensor/fault argument surface. The target/reset process is in `src/aegis/env/mujoco_3d_cbf.py:354–377`.

## What is actually matched, and what is not

| Input/process | Source evidence | Proposed pairing rule and interpretation |
|---|---|---|
| World/reset target | Benchmark lines 149–159 split environment and sensor streams; reset at line 160. Environment lines 364–374 sample target. | Same development seed and same reset implementation should yield identical initial position/velocity/target. Persist and compare actual reset values before calling it matched. |
| Vector A/B and raw range noise | Benchmark lines 253–257 draw two 3-vectors and one scalar from the sensor stream each decision iteration. | Audit common **decision-step prefix** noise innovations. Sensor values themselves must differ when trajectories differ. Do not require equal measurements. |
| Velocity noise | Benchmark lines 465–469 draw from a separate velocity stream on each iteration for these recovery controllers. | With proposed zero latency/dropout/replay and scale one, audit `velocity_observation - recorded_velocity` over the common step prefix. This is coupling by step index, not proof that hardware would deliver identical readings. |
| Anchor noise and dropout | Benchmark lines 448–459 draw only when `next_query_anchor` is true. | The common seed couples anchors by **query ordinal**, not necessarily by decision time. Record query ordinal, request/delivery step and validity. Differing request times/counts are part of the controller response. |
| Range faults | Benchmark lines 258–267 condition dropout draws and maintain a latency history. | Explicit zero dropout/latency in the initial diagnostic avoids ambiguity. Any later fault study needs its own recorded matching rule. |
| State, force and CBF inputs | Benchmark lines 245–250 consume environment state; environment `step()` uses truth position/velocity. Synchronized module lines 20–37 refresh before/after integration. | These are expected to differ after trajectories diverge. The synchronized arm changes both observation and control-state timing; legacy values must retain their historical meaning. |
| Adaptive vector loss | Benchmark line 419 uses controller phase to activate targeted loss. | Disabled explicitly in this first comparison. Enabling it later creates intervention times that depend on each arm's decisions; it is not a fixed common fault timeline. |

**Finding from source inspection:** same seed alone is insufficient to claim all sensor observations are aligned in physical time. The code already separates random streams; this is not a finding that all random-number pairing is broken. Query-indexed anchor coupling is a defensible exploratory choice if declared and audited. Replacing it silently with timestep-indexed anchors would change the coupling/design and should receive a new study identity and explicit rationale. No random process was changed in this turn.

For the proposed query-indexed design, common prefix means only steps observed in both arms. Differences in terminal time cause unequal coverage; the absent tail must not be imputed or counted as agreement. Common anchor-query count can likewise be smaller than either total query count. Raw post-action braking extensions contain physical steps without new sensor decisions; do not invent sensor draws for those steps.

## Required new runner/ledger contract

1. Persist all eight assignment identities, explicit arguments, environment/module source identities, parent commit and dirty-source map before any assignment starts. Preserve complete selected-file coverage, runtime versions and model configuration/timestep per arm. These remain self-reported provenance, not authentication.
2. Record RESET before any decision: qpos/qvel, reported position, target, actual time/timestep, model identity and explicit phase. The legacy environment has no built-in environment ID; any wrapper label is a development metadata label, not an authenticated upstream version.
3. Record each DECISION with observed state, sensor readings, raw range, velocity reading, anchor request/delivery/ordinal, command and the time/phase represented by every state field. Legacy position and velocity are mixed-phase; do not stamp them as synchronized post-integration state.
4. Record each PHYSICS transition incrementally, including actual runtime time, phase, qpos-derived translation, reported position/velocity, contact/clearance fields, command/projected force and pre-integration CBF diagnostics. Synchronized state and transition-control diagnostics have distinct phases. Preserve the terminal integrated sample and both post-action horizons.
5. The current benchmark callback strips several environment timestamp/phase fields (`emit_physics` around lines 212–230). A new adapter must obtain and persist them explicitly, or a separately identified instrumentation extension must emit them. Do not infer historical phases after the fact from current source.
6. Keep STOP/ABSTAIN/timeout/error labels as existing development outcomes. Record observed motion descriptively; mark physical-rest/dwell acceptance **NOT EVALUATED** until an operational criterion exists. Do not derive scientific acceptance from execution completion or controller labels.
7. Ledger/sink failures must abort without terminal retry or automatic rerun. Persist ERROR for ordinary execution failures with their partial evidence. Detect source/runtime changes; retain assigned/unstarted cases. Record source/runtime checks on failed paths as well as completed paths.
8. Reader must reject wrong study identity, omitted assignments/metadata/source coverage, contradictory geometry/contact/collision flags, phase/time/count inconsistencies and impossible terminal coverage even with a valid rehashed chain. Preserve unresolved/incomplete evidence explicitly.

## Comparison output and missing evidence

Report all eight declared assignments and the four named environment pairs. For each, show execution status, decision/physics counts, decision-time labels/distances, sensor/query coverage and observed post-action speed/distance/contacts. Separate observation-window completion from episode execution completion and from any scientific claim.

Proposed handling for this development diagnostic:

- An execution error, source/runtime drift or incomplete required evidence makes that pair **not evaluable for the requested comparison**, with a reason. Keep both raw assignments and the declared denominator of four pairs visible.
- No matching baseline/environment counterpart: report missing counterpart; do not substitute a nominal controller, another bias condition or historical run.
- Contradictory evidence: reject semantic comparison rather than choose whichever status looks more favorable; retain the raw bytes and diagnostics.
- Unequal successful trace lengths: compare innovations only on the common prefix and show unmatched tail counts. Do not treat the shorter arm as zero motion/no collision after it stops logging.
- No observations: use missing/null values, not zeros or a collision-free label.
- A completed post-action horizon permits descriptive sample summaries only; it does not supply safe-rest or infinite-horizon stability evidence.

These are proposed engineering reporting rules for a future new development study. They do not amend V9-M4 H1–H5, multiplicity, gatekeeping or approved acceptance decisions.

## Required tests before the proposed eight-assignment run

- Verify exact eight-case manifest and all four counterparts, with fixed explicit argument maps and complete source/runtime identities; missing/reduced manifests must reject.
- Verify reset world/target equality across each environment pair while leaving arm-specific phase labels distinct.
- Use short synthetic executions to reconstruct vector/range/velocity innovations over the common prefix; compare against the documented seeded stream schedule within an explicitly numerical floating-point tolerance. This tolerance is an engineering equality check, not a scientific acceptance threshold.
- Force differing anchor request times/counts and verify query ordinals, step/time metadata and common-query coverage. Do not assert time-aligned anchor observations from ordinal matching.
- Inject early STOP/ABSTAIN/timeout and verify correct terminal physical sample count and post-action timestamps; test no silent sensor sampling during braking-only extensions.
- Exercise missing counterpart, omitted assignment, shifted phase/time, false collision flag, source/runtime drift, execution exception, sink failure and child-process exit. Confirm no automatic retry or successful classification of missing evidence.
- Verify the new runner leaves legacy behavior and all existing frozen/historical files unchanged, and the old readers continue to reject unsupported new study identities.

The current 78-test fixture suite is a prerequisite, not evidence that all these policy-runner tests exist or pass.

## Questions for future independent review and remaining work

A future confirmatory claim needs independent review of the unit of replication, number and selection of independent worlds, conditional anchor/query process, paired censoring/unequal duration, endpoint definitions, missing-data rules, uncertainty/multiplicity and power. This one-world development diagnostic cannot answer those questions statistically.

The environment still uses simulator-truth CBF inputs, and the benchmark uses truth velocity in ordinary damping (`benchmark_physical_3d_cbf.py:605`) and active braking. Synchronization does not establish non-oracle control. Callback/solver/warm-start effects and sensor/actuator realism remain limitations. No hardware or safety certification claim follows.

Next implementation task: build the separately versioned recovery runner/reader and the tests above, then execute the declared development comparison with preserved raw evidence. This document supplies the concrete plan; it does not assert that implementation or comparison has happened. Existing scientific/security/release blockers remain open. No Final Release Commit was created and **Gate B remains `GATE_B_NOT_AUTHORIZED`**.
