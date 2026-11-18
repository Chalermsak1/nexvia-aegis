# NEXVIA AEGIS Verification & Anomaly Detection Report

- **Author:** Pattaradanai Kantamee (Tine) — Verification & Reproducibility Lead
- **Branch:** `tine/verification-suite` (base commit `bc9d522`)
- **Date:** 2026-11-18
- **Release Status:** `BLOCKED` · `GATE_B_NOT_AUTHORIZED`
- **Scope:** Read-only verification, anomaly probes, reproducibility checks, and failure-evidence preservation. Zero teammates' source files, frozen scientific rules, `results/` history, `docs/` history, or V9-M4 Holdout data were modified or accessed.

## 1. Environment & Baseline Verification Summary

Tests were executed on Ubuntu 26.04.1 LTS (WSL2) using `uv` (`cpython-3.12.16`, `pytest-9.1.1`) with `/private/tmp -> /tmp` symlinked for POSIX UNIX-domain socket compatibility (`AF_UNIX` `SOCK_DGRAM`) and without altering source code or timeouts.

| Suite / Scope | Command Target | Result | Notes |
| --- | --- | --- | --- |
| LIVE01 core & packaging (5 files) | `test_live_recovery_{contract,processes,study}.py`, `test_chunk_development_evidence.py`, `test_package_temporal_feedback.py` | **125 passed** (56.59s) | Clean pass in WSL2 POSIX environment |
| Duties 2–6 targeted baseline (14 files) | No-oracle, observability gate, V9 controller, sensor corruption, freshness lease, security canonical/ledger, restart protocol/integration, durable executor, 3D reproducibility, randomization, forensics, physics ledger | **183 passed** (56.60s) | Clean pass |
| Full existing repository baseline | `pytest -q --ignore=tests/test_tine_anomaly_verification.py` | **2364 passed, 3 failed, 4 errors** (423.83s) | All 7 non-passes are in `test_safety_box_bridge.py` (3) and `test_cpp_micro_kernel.py` (4) due to missing `c++` compiler in fresh WSL2 image (`FileNotFoundError: 'c++'`) |
| LIVE01 2-case reproducibility + read-only audit | `scripts/research/live_recovery_study.py` (`nominal`, `retimestamped_freeze`) | **2 COMPLETED**, `audit` exit `0` | `nominal`: 0 violations; `retimestamped_freeze`: 50 violating segments, 122 false-premise leases, 115 false-premise consumptions |
| Tine anomaly & verification probes | `tests/test_tine_anomaly_verification.py` | **6 passed, 7 failed** (3.52s) | Strict invariant probes; 7 failures preserved as real counterexamples (not weakened) |

## 2. Verification Findings (`tests/test_tine_anomaly_verification.py`)

### Passed Invariants (6)
1. **No-oracle common-mode isolation:** `AegisV9Controller` with `_GroundTruthTrapReading` did not access `.bias`, `.drift`, `.anomaly`, or `.dropped` across 20 common-mode biased steps.
2. **Vacuous interval rejection in LIVE01:** `assess_frame` withheld `CONTINUE` for `position=["-0.49", "0.31"]` after `STATE_TUBE_WINDOW_V1` state transport exceeded `[-0.5, 0.32]`.
3. **Cross-artifact tampering detection:** Modifying `artifacts.json` against an intact `evidence_bundle.json` was rejected by `live_recovery_study.audit_frame`.
4. **V9 seed reproducibility:** `AegisPhysicalWorld` + `AegisV9Controller` (seed `71001`, non-Holdout) produced identical decision traces, final distance, and action-byte SHA-256 across two runs.
5. **3D MuJoCo non-Holdout reproducibility:** `run_3d_episode` (`AEGIS_3D_AWARE_CBF`, seed `2256000`, 10 steps) produced identical results across two runs.
6. **Review evidence consistency:** `six_outcomes.csv` (`batch == "main"`, 27 rows) matched `main_campaign_audit.json` row-for-row across steps, violating segments, unresolved effects, and false-premise consumptions, with `gate_b == "GATE_B_NOT_AUTHORIZED"`.

### Exposed Defects & Counterexamples Preserved (7)
1. **Future-dated host timestamp bypass (`live_recovery_contract.py`):**
   - `assess_frame` checks `start_host - emitted_host_ns > max_observation_host_ns` (staleness) without rejecting `emitted_host_ns > start_host`. A sample with `emitted_host_ns=5_000_000_000` at `host_clock=(1_000_000_000, 1_010_000_000)` passed (`reason=None`).
2. **Intra-epoch clock-offset forgery (`live_recovery_contract.py`):**
   - `select_samples` / `observation_problem` accepts per-packet `clock_offset_ms` so long as `remote_time == 20*tick + clock_offset_ms`, failing to flag a jump from `1000` to `5000` within the same `sensor-0` epoch (`critical=None`).
3. **Unchecked `NaN` / non-finite state in `RobustTubeCLBFController` (`robust_tube_clbf.py`):**
   - With `enable_observability_gate=True`, feeding `p_hat=[nan, 0, 0]` bypassed the covariance gate (`NaN > threshold` evaluates `False`) and returned phase `CRUISING` instead of failing closed to `EMERGENCY_STOP`.
4. **All-channel silent sensor freeze blind spot (`controller.py`):**
   - Feeding `AegisV9Controller` 60 consecutive identical valid readings (`[1.5, 0.0]`, `range=1.5`) produced `ACT` at every step without triggering `PROBE`, `VERIFY`, or `ABSTAIN`.
5. **No-oracle frozen-sensor blind spot in `OnlineCovarianceEstimator` (`sensor_corruption_suite.py`):**
   - When driven by an estimated predictor rather than simulator ground truth (`p_true`, `v_true`), a frozen sensor produces zero innovation residuals (`measured == predicted`) and never triggers blackout detection over 30 steps.
6. **Malformed `STATUS` datagram crashes LIVE01 `controller` (`live_recovery_processes.py:198`):**
   - Sending `{"kind": "STATUS"}` over `c0.sock` terminated the `controller` process (`rc=1`, `KeyError: 'backup_requested'`).
7. **Malformed `HEARTBEAT` datagram crashes LIVE01 `watchdog` (`live_recovery_processes.py:253`):**
   - Sending `{"kind": "HEARTBEAT"}` over `w.sock` terminated the `watchdog` process (`rc=1`, `KeyError: 'generation'`).

## 3. Preserved Evidence Artifacts

- Test suite: `tests/test_tine_anomaly_verification.py`
- Tine suite trace & JUnit XML: `results/research_development/tine_verification/tine_anomaly_verification_output.txt`, `results/research_development/tine_verification/tine_anomaly_verification_junit.xml`
- Full repo baseline trace & JUnit XML: `results/research_development/tine_verification/repo_baseline_output.txt`, `results/research_development/tine_verification/repo_baseline_junit.xml`
- LIVE01 2-case reproducibility output & audit: `results/research_development/tine_verification/live01_repro_sample.json`, `results/research_development/tine_verification/live01_repro_audit.json`