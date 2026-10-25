# NEXVIA AEGIS V9-M4 — Final H3 Protocol and Common-Random-Numbers Consistency Audit

**Document ID:** `AEGIS-V9-M4-CRN-16`  
**Milestone:** V9-M4 Confirmatory Holdout Evaluation — Final Consistency Audit  
**Git Branch:** `v9.0-runtime-assurance`  
**Reported Latest Implementation Commit:** `372576c`  
**Prior Pre-Execution Review Commit:** `9c4c36f`  
**Date:** October 25, 2026  
**Final Status:** `H3_CRN_CONSISTENCY_CONFIRMED_WITH_QUALIFICATIONS`  
**Holdout Data Accessed:** FALSE (Zero production holdout manifests, datasets, or RNG streams accessed)

---

## CRITICAL NON-AUTHORIZATION DIRECTIVE

This audit document resolves the authoritative baseline requirements for Hypothesis $H_3$ and independently verifies the Common Random Numbers (CRN) architecture across controllers V9, V8.1, and V7. **This document does NOT constitute authorization to execute V9-M4.** All empirical evaluations in this report were conducted using synthetic test fixtures and isolated mock environments. The production holdout manifests (`test_mix_manifest_r1.json` and `test_scen_manifest_r1.json`) and output directories (`results/v9/test_mix/` and `results/v9/test_scen/`) do not exist. Reserved seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) remain completely uninstantiated and untouched. Production execution requires explicit authorization from the project owner.

---

## Abstract

This audit resolves two foundational questions prior to production holdout authorization: (1) Does Hypothesis $H_3$ use the exact baseline registered in the authoritative experiment protocol? (2) Does the implemented Common Random Numbers (CRN) architecture preserve matched exogenous random inputs across V9, V8.1, and V7? 

Through systematic reconciliation of protocol specifications ([docs/v9_experiment_protocol.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md)), readiness reviews, and prior audit reports, we establish that Section 3.1.1 of the Authoritative Protocol formally defines the primary null hypothesis $H_{0,3}$ as paired True-Success Rate (TSR) noninferiority against baseline V8.1 at margin $\Delta_{\mathrm{NI}} = -0.05$ on the $S_{10}$ scenario block, while explicitly designating co-evaluation against baseline V7 MPC at the same margin. Prior reports exhibited narrative tension: Report 13 focused on V7 MPC, whereas Report 14 summarized V8.1. We remediated [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) to evaluate both baselines simultaneously (`h3_tsr_noninferiority_vs_v8` and `h3_tsr_noninferiority_vs_v7`), maintaining strict backward compatibility while guaranteeing full protocol compliance. 

Audit of the CRN pipeline demonstrates that each controller receives independent `np.random.Generator` instances derived from shared `SeedSequence` spawn keys, ensuring controller execution-order invariance, isolation against early termination/step-count differences, and bitwise identical initial conditions ($\mathbf{p}_{\mathrm{target}}$ and sensor noise at $t=0$). However, because physical simulation utilizes incremental mutable streams rather than stateless spatio-temporal hash functions, controller-specific decisions (such as conditional anchor queries in `AnchorSensor.measure`) cause subsequent random draws to offset between controllers in closed-loop trajectory execution. This behavior matches the preregistered protocol qualification in `docs/v9_research_audit.md:240`. Five new synthetic verification tests (`test_45`–`test_49`) validate dual-baseline enforcement, substitution rejection, order invariance, early-termination isolation, and stream divergence characteristics. All 49 preflight tests and all 160 repository tests pass with zero failures.

---

## 1. Executive Summary

