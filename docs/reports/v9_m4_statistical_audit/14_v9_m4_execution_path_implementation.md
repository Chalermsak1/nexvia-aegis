# NEXVIA AEGIS V9-M4 — Production Execution Path Implementation Report

**Document ID:** `AEGIS-V9-M4-EXE-14`  
**Milestone:** V9-M4 Confirmatory Holdout Evaluation — Production Execution Path  
**Git Branch:** `v9.0-runtime-assurance`  
**Reported Previous Commit:** `9c4c36f`  
**Date:** October 25, 2026  
**Status:** COMPLETE (Execution Path Implemented and Guarded)  
**Holdout Data Accessed:** FALSE (Zero real holdout data or reserved RNG streams accessed)

---

## CRITICAL NON-AUTHORIZATION DIRECTIVE

This document reports the technical design, implementation, and code-level verification of the production execution pathway for Milestone V9-M4. **This document does NOT authorize or trigger live holdout execution.** No real holdout manifests or episode datasets were generated, loaded, or inspected. The reserved holdout seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) remain completely uninstantiated and pristine. Execution of V9-M4 requires an explicit, separate instruction and authorization decision from the project owner.

---

## Abstract

This report details the implementation of the complete production execution pathway for Milestone V9-M4 (Confirmatory Holdout Evaluation) within the NEXVIA AEGIS runtime assurance platform. While prior milestones established statistical consistency, hypothesis tests ($H_1$ through $H_5$), and preflight validation, the execution loop remained blocked by design. In this work, we implement a production-capable, defense-in-depth evaluation harness in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py). Key innovations include: (1) Common Random Numbers (CRN) simulation derivation via `_derive_episode_rngs`, guaranteeing identical physical disturbances and sensor noise across controllers; (2) unified evaluation of the frozen selected policy (`V9_CAND_1_TIER1_STRICTEST`), V8.1 martingale baseline (`AegisNextController`, commit `4d891c7`), and V7 MPC baseline (`AegisV7MPCBaselineController`); (3) order-invariant bijective record pairing via `align_and_pair_records` over `(seed, scenario)`; (4) strict outcome algebra verification respecting fail-unsafe crash penalization; (5) multi-layered fail-closed execution guards incorporating secret authorization token validation, single-shot overwrite prevention, and partial failure recording (`_PARTIAL.csv` and `INCOMPLETE_INVALID.json`); and (6) injectable mock simulator architecture enabling rigorous synthetic verification without accessing holdout data.

---

## 1. Executive Summary

### 1.1 Executive Summary (English)
1. **Multi-Controller Execution Architecture:** Implemented `execute_production_holdout_pipeline` in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py), providing end-to-end evaluation for the frozen candidate policy alongside both V8.1 and V7 baselines on identical episode conditions.
2. **Common Random Numbers (CRN) Coupling:** Established `_derive_episode_rngs`, deriving decoupled `rng_env` and `rng_sensors` from stored `SeedSequence` spawn keys for each manifest item. This mathematically guarantees that V9, V8.1, and V7 navigate identical trajectory perturbations, obstacles, and sensor dropout profiles.
3. **Paired Record Integrity:** Integrated `align_and_pair_records` into the hypothesis evaluation workflow, enforcing bijective `(seed, scenario)` matching for $H_2$ (McNemar paired incidence test vs V8.1 and V7) and $H_3$ (paired TSR noninferiority vs V8.1).
4. **Outcome Algebra and Fail-Unsafe Accounting:** Enforced exact outcome categorization: for non-crashed episodes, $A = TS + FS$; for crashed episodes, fail-unsafe penalization requires $A=0, TS=0, FS=1, \text{abstain}=0$.
5. **Defense-in-Depth Execution Guards:** Production execution is guarded by an authorization barrier requiring an explicit secret token, single-shot directory overwrite refusal, simulator spoofing protection (`allow_mock_simulation=True` required for custom simulators), and crash recovery marking.
6. **Isolation Assurance:** No production holdout manifests or output directories were created. All tests utilized synthetic manifests and in-memory mock fixtures.

