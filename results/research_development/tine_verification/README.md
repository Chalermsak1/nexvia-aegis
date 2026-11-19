# NEXVIA AEGIS — Tine Verification & Reproducibility Results

- **Lead:** Pattaradanai Kantamee (Tine) — Verification & Reproducibility Lead
- **Branch:** `tine/verification-suite`
- **Status:** `BLOCKED` · `GATE_B_NOT_AUTHORIZED`
- **Rule Compliance:** Read-only verification only — zero teammates' source files, frozen scientific rules, historical `results/`/`docs/`, `main`, or V9-M4 Holdout data were modified or accessed.

![NEXVIA AEGIS Verification & Reproducibility Summary](tine_verification_summary.png)

## Quick Summary

| Check | Scope | Result | Evidence |
| --- | --- | --- | --- |
| Existing Repository Baseline | Full `tests/` (excluding Tine probes) | **2,364 passed**, 3 failed, 4 errors (`c++` compiler absent in fresh WSL2) | `repo_baseline_output.txt`, `repo_baseline_junit.xml` |
| LIVE01 Core & Packaging | 5 LIVE01 test files | **125 / 125 passed** | Verified in WSL2 POSIX environment |
| Provenance & Source Parity | 6 summary files + 76 LIVE01 source files | **100% SHA-256 match (0 diffs)** | Phase 2 suite |
| LIVE01 Reproducibility Run | `nominal` vs `retimestamped_freeze` (140 steps) | `nominal`: **0** violations · `freeze`: **50** violations, **122** false leases, **115** false consumptions | `live01_repro_sample.json`, `live01_repro_audit.json` |
| Tine Anomaly & System Probes | Phase 1 (13) + Phase 2 (10) = **23 cases** | **11 passed**, **12 real defects exposed** (preserved as failing evidence) | `tine_anomaly_verification_output.txt`, `tine_phase2_verification_output.txt` |

## 12 Exposed System Defects (Preserved Without Weakening Tests)

| # | Area | Finding | Location | Actual Behavior Observed |
| :-: | --- | --- | --- | --- |
| 1 | LIVE01 | Future host timestamp accepted | `live_recovery_contract.py:96,128` | `emitted_host_ns` ahead of host clock returns `reason=None` |
| 2 | LIVE01 | Intra-epoch `clock_offset_ms` forgery | `live_recovery_contract.py:223` | Jumping offset `1000 -> 5000` in same epoch returns `critical=None` |
| 3 | LIVE01 | Malformed `STATUS` crashes controller | `live_recovery_processes.py:198` | `{"kind":"STATUS"}` exits `rc=1` (`KeyError: 'backup_requested'`) |
| 4 | LIVE01 | Malformed `HEARTBEAT` crashes watchdog | `live_recovery_processes.py:253` | `{"kind":"HEARTBEAT"}` exits `rc=1` (`KeyError: 'generation'`) |
| 5 | V9 | `NaN` state bypasses Observability Gate | `robust_tube_clbf.py:543` | `p_hat=[nan,0,0]` returns `CRUISING` instead of `EMERGENCY_STOP` |
| 6 | V9 | All-channel silent freeze blind spot | `v9/controller.py` | 60 identical frozen readings return `ACT` every step |
| 7 | V9 | No-oracle covariance estimator freeze blind spot | `sensor_corruption_suite.py:190` | Without `p_true`/`v_true`, frozen readings yield `is_blackout=False` |
| 8 | 3D | MuJoCo env passes simulator ground truth to CBF | `mujoco_3d_cbf.py:418-428` | `step()` feeds exact `data.xpos` & `data.qvel[:3]` to CBF & braking |
| 9 | 3D | 3D controller reads fault-injection `.dropped` flag | `v9/controller_3d.py:165` | Fails no-oracle trap (`AssertionError` on `.dropped`) |
| 10 | 3D | 3D controller fails to latch terminal `ABSTAIN` | `v9/controller_3d.py:184-198` | Resumes `NAVIGATE` on step 1 right after `ABSTAIN` on step 0 |
| 11 | 3D | 3D controller ignores range blackout in `NOMINAL` | `v9/controller_3d.py:229` | 15 dropped range steps in `NOMINAL` return `NAVIGATE` every step |
| 12 | 3D | 3D controller all-channel silent freeze blind spot | `v9/controller_3d.py` | 60 identical frozen 3D readings return `NAVIGATE` every step |

## Reports & Test Suites

- **Phase 1 Report:** [`docs/research/TINE_VERIFICATION_ANOMALY_REPORT_2026-11-18.md`](../../../docs/research/TINE_VERIFICATION_ANOMALY_REPORT_2026-11-18.md)
- **Phase 2 Report:** [`docs/research/TINE_SYSTEM_VERIFICATION_PHASE2_REPORT_2026-11-19.md`](../../../docs/research/TINE_SYSTEM_VERIFICATION_PHASE2_REPORT_2026-11-19.md)
- **Phase 1 Suite:** [`tests/test_tine_anomaly_verification.py`](../../../tests/test_tine_anomaly_verification.py)
- **Phase 2 Suite:** [`tests/test_tine_system_verification_phase2.py`](../../../tests/test_tine_system_verification_phase2.py)