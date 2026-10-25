# NEXVIA AEGIS V9-M4 — Mock End-to-End Verification Report

**Document ID:** `AEGIS-V9-M4-MCK-15`  
**Milestone:** V9-M4 Confirmatory Holdout Evaluation — Mock End-to-End Verification  
**Git Branch:** `v9.0-runtime-assurance`  
**Reported Previous Commit:** `9c4c36f`  
**Date:** October 25, 2026  
**Status:** COMPLETE (End-to-End Pipeline Verified on Synthetic Fixtures)  
**Holdout Data Accessed:** FALSE (Zero real holdout data or reserved RNG streams accessed)

---

## CRITICAL NON-AUTHORIZATION DIRECTIVE

This document reports the synthetic mock verification and end-to-end testing of the NEXVIA AEGIS Milestone V9-M4 execution pathway. **This document does NOT constitute authorization to execute V9-M4.** All data, manifests, and outcomes evaluated in this report were generated dynamically in isolated temporary directories using deterministic synthetic models. The reserved holdout seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) remain completely uninstantiated and untouched. Live execution requires explicit authorization from the project owner.

---

## Abstract

This report provides the formal verification of the NEXVIA AEGIS Milestone V9-M4 execution harness using an injectable synthetic simulator ([MockHoldoutSimulator](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py#L182-L248)) and isolated end-to-end test fixtures. We evaluate the entire execution pathway without touching production holdout partitions or consuming reserved RNG seeds. Across 15 newly developed and rigorous unit and integration tests ([tests/test_v9_holdout_preflight.py:test_30..test_44](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L500-L950)), we confirm: (1) Common Random Numbers determinism across V9, V8.1, and V7 controllers; (2) fail-closed execution authorization barrier; (3) complete synthetic mixture holdout evaluation ($H_1, H_2, H_4$); (4) complete synthetic scenario holdout evaluation ($H_3, H_5$ across 12 stratified scenarios); (5) single-shot output protection and mid-run failure containment; (6) outcome algebra verification and fail-unsafe crash accounting; (7) undefined selective risk handling when accepted coverage is zero; and (8) manifest and policy tampering detection. All 44 tests in the focused preflight suite and all 155 tests in the full repository regression suite passed with zero failures.

---

## 1. Executive Summary

### 1.1 Executive Summary (English)
1. **Synthetic Verification Guarantee:** Designed and verified `MockHoldoutSimulator`, enabling full multi-controller execution, artifact generation, and statistical aggregation without accessing real holdout data.
2. **End-to-End Pipeline Validation:** Verified the complete evaluation pathway on synthetic mixture ($N=100$) and synthetic scenario ($12 \times 10 = 120$) holdout manifests, validating the generation of episode CSVs, baseline comparison CSVs, summary tables, scenario breakdowns, and canonical JSON reports.
3. **Statistical Reconciliation:** Confirmed exact calculation and reporting of $H_1$ (Clopper--Pearson upper bound), $H_2$ (McNemar paired incidence test vs V8.1 and V7), $H_3$ (paired TSR noninferiority and nominal TSR threshold), $H_4$ (empirical coverage floor), and $H_5$ (Berger Intersection--Union Test and auxiliary Holm--Šidák step-down).
4. **Undefined Risk Invariant:** Verified that when a scenario experiences zero accepted decisions ($M_s = 0$), selective risk is reported as `UNDEFINED` (null in JSON / NaN in CSV), preventing division-by-zero errors while maintaining valid binomial p-values on unconditional incidence ($N_s$).
5. **Failure Injection Resilience:** Verified that the harness halts fail-closed on unauthorized execution tokens, missing simulator mock flags, directory overwrite collisions, mid-run simulation crashes, outcome algebra violations, corrupted manifest digests, and tampered policy configurations.
6. **Regression Suite Integrity:** The focused preflight suite achieved 44/44 passing tests in 1.88s; the complete repository test suite achieved 155/155 passing tests in 32.00s. Zero production holdout manifests or directories exist.

### 1.2 บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)
1. **การรับรองความถูกต้องด้วยระบบจำลองสังเคราะห์:** พัฒนาและทดสอบตัวจำลองสังเคราะห์ `MockHoldoutSimulator` ซึ่งสามารถจำลองการทำงานของตัวควบคุมหลายระบบ การสร้างไฟล์ผลลัพธ์ และการคำนวณทางสถิติได้อย่างครบถ้วนสมบูรณ์ โดยไม่ต้องเข้าถึงหรือเปิดเผยข้อมูล Holdout จริง
2. **การทดสอบกระบวนการตั้งแต่ต้นจนจบ (End-to-End):** ตรวจสอบวงรอบการประเมินผลบนข้อมูลสังเคราะห์ทั้งแบบ Mixture ($N=100$) และแบบ Scenario ($12 \times 10 = 120$) พบว่าระบบสามารถสร้างไฟล์ระเบียนผลลัพธ์ CSV ของ V9, V8.1, V7 ตารางสรุปผล และรายงาน JSON ที่มีค่าแฮชถูกต้องครบถ้วน
3. **ความสอดคล้องของการคำนวณทางสถิติ ($H_1$--$H_5$):** ยืนยันความถูกต้องของการคำนวณขอบเขตบน Clopper--Pearson ($H_1$), การทดสอบ McNemar แบบจับคู่ ($H_2$), การทดสอบ Noninferiority ของ TSR ($H_3$), สัดส่วนการยอมรับงาน ($H_4$) และการทดสอบ Berger IUT ร่วมกับ Holm--Šidák ($H_5$)
4. **การจัดการความเสี่ยงที่ไม่นิยาม (Undefined Risk):** ตรวจสอบว่าในกรณีที่ไม่มีการยอมรับภารกิจในสถานการณ์ย่อย ($M_s = 0$) ระบบจะบันทึก Selective Risk เป็น `UNDEFINED` อย่างถูกต้อง โดยไม่เกิดข้อผิดพลาดทางคณิตศาสตร์ และยังคงคำนวณ p-value บนขนาดตัวอย่างรวม ($N_s$) ได้อย่างสมบูรณ์
5. **ความทนทานต่อความล้มเหลว (Failure Injection):** ยืนยันว่าระบบหยุดการทำงานแบบ Fail-Closed ทันทีเมื่อพบ Token ผิดพลาด, ลืมระบุแฟล็กจำลอง, โฟลเดอร์ผลลัพธ์ซ้ำซ้อน, การเกิดข้อยกเว้นขณะจำลอง, ความผิดปกติของพีชคณิตผลลัพธ์ หรือการดัดแปลงไฟล์ Manifest/Policy
6. **ความสมบูรณ์ของการทดสอบเชิงถดถอย:** ชุดทดสอบ Preflight ผ่าน 44 จาก 44 การทดสอบ (1.88 วินาที) และชุดทดสอบทั้งระบบผ่าน 155 จาก 155 การทดสอบ (32.00 วินาที) โดยไม่มีไฟล์หรือโฟลเดอร์ Holdout จริงถูกสร้างขึ้นในระบบ

---

## 2. Mock Simulator Architecture

### 2.1 Design of `MockHoldoutSimulator`
The class `MockHoldoutSimulator` in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py#L182-L248) provides deterministic, injectable simulation modeling the physical dynamics and decision behaviors of V9, V8.1, and V7:
- **Common Random Numbers Determinism:** Consumes pseudorandom floats from `rng_env` and `rng_sensors` derived by `_derive_episode_rngs`. For a given episode seed, the environmental disturbance realization is bitwise invariant across controller evaluations.
- **Controller-Specific Logic:** Models realistic performance differentials:
  - V9 exhibits high safety ($TS \gg FS$) and selective abstention on severe disturbances.
  - V8.1 exhibits moderate abstention but higher false-success rates under heavy sensor degradation.
  - V7 (unfiltered MPC) never abstains ($A=1$), yielding high throughput in nominal scenarios but frequent collisions in adversarial scenarios.
- **Programmable Failure Injections:**
  - `inject_crash_keys`: Forces catastrophic crash events ($crashed=1$).
  - `inject_timeout_keys`: Forces horizon expiration ($timed_out=1$).
  - `inject_abstain_keys`: Forces safety abstention ($abstain=1$).
  - `inject_algebra_violation_keys`: Injects non-conforming outcome tuples to test algebraic guards.
  - `inject_runtime_exception_keys`: Injects simulator exceptions mid-run to test partial output dumping.
  - `scenario_overrides`: Injects scenario-specific behavior, such as forcing zero accepted episodes ($M_s=0$) to test undefined selective risk handling.

---

## 3. Mock Verification Test Suite

Fifteen dedicated unit and integration tests ([tests/test_v9_holdout_preflight.py:test_30..test_44](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L500-L950)) verify the production execution harness:

### Table 1: Mock End-to-End Verification Test Results

| Test Identifier | Verified Property | Injection / Scenario | Duration | Status |
| :--- | :--- | :--- | :---: | :---: |
| `test_30` | CRN Determinism Across Controllers | Shared `spawn_keys` across V9, V8.1, V7 | 0.02s | PASS |
| `test_31` | Authorization Token Barrier | Invalid & missing token rejection | 0.01s | PASS |
| `test_32` | Custom Simulator Mock Guard | Missing `allow_mock_simulation=True` | 0.01s | PASS |
| `test_33` | Full Mixture Holdout Pipeline | Synthetic mixture manifest ($N=100$) | 0.42s | PASS |
| `test_34` | Full Scenario Holdout Pipeline | Synthetic scenario manifest ($12 \times 10$) | 0.51s | PASS |
| `test_35` | Single-Shot Overwrite Protection | Existing destination files & markers | 0.03s | PASS |
| `test_36` | Partial Crash Marking | Injected exception at episode $i=3$ | 0.04s | PASS |
| `test_37` | Outcome Algebra Violation Guard | Injected $A \ne TS + FS$ tuple | 0.02s | PASS |
| `test_38` | Fail-Unsafe Crash Accounting | Crash with $A=0, TS=0, FS=1$ | 0.03s | PASS |
| `test_39` | Timeout and Abstention Accounting | Forced timeout and explicit abstention | 0.02s | PASS |
| `test_40` | Undefined Selective Risk Handling | Forced $M_s = 0$ in scenario breakdown | 0.08s | PASS |
| `test_41` | Manifest Tampering Hash Guard | Corrupted manifest SHA-256 payload | 0.02s | PASS |
| `test_42` | Selected Policy Tampering Guard | Corrupted policy parameters SHA-256 | 0.02s | PASS |
| `test_43` | Bijective Paired Identity Alignment | Shuffled $(seed, scenario)$ records | 0.04s | PASS |
| `test_44` | Default CLI Preflight Guard | CLI invocation defaults to preflight | 0.03s | PASS |

---

## 4. Statistical and Artifact Reconciliation

### 4.1 Mixture Holdout Artifacts ($H_1, H_2, H_4$)
In `test_33`, the synthetic mixture pipeline processed 100 episodes. The generated artifacts were verified in temporary storage:
- `test_mix_episodes.csv`: Contains 100 records for V9 conforming to schema (`seed, scenario, outcome, ts, fs, crashed, abstain, cost, latency_ms`).
- `test_mix_baseline_v8_episodes.csv`: Contains 100 paired records for V8.1.
- `test_mix_baseline_v7_episodes.csv`: Contains 100 paired records for V7.
- `test_mix_summary.csv`: Contains summary metrics for V9, V8.1, and V7.
- `test_mix_report.json`: Contains the complete report payload, including:
  - $H_1$: Selective risk point estimate $\hat{r} = FS / M$, Clopper--Pearson 95% UCB, and decision status.
  - $H_2$: Contingency matrices vs V8.1 and V7, exact McNemar $p$-values, odds ratios, and superiority decisions.
  - $H_4$: Empirical coverage $\hat{c} = M / N$ and threshold comparison ($\ge 0.35$).
  - `integrity_sha256`: Cryptographic hash over all constituent CSV files.

### 4.2 Scenario Holdout Artifacts ($H_3, H_5$)
In `test_34`, the synthetic scenario pipeline processed 120 episodes ($10$ per scenario across 12 scenarios):
- `test_scen_episodes.csv`, `test_scen_baseline_v8_episodes.csv`, `test_scen_baseline_v7_episodes.csv`: 120 records per controller.
- `test_scen_breakdown.csv`: Stratified breakdown table reporting per-scenario sample sizes ($N_s, M_s$), accepted counts, true/false success counts, selective risk, unconditional false-success incidence, and exact binomial p-values.
- `test_scen_report.json`: Contains:
  - $H_3$: Paired TSR difference $\Delta\text{TSR} = \text{TSR}_{\text{V9}} - \text{TSR}_{\text{V8.1}}$, 1-sided 95% LCB, nominal scenario TSR check, and noninferiority decision.
  - $H_5$: Berger IUT overall statistic $p_{\text{IUT}} = \max_s p_s$, global confirmation decision, and auxiliary Holm--Šidák adjusted $p$-values with the sequential break stopping rule.

---

## 5. Failure Injection Analysis

1. **Authorization Token Rejection:** Supplying `authorized_execution_token=None` or an invalid token string raises `PermissionError` before any simulation setup occurs.
2. **Simulator Spoofing Rejection:** Passing a simulator object without `allow_mock_simulation=True` raises `RuntimeError`, preventing accidental test simulator leakage into production.
3. **Single-Shot Overwrite Protection:** Running the pipeline when output files or `INCOMPLETE_INVALID.json` exist immediately raises `FileExistsError`.
4. **Mid-Run Failure Containment:** When an exception is injected at episode 3, the pipeline writes completed episodes to `test_mix_episodes_PARTIAL.csv`, creates `INCOMPLETE_INVALID.json` with the exception details, and re-raises `RuntimeError`.
5. **Outcome Algebra Violation:** Injected tuples where $A \ne TS + FS$ (for non-crashed episodes) or where a crash does not satisfy $A=0, TS=0, FS=1$ raise `ValueError` and halt evaluation.
6. **Manifest and Policy Integrity:** Tampering with manifest JSON or modifying `selected_policy.json` parameters is caught during preflight validation, raising `ValueError`.

---

## 6. Regression Testing Summary

### 6.1 Focused Preflight Suite
- Command: `PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py`
- Result: **44 passed in 1.88s** (Exit Code: 0)

### 6.2 Complete Repository Suite
- Command: `PYTHONPATH=src uv run pytest -q`
- Result: **155 passed in 32.00s** (Exit Code: 0)

---

## 7. Confirmation of Holdout Isolation

The verification confirmed the following filesystem isolation invariants:
1. `results/v9/manifests/test_mix_manifest_r1.json`: **DOES NOT EXIST**
2. `results/v9/manifests/test_scen_manifest_r1.json`: **DOES NOT EXIST**
3. `results/v9/test_mix/`: **DOES NOT EXIST**
4. `results/v9/test_scen/`: **DOES NOT EXIST**
5. Reserved Seed Blocks ($73000..74439$ and $75000..75119$): **100% UNTOUCHED**

---

## 8. Conclusion

The production execution pathway for Milestone V9-M4 has been thoroughly verified using synthetic mock fixtures. All components—multi-controller execution, CRN determinism, paired record alignment, statistical inference, artifact generation, and fail-closed defenses—function exactly as preregistered.

The technical evaluation harness is **ready for production execution**, pending separate authorization and execution token delivery from the project owner.
