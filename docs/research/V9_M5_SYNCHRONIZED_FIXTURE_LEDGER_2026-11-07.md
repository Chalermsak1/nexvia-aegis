# Synchronized fixture runner and evidence contract — development integration

**Status: implemented; targeted regression and six declared fixture runs completed. Governance: `GATE_B_NOT_AUTHORIZED`.** This run used synthetic simulation only. No Holdout outcomes/reserved seeds, confirmatory evaluation, production ticket, Gate B authorization, frozen artifact or unapproved V9-M4 statistical rule was involved. No commit, push, merge or publication was performed.

## Starting point and scope

Inspected branch `codex/research-hardening`, parent `74b0bfab8e57cd450293e49de881207074df3141`, working-tree changes and `AI_RESEARCH_TEAM_CHARTER_2026-10-31.md`. Existing user changes and all prior evidence were preserved. The preceding opt-in synchronized environment was tested, but lacked its own runner/ledger contract. The scoped next task was to persist its identity, runtime configuration, reset and each integrated step under a new study identity before attempting controller-policy comparisons.

New code: `scripts/research/synchronized_fixture_ledger.py`.

New tests: `tests/test_synchronized_fixture_ledger.py`.

Study identity: **`V9-M5 synchronized physics fixtures v1`** using `nexvia-development-ledger/2` and **`AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT`**. The old physical-evidence analyzer explicitly rejects this new study; it is not silently interpreted as legacy v1/v2 data. Existing runners, environment classes, analyzers and historical artifacts were not modified in this run.

## Declared engineering fixtures

The six cases and their initial conditions, timestep, requested count, target, zero desired command and braking mode are fixed in the versioned runner source and persisted in the header **before execution**. These are engineering checks, not independently sampled reliability episodes. The development reset RNG is explicit; no reserved seed source is consulted.

| Assignment | Runtime timestep (s) | Requested/persisted integration steps | Purpose | Collision flag in persisted steps |
|---|---:|---:|---|---|
| drift_10ms | 0.01 | 3 / 3 | Constant-velocity timing | false |
| drift_20ms | 0.02 | 3 / 3 | Constant-velocity timing | false |
| active_braking | 0.02 | 5 / 5 | Braking transition observations | false |
| floor_crossing | 0.02 | 1 / 1 | Deliberate floor crossing/contact | true |
| obstacle_crossing | 0.02 | 1 / 1 | Deliberate sphere crossing/contact | true |
| boundary_crossing | 0.02 | 1 / 1 | Deliberate horizontal-boundary crossing | true |

All six assignments completed, with six RESET records and **14 STEP records**. The ledger is structurally FINALIZED with no recorded execution errors. The three collision cases deliberately start with motion that crosses a physical constraint; their collision observations are preserved rather than filtered out. COMPLETED means the assigned engineering execution finished, not that an intervention is safe or scientifically accepted. The five-step braking case does not establish an acceptable stopping time or dwell endpoint.

## Runtime and phase contract

Each assignment records the environment identity, full dataclass configuration, actual compiled-model timestep, gravity, integrator, robot body mass/geom size, obstacle geometry and Python/NumPy/MuJoCo versions. Source-file hashes and Git parent identify the selected code state; the parent is not a new release identity and does not include uncommitted work by itself.

RESET is explicitly stamped `FORWARD_REFRESH_RESET`, with time/step zero and no transition-control diagnostics. Each STEP contains synchronized position, generalized free-joint translation, velocity, target, distance, contact/collision flags, clearances, interval start/end and the actual runtime timestep. Its physical phase is `POST_INTEGRATION_FORWARD_REFRESH`; its selected force/CBF residual phase remains **`PRE_INTEGRATION_CBF`**.

The dedicated read-only analyzer checks:

- Exact study/schema/environment identity and all six declared cases with their fixed initial/configuration/count contract.
- Complete declared runtime/configuration fields and the exact selected source-file coverage; a reduced hash map cannot masquerade as the declared manifest.
- RESET before STEP, exactly ordered integration counts, constant declared timestep and matching interval start/end times.
- Finite vectors/scalars, position agreement with recorded integrated free-joint translation, target/distance consistency and reset values matching the assignment.
- Boundary/obstacle clearances reconstructed from the recorded geometry, and collision flags consistent with recorded contact/clearance observations.
- Full requested evidence plus unchanged selected source/runtime metadata for COMPLETED assignments.

`persisted_step_seconds` describes the duration represented by persisted steps at the declared runtime timestep. It does not account for any physical step lost between integration and logging. With no STEP records, `collision_observed` remains null; missing observations are not positive evidence of no collision. A partial assignment retains STARTED/ASSIGNED/ERROR status separately from observed counts.