### 1.1 Executive Summary (English)
1. **Authoritative H3 Baseline Identity:** Protocol Section 3.1.1 designates V8.1 Martingale as the primary noninferiority baseline and V7 MPC as a co-evaluated baseline for $H_3$ True-Success Rate noninferiority ($\Delta_{\mathrm{NI}} = -0.05$ on $S_{10}$, nominal TSR $\ge 0.94$). $H_2$ remains the separate unconditional incidence ($R_{\mathrm{inc}}$) superiority comparison on the Mixture partition ($\mathcal{D}_{\text{test}}^{\text{mix}}$).
2. **Minimal Pipeline Remediation:** Updated `evaluate_scenario_holdout` in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) to accept `v8_records` alongside `v7_records`, reporting both `h3_tsr_noninferiority_vs_v8` and `h3_tsr_noninferiority_vs_v7`, with overall pass requiring satisfaction of primary protocol criteria.
3. **CRN Independence & Invariance:** Confirmed that `_derive_episode_rngs` spawns isolated `np.random.Generator` objects. Controller execution order (e.g., V9 $\to$ V8 $\to$ V7 vs V7 $\to$ V8 $\to$ V9) and differential run lengths (e.g., early crash or abstention) produce zero cross-talk or stream corruption.
4. **Initial Condition & Noise Coupling:** Initial target locations ($\mathbf{p}_{\mathrm{target}}$) and initial sensor noise realizations at step $t=0$ are 100% bitwise identical across all controllers under matched episode seeds.
5. **Closed-Loop Mutable Stream Qualification:** Because sensor streams are stateful generators, conditional sensor queries (e.g., V8 querying the anchor while V7 does not) advance the generator, offsetting subsequent noise draws. This is documented and accepted under the preregistered protocol design.
6. **Synthetic Verification Suite:** Implemented 5 dedicated unit and integration tests (`test_45` through `test_49`) in [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py). Preflight suite achieves 49/49 passing tests (1.14s); full repository suite achieves 160/160 passing tests (25.52s).
7. **Holdout Protection:** Confirmed 100% holdout isolation. No production holdout manifests, datasets, or directories exist; reserved seed ranges remain untouched.

### 1.2 บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)
1. **การกำหนด Baseline ทางการของสมมติฐาน H3:** ข้อกำหนดการทดลองหมวด 3.1.1 ระบุอย่างเป็นทางการว่า V8.1 Martingale คือ Baseline หลักในการทดสอบความไม่ด้อยกว่า (Noninferiority) ของ True-Success Rate ($H_3$ ที่ระยะ $\Delta_{\mathrm{NI}} = -0.05$ บนกลุ่ม $S_{10}$ ร่วมกับเกณฑ์ TSR ในสภาวะปกติ $\ge 0.94$) พร้อมทั้งกำหนดให้ประเมินร่วมกับ V7 MPC โดยสมมติฐาน $H_2$ แยกต่างหากเพื่อทดสอบความเหนือกว่าของอุบัติการณ์ความล้มเหลวเท็จ ($R_{\mathrm{inc}}$) บนข้อมูลแบบผสม
2. **การปรับปรุงระบบประเมินผล:** ปรับฟังก์ชัน `evaluate_scenario_holdout` ใน [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) ให้รองรับการประเมินคู่ขนานทั้ง V8.1 (`h3_tsr_noninferiority_vs_v8`) และ V7 (`h3_tsr_noninferiority_vs_v7`) อย่างสมบูรณ์และคงความเข้ากันได้ย้อนหลัง 100%
3. **ความเป็นอิสระและความไม่แปรผันของ CRN:** ยืนยันว่าการกำเนิดสตรีมสุ่มผ่าน `_derive_episode_rngs` ให้ตัวสร้างสุ่ม `np.random.Generator` ที่แยกขาดจากกันในแต่ละตัวควบคุม ลำดับการเรียกทำงาน (เช่น V9 $\to$ V8 $\to$ V7 หรือ V7 $\to$ V8 $\to$ V9) และการหยุดทำงานก่อนกำหนดไม่มีผลกระทบต่อสตรีมสุ่มของตัวควบคุมอื่น
4. **ความเหมือนกันระดับบิตของเงื่อนไขเริ่มต้น:** พิกัดเป้าหมายเริ่มต้น ($\mathbf{p}_{\mathrm{target}}$) และสัญญาณรบกวนของเซนเซอร์ ณ ก้าวที่ $t=0$ เหมือนกันระดับบิต (Bitwise Identical) ครบถ้วนทุกประการ
5. **ข้อจำกัดของสตรีมแบบ Mutable ใน Closed-Loop:** เนื่องจากเซนเซอร์ใช้ตัวสร้างสุ่มแบบมีสถานะ การเรียกค้นข้อมูลเซนเซอร์ที่ไม่พร้อมเพรียงกัน (เช่น V8 เรียกอ่าน Anchor แต่ V7 ไม่ได้อ่าน) ทำให้ลำดับสุ่มถัดไปใน Closed-Loop เหลื่อมกัน ซึ่งเป็นพฤติกรรมที่ยอมรับได้ตามที่ระบุไว้ในเอกสารพิธีสารเดิม
6. **ผลการทดสอบเชิงสังเคราะห์:** เพิ่มการทดสอบเฉพาะทาง 5 รายการ (`test_45` ถึง `test_49`) ส่งผลให้ชุดทดสอบ Preflight ผ่าน 49/49 รายการ (1.14 วินาที) และชุดทดสอบระบบรวมผ่าน 160/160 รายการ (25.52 วินาที)
7. **การรักษาระยะห่างจาก Holdout จริง:** ยืนยันว่าไม่มีไฟล์ Manifest, ชุดข้อมูล หรือโฟลเดอร์ Holdout จริงถูกสร้างขึ้น และไม่มีการแตะต้องช่วง Seed สำรองแต่อย่างใด