### 1.2 บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)
1. **สถาปัตยกรรมการประเมินผลหลายตัวควบคุม:** ดำเนินการติดตั้งฟังก์ชัน `execute_production_holdout_pipeline` ใน [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) เพื่อรองรับการประเมินผลนโยบายที่ถูกตรึง (Frozen Policy) ควบคู่กับตัวควบคุมอ้างอิง V8.1 และ V7 ภายใต้เงื่อนไขตอนจำลองเดียวกันอย่างสมบูรณ์
2. **การรักษาความคงที่ของสภาวะสุ่ม (Common Random Numbers):** พัฒนาฟังก์ชัน `_derive_episode_rngs` เพื่อสร้างตัวสร้างเลขสุ่ม `rng_env` และ `rng_sensors` จาก SeedSequence spawn keys ของแต่ละตอน ทำให้รับประกันได้ว่าทั้ง V9, V8.1 และ V7 จะเผชิญกับสภาวะรบกวนทางกายภาพและสัญญาณเซนเซอร์ที่ผิดพลาดในจุดเวลาและตำแหน่งเดียวกันอย่างแม่นยำ
3. **การจับคู่ระเบียนผลลัพธ์แบบสองทิศทาง (Bijective Pairing):** บูรณาการฟังก์ชัน `align_and_pair_records` เข้าสู่วงรอบการวิเคราะห์สมมติฐาน $H_2$ (การทดสอบ McNemar เทียบ V8.1 และ V7) และ $H_3$ (การทดสอบ Noninferiority เทียบ V8.1) เพื่อป้องกันการจับคู่ผิดพลาดตามลำดับแถว
4. **พีชคณิตผลลัพธ์และการบันทึกความล้มเหลวแบบไม่ปลอดภัย:** บังคับใช้กฎผลลัพธ์อย่างเข้มงวด โดยกรณีปกติ $A = TS + FS$ และในกรณีที่ยานชนสิ่งกีดขวาง ($crashed=1$) ระบบจะปรับให้ $A=0, TS=0, FS=1, \text{abstain}=0$ เพื่อสะท้อนความเสี่ยงสูงสุดตามระเบียบวิธีวิจัย
5. **ระบบป้องกันหลายชั้นแบบ Fail-Closed:** ป้องกันการรันจริงด้วย Secret Authorization Token, บล็อกการเขียนทับไดเรกทอรีผลลัพธ์, บล็อกการใช้ Custom Simulator โดยไม่ระบุแฟล็กอนุญาต และมีระบบบันทึก `_PARTIAL.csv` พร้อมไฟล์สถานะ `INCOMPLETE_INVALID.json` หากการประมวลผลหยุดชะงักกลางคัน
6. **การรับรองความบริสุทธิ์ของข้อมูล Holdout:** ยืนยันว่าไม่มีการสร้างหรือแตะต้องไฟล์ Manifest และโฟลเดอร์ผลลัพธ์จริง การทดสอบทั้งหมดกระทำบนข้อมูลสังเคราะห์ในหน่วยความจำชั่วคราวเท่านั้น

---

## 2. Selected Policy and Baseline Architecture

### 2.1 Frozen Policy Identity and Integrity
The primary subject of evaluation is `V9_CAND_1_TIER1_STRICTEST`, calibrated during Milestone V9-M2 and audited in V9-M3. Its configuration artifact resides at [results/v9/cal_r2/selected_policy.json](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/cal_r2/selected_policy.json) with cryptographic hash:
$$\text{SHA-256} = \texttt{5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2}$$

The evaluation pipeline validates this digest against the hard-coded baseline in `EXPECTED_SELECTED_POLICY_SHA256` prior to any execution step.

### 2.2 Baseline Controllers
To test Hypotheses $H_2$ and $H_3$, the execution pipeline instantiates two historical baseline controllers:
1. **V8.1 Audited Controller:** Implemented by `AegisNextController` pinned to snapshot commit `4d891c7500cfb4c8110f276038455bc62765ef3b`. V8.1 employs sequential martingale boundary testing for runtime assurance but lacks V9's dual-tier conformal predictive safety filter.
2. **V7 Baseline Controller:** Implemented by `AegisV7MPCBaselineController` located in [src/aegis/next/baselines.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/next/baselines.py). V7 represents classical Model Predictive Control without selective abstention or conformal calibration.

