# NEXVIA AEGIS V9-M4 — Final CRN Semantics and H3 Decision-Rule Audit

**Document ID:** `AEGIS-V9-M4-CRN-17`  
**Milestone:** V9-M4 Confirmatory Holdout Evaluation — Final Methodological Protocol Audit  
**Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`  
**Branch:** `v9.0-runtime-assurance`  
**Prior Implementation Commit:** `dc39f36`  
**Date:** October 25, 2026  
**Final Status:** `CRN_H3_PROTOCOL_CONFIRMED_WITH_QUALIFICATIONS`  
**Production Holdout Data Accessed:** `FALSE` (Zero real holdout data or reserved RNG streams accessed)

---

## CRITICAL NON-AUTHORIZATION DIRECTIVE

This audit document resolves the final methodological qualifications concerning the preregistered Common Random Numbers (CRN) semantics and Hypothesis $H_3$ decision rules. **This document does NOT constitute authorization to execute Milestone V9-M4.** All evaluations in this report were conducted strictly using synthetic test fixtures, in-memory models, and mock environments. Production holdout manifests (`test_mix_manifest_r1.json` and `test_scen_manifest_r1.json`) and output directories (`results/v9/test_mix/` and `results/v9/test_scen/`) do not exist. Reserved holdout seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) remain completely uninstantiated and untouched. Live execution requires explicit authorization from the project owner.

---

## Abstract

This audit resolves the final two methodological questions concerning the NEXVIA AEGIS Milestone V9-M4 confirmatory holdout pipeline: (1) Does the implemented Common Random Numbers (CRN) architecture conform to the authoritative preregistered protocol, and what exact variance-reduction guarantees does it substantiate? (2) How are the primary V8.1 Martingale baseline and the co-evaluated V7 MPC baseline aggregated and interpreted under Hypothesis $H_3$? 

Through comprehensive citation of governing documents ([docs/v9_experiment_protocol.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md), [docs/v9_research_audit.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_research_audit.md), and [docs/v9_risk_calibration_design.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_risk_calibration_design.md)), we establish that the authoritative protocol preregistered **Model A** (episode-level matched pairs with identical seed derivation, bitwise matching initial conditions at $t=0$, and stateful streams coupled via common random numbers that diverge in closed loop as actions and queries differ). The alternative interpretation (**Model B**, requiring timestep- and channel-aligned exogenous noise independent of controller action) was never specified in the protocol; narrative statements in prior Report 14 suggesting timestep-wise identical disturbance across controllers were overstatements of report text. The implemented simulation architecture in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) accurately fulfills Model A, providing valid paired-sample variance reduction for $H_2$ and $H_3$. 

Regarding Hypothesis $H_3$, we establish that Section 3.1.1 formally preregisters paired True-Success Rate (TSR) noninferiority against **V8.1 Martingale** as the primary confirmatory null hypothesis ($H_{0,3}$) at margin $\Delta_{\mathrm{NI}} = -0.05$ on the $S_{10}$ block, subject to nominal utility ($\widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$). Comparison against **V7 MPC** is an auxiliary co-evaluated baseline. We refined `evaluate_scenario_holdout` to report `primary_passed`, `coeval_passed`, and `all_baselines_passed` without conflating their distinct statistical roles. Six additional synthetic unit tests (`test_50` through `test_55`) verify independent generator states, anchor-query offset mechanics, extension scenario exclusion, and all combinations of primary and co-evaluation pass/fail outcomes. All 55 preflight tests and all 166 full repository regression tests passed with zero failures.

---

## 1. Executive Summary

### 1.1 Executive Summary (English)
1. **Registered CRN Semantics (Model A Confirmed):** The authoritative protocol defines paired comparisons at the episode level over matched $(s, \text{seed})$ pairs. As documented in [docs/v9_research_audit.md:240](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_research_audit.md#L240), controllers initialize independent generators from identical seed derivations, matching initial target locations $\mathbf{p}_{\mathrm{target}}$ and initial sensor noise at $t=0$. In closed-loop execution, mutable streams advance statefully, and differing controller actions or anchor queries induce offsets in subsequent steps. Model B (spatio-temporal hash grids) was never preregistered.
2. **Clarification of Narrative Overstatements:** Report 14 contained narrative claims that CRN "guarantees identical physical disturbances and sensor noise across controllers at every timestep." We formally qualify this statement: identical noise holds strictly at initial conditions ($t=0$) and across open-loop playback, but stateful streams offset when anchor queries differ. The paired statistical tests remain asymptotically and nonparametrically valid because episode pairs are i.i.d. and positively correlated.
3. **Exact H3 Baseline and Aggregation Rules:** 
   - **Primary Baseline:** V8.1 Martingale (`AegisNextController`). Rejection of $H_{0,3}$ requires 1-sided 95% paired LCB of $\Delta\mathrm{TSR}_{\mathrm{V8.1}} > -0.05$ on the 10 scenarios of $S_{10}$ **and** $\widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$.
   - **Co-Evaluated Baseline:** V7 MPC (`AegisV7MPCBaselineController`). Evaluated at the same noninferiority margin $\Delta_{\mathrm{NI}} = -0.05$.
   - **Aggregation Transparency:** The evaluator reports `primary_passed`, `coeval_passed`, `nominal_tsr_criterion_met`, `all_baselines_passed`, and `passed` (tracking the primary null) without conflating co-evaluation into an ad-hoc joint intersection null.
4. **Synthetic Verification Expansion:** Implemented tests `test_50` to `test_55` in [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py), verifying: (i) independent generator memory state; (ii) exact offset realignment after anchor queries; (iii) primary pass with co-eval fail; (iv) primary fail with co-eval pass; (v) nominal TSR failure blocking both claims; and (vi) exclusion of extension scenarios $S_{\mathrm{ext}}$ from $H_3$.
5. **Regression Suite Integrity:** Focused preflight suite achieved 55/55 passed (1.11s); full repository regression suite achieved 166/166 passed (26.04s).
6. **Strict Holdout Non-Execution:** Zero real holdout manifests or output directories exist; reserved seed ranges ($73000..74439$ and $75000..75119$) remain untouched; frozen policy SHA-256 (`5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`) is 100% unchanged.

### 1.2 บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)
1. **การยืนยันแบบจำลอง CRN ทางการ (Model A):** พิธีสารหลักกำหนดการเปรียบเทียบแบบจับคู่ในระดับตอน (Episode-level matched pairs) บนคู่ $(s, \text{seed})$ โดยตัวควบคุมแต่ละตัวจะเริ่มต้นตัวสร้างเลขสุ่มอิสระจาก SeedSequence เดียวกัน ทำให้พิกัดเป้าหมายเริ่มต้น ($\mathbf{p}_{\mathrm{target}}$) และสัญญาณรบกวน ณ ก้าว $t=0$ เหมือนกันระดับบิต แต่ในระบบวงรอบปิด ลำดับสุ่มจะเคลื่อนไปตามการกระทำและการเรียกค้นเซนเซอร์ Anchor ซึ่งตรงตามที่ระบุไว้ในเอกสารพิธีสารเดิมทุกประการ มิได้มีการกำหนดให้ต้องใช้แบบจำลองสุ่มแยกตามพิกัดเวลาและช่องสัญญาณ (Model B)
2. **การแก้ไขข้อความที่ระบุเกินจริง:** รายงานฉบับที่ 14 มีการระบุในเชิงบรรยายว่า CRN รับประกันสภาวะรบกวนที่เหมือนกันทุกก้าวเวลา ซึ่งข้อความนี้ได้รับการปรับปรุงและระบุข้อจำกัดอย่างชัดเจนว่า ความเหมือนกันระดับบิตเกิดขึ้น ณ สภาวะเริ่มต้น ($t=0$) ส่วนการทดสอบทางสถิติแบบจับคู่ ($H_2, H_3$) ยังคงมีความถูกต้องทางสถิติและลดความแปรปรวนได้อย่างสมบูรณ์เนื่องจากคู่ตัวอย่างมีความสัมพันธ์เชิงบวกและเป็นอิสระต่อกันระหว่างตอน
3. **ข้อกำหนดเกณฑ์การตัดสินของสมมติฐาน H3:**
   - **Baseline หลัก (Primary):** V8.1 Martingale โดยการปฏิเสธสมมติฐานว่าง $H_{0,3}$ ต้องได้ค่าขอบเขตล่างด้านเดียว 95% ($\text{LCB}_{95\%}$) ของ $\Delta\mathrm{TSR}_{\mathrm{V8.1}} > -0.05$ บนกลุ่ม $S_{10}$ ร่วมกับเกณฑ์ความสำเร็จในสภาวะปกติ $\ge 0.94$
   - **Baseline ประเมินร่วม (Co-evaluated):** V7 MPC ซึ่งประเมินที่ระยะความไม่ด้อยกว่าเดียวกัน ($\Delta_{\mathrm{NI}} = -0.05$)
   - **ความโปร่งใสในการรายงานผล:** ปรับโครงสร้างรายงานให้แสดงผลลัพธ์แยกกันชัดเจน ได้แก่ `primary_passed`, `coeval_passed`, `all_baselines_passed` โดยไม่นำผลของ Baseline ร่วมไปปะปนกับสมมติฐานหลัก
4. **การขยายชุดทดสอบเชิงสังเคราะห์:** เพิ่มการทดสอบ `test_50` ถึง `test_55` ใน [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py) เพื่อพิสูจน์ความเป็นอิสระของสถานะหน่วยความจำ, การเหลื่อมของสตรีมเมื่อเรียกค้น Anchor, และกรณีผลลัพธ์ผสมทุกรูปแบบ
5. **ความสมบูรณ์ของการทดสอบทั้งระบบ:** ชุดทดสอบ Preflight ผ่าน 55/55 รายการ (1.11 วินาที) และชุดทดสอบระบบรวมผ่าน 166/166 รายการ (26.04 วินาที)
6. **การคงความบริสุทธิ์ของข้อมูล Holdout:** ยืนยันว่าไม่มีการสร้างไฟล์ Manifest หรือรันซิมูเลชันบนข้อมูล Holdout จริง และค่าแฮชของนโยบายควบคุมยังคงเดิม 100%

---

## 2. Phase 1 — Authoritative Textual Evidence on Registered CRN Semantics

### 2.1 Authoritative Citations
A rigorous review of the governing repository documents confirms that the experiment protocol specifies **Model A**:

1. **Protocol Document ([docs/v9_experiment_protocol.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md)):**
   - Section 3.1.1 (line 30):  
     *"One-sided 95% paired lower confidence bound (Newcombe/Wald paired difference CI on the 1,200 matched `(scenario, seed)` pairs) strictly exceeds $-0.05$, and `NOMINAL` true-success rate satisfies $\widehat{TSR}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$."*
   - Section 3.2.4 (line 112):  
     *"For paired binary `TSR` comparisons across $N$ matched `(scenario, seed)` episodes with total discordant proportion $q = p_{01} + p_{10}$ (empirically $q = (43 + 59)/500 = 0.204$ between V7 and V8 in `benchmark_episodes.csv`)..."*
   - Table 3.5.1 (line 247):  
     *"Prespecified NI Test: 1-sided 95% paired LCB on $\Delta TSR = TSR(\hat{\pi}) - TSR(\pi_{\mathrm{ref}})$ across $N=1,200$ matched $\mathcal{S}_{10}$ pairs (`D_test^scen`)."*
2. **Prior Research Audit ([docs/v9_research_audit.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_research_audit.md)):**
   - Line 240 explicitly defines the exact coupling mechanism:  
     *"In `experiments/benchmark_next.py:198-205, 241`, for each of the 10 scenarios and each `ep_idx in range(50)` (`ep_seed = 60000 + ep_idx`), **every policy is evaluated on the exact same initial target position `world.reset(np.random.default_rng(ep_seed))` and identical sensor RNG seed `np.random.default_rng(ep_seed)`**. Thus the 500 episodes form **500 matched pairs** $(s, \text{seed})$ across any two policies $(\pi_A, \pi_B)$ **(note that closed-loop trajectories diverge once actions differ, so sensor draws remain matched at step $t=0$ and coupled via common random numbers thereafter)**. Statistical tests on episode-level binary or continuous outcomes across 500 episodes **must respect this paired design**."*
3. **Risk Calibration Design ([docs/v9_risk_calibration_design.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_risk_calibration_design.md)):**
   - Section 2.1 (line 151):  
     *"common random numbers across $\lambda \in \Lambda$ permitted because FWER control holds under arbitrary p-value dependence."*

### 2.2 Model A versus Model B Comparison
- **Model A (Preregistered Protocol Design):**
  Controllers instantiate independent `np.random.Generator` objects derived from matching `SeedSequence` spawn keys for each episode. Target positions and sensor noise draws match exactly at step $t=0$. In closed loop, random numbers are drawn incrementally; mutable streams can diverge or offset when actions differ or when anchor queries occur conditionally. The statistical unit of pairing is the episode.
- **Model B (Unregistered Alternative Design):**
  Exogenous random disturbances and sensor noise tensors are pre-generated on a fixed 4D grid $\mathbf{W}(\text{scenario}, \text{seed}, t, \text{channel})$ or indexed by stateless hash functions $\mathrm{Hash}(\text{seed}, t, \text{channel})$. Random inputs at step $t$ are enforced to be bitwise identical across controllers regardless of whether preceding queries or actions occurred.

**Conclusion of Phase 1:** **Model A is the authoritative preregistered design.** Model B was never specified or implemented in the NEXVIA AEGIS codebase.

---

## 3. Phase 2 — Implementation Verification and Guarantee Decomposition

We decompose the random-number properties into five distinct guarantees:

| Guarantee Level | Technical Description | Implemented? | Evidentiary Basis |
| :--- | :--- | :---: | :--- |
| **G1: Separate RNG State** | Each controller executes with its own distinct `Generator` instance in memory; early termination or exceptions in one controller cannot corrupt or truncate another's stream. | **YES** | Proven in `test_48` and `test_50`. |
| **G2: Deterministic Reproducibility** | Executing the pipeline twice with identical manifest items and master seeds yields bitwise identical results regardless of controller execution order. | **YES** | Proven in `test_12` and `test_47`. |
| **G3: Common Initial Random Values** | Initial target coordinates $\mathbf{p}_{\mathrm{target}}$ and initial sensor noise realizations at step $t=0$ are bitwise identical across all controllers. | **YES** | Proven in `test_49` and `test_50`. |
| **G4: Timestep-Aligned Exogenous Noise** | Closed-loop disturbance and sensor noise match bitwise at every step $t > 0$ across controllers. | **NO (Qualified)** | Anchor queries conditionally consume random variates; stream offsets occur as verified in `test_49` and `test_51`. |
| **G5: Paired Variance Reduction** | Positive correlation across matched $(s, \text{seed})$ pairs reduces the standard error of paired differences $\mathrm{SE}(\overline{\Delta\mathrm{TSR}})$. | **YES** | Guaranteed by shared initial states, identical scenario parameters, and shared episode seed derivations. |

---

## 4. Phase 3 — Authoritative H3 Baseline and Aggregation Semantics

### 4.1 Formal Decision Rule Specification
Hypothesis $H_3$ in Section 3.1.1 of the Authoritative Protocol consists of:
1. **Primary Null Hypothesis $H_{0,3}$:**
   $$\mathrm{TSR}(\hat{\pi}; \mathcal{P}_{10}) - \mathrm{TSR}(\pi_{\mathrm{V8}}; \mathcal{P}_{10}) \le \Delta_{\mathrm{NI}} = -0.05$$
2. **Co-Evaluated Comparison:**
   Co-evaluated against $\pi_{\mathrm{V7}}$ at margin $\Delta_{\mathrm{NI}} = -0.05$.
3. **Operational Utility Condition:**
   $$\widehat{\mathrm{TSR}}_{\mathrm{nominal}}(\hat{\pi}) \ge 0.94 \quad (\ge 113 / 120)$$
4. **Partition Domain:** Evaluated strictly on the $\mathcal{S}_{10}$ block of the scenario holdout ($N=1,200$). Scenarios 11 and 12 ($\mathcal{S}_{\mathrm{ext}}$) are excluded.

### 4.2 Aggregation Semantics in the Evaluator
To prevent conflating the formal primary null hypothesis with the auxiliary co-evaluation:
- `h3_overall.passed`: Set strictly to `h3_v8_passed` (rejection of $H_{0,3}$).
- `h3_overall.primary_passed`: Boolean tracking V8.1 noninferiority + nominal TSR.
- `h3_overall.coeval_passed`: Boolean tracking V7 noninferiority + nominal TSR.
- `h3_overall.all_baselines_passed`: Boolean tracking whether both baselines pass.
- `h3_overall.status`: Informative categorical string (`CONFIRMATORY_PASS_PRIMARY_AND_COEVAL`, `CONFIRMATORY_PASS_PRIMARY_ONLY`, `FAIL_PRIMARY_NONINFERIORITY`, or `FAIL_NOMINAL_UTILITY`).

---

## 5. Phase 5 — Synthetic Verification Suite

Table 1 details the expanded synthetic test suite in [`tests/test_v9_holdout_preflight.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py):