---

## 2. Phase 1 — Authoritative H3 Baseline Identity Resolution

### 2.1 Cross-Document Reconciliation
A rigorous textual and mathematical comparison was conducted across all governing documents in the repository:

| Document Source | Location | Stated H3 Baseline | Context & Decision Criterion |
| :--- | :--- | :--- | :--- |
| `docs/v9_experiment_protocol.md` | §3.1.1 (lines 28–30) | **V8.1 Martingale** (primary) & **V7 MPC** (co-evaluated) | $H_{0,3}: \mathrm{TSR}(\hat{\pi};\mathcal{P}_{10}) - \mathrm{TSR}(\pi_{\mathrm{V8}};\mathcal{P}_{10}) \le -0.05$ (co-evaluated against $\pi_{\mathrm{V7}}$ at $-0.05$) |
| `docs/v9_experiment_protocol.md` | Table 3.5.1 (line 247) | **$\pi_{\mathrm{V8}}$ (co-eval $\pi_{\mathrm{V7}}$)** | Noninferiority margin $\Delta_{\mathrm{NI}} = -0.05$ on $S_{10}$; nominal utility $\mathrm{TSR} \ge 0.94$ |
| `docs/v9_risk_calibration_design.md` | §7.2 (line 263) | **$\pi_{\mathrm{V8.1}}$** | Secondary confirmatory objective: noninferiority to V8.1 in nominal/adversarial scenarios |
| `docs/v9_m4_readiness_review.md` | Table 3 (line 55) | **V7 MPC** | Abbreviated table listed V7 MPC for operational noninferiority |
| Report 13 (Final Pre-Execution) | §1.1 & §3.2 | **V7 MPC** | Emphasized V7 MPC comparison as the strict historical baseline |
| Report 14 (Execution Path) | §1.1 & §4.2 | **V8.1 Martingale** | Summarized primary protocol comparison against V8.1 Martingale |

### 2.2 Distinguishing H2 and H3 Comparisons
The protocol establishes distinct partitions and estimands for $H_2$ and $H_3$:
- **Hypothesis $H_2$ (Incidence Superiority):** Evaluated strictly on the **Mixture holdout partition** ($\mathcal{D}_{\text{test}}^{\text{mix}}$, $N=1,440$). It tests whether V9 achieves a statistically significant reduction in unconditional false-success incidence ($R_{\mathrm{inc}} = \Pr(FS=1)$) compared to baseline controllers using paired exact McNemar tests against both V8.1 and V7 at $\alpha = 0.05$.
- **Hypothesis $H_3$ (Operational Utility & TSR Noninferiority):** Evaluated strictly on the **Scenario holdout partition** ($\mathcal{D}_{\text{test}}^{\text{scen}}$, $N=1,200$, focusing on the 10 nominal/adversarial scenarios comprising $S_{10}$). It tests whether V9 preserves mission completion capability without excessive abstention:
  1. Primary Noninferiority: 1-sided 95% paired LCB of $\Delta\mathrm{TSR} = \mathrm{TSR}_{\mathrm{V9}} - \mathrm{TSR}_{\mathrm{V8.1}}$ exceeds $-0.05$.
  2. Co-Evaluated Noninferiority: 1-sided 95% paired LCB of $\Delta\mathrm{TSR} = \mathrm{TSR}_{\mathrm{V9}} - \mathrm{TSR}_{\mathrm{V7}}$ exceeds $-0.05$.
  3. Operational Utility: Point estimate of nominal TSR satisfies $\widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$.