These checks establish internal consistency only. Header/runtime/geometry/source maps and step observations are self-reported. A consistent forged chain is not independently authenticated physical evidence or rollback protection.

## Persistence, failure and interruption handling

The existing ledger creates new paths exclusively, appends a record after each reset/step and requests fsync. START is persisted before executing an assignment. No existing output is resumed, repaired, truncated or overwritten.

Persistence/ledger failures propagate once without terminal retry. A normal execution exception records ERROR without retrying that assignment. Detected source drift and post-execution runtime drift stop further execution; remaining assignments stay unexecuted. A runtime mismatch found before reset is recorded as ERROR, and other distinct assignments may still be attempted; it cannot produce completed fixture evidence. Source drift on an execution-error path is also tested. A process-exit test after one persisted STEP leaves the first assignment STARTED and the other five ASSIGNED.

A crash can still occur after integration and before its event is persisted. The analyzer never invents that missing step. Filesystem/fsync requests and a hash chain do not prove power-loss durability, trusted storage, authentication or rollback resistance. Existing generic-ledger tests cover writer failure details; this run adds runner-specific failure scenarios.

## Review and regression evidence

An AI evidence-review agent reproduced three gaps in the first reader: contradictory collision flags could yield false collision-free summaries; reduced metadata/source maps were accepted; and a subset of fixtures could appear complete. These were engineering validator defects, not observed failures of the six final simulation cases. All three were corrected with adversarial valid-rehashed-chain tests. The reviewer re-read the updated files and found no additional material blocker in this scope. This is not independent statistical/security/safety approval.

Initial targeted run: **72 passed**. After the six additional hardening tests, final targeted run: **78 passed in 3.51 seconds**, with zero failures, errors or skips. This includes **20 new tests** and 58 adjacent synchronized-environment/state-phase/motion/physical-ledger tests. It is not the full repository test suite. `git diff --check` passed.

Tests include deliberate contradictory evidence, omitted metadata/source entries, missing planned cases, malformed phase/time/position/reset/terminal counts, source/runtime mismatch, sink failure, execution errors, source drift on an error path, actual child-process exit and existing-output preservation. Expected synthetic failures remain ERROR/STARTED/ASSIGNED or produce validation rejection; they are not reported as successful execution evidence.

Runtime for the actual fixture run: Python 3.12.14, NumPy 2.5.3, MuJoCo 3.14.0. Runner and analyzer both exited zero. Selected source/input hash maps before/after the actual run match. Prior v1/v2 development raw hashes remain unchanged. No unexpected failed/incomplete actual fixture run was recorded.

## Retained evidence and reproduction

- Raw new ledger: `results/research_development/dev/synchronized_fixtures_v1_2026-11-07.jsonl`.
- Raw SHA-256: `a6b0e59469f514892b727b2dd1b3266aa51823f09658ce1951ead0a19b8ff9e9`.
- New semantic summary: `results/research_development/analysis/synchronized_fixtures_v1_summary_2026-11-07.json`.
- Verification record: `results/research_development/analysis/synchronized_fixture_verification_2026-11-07.json`.
- Per-test results: `results/research_development/analysis/synchronized_fixture_tests_2026-11-07.xml`.

The raw ledger was originally written to a unique temporary path and copied byte-for-byte to the new repository evidence path after validation. The verification JSON preserves original command paths and output hashes; copying is not an independently authenticated execution. Repository writes used approved scoped filesystem escalation for these new files. Existing evidence was not replaced.

Reproduce only to **new output paths**:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python scripts/research/synchronized_fixture_ledger.py --output NEW_FIXTURE_LEDGER.jsonl
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python scripts/research/synchronized_fixture_ledger.py --analyze NEW_FIXTURE_LEDGER.jsonl --output NEW_SUMMARY.json
```

The targeted test files and pytest XML capture the regression scope. The new runner is intentionally a fixed engineering-fixture harness; it does not call the recovery-policy benchmark or implement H1–H5 decisions.

## Next task and remaining blockers

Next integrate synchronized observations into a separately identified **recovery-policy development study**, using this explicit runtime/phase and failure-handling approach. Specify matched inputs and what changes between legacy and synchronized arms; persist reset/control/post-action samples and all errors. Review warm-start/callback effects before interpreting policy differences. Do not compare a new synchronized trajectory with a legacy trajectory as if only an observation label changed.

Still unresolved: full recovery-runner integration, non-oracle estimated-state control, actuator/sensor realism, continuous monitoring and acceptable operational stopping/dwell endpoints. Confirmatory criteria, independent units, sample sizes and missing-evidence/statistical decisions remain subject to the owner's existing governance process. No release blocker is marked resolved by this development integration. The Final Release Commit was not created, and **Gate B remains `GATE_B_NOT_AUTHORIZED`**.
