# NEXVIA AEGIS V9-M4 — Owner Decision Record

**Document Identifier:** `AEGIS-V9-M4-DEC-22`  
**Phase:** Phase 22 — Formal Owner Decision Gate  
**Date:** October 26, 2026  
**Auditor / Recorder:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Base Commit:** [`c271d76`](https://github.com/Chalermsak1/nexvia-aegis/commit/c271d76)  
**Target Milestone:** Milestone V9-M4 (Confirmatory Holdout Evaluation)

---

## 1. Decision Summary & Governance Directives

| Decision Field | Formal Determination | Operational Meaning |
| :--- | :---: | :--- |
| **1. Acceptance of Report 21 Corrections** | **`ACCEPT`** | Formally accepts all five reporting corrections documented in Report 21 ([`21_v9_m4_statistical_protocol_consistency_audit.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_statistical_audit/21_v9_m4_statistical_protocol_consistency_audit.md)), superseding clerical/narrative errors in Report 20. |
| **2. Confirmation of Registered Targets** | **`CONFIRMED`** | Confirms that V9-M4 evaluation is governed strictly by the preregistered protocol ([`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md)) and verified implementation ([`experiments/v9_evaluate_holdout.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py)). |
| **3. Production Holdout Execution Decision** | **`NOT AUTHORIZED`** | Confirmatory holdout evaluation remains **strictly locked and unauthorized**. No execution token has been provided, discovered, or invoked. |

---

### Critical Governance Directives

> [!CAUTION]
> ### STRICT SEPARATION OF PROTOCOL CONFIRMATION AND EXECUTION AUTHORIZATION
> 1. **Acceptance of corrections does NOT authorize execution.** Confirming statistical decision rules and accepting Report 21 reporting errata are necessary quality-control preconditions, but do **not** constitute authorization to run Milestone V9-M4.
> 2. **Default-Closed Gate:** In accordance with strict governance invariants, production holdout evaluation defaults to **`NOT AUTHORIZED`** until the project owner independently issues an explicit, separate execution authorization accompanied by the secret execution token outside this documentation review.
> 3. **Holdout Independence Preserved:** Real holdout manifests (`test_mix_manifest_r1.json`, `test_scen_manifest_r1.json`) and output directories (`results/v9/test_mix/`, `results/v9/test_scen/`) **do not exist**. Reserved holdout seed blocks ($73000..74439$ and $75000..75119$) remain **completely uninstantiated and untouched**. Zero real holdout episodes have been generated, loaded, simulated, or evaluated.

---

### บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)

1. **การยอมรับข้อแก้ไขใน Report 21:** **`ACCEPT`** (ยอมรับอย่างเป็นทางการ)  
   ยอมรับข้อแก้ไขเชิงรายงานทั้ง 5 ประเด็นตามที่บันทึกไว้ใน Report 21 ซึ่งพิสูจน์แล้วว่ารหัสต้นฉบับการประเมินผล (`experiments/v9_evaluate_holdout.py`) และพิธีสารที่จดทะเบียนไว้ล่วงหน้ามีความถูกต้องตรงกัน 100% โดยข้อผิดพลาดใน Report 20 เป็นเพียงความคลาดเคลื่อนในการพิมพ์ข้อความบรรยายเท่านั้น
2. **การยืนยันเป้าหมายและเกณฑ์การประเมินทางสถิติ:** **`CONFIRMED`** (ยืนยันความถูกต้อง)  
   ยืนยันการใช้เกณฑ์ตามพิธีสารหลักอย่างเคร่งครัด ได้แก่ $H_1$ (เกณฑ์ความเสี่ยง $U_{\mathrm{CP},1} \le 0.05$ บน $M \ge 59$), $H_4$ (เกณฑ์สัดส่วนการตัดสินใจ $\hat{C} \ge 0.35$), ขนาดตัวอย่าง Scenario Holdout ทั้งหมด 12 ฉากทัศน์ $\times$ 120 ตอน = 1,440 ตอน, และ $H_3$ ประเมินเฉพาะกลุ่ม $S_{10}$ จำนวน 1,200 คู่เทียบ
3. **การตัดสินใจอนุมัติการรันชุดข้อมูลทดสอบจริง (Holdout):** **`NOT AUTHORIZED`** (ยังไม่อนุมัติ)  
   การประเมินผลชุดข้อมูลจริงใน Milestone V9-M4 ยังคงถูกล็อกและไม่ได้รับอนุญาตให้ดำเนินการ การยืนยันความถูกต้องของระเบียบวิธีไม่ได้หมายถึงการอนุญาตให้รันจริง การรันจริงจะต้องเกิดขึ้นจากการตัดสินใจอนุมัติเป็นการเฉพาะและการส่งมอบ Token ลับจากเจ้าของโครงการในขั้นตอนถัดไปเท่านั้น
4. **ความบริสุทธิ์ของชุดข้อมูล Holdout:** ยืนยัน 100% ว่าไม่มีการสร้าง เข้าถึง หรือจำลองข้อมูลในชุด Holdout บล็อก seed สำรอง ($73000..74439$ และ $75000..75119$) ยังคงไม่ถูกแตะต้อง

---

## 2. Decision Field 1: Acceptance of Report 21 Corrections (`ACCEPT`)

The project owner formally **ACCEPTS** the five source-of-truth corrections established in Report 21 ([`21_v9_m4_statistical_protocol_consistency_audit.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_statistical_audit/21_v9_m4_statistical_protocol_consistency_audit.md)), which supersede all prior clerical and transcription ambiguities in Report 20:

1. **Correction 1 ($H_1$ Selective Risk Upper Bound):**  
   The authoritative confirmatory threshold for Hypothesis $H_1$ is exact one-sided $95\%$ Clopper–Pearson $U_{\mathrm{CP}, 1}(K, M; 0.05) \le \mathbf{0.05}$ evaluated on accepted decisions $M \ge 59$. The citation of $\le 0.01$ in Report 20's conversational summary table was an informal transcription conflation with the M2R2 calibration Loss-to-Tolerance threshold ($\alpha_{\text{mon}} = 0.010$).
2. **Correction 2 ($H_4$ Task Coverage Precondition):**  
   The authoritative task coverage floor precondition is sample proportion $\hat{C} = M / N \ge \mathbf{0.35}$ ($M \ge 504$ on $N = 1,440$). The citation of $\ge 0.95$ in Report 20's conversational summary table was an informal transcription conflation with statistical confidence level ($1 - \delta = 0.95$) or conformal prediction set coverage.
3. **Correction 3 (Scenario Holdout Total Sample Size):**  
   The Scenario Holdout partition $\mathcal{D}_{\text{test}}^{\text{scen}}$ comprises exactly **12 scenarios $\times$ 120 seeds = 1,440 episodes** under seeds $75000..75119$ and partition branch $p = 5$. The citation of $N = 1,200$ as the partition total was a conflation with the $S_{10}$ subset size.
4. **Correction 4 ($H_5$ Scenario Allocation & Denominator):**  
   Hypothesis $H_5$ evaluates unconditional false-success incidence across all **12 scenarios** with **$N_s = 120$ episodes per scenario** ($p_{\mathrm{inc}, s} = \operatorname{binom.cdf}(\mathrm{FS}_s, 120, 0.05)$) under Berger IUT ($\max_{s} p_s \le 0.05$) and sequential step-down Holm–Šidák. The informal narrative phrases *"6 scenarios with $N=200$"* and *"12 scenarios with $N_s=100$"* in Report 20 are formally superseded as spurious arithmetic factorizations of 1,200.
5. **Correction 5 ($H_3$ Sample Size Scope):**  
   The sample size of $N = 1,200$ applies exclusively to the paired comparison on the 10 core scenarios of the **$\mathcal{S}_{10}$ block** ($10 \times 120 = 1,200$ matched pairs). The two compound stress scenarios of $\mathcal{S}_{\text{ext}}$ ($2 \times 120 = 240$ episodes) are intentionally excluded from $H_3$ to protect nominal noninferiority testing from stress-test contamination.

---

## 3. Decision Field 2: Confirmation of Registered Targets (`CONFIRMED`)

The governing statistical hypotheses, decision rules, thresholds, sample sizes, and baseline identities are formally **CONFIRMED** as follows:

| Hypothesis | Partition & Block | Estimand & Metric | Sample Size | Decision Rule & Test Statistic | Confirmatory Passing Threshold |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **$H_1$** | $\mathcal{D}_{\text{test}}^{\text{mix}}$ | Selective False-Success Risk $R_{\text{sel}} = K / M$ | $N = 1,440$ ($M \ge 59$) | Exact 1-sided Clopper–Pearson 95% UCB | $U_{\mathrm{CP}, 1}(K, M; 0.05) \le \mathbf{0.05}$ |
| **$H_2$** | $\mathcal{D}_{\text{test}}^{\text{mix}}$ | Unconditional FS Incidence Reduction vs V8.1 & V7 | $N = 1,440$ matched pairs | Exact paired McNemar test & Newcombe paired CI | $n_{10} < n_{01} \land p_{\mathrm{McNemar}} < \mathbf{0.05}$ |
| **$H_3$** | $\mathcal{D}_{\text{test}}^{\text{scen}} \cap \mathcal{S}_{10}$ | Paired TSR Difference vs V8.1 (Primary) & V7 (Auxiliary) | $N = 1,200$ matched pairs | Paired Student's $t$ Wald 95% LCB & nominal TSR | $\mathrm{LCB}_{95} > \mathbf{-0.05} \land \widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge \mathbf{0.94}$ |
| **$H_4$** | $\mathcal{D}_{\text{test}}^{\text{mix}}$ | Task Coverage Floor Precondition $\hat{C} = M / N$ | $N = 1,440$ | Sample proportion point estimate | $\hat{C} \ge \mathbf{0.35}$ ($M \ge 504$) |
| **$H_5$** | $\mathcal{D}_{\text{test}}^{\text{scen}}$ | Worst-Case Scenario Safety across 12 Scenarios | $12 \times 120 = 1,440$ episodes | Berger Intersection–Union Test & Holm–Šidák step-down | $\max_{s \in \mathcal{S}_{12}}(p_{\mathrm{inc}, s}) \le \mathbf{0.05}$ ($N_s = 120$) |

### Additional Technical Parameters Confirmed
- **Certified Frozen Policy:** [`results/v9/cal_r2/selected_policy.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/cal_r2/selected_policy.json) (`V9_CAND_1_TIER1_STRICTEST`).
  - Raw File SHA-256: `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`.
  - Canonical Payload SHA-256: `90dc5c0068bb62187415bba57fbf9cafc1f18e111ad5790b0214961490902034`.
  - Parameters: $\alpha_{\text{mon}}=0.010, h=6.0, \tau_{\text{diff}}=3.20, \tau_{\text{ar}}=3.80, \tau_{\text{val}}=0.10, \tau_{\text{stop}}=0.36$.
- **Baseline Identities:** Primary confirmatory baseline is **V8.1 Martingale** (`v8_martingale`); auxiliary co-evaluated baseline is **V7 MPC** (`v7_mpc`).
- **Paired Matching Key:** Exact 1-to-1 matching enforced on `(seed, scenario)` via `align_and_pair_records`.
- **$H_3$ Controlling Method:** Governed strictly by the paired Student's $t$ Wald LCB ($> -0.05$) and nominal TSR ($\ge 0.94$). Newcombe Method 10 is reported concurrently as prespecified sensitivity analysis with boolean concurrence indicator.
- **CRN Caveat Preserved:** Variance reduction remains an empirical outcome to be quantified post-execution, not an a priori mathematical guarantee.

---

## 4. Decision Field 3: Production Holdout Decision (`NOT AUTHORIZED`)

The production execution of Milestone V9-M4 is:

$$\mathbf{STATUS:\ NOT\ AUTHORIZED}$$

### Rationale
1. **Separation of Concerns:** The purpose of this decision task is to review and accept the Report 21 corrections, record the authoritative protocol targets, and establish repository provenance. It is not an execution runner.
2. **Fail-Closed Default:** In accordance with strict software safety governance, production holdout evaluation remains fail-closed and locked by default until a separate, deliberate operational decision is executed.
3. **Execution Guard Active:** The execution guard in [`experiments/v9_evaluate_holdout.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) requires `--authorized-execution-token` matching the secret environment token. No token has been supplied, discovered, or requested.

---

## 5. Decision Field 4: Owner Rationale & Outstanding Conditions

### Rationale for Accepting Corrections and Confirming Targets
- Protocol consistency audit Report 21 conclusively proved that the production evaluation harness ([`experiments/v9_evaluate_holdout.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py)) and the preregistered protocol ([`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md)) are in 100% agreement.
- The 62 synthetic preflight unit tests and 173 full repository regression tests pass with zero failures.
- The discrepancies noted in Report 20 were strictly narrative transcription errors. Correcting the documentation removes all lingering protocol ambiguities without requiring code modifications.

### Outstanding Conditions for Live Authorization
Before the project owner issues live execution authorization for Milestone V9-M4 in a subsequent operational step:
1. **Owner Operational Sign-Off:** The project owner must confirm that this decision record (`AEGIS-V9-M4-DEC-22`) constitutes the final pre-execution documentation baseline.
2. **Token Provisioning:** The authorized execution token (`NEXVIA_AEGIS_V9_M4_AUTHORIZED_CONFIRMATORY_EXECUTION_20261025`) must be explicitly passed to the runner in the separate execution invocation.
3. **Single-Shot Execution Environment:** Execution must proceed in a single-shot, non-interactive environment with write-access to `results/v9/test_mix/` and `results/v9/test_scen/`, ensuring clean output creation without directory collisions.

---

## 6. Decision Field 5: Repository & Report References

- **Active Git Branch:** `v9.0-runtime-assurance`
- **Active Git Commit:** [`c271d76a0ecab5085b0a056593b230c94ca29978`](https://github.com/Chalermsak1/nexvia-aegis/commit/c271d76)
- **Remote Synchronization:** Exactly matches `origin/v9.0-runtime-assurance`.
- **Governing Protocol Reference:** [`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md) (Step 3 of 3).
- **Audit Reports Reviewed:**
  - Report 20: [`20_v9_m4_owner_authorization_readiness.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_statistical_audit/20_v9_m4_owner_authorization_readiness.md)
  - Report 21: [`21_v9_m4_statistical_protocol_consistency_audit.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_statistical_audit/21_v9_m4_statistical_protocol_consistency_audit.md)
- **Audit Manifest:** [`report_manifest_protocol_consistency_audit.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_statistical_audit/report_manifest_protocol_consistency_audit.json)

---

## 7. Decision Field 6: Confirmation of Zero Holdout Execution

It is strictly certified that during this decision-gate task:
- The production Holdout evaluator was **NOT executed**.
- Zero real Holdout episodes were generated, loaded, inspected, or simulated.
- No authorization token was used, supplied, or requested.
- Reserved seed blocks ($73000..74439$ and $75000..75119$) remain **100% uninstantiated and untouched**.
- Production holdout paths (`results/v9/manifests/test_mix_manifest_r1.json`, `results/v9/manifests/test_scen_manifest_r1.json`, `results/v9/test_mix/`, `results/v9/test_scen/`) **do not exist**.