### 2.3 Common Random Numbers (CRN) Simulation Mechanics
Comparing controller safety requires eliminating Monte Carlo variance attributable to environmental divergence. In `experiments/v9_evaluate_holdout.py`, the function `_derive_episode_rngs(item, fallback_seed)` handles RNG stream derivation:
```python
def _derive_episode_rngs(item: Dict[str, Any], fallback_seed: int = 0) -> Tuple[np.random.Generator, np.random.Generator]:
    spawn_keys = item.get("spawn_keys")
    if spawn_keys and isinstance(spawn_keys, list) and len(spawn_keys) >= 2:
        ss_env = np.random.SeedSequence(spawn_keys[0])
        ss_sen = np.random.SeedSequence(spawn_keys[1])
        return np.random.default_rng(ss_env), np.random.default_rng(ss_sen)
    seed = int(item.get("seed", fallback_seed))
    ss = np.random.SeedSequence(seed)
    children = ss.spawn(2)
    return np.random.default_rng(children[0]), np.random.default_rng(children[1])
```
When simulating an episode across V9, V8.1, and V7, `_derive_episode_rngs` is called independently for each controller evaluation. Consequently, each controller receives an identical initial state, obstacle motion trajectory, sensor noise realization, and communication dropout sequence.

---

## 3. End-to-End Orchestration Workflow

The production pipeline is encapsulated within `execute_production_holdout_pipeline(...)`. It operates in eleven strictly ordered phases:

```
+-------------------------------------------------------------+
| Phase 1: Policy and Protocol Identity Validation            |
| (Verifies SHA-256 of selected_policy.json and protocol)     |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 2: Execution Authorization Barrier                    |
| (Validates secret token; rejects unauthorized attempts)     |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 3: Manifest Verification & Integrity Check            |
| (Checks canonical JSON SHA-256 and prohibited seed blocks)  |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 4: Output Path Isolation & Single-Shot Check          |
| (Prevents overwrite of existing results or invalid runs)    |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 5: Episode Execution (V9, V8.1, V7)                   |
| (Executes all episodes using CRN stream derivation)         |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 6: Outcome Algebra Verification                       |
| (Enforces A == TS + FS and crashed fail-unsafe rules)       |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 7: Bijective Record Pairing                           |
| (Executes align_and_pair_records over seed and scenario)    |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 8: Statistical Hypothesis Testing (H1-H5)             |
| (Clopper-Pearson, McNemar, TSR Noninferiority, Berger IUT)  |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 9: Partition-Specific Reporting                       |
| (Generates CSV records for V9, V8.1, V7, and summaries)     |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 10: Cryptographic Provenance & Hash Digesting         |
| (Computes SHA-256 digests for all generated CSV artifacts)  |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| Phase 11: Final Report Packaging                            |
| (Writes canonical test_{partition}_report.json)             |
+-------------------------------------------------------------+
```

---

## 4. Execution Guards and Fail-Closed Mechanics

To prevent premature or accidental execution on production holdout partitions, the implementation incorporates five layers of defense-in-depth:

1. **Explicit Authorization Token Gate:**
   Production execution requires passing `authorized_execution_token`. If the token is `None`, empty, or does not match `REQUIRED_EXECUTION_TOKEN`, the pipeline immediately aborts with `PermissionError`.
2. **Simulator Spoofing Guard:**
   To guarantee that mock simulators are never inadvertently supplied to production evaluation (or real simulators to mock tests), any custom simulator object requires `allow_mock_simulation=True`. If a custom simulator is supplied without this flag, the pipeline raises `RuntimeError`.
3. **Single-Shot Output Guard:**
   Before running any simulations, the pipeline inspects the destination directory. If `test_{partition}_episodes.csv` or `INCOMPLETE_INVALID.json` exists, the pipeline halts with `FileExistsError`.
4. **Partial Failure Recording:**
   If an unexpected runtime exception occurs during the simulation loop, an exception handler traps the error, writes all completed episodes to `test_{partition}_episodes_PARTIAL.csv`, emits `INCOMPLETE_INVALID.json` documenting the failure reason, and re-raises the exception.