### 2.3 Implementation Remediation
In earlier revisions of [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py), while both V8.1 and V7 baseline episodes were simulated and recorded to disk, `evaluate_scenario_holdout` only accepted `v7_records`, labeling the output `h3_tsr_noninferiority_vs_v7`. 

To achieve full protocol fidelity without breaking existing callers or tests:
1. `evaluate_scenario_holdout` signature was expanded to accept `v8_records: Sequence[Mapping[str, Any]] | None = None` and `v7_records: Sequence[Mapping[str, Any]] | None = None`.
2. Both baselines are aligned and paired via `align_and_pair_records` over $(\text{seed}, \text{scenario})$.
3. The evaluation dictionary produces:
   - `h3_tsr_noninferiority_vs_v8`: Primary protocol noninferiority result against V8.1 Martingale.
   - `h3_tsr_noninferiority_vs_v7`: Co-evaluated noninferiority result against V7 MPC.
   - `h3_overall`: Unified hypothesis status requiring satisfaction of the primary noninferiority criterion and nominal utility.

---

## 3. Phase 2 — Common Random Numbers (CRN) Architectural Audit

### 3.1 Randomization Path Tracing
The randomization path flows deterministically through the following hierarchy:
```
Manifest Item (manifest_id, seed, scenario)
       │
       ▼
_derive_episode_rngs(master_seed, manifest_id, ep_seed)
       │
       ▼
SeedSequence(master_seed, spawn_key=(manifest_id, ep_seed)).spawn(10)
       ├── child[0] ──► np.random.default_rng(child[0])  ──► rng_env
       ├── child[1] ──► np.random.default_rng(child[1])  ──► rng_sensors
       └── child[2..] ──► Controller / Auxiliary RNGs
```

### 3.2 Evaluation of CRN Invariants across Controllers
A complete technical audit of physical simulation ([src/aegis/core/world.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/core/world.py)) and sensor components ([src/aegis/sensors/sensors.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/sensors/sensors.py)) established the following properties:

1. **Cross-Controller Stream Independence:**
   For each episode, `execute_production_holdout_pipeline` calls `_derive_episode_rngs` separately for V9, V8.1, and V7. Because each invocation creates fresh `np.random.Generator` instances from identical spawn keys, the RNG state of one controller is completely isolated in memory from another.
2. **Controller-Order Invariance:**
   Executing controllers in sequence V9 $\to$ V8.1 $\to$ V7 produces bitwise identical trajectories, decisions, and outcome records as executing them in reverse order V7 $\to$ V8.1 $\to$ V9. This was empirically proven in `test_47`.
3. **Differential Run-Length & Early Termination Isolation:**
   If Controller V9 triggers safety abstention at $t=5$ or crashes at $t=10$, its consumption of random numbers halts. Because Controllers V8.1 and V7 possess their own distinct `Generator` instances, their streams are not truncated or shifted. They proceed to step $t=100$ consuming exactly the random variates intended for those steps. This was empirically proven in `test_48`.
4. **Common Initial Conditions:**
   The initial physical state, including target location $\mathbf{p}_{\mathrm{target}} \sim \mathcal{U}(\text{bounds})$, is sampled from `rng_env` at $t=0$. Initial sensor measurement noise is sampled from `rng_sensors` at $t=0$. These values are 100% bitwise identical across all three controllers. This was verified in `test_49`.
5. **Closed-Loop Mutable Stream Coupling (The Technical Qualification):**
   The repository employs NumPy's stateful `Generator` rather than a stateless spatio-temporal hash function (such as `Hash(episode, timestep, sensor_id)`). While `rng_env` disturbances are sampled uniformly at each timestep, `rng_sensors` calls depend on sensor query behavior. Specifically, `AnchorSensor.measure(true_pos, query=...)` only draws random noise when `query=True`. If Controller V8 queries the anchor at step $t$ while Controller V7 does not, `rng_sensors` advances for V8 but remains unadvanced for V7. Consequently, subsequent sensor noise draws at $t+1$ will be offset by one normal variate. Furthermore, because controllers take different control actions $\mathbf{u}_t$, the physical states $\mathbf{x}_t$ immediately diverge. As explicitly noted in `docs/v9_research_audit.md:240`, sensor draws are matched at $t=0$ and coupled via common random numbers thereafter.

