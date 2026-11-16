# Opt-in synchronized development environment — implementation and tests

**Status: IMPLEMENTED AND TARGETED TESTS PASS; broader experiment integration pending. `GATE_B_NOT_AUTHORIZED`.** This is a separate development simulation component, not a frozen-artifact change, statistical rule, release decision, confirmatory result or real-robot validation. No Holdout outcomes/reserved seeds, production tickets, commit, push or external publication were involved.

## Problem addressed and chosen scope

The preceding `V9_M5_STATE_PHASE_FINDING_2026-11-07.md` reproduced mixed state phases: after integration, the legacy environment reports cached position with updated velocity. The next scoped task was to implement and test an explicitly identified alternative without silently changing historical trajectories or benchmark defaults.

Inspected `codex/research-hardening` at parent `74b0bfab8e57cd450293e49de881207074df3141`, its uncommitted changes and `AI_RESEARCH_TEAM_CHARTER_2026-10-31.md`. Preserved existing files and evidence. Added the new module, its tests, this report and new verification artifacts; no existing environment, benchmark or prior analyzer was modified in this run.

## Implementation and phase contract

New module: `src/aegis/env/mujoco_3d_synchronized.py`.

Class: `SynchronizedAegisMuJoCo3DEnvironment`.

Identity: `AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT`.

The class explicitly subclasses the legacy environment, with an alternative `step()` pipeline:

1. Run `mj_forward` on live data before constructing CBF inputs. This refreshes position-dependent quantities, including after an explicit external state edit.
2. Execute one legacy step/integration, preserving its control and CBF diagnostic values.
3. Run `mj_forward` after integration and replace physical observation fields with the refreshed observation.
4. Stamp the **returned step observation** with environment identity, the actual runtime timestep, control interval start time, simulation time and distinct phase labels.

`state_phase=POST_INTEGRATION_FORWARD_REFRESH` applies to the refreshed physical observation. `control_diagnostics_phase=PRE_INTEGRATION_CBF` applies to the selected force, feasibility/projection information and CBF residuals associated with the transition. These diagnostics are not recomputed as post-integration certificates.

There is still exactly one integration per `step()`. Repeated `get_state()` reads after a step do not integrate or perform additional forward passes, and returned position arrays are independent copies.

**Integration boundary:** inherited `reset()` and direct `get_state()` outputs do not receive the step-only identity/timestamp fields. Future runners must record `ENVIRONMENT_ID`, model/runtime metadata and timestep in their assignment header before execution, and separately identify reset versus transition versus post-step observations. Do not rely on the reset dictionary to infer the simulation arm or timestep. The new class is not imported by the default benchmark or substituted into existing studies.

## Solver and callback consequences

Extra live forward passes can change derived solver/warm-start state and invoke installed MuJoCo callbacks. The tests validate the intended callback-free pipeline and compare it with an explicit manually refreshed reference. They do **not** establish equivalence to a legacy trajectory, absence of callback side effects, all integrators, or general MuJoCo model correctness. Applications with callbacks require additional validation before using this arm. Source state and environment identity must remain explicit in any future paired study.

The legacy implementation remains available and its known timing discrepancy is still characterized by a passing regression test; the default simulator bug is not silently declared resolved. Historical logs retain their original time semantics and are not reclassified.

## Verification and review

Initial targeted run: **56 passed in 6.42 s**. An AI code-review agent found no material blocker in the scoped opt-in pipeline and suggested obstacle-contact, horizontal-boundary and metadata/callback checks. Added the two physical crossing fixtures and documented the remaining integration limitations. The agent's review is not an independent control, statistical, security or safety approval.

Final targeted run: **58 passed in 5.99 s**, comprising **13 new tests** plus the 45 adjacent timing/physics/ledger/motion tests from the previous run. No unexpected failure or incomplete test was recorded. This is not the full repository suite. `git diff --check` passed.

New tests cover:

- Six timestep/speed cases: synchronized position matches integrated free-joint translation, velocity matches the same integrated state and distance uses that position; timestamps/counts show exactly one integration.
- Explicit external position/velocity changes are refreshed before the CBF sees them.
- Floor and spherical-obstacle contacts are detected at the integrated state when crossing into collision; these intentionally unsafe synthetic initial conditions do not assert controller safety.
- A horizontal arena-boundary crossing produces negative post-integration clearance rather than a stale pre-crossing observation.
- Ten acceleration/braking transitions match the explicit refreshed reference pipeline, including force/CBF transition diagnostics.
- Repeated read queries preserve time, qpos/qvel and step count; mutating a returned observation does not mutate the simulator.
- The legacy default retains its identifiable one-step position lag.

Tests were run with bytecode and pytest-cache writes disabled and a temporary test directory. MuJoCo 3.14.0, NumPy 2.5.3, Python 3.12.14 were recorded. Selected source and retained-development-input hash maps before/after execution agree. The raw development ledger hashes also agree with the previous retained values. These are consistency checks, not independent authentication or complete dependency closure.

## Artifacts and reproduction

- Tests: `tests/test_synchronized_3d_environment.py`.
- Verification record with exact command, runtime, stdout/exit status and selected hashes: `results/research_development/analysis/synchronized_state_verification_2026-11-07.json`.
- Per-test results: `results/research_development/analysis/synchronized_state_tests_2026-11-07.xml`.

The final command is recorded verbatim in the verification JSON. Its test scope is:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -p no:cacheprovider -q tests/test_synchronized_3d_environment.py tests/test_state_phase_diagnostic.py tests/test_recovery_motion_summary.py tests/test_recovery_physics_events.py tests/test_recovery_physics_ledger.py tests/test_recovery_post_abstention.py
```

The record identifies a dirty working tree and its parent; it is not a new release identity. Repository writes used scoped filesystem escalation approved for these authorized new development files. Earlier reports, raw artifacts and existing user changes were not overwritten.

## Next development task and open limitations

Integrate the new environment into a **separately versioned, development-only runner and ledger contract** with arm identity and actual timestep/model configuration in every assignment. Record pre-action control diagnostics and synchronized post-step observations separately; test interruption, logging failures, reset metadata and final integrated sample retention. Then run a small declared matched development comparison, retaining all errors and incomplete assignments. Existing ledger validators must not accept the new semantics under an old study identity by inference.

A later comparison may change decisions and trajectories because the CBF now sees a different, synchronized state. Do not infer corrections to old outcomes from the engineering tests. Still unresolved: estimated-state versus simulator-truth control, actuator realism, sensor-loss/fallback behavior, continuous monitoring, approved stopping/dwell endpoints, independent units and missing-data/statistical rules. Timing synchronization alone does not establish safe stopping or safety certification.

Scientific/security/release blockers remain open, no Final Release Commit was created, and **Gate B remains `GATE_B_NOT_AUTHORIZED`**.
