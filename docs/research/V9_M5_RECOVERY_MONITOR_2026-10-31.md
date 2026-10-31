# V9-M5 exploratory post-proposal monitoring candidate

**Status:** exploratory development, integrated into a separately named simulation benchmark arm after initial synthetic tests; not a V9-M4 evaluator, not a safety-certified component, and not tested on a real robot. Gate B remains `GATE_B_NOT_AUTHORIZED`; this work did not access reserved Holdout seed contents or outcomes, run Holdout, or create a production authorization ticket. See the separate ledger study for the subsequent small simulation run.

## Problem and candidate

The prior exploratory `AnchorRecoveryCandidate` does not call its base controller's monitor while it handles BRAKING, ANCHOR or RECOVERY phases. Consequently, invalid or missing vector data could escape the candidate's confirmation path even if range and anchor were valid. The separate `RecoveryMonitorCandidate` in `src/aegis/v9/recovery_monitor_candidate.py` tests a stricter development policy:

1. After the wrapped base proposes STOP and the candidate begins braking, inspect both vector sensor observations and the range observation on every BRAKING, ANCHOR and RECOVERY update.
2. Require two `SensorReading` objects with valid, non-dropped, non-anomalous, finite 3D vectors and positive finite declared sigma; require a valid non-anomalous range. Missing, malformed, or explicitly anomalous data immediately returns and latches `ABSTAIN` with a zero action and no anchor request.
3. Feed the three raw vector/vector and vector/range discrepancies into a **separate monitor** with the existing 3D channel construction. A monitor alarm or invalid monitored input returns and latches `ABSTAIN`. Reject a subsequent change in the declared sigmas rather than silently applying a fixed initial noise model to a different reported one.
4. On valid observations, delegate the actual braking, anchor confirmation and bounded recovery decisions to the existing exploratory candidate. The observer does not call the base controller update again, so it does not execute an extra navigation/anchor/calibration step.

The independent post-proposal monitor starts at the first update *after* the original STOP proposal. It does **not** import or continue the base Ville monitor's wealth/history. No automatic claim of continuous original monitoring, nominal false-alarm control, confidence level, risk limit, or closed-loop safety follows. It uses raw vectors, as in the base monitor, so an existing or drifting common sensor bias, model mismatch or anchor correlation can cause persistent alarms or evade disagreement; the reference distributions, thresholds and assumptions require prospective independent evaluation. Its zero action on `ABSTAIN` is an interface signal; safe braking depends on the integration/actuator safety layer.

## Synthetic verification

The dedicated regression checks (`tests/test_recovery_monitor_candidate.py`) cover:

- Missing one or both vectors, dropped/anomalous/nonfinite vectors and malformed flags in each of BRAKING, ANCHOR and RECOVERY.
- Missing, malformed, dropped and anomalous range in each monitored phase.
- Monitoring steps advancing during braking, anchor confirmation and recovery, without injecting a second base control call.
- A later explicitly anomalous vector and an e-process alarm causing latched abstention.
- Declared-sigma changes and extreme finite sigma causing a monitor initialization overflow failing closed, and reset clearing monitor history.
- Successful confirmation on valid synthetic observations, with the candidate still returning the original controller's STOP only after the additional checks.

The focused suite has **39 tests**. The candidate plus adjacent recovery, sustained-arrival, 3D controller and malformed-input tests passed **119 tests** using:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_recovery_monitor_candidate.py tests/test_anchor_recovery_candidate.py \
  tests/test_stabilized_arrival_candidate.py tests/test_sustained_stop_candidate.py \
  tests/test_3d_aware_controller.py tests/test_exploratory_sensor_validation.py
```

These tests use synthetic sensor fixtures and deterministic mocked STOP proposals. They do not establish operating performance, calibration, safety under common-mode failures, or real-world false-alarm rates.

## Outstanding work

- Expand testing of the separately named development-only benchmark arm while retaining original arms and outputs. Its selected-file hashes do not provide complete source provenance.
- Evaluate matched development scenarios for both false positives and sensor-loss/anomaly detection, retaining all assigned episodes, incomplete/error outcomes, and post-stop behavior. Inputs must include realistic observation timestamp, missingness and calibration assumptions. Do not tune against a confirmatory set.
- Establish real sensor timing/age and trusted provenance contracts. This wrapper cannot determine whether an otherwise plausible reading is replayed or falsely time-stamped; it does not validate anchor or velocity provenance itself.
- Review how to preserve or deliberately restart monitor evidence at phase transitions, including handling prior alarms, calibration error, measurement distributions and correlated faults. Obtain appropriate independent statistical and control review before asserting any monitor guarantee.
- The simulator still uses ground-truth velocity in portions of braking and damping. A separate no-oracle arm and eventually real sensor recordings with independently measured ground truth are needed before claiming real-world relevance.