---

## 4. Synthetic Verification Suite

Five dedicated tests were authored in [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py) to independently verify the audit conclusions:

### Table 2: Dedicated H3 Protocol and CRN Audit Tests

| Test Identifier | Verified Property | Injection & Assertion Details | Duration | Status |
| :--- | :--- | :--- | :---: | :---: |
| `test_45` | Dual-Baseline H3 Evaluation | Evaluates synthetic scenario run with V8.1 primary and V7 co-evaluated; verifies `h3_overall`, `h3_tsr_noninferiority_vs_v8`, and `h3_tsr_noninferiority_vs_v7`. | 0.05s | **PASS** |
| `test_46` | Baseline Substitution Rejection | Replaces baseline record with corrupt or misaligned keys; verifies fail-closed `ValueError` rejection in `align_and_pair_records`. | 0.04s | **PASS** |
| `test_47` | Controller-Order Invariance | Simulates V9 $\to$ V8.1 $\to$ V7 vs V7 $\to$ V8.1 $\to$ V9; verifies bitwise equality of all output records across orderings. | 0.06s | **PASS** |
| `test_48` | Consumption Isolation | Simulates early termination in V9 at step 5; verifies that V8.1 and V7 continue to step 100 with zero stream distortion. | 0.05s | **PASS** |
| `test_49` | Initial Conditions & Divergence | Verifies bitwise identity of $\mathbf{p}_{\mathrm{target}}$ and $t=0$ noise; verifies and characterizes mutable stream offset upon anchor query divergence. | 0.05s | **PASS** |

---

## 5. Regression Integrity and Holdout Isolation

### 5.1 Regression Test Execution
Following code updates and test suite expansion, the entire test suite was executed:
1. **Focused Preflight Suite:**
   ```bash
   PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py
   ```
   **Result:** 49 passed in 1.14 seconds (Exit Code: 0).
2. **Full Repository Regression Suite:**
   ```bash
   PYTHONPATH=src uv run pytest -q
   ```
   **Result:** 160 passed in 25.52 seconds (Exit Code: 0). Zero regressions observed.

### 5.2 Holdout Isolation Audit
A filesystem verification confirms complete isolation:
```python
assert not Path("results/v9/manifests/test_mix_manifest_r1.json").exists()
assert not Path("results/v9/manifests/test_scen_manifest_r1.json").exists()
assert not Path("results/v9/test_mix").exists()
assert not Path("results/v9/test_scen").exists()
```
Zero production holdout manifests or output directories exist. Reserved holdout seed blocks ($73000..74439$ and $75000..75119$) remain untouched.

### 5.3 Cryptographic Artifact Verification
- **Frozen Selected Policy (`results/v9/cal_r2/selected_policy.json`):**
  `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` (100% UNCHANGED)
- **Baseline Controller Commit:** `4d891c7500cfb4c8110f276038455bc62765ef3b` (V8.1 Martingale)

---

## 6. Audit Conclusion and Final Status

### Final Status Determination: `H3_CRN_CONSISTENCY_CONFIRMED_WITH_QUALIFICATIONS`

**Qualifications Summary:**
1. **H3 Baseline Dual-Enforcement:** The authoritative protocol requires V8.1 Martingale as primary noninferiority baseline and V7 MPC as co-evaluated baseline. The implementation has been upgraded and verified to evaluate both baselines simultaneously.
2. **CRN Statefulness Qualification:** Exogenous disturbance streams are strictly decoupled across controllers and bitwise matched at initial conditions ($t=0$). However, because simulation uses stateful generators rather than stateless hash functions, controller-dependent sensor query decisions cause closed-loop noise sequences to offset across controllers after $t=0$. This is compliant with the registered protocol design.

The evaluation pipeline is statistically sound, fully traceable to governing protocol documents, and ready for production holdout authorization by the project owner.