### Table 1: Expanded Methodological and Synthetic Test Suite

| Test Identifier | Methodological Invariant Tested | Assertions and Validations | Duration | Status |
| :--- | :--- | :--- | :---: | :---: |
| `test_47` | Controller-Order Invariance | V9 $\to$ V8 $\to$ V7 vs V7 $\to$ V8 $\to$ V9 bitwise equality | 0.06s | **PASS** |
| `test_48` | Early Termination Isolation | Controller 1 stop at $t=5$ leaves Controller 2 unaffected | 0.05s | **PASS** |
| `test_49` | Initial State & Mutable Divergence | Bitwise $t=0$ match; proves stream offset on anchor query | 0.05s | **PASS** |
| `test_50` | Independent State & Channel Match | In-memory Generator isolation; channel A match at $t=0$ | 0.04s | **PASS** |
| `test_51` | Anchor Query Stream Shift | Exact scalar offset tracking ($k=2$ draws per query) | 0.03s | **PASS** |
| `test_52` | Primary Pass / Co-eval Fail | `primary_passed=True`, `coeval_passed=False`, `passed=True` | 0.06s | **PASS** |
| `test_53` | Primary Fail / Co-eval Pass | `primary_passed=False`, `coeval_passed=True`, `passed=False` | 0.06s | **PASS** |
| `test_54` | Nominal TSR Failure Barrier | Nominal TSR $< 0.94$ blocks both V8 and V7 claims | 0.05s | **PASS** |
| `test_55` | S10 Block Domain Restriction | Altering $S_{\mathrm{ext}}$ outcomes leaves $H_3$ statistics invariant | 0.06s | **PASS** |