5. **Preflight CLI Default:**
   The CLI entry point `experiments/v9_evaluate_holdout.py` defaults to `--preflight-only`. Running the CLI without flags executes read-only inspection without generating manifests or modifying the filesystem.

---

## 5. Traceability Matrix

Table 1 maps the design requirements to the implementation in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) and corresponding verification tests in [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py).

### Table 1: Code and Test Traceability Matrix

| Requirement | Implementation Component | Source Location | Verification Test | Result |
| :--- | :--- | :--- | :--- | :---: |
| CRN RNG Derivation | `_derive_episode_rngs` | `v9_evaluate_holdout.py:91-115` | `test_30_mock_simulator_crn_determinism` | PASS |
| Execution Authorization Token | `execute_production_holdout_pipeline` | `v9_evaluate_holdout.py:1017-1025` | `test_31_execution_token_guard` | PASS |
| Mock Simulator Flag Guard | `execute_production_holdout_pipeline` | `v9_evaluate_holdout.py:1027-1033` | `test_32_custom_simulator_requires_mock_flag` | PASS |
| Mixture Holdout Pipeline | `execute_production_holdout_pipeline` | `v9_evaluate_holdout.py:1035-1175` | `test_33_full_mixture_holdout_mock_orchestration` | PASS |
| Scenario Holdout Pipeline | `execute_production_holdout_pipeline` | `v9_evaluate_holdout.py:1176-1260` | `test_34_full_scenario_holdout_mock_orchestration` | PASS |
| Single-Shot Overwrite Block | `execute_production_holdout_pipeline` | `v9_evaluate_holdout.py:1048-1060` | `test_35_single_shot_output_protection` | PASS |
| Partial Crash Marking | `execute_production_holdout_pipeline` | `v9_evaluate_holdout.py:1120-1135` | `test_36_mid_run_failure_partial_output_handling` | PASS |
| Outcome Algebra Validation | `verify_holdout_outcome_algebra` | `v9_evaluate_holdout.py:117-142` | `test_37_injected_outcome_algebra_violation` | PASS |
| Fail-Unsafe Crash Accounting | `verify_holdout_outcome_algebra` | `v9_evaluate_holdout.py:126-133` | `test_38_crashed_classification_accounting` | PASS |
| Timeout & Abstain Accounting | `MockHoldoutSimulator.simulate_episode` | `v9_evaluate_holdout.py:192-205` | `test_39_timeout_and_abstention_accounting` | PASS |
| Undefined Selective Risk | `calculate_scenario_holdout_statistics` | `v9_evaluate_holdout.py:922-928` | `test_40_undefined_selective_risk_scenario_breakdown`| PASS |
| Manifest Hash Guard | `verify_and_load_holdout_manifest` | `v9_evaluate_holdout.py:465-492` | `test_41_manifest_tampering_hash_guard` | PASS |
| Policy Hash Guard | `verify_selected_policy_identity` | `v9_evaluate_holdout.py:435-460` | `test_42_policy_tampering_guard` | PASS |
| Bijective Record Pairing | `align_and_pair_records` | `v9_evaluate_holdout.py:145-180` | `test_43_paired_record_identity_keys_alignment` | PASS |
| Default CLI Preflight Guard | `main` | `v9_evaluate_holdout.py:1265-1320` | `test_44_cli_default_preflight_dispatch` | PASS |

---

## 6. Remaining Limitations and Next Steps

1. **Live Simulator Block in Preflight:** The preflight workflow function `execute_holdout_workflow` intentionally preserves `NotImplementedError` to ensure standard audit executions cannot simulate live episodes.
2. **Holdout Manifest Non-Existence:** Production holdout manifests (`test_mix_manifest_r1.json` and `test_scen_manifest_r1.json`) have not been generated. They will be generated only after project owner authorization.
3. **Execution Authorization Required:** Execution of `execute_production_holdout_pipeline` requires the project owner to furnish the production authorization token in a dedicated execution session.

---

## 7. Conclusion

The production execution pathway for Milestone V9-M4 is fully implemented, verified, and safely locked. The harness provides complete multi-controller simulation capabilities, Common Random Numbers guarantees, bijective paired comparisons, and robust fail-closed security.
