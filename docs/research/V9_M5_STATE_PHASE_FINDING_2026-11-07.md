# V9-M5 development finding: post-integration state phase mismatch

**Status: REPRODUCED; environment remediation remains outstanding. Gate B: `GATE_B_NOT_AUTHORIZED`.** No V9-M4 Holdout outcomes/reserved seeds were accessed, no Holdout episodes or production tickets were created, and no frozen policy, registered statistical rule, release candidate or historical evidence was changed. This is simulation engineering, not real-robot validation.

## Finding and scope

The current development environment returns a mixture of state phases after `mj_step`: `robot_pos`/distance use cached Cartesian positions while `robot_velocity` uses the already integrated generalized velocity. In a simple constant-speed fixture, the reported position lags the integrated free-joint translation by one timestep. This is a reproducible measurement/interface defect and also affects the position supplied to the next CBF call. It is not an independent finding that a particular historical pass/fail outcome must change.

Source evidence in `src/aegis/env/mujoco_3d_cbf.py`:

- Lines 380–382: `get_state()` reads position from `data.xpos` and velocity from `data.qvel`, then computes target distance from that position.
- Lines 394–400: contact flags are also read from derived data. The present test quantifies position timing only; it does not establish exact contact-report corrections.
- Lines 417–424: the next environment call reads cached position and integrated velocity before constructing CBF constraints.
- Lines 434–438: `mj_step` advances integration and `step_count`, then immediately calls `get_state()` without refreshing derived position fields.
- `experiments/benchmark_physical_3d_cbf.py:564–581` and `:588–602` consume these returned observations for the post-ABSTAIN and post-STOP diagnostics.

MuJoCo's official computation documentation describes the distinction between integration state and derived quantities after stepping; its API reference states that `mj_forward` performs forward computations without integrating again. These sources support the explanation, while the measurements below establish behavior in the locally installed runtime:

- https://mujoco.readthedocs.io/en/latest/computation/
- https://github.com/google-deepmind/mujoco/blob/main/doc/computation/index.rst
- https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html

These are living documentation URLs, not immutable dependency snapshots. Local runtime versions and source hashes are retained with the reproduction.

## Isolated reproduction and diagnostic implementation

New `scripts/research/diagnose_state_phase.py` creates six explicitly synthetic, open-loop fixture cases: timesteps 0.01/0.02 seconds crossed with initial X velocity 0/0.1/0.5 m/s, three zero-command steps each. The model still applies its existing CBF and idealized gravity compensation. The development-only reset uses an explicit diagnostic RNG and fixes the target; it is not a confirmatory seed or policy evaluation.

After each legacy step, the tool copies `MjData`, runs `mj_forward` on the **copy**, and compares the resulting Cartesian position to the reported position and integrated free-joint translation. The live environment/controller data are not refreshed or modified by this diagnostic. This preserves the actual behavior under investigation instead of silently changing its trajectory.

| Runtime timestep (s) | Initial speed (m/s) | Position offset observed at each of 3 steps (m) |
|---:|---:|---:|
| 0.01 | 0.0 | 0 |
| 0.01 | 0.1 | 0.001 |
| 0.01 | 0.5 | 0.005 |
| 0.02 | 0.0 | 0 |
| 0.02 | 0.1 | 0.002 |
| 0.02 | 0.5 | 0.010 |

The copied forward position agrees with integrated `qpos[:3]` in this single free-body model. The position error equals timestep times velocity in these specific constant-velocity cases; this formula is **not** asserted for arbitrary acceleration, contacts, integrators, articulated bodies or old datasets.

## Implication for earlier development reports

`V9_M5_POST_ACTION_MOTION_DIAGNOSTICS_2026-11-01.md` and its JSON outputs remain preserved descriptions of retained samples. Their coordinate and target-distance observations should now be read as **legacy cached-position samples**, rather than fully synchronized post-integration physical states. Speed observations and position observations cannot be assumed to describe the same instant. The final integrated position may not be represented by the last cached position.

The prior residual-motion observations motivate further work, but exact stopping distance, synchronized stopping/dwell behavior, endpoint contact timing and CBF decisions require a separately versioned corrected experiment. Existing hash-chain and chronology tests establish the consistency of logged records, not the physical time semantics of their contents. None of the old records, summaries or outcomes were relabeled in this run. No statement that all old metrics are invalid or that any particular outcome flips follows from this diagnostic.

## Verification, identities and retention

Inspected branch `codex/research-hardening`, parent `74b0bfab8e57cd450293e49de881207074df3141`, uncommitted changes and `AI_RESEARCH_TEAM_CHARTER_2026-10-31.md`. Existing user files and changes were preserved. Added only this report, the diagnostic script/test and its result/verification files.

- Runtime: Python 3.12.14, NumPy 2.5.3, MuJoCo 3.14.0.
- New synthetic characterization tests: **7 passed**, included in a targeted **45-test** regression run, all passing in 7.07 s. This is not the full repository test suite.
- Tests explicitly check zero-motion control, two timesteps and two nonzero speeds, copied-forward/qpos agreement and preservation of live qpos/qvel/qacc/warm-start buffers/xpos/applied force/time/step count.
- Six declared fixture cases produced all 18 expected observations. No unexpected failed or incomplete case was recorded.
- Source SHA maps before/after the diagnostic match. This is selected-file consistency, not authenticated provenance or complete dependency closure.
- Output: `results/research_development/analysis/state_phase_reproduction_2026-11-07.json`.
- Output SHA-256: `bf52b668daff4a4b2f874f576baa82171b139221348251b0fff90a6bd81b65a3`.
- Verification record: `results/research_development/analysis/state_phase_verification_2026-11-07.json`.
- Repository write access required the environment's scoped filesystem escalation; it was approved automatically for creating new files. No original file was overwritten.

Reproduction:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python scripts/research/diagnose_state_phase.py --output NEW_OUTPUT_PATH.json
```

The output path must be new. Tests ran with pytest cache/bytecode writes disabled and a temporary test directory outside the repository.

## Remediation plan and completion conditions

1. Introduce a separately identified development environment/runner version with explicitly synchronized observations and pre/post integration timestamps. Keep legacy behavior identifiable for historical reproducibility. This is a technical recommendation, not a protocol amendment or authorization.
2. Review refresh placement both **before CBF inputs** and **after integration**. A position-only cache refresh is insufficient to assume contacts and all derived fields are current. A full `mj_forward` on live data can update solver-related derived state; test trajectory and warm-start effects rather than assuming equivalence. The diagnostic's copied forward does not itself fix live control.
3. Specify each logged field's phase: pre-action state, transition control/residual, integrated post-action state and contact observations. Do not label all of them as one instantaneous physical state.
4. Add regression cases for acceleration/braking, obstacle/floor contact, boundary crossing, terminal-step capture and repeated queries that must not integrate twice. Compare old/new development arms with matched explicit inputs and preserve their identities separately; do not retrofit old raw evidence.
5. Only after those semantics and changes are tested should new exploratory stopping/dwell estimates be produced. Any future confirmatory endpoint, acceptable threshold, sample size and missing-data rules still require the existing owner/independent-review process.

The model continues to use simulator-truth CBF inputs and idealized compensation. Fixing phase synchronization alone would not establish non-oracle control, hardware applicability or safety. Existing scientific/security/release blockers remain open; the Final Release Commit has not been created by this run, and **Gate B remains `GATE_B_NOT_AUTHORIZED`**.