---

## 6. Regression Testing and Holdout Isolation Audit

### 6.1 Test Suite Results
1. **Preflight Verification Suite (55 tests):**
   ```bash
   PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py
   ```
   **Result:** **55 passed in 1.11s** (Exit Code: 0).
2. **Full Repository Regression Suite (166 tests):**
   ```bash
   PYTHONPATH=src uv run pytest -q
   ```
   **Result:** **166 passed in 26.04s** (Exit Code: 0). Zero regressions.

### 6.2 Proof of Production Holdout Isolation
- `results/v9/manifests/test_mix_manifest_r1.json`: **ABSENT**
- `results/v9/manifests/test_scen_manifest_r1.json`: **ABSENT**
- `results/v9/test_mix/`: **ABSENT**
- `results/v9/test_scen/`: **ABSENT**
- Reserved holdout seed blocks ($73000..74439$ and $75000..75119$): **Completely unconsumed**
- Frozen Selected Policy SHA-256: `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` (**UNCHANGED**)

---

## 7. Audit Conclusion and Final Status

### Final Status Determination: `CRN_H3_PROTOCOL_CONFIRMED_WITH_QUALIFICATIONS`

**Summary of Qualifications:**
1. **CRN Semantics Qualification:** The implementation strictly satisfies the preregistered episode-level paired design (Model A), guaranteeing independent generator states, controller-order invariance, and bitwise matching initial conditions at $t=0$. Statements in Report 14 claiming bitwise identical disturbance at every timestep were narrative overstatements and are formally superseded by this audit.
2. **H3 Aggregation Qualification:** V8.1 Martingale is the sole primary confirmatory baseline for $H_3$, with V7 MPC serving as an auxiliary co-evaluated baseline. The evaluator reports primary and co-evaluated outcomes with complete statistical transparency.
3. **Execution Guard Status:** The production evaluation pipeline remains safely locked behind the authorization barrier pending project-owner authorization.
