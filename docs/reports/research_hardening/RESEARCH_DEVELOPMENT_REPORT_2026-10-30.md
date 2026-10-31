# Research development and safety hardening — 2026-10-30

**Scope:** exploratory simulation and synthetic regression testing. Base commit: `f0cbe3216881b9f6cb67b00d9d051e6f8af0b9ce` on `origin/main`. Changes are in the working tree of `codex/research-hardening`; source identities below describe the tested files, not a release commit.

The latest base already addressed several earlier findings: it removed the empty-core H2 fallback, added watchdog startup checks and an air-brake branch, and cleared arrival samples on range dropout. This work tests those changes and addresses additional input-boundary failures. It does not authorize Gate B, run a confirmatory Holdout, access reserved seed contents or raw Holdout outcomes, change frozen artifacts, or approve new H1–H5 decision rules.

## Reproduced defects and changes

| Area | Reproduction before change | Development fix | Limits |
|---|---|---|---|
| Watchdog clocks | Odometry and perception timestamps of `1000` evaluated at `10` yielded `HEALTHY_NOMINAL` and `NONE`. | Future timestamps trigger a non-nominal action; the invalid timestamp is cleared for recovery. Invalid evaluation clocks also fail closed. | Requires a common clock domain; real clock synchronization and tolerance need a platform-specific design. |
| Telemetry replay and malformed state | An older odometry packet overwrote a newer position; a NaN position was accepted. | Ignore nonfinite, nonpositive, duplicate, and out-of-order odometry/perception timestamps; reject malformed/nonfinite vectors and invalid quaternions before updating the state. | Invalid packets are ignored rather than retained as raw external telemetry; physical transport and independently monitored logging are not implemented. |
| Battery | Missing or NaN battery voltage could yield `HEALTHY_NOMINAL`. | Invalid/missing or future-dated battery telemetry causes a non-nominal recommendation; invalid and out-of-order updates do not replace good data. | No maximum battery-message age has been specified. The current hold recommendation is a simulated behavior, not a verified physical failsafe. |
| 3D vector inputs | A 2-component input raised `IndexError`; a NaN vector could enter monitoring. | Invalid shape, nonfinite vectors, and invalid vector sigma cause zero-action `ABSTAIN` and clear arrival samples. | Further sensor validity, freshness, uncertainty calibration, and control dynamics require study. |
| 3D range and anchor | A `valid=True` NaN range did not clear arrival evidence. An unqueried anchor and a NaN anchor were counted toward bias calibration. | Invalid range values/sigma act as missing observations; anchors must be queried, valid, finite, and 3D before calibration. | `RangeReading` carries no timestamp, so actual sensor freshness cannot be established from this interface. |
| Live ROS 2 transport | The node claimed to publish, but functions appended to Python lists and `_init_ros2_interfaces` created only a timer. | Document the in-memory simulation interface honestly; fail explicitly before live ROS 2 node initialization until real transport is implemented and validated. | This deliberately disables the incomplete live ROS path. No ROS 2 or PX4 system integration was tested. |

The synthetic regressions are in `tests/test_development_safety_hardening.py`. Tests for the latest upstream fixes remain in `tests/test_audit_regression_fixes.py`.

## Unresolved statistical and provenance findings

### H2 scenario identity contradiction

The preregistered protocol identifies `COMPOUND_DRIFT_DROPOUT` as scenario 11 outside core-10 (`docs/v9_experiment_protocol.md`, scenario table). The current `experiments/v9_evaluate_holdout.py` selects a core-10 row if **either** its name is core-10 **or** `scenario_index <= 10`. The latest upstream fix correctly handles an empty core-10 set, but the OR condition still accepts contradictory identity fields.

Using 100 **synthetic** valid episode records with scenario name `COMPOUND_DRIFT_DROPOUT`, index `1`, all accepted and no false successes, `evaluate_mixture_holdout(..., expected_n=100)` reports `n_core10=100`, `cp_ucb95=0.029513`, and `CONFIRMATORY_PASS`. This demonstrates a potential classification error; it does not establish that any historical Holdout record has such a mismatch.

**Proposed decision for owner and statistician:** specify a canonical mapping of scenario IDs/names, require agreement where both are provided, and classify missing or contradictory identity as unevaluable before calculating H2. Review the treatment of crashes in the selective-risk numerator as well. Adopt changes only after the controlling H1–H5 rules and historical-result handling are approved. No evaluator logic was changed by this work.

### Simulated ROS sensor monitor claim

`AegisROS2DroneNode.update_martingale_sensor_check` uses a heuristic multiplier and floors the wealth at one during recovery. In a synthetic sequence of residuals `0.1`, then `0.0`, the recorded wealth increased from `0.8464817248906141` to `1.0`. This sequence illustrates why the current implementation needs a formal conditional expectation argument before describing it as an anytime-valid supermartingale under a specified null. It is not evidence of a calibrated false-alarm rate. Independent statistical review should identify the null model, filtration, valid betting factors, recovery/restart policy, and familywise error accounting. This work does not alter the monitor's decision logic.

### V9-M4 published evidence

The [post-execution audit](../v9_m4_release_remediation/V9_M4_POSTEXECUTION_SOURCE_AUDIT_2026-10-29.md) concerns a historical snapshot. A later code fix does not by itself recalculate or independently authenticate historical Holdout outcomes, authorization, or provenance. Preserve the original evidence and issue any correction as a dated, reviewed addendum.

## Tests and simulation executed

```text
.venv/bin/python -m pytest -q \
  tests/test_development_safety_hardening.py tests/test_audit_regression_fixes.py \
  tests/test_sim2real_ros2.py tests/test_3d_aware_controller.py \
  tests/test_mujoco_3d_benchmark_integrity.py tests/test_aerial_resilience_engine.py \
  tests/test_mujoco_swarm_3d.py tests/test_swarm_decentralized_brmc.py \
  tests/test_quadrotor_6dof.py tests/test_nmpc_cbf.py tests/test_vision_slam_occlusion.py

69 passed in 1.60s
```

The complete test suite was not run because the existing `.venv` does not contain the project's `torch` dependency; these selected tests cover the changed areas and adjacent simulation components. Historical 380-test claims in other reports were not independently reproduced in this environment.

```text
PYTHONPATH=src .venv/bin/python experiments/benchmark_physical_3d_cbf.py \
  --seed-start 1234000 --n-seeds 3 --max-steps 100 --include-3d-aware \
  --output results/research_hardening/dev/3d_smoke_2026-10-30.json
```

This ran 7 arms × 3 bias settings × 3 development seeds = **63 episode records**. For the 3D-aware arm the observed result was 6 true successes, 0 false arrivals, and 3 timeouts out of 9; this tiny smoke run is not a safety estimate or a confirmatory experiment. Its JSON and console log are preserved separately:

The pure-Python `aegis_ros2` software-in-the-loop model also completed one 10-step development smoke episode using seed `1234000`: no recorded collision, two watchdog interventions, and 0.18 seconds of simulated flight. This checks the in-memory harness only and does not exercise live ROS 2, MAVLink, PX4, or hardware.

| Artifact | SHA-256 |
|---|---|
| `results/research_hardening/dev/3d_smoke_2026-10-30.json` | `ff873f92b23212e366d63bb17f4d54dedff8c9c13526a8e4ec8e439caaf4695c` |
| `results/research_hardening/dev/3d_smoke_2026-10-30.log` | `9be0e804e09e6d76d13b386df34df5ac3f6c20ee77d3789793ad5ef22a7447cc` |
| `src/aegis/v9/controller_3d.py` | `8e4172c73678fec4c08a8152ec962a56838822cd14c1a980b7b5e995f38f2997` |

The benchmark's JSON records hashes of the benchmark and simulation world, but not the 3D controller. The controller hash above is included to make this smoke-run dependency explicit. Source files and output hashes must be checked again if code is subsequently edited.

## Remaining next steps

1. Owner and independent statistician decide H2 scenario identity and missing-evidence rules, H1–H5 error accounting, and historical-result corrections; implement only after approval.
2. Specify and independently review the sensor-monitor null model and prove or recalibrate any proposed sequential risk guarantee.
3. Implement and test real ROS 2 subscriptions, publishers, timestamp conversion, watchdog isolation, and PX4 failsafe behavior in a suitable SITL/HIL environment; retain the live-mode block until verified.
4. Define battery freshness limits, clock skew handling, sensor-age metadata, and process-independent heartbeat monitoring for a named platform.
5. Complete a prospective V9-M5 protocol with joint safety/coverage outcomes, baselines, sample size, and fresh confirmatory data. Continue development in simulation while hardware is unavailable.

**Disposition:** exploratory engineering improvements verified in selected tests. Release readiness and confirmatory claims remain unverified; there is no real-robot validation.
