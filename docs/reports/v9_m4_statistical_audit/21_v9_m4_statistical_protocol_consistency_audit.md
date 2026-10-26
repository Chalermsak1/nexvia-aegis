# NEXVIA AEGIS V9-M4 Independent Statistical Audit
## Phase 21 Report: Source-of-Truth Protocol Consistency Audit of Report 20

**Document Identifier:** `AEGIS-V9-M4-AUD-21`  
**Phase:** Phase 21 — Statistical Protocol & Sample Allocation Consistency Audit  
**Date:** October 26, 2026  
**Auditor:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Starting Commit:** [`a8895a0`](https://github.com/Chalermsak1/nexvia-aegis/commit/a8895a0)  
**Status Determination:** `M4_REPORTING_CORRECTIONS_REQUIRED`

---

> [!CAUTION]
> ### CRITICAL GOVERNANCE & NON-AUTHORIZATION DIRECTIVE
> This document reports an independent source-of-truth protocol consistency audit of Report 20 (`20_v9_m4_owner_authorization_readiness`) and reconciles all statistical decision thresholds, estimands, sample size partitions, and scenario allocations before the project owner makes an authorization decision for Milestone V9-M4 (Confirmatory Holdout Evaluation).
> 
> **This document does NOT constitute authorization to execute Milestone V9-M4.**
> - Real holdout manifests (`test_mix_manifest_r1.json`, `test_scen_manifest_r1.json`) and output directories (`results/v9/test_mix/`, `results/v9/test_scen/`) **do not exist**.
> - Reserved holdout seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) remain **completely uninstantiated and untouched**.
> - Zero real holdout episodes have been generated, loaded, simulated, or evaluated.
> - No execution token has been supplied, discovered, printed, or used.
> - Historical calibration, validation, and audit reports 00–20 remain preserved untouched.

---

## Executive Summary

This audit performs an exhaustive source-of-truth reconciliation of Report 20 (`20_v9_m4_owner_authorization_readiness`) against the governing preregistered experiment protocol, frozen configuration files, production implementation code, and regression tests.

The review resolves five specific potential discrepancies identified in Report 20:
1. **Hypothesis $H_1$ (Selective Risk) Threshold:** Whether the upper confidence bound threshold is $0.01$ or $0.05$.
2. **Hypothesis $H_4$ (Task Coverage) Threshold:** Whether the coverage precondition threshold is $\ge 0.95$ or $\ge 0.35$.
3. **Scenario Holdout Total Sample Size:** Whether the total scenario holdout partition has $N = 1,200$ or $N = 1,440$ episodes.
4. **Hypothesis $H_5$ Scenario Allocation & Denominator:** Whether $H_5$ evaluates across $6$ scenarios with $N = 200$, $12$ scenarios with $N_s = 100$, or $12$ scenarios with $N_s = 120$.
5. **Hypothesis $H_3$ Sample Size Alignment:** Clarifying whether $N = 1,200$ is an $S_{10}$-specific matched-pair count or the total scenario holdout size.

### Core Audit Determination

$$\mathbf{AUDIT\ STATUS:\ M4\_REPORTING\_CORRECTIONS\_REQUIRED}$$

### Key Findings Summary
1. **Production Code & Registered Protocol in 100% Agreement:**  
   The authoritative experiment protocol (`docs/v9_experiment_protocol.md`), the production holdout evaluation harness (`experiments/v9_evaluate_holdout.py`), and the synthetic regression test suite (`tests/test_v9_holdout_preflight.py`) agree unanimously and without defect on all statistical estimands, decision rules, thresholds, sample sizes, and scenario allocations. There is **zero code or configuration defect**.
2. **Identified Issues are Purely Narrative/Transcription Errors in Report 20:**  
   The identified inconsistencies in Report 20 stem exclusively from clerical narrative transcription errors in the conversational executive summaries, manifest metadata strings, and informal descriptive sentences:
   - **$H_1$:** Report 20's summary table listed $\text{UCB} \le 0.01$, conflating the M2R2 calibration loss-to-tolerance parameter $\alpha_{\text{mon}} = 0.010$ with the registered holdout confirmatory threshold $\alpha = 0.05$. In contrast, Report 20's own technical markdown body (line 140) and LaTeX source (line 140) correctly specified $\le 0.05$.
   - **$H_4$:** Report 20's summary table listed coverage $\ge 0.95$, conflating the task coverage floor precondition ($C_{\min} = 0.35$) with nominal statistical confidence ($1 - \delta = 0.95$) or conformal prediction coverage ($1 - \alpha = 0.95$). Report 20's markdown body (line 162) and LaTeX source (line 143) correctly specified $\ge 0.35$.
   - **Scenario Holdout Total & $H_5$ Allocation:** Report 20 conflated the $H_3$ core block sample size ($N_{\mathcal{S}_{10}} = 1,200$) with the total scenario holdout partition size ($N = 1,440$), leading to spurious narrative factorizations ($6 \times 200$ or $12 \times 100$). The true registered sampling design is unequivocally **12 scenarios $\times$ 120 episodes/scenario = 1,440 episodes**, with seeds $75000..75119$ instantiated under branch $p=5$.
3. **No Code Modification Required:**  
   Because the production implementation and test fixtures strictly implement the registered protocol, the code must not be altered. The errata are confined to documentation and reporting artifacts.

---

### บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)

1. **ผลการตรวจสอบความสอดคล้องของระเบียบวิธี:** `M4_REPORTING_CORRECTIONS_REQUIRED`  
   จากการตรวจสอบความถูกต้องของรายงานฉบับที่ 20 (Report 20) เทียบกับพิธีสารที่จดทะเบียนไว้ล่วงหน้า รหัสต้นฉบับการประเมินผล และชุดการทดสอบถดถอย พบว่า **รหัสต้นฉบับและพิธีสารมีความสอดคล้องกัน 100% โดยสมบูรณ์ ไม่พบข้อบกพร่องในโค้ดหรือการกำหนดค่าใดๆ**
2. **สาเหตุของความคลาดเคลื่อน:**  
   ข้อความที่ไม่สอดคล้องกันในรายงานฉบับที่ 20 เกิดจาก **ความคลาดเคลื่อนในการพิมพ์เชิงบรรยาย (Transcription/Narrative Errors)** ในส่วนสรุปการสนทนาและข้อความประกอบบางส่วนเท่านั้น:
   - **สมมติฐาน $H_1$ (Selective Risk):** เกณฑ์ที่ถูกต้องคือ $U_{\mathrm{CP},1} \le 0.05$ บนจำนวนการตัดสินใจ $M \ge 59$ (การระบุ $0.01$ เกิดจากการสับสนกับค่าขอบเขตความคลาดเคลื่อนในการสอบเทียบ $\alpha_{\text{mon}} = 0.010$)
   - **สมมติฐาน $H_4$ (Task Coverage):** เกณฑ์สัดส่วนการตัดสินใจขั้นต่ำที่ถูกต้องคือ $\hat{C} \ge 0.35$ หรือ $35\%$ ($M \ge 504$) (การระบุ $0.95$ เกิดจากการสับสนกับระดับความเชื่อมั่น $1-\delta = 0.95$)
   - **ขนาดตัวอย่างรวมของ Scenario Holdout และ $H_5$:** การออกแบบที่แท้จริงคือ **12 ฉากทัศน์ $\times$ 120 ตอน = 1,440 ตอน** โดยใช้ seed ช่วง $75000..75119$ สำหรับขนาด $N = 1,200$ นั้นเป็นขนาดตัวอย่างเฉพาะกลุ่มฉากทัศน์หลัก 10 ฉากทัศน์แรก ($S_{10}$) ที่ใช้ทดสอบความไม่ด้อยกว่า ($H_3$) เท่านั้น
3. **การดำเนินการต่อไป:**  
   ไม่จำเป็นต้องแก้ไขรหัสต้นฉบับทางสถิติ แต่ต้องบันทึกข้อแก้ไขเชิงรายงานนี้อย่างเป็นทางการในรายงานฉบับที่ 21 เพื่อให้เจ้าของโครงการมีข้อมูลที่ถูกต้องแม่นยำในการพิจารณาตัดสินใจอนุมัติ

---

## 1. Repository Identity & Evidence Inspected

- **Workspace Path:** `/Users/chalermsak/Desktop/nexvia-aegis-main`
- **Current Branch:** `v9.0-runtime-assurance`
- **Current HEAD Commit:** [`a8895a0b4ccd534286f1c52297cd0f59bddcc886`](https://github.com/Chalermsak1/nexvia-aegis/commit/a8895a0)
- **Remote Synchronization:** Exactly synchronized with `origin/v9.0-runtime-assurance` (zero unpushed commits, zero unpulled commits).
- **Working Tree State:** Clean with respect to tracked files. Existing untracked calibration and validation directories under `results/v9/` (`cal/`, `cal_r2/`, `val_r1/`) are strictly preserved untouched.
- **Report 20 Artifact Checksums:**
  - `docs/reports/v9_m4_statistical_audit/20_v9_m4_owner_authorization_readiness.md`  
    SHA-256: `36502a1207e316c3a5b843f92370400a150f1195f2709200456353eabdd5d9f0` (30,146 bytes)
  - `docs/reports/v9_m4_statistical_audit/20_v9_m4_owner_authorization_readiness.tex`  
    SHA-256: `1d9a00c70e23c1c2acd9989c123ba8327c553850aefc94c614ee3535618430ae` (20,065 bytes)
  - `docs/reports/v9_m4_statistical_audit/20_v9_m4_owner_authorization_readiness.pdf`  
    SHA-256: `6a38063c7cd4af5e33ad93ba0063abd630ff4b438d32dc327657543c9ce64443` (137,037 bytes, 4 pages, VALIDATION: PASS)
  - `docs/reports/v9_m4_statistical_audit/report_manifest_owner_readiness.json`  
    SHA-256: `8d233e64c48d8f6e052a7b278e8164be60ba5571040d8f75dd96cd8e64b6cc5c`

---

## 2. Authoritative Protocol Hierarchy & Traceability

In accordance with repository governance conventions, conflicting statements are resolved by applying the strict precedence hierarchy:
1. **Level 1 — Authoritative Preregistered Protocol & Formal Amendments:**  
   - `docs/v9_experiment_protocol.md` (Step 3 of 3: Frozen Protocol locked prior to V9 implementation)
   - `docs/v9_risk_calibration_design.md` (Step 2 of 3: Fixed-Sequence LTT and Loss-to-Tolerance design)
   - `docs/v9_m2r2_protocol_amendment.md` (Formal M2R2 Calibration and Candidate Re-ranking amendment)
   - `docs/v9_m2r2_statistical_consistency_amendment.md` (Reconciled calibration tolerance threshold $\alpha_{\text{mon}} = 0.010$)
   - `docs/v9_m4_readiness_review.md` (Pre-execution partition layout, sample allocation, and hypothesis mapping)
2. **Level 2 — Frozen Configuration Manifests:**  
   - `configs/v9_candidates_frozen_r1.json` (Candidate family definitions)
   - `results/v9/cal_r2/selected_policy.json` (Certified policy artifact)
   - `results/v9/cal_r2/calibration_run_config_frozen_r2.json` (Certified calibration parameters)
3. **Level 3 — Production Implementation Code:**  
   - `experiments/v9_evaluate_holdout.py` (Holdout evaluation harness and statistical estimators)
   - `src/aegis/v9/risk_statistics.py` (Confidence bounds, Wilson intervals, outcome algebra)
   - `src/aegis/v9/randomization.py` (SeedSequence hierarchy, partition branch constants)
4. **Level 4 — Regression Test Suites:**  
   - `tests/test_v9_holdout_preflight.py` (62 synthetic unit and boundary tests)
   - `tests/test_v9_validation.py` (10 validation pipeline tests)
   - `tests/test_v9_step_zero_fail_closed.py` (Fail-closed execution guard tests)
5. **Level 5 — Historical Reports & Narrative Summaries:**  
   - Reports 00 through 20 in `docs/reports/v9_m4_statistical_audit/`

---

## 3. Discrepancy-by-Discrepancy Source-of-Truth Reconciliation

| Audit Dimension | Report 20 Inconsistency | Authoritative Protocol Reference | Production Implementation Reference | Regression Test Evidence | Root Cause & Resolution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **H1 Selective-Risk Upper Bound** | Conversational summary table listed $\le 0.01$ | `docs/v9_experiment_protocol.md` lines 15, 20–22: $\alpha = 0.05$, $U_{\mathrm{CP},1} \le 0.05$ on $M \ge 59$ | `experiments/v9_evaluate_holdout.py` lines 666–670: `h1_ucb95 <= 0.05` on `m >= 59` | `tests/test_v9_holdout_preflight.py` line 220: `M=60 >= 59 and K=0 -> UCB95 <= 0.05` | **Transcription Error**. Summary table conflated M2R2 calibration tolerance $\alpha_{\text{mon}} = 0.010$ with holdout risk threshold $\alpha = 0.05$. Protocol and code both enforce $0.05$. |
| **H4 Task Coverage Precondition** | Conversational summary table listed coverage $\ge 0.95$ | `docs/v9_experiment_protocol.md` line 22: $\hat{C}_{\text{test}}^{\text{mix}}(\hat{\pi}) \ge C_{\min} = 0.35$ | `experiments/v9_evaluate_holdout.py` lines 673–674: `cov = m / n >= 0.35` | `tests/test_v9_holdout_preflight.py` line 1107: verifies `h4_coverage_floor` pass at $\ge 0.35$ | **Transcription Error**. Summary table conflated task decision coverage floor ($C_{\min} = 0.35$) with nominal confidence ($1 - \delta = 0.95$). Protocol and code both enforce $\ge 0.35$. |
| **Scenario Holdout Total Episodes** | Conversational summary listed $N = 1,200$ total | `docs/v9_experiment_protocol.md` line 41: 12 scenarios $\times$ 120 seeds = $1,440$ episodes | `experiments/v9_evaluate_holdout.py` lines 93, 808–814: `TEST_SCEN_EXPECTED_EPISODES = 1440` | `tests/test_v9_holdout_preflight.py` line 805: raises `ValueError` if total episodes $\ne 1,440$ | **Conflation Error**. Summary conflated $S_{10}$ subset size ($N = 1,200$) with full scenario holdout size ($N = 1,440$). Code enforces $1,440$. |
| **H5 Scenario Allocation & Denominator** | Summary listed "6 scenarios with $N=200$"; Report 20 text had "$N_s=100$" | `docs/v9_experiment_protocol.md` lines 36–38, 43–58: 12 scenarios, $N_s = 120$ per scenario | `experiments/v9_evaluate_holdout.py` lines 92, 824–830: 12 scenarios, $N_s = 120$ per scenario | `tests/test_v9_holdout_preflight.py` lines 390–420: tests $N_s = 120$ across all 12 scenarios | **Transcription Error**. Spurious factorizations of $1,200$ ($6 \times 200$ and $12 \times 100$) in narrative. Protocol and code enforce $12 \times 120 = 1,440$. |
| **H3 Sample Size Scope** | Ambiguity whether $N=1,200$ applies to entire partition or $S_{10}$ | `docs/v9_experiment_protocol.md` line 28: evaluated on $S_{10}$ block ($10 \times 120 = 1,200$ matched pairs) | `experiments/v9_evaluate_holdout.py` lines 909–940: filters `scen.suite == "S_10"`, $1,200$ pairs | `tests/test_v9_holdout_preflight.py` line 2008: `test_55` proves $S_{\text{ext}}$ excluded from $H_3$ | **Clarity Reconciled**. $N=1,200$ is exclusively the $S_{10}$ matched-pair count. Full scenario partition is $1,440$ episodes. |

---

## 4. Resolution of Specific Inconsistencies

### 4.1 Resolution of Hypothesis $H_1$ (Selective Risk Threshold)

- **The Registered Target:** $\alpha = 0.05$ ($5.0\%$).
- **The Decision Rule:**
  $$\text{Pass } H_1 \iff M \ge 59 \quad \text{AND} \quad U_{\mathrm{CP}, 1}(K, M; 0.05) \le 0.05$$
  where $M = \sum_{i=1}^N I(A_i = 1)$ is the number of accepted decisions, $K = \sum_{i=1}^N I(\mathrm{FS}_i = 1)$ is the number of false successes, and $U_{\mathrm{CP}, 1}$ is the exact one-sided $95\%$ Clopper–Pearson upper confidence bound.
- **Why $0.01$ was Incorrectly Cited in Summary Text:**  
  During Milestone V9-M2R2, the policy calibration algorithm (`experiments/v9_calibrate_ltt.py`) operated under a Loss-to-Tolerance (LTT) parameter $\alpha_{\text{mon}} = 0.010$ ($1.0\%$) to calibrate candidate $\tau_{\text{stop}} = 0.36$. The author of Report 20's conversational summary table mistakenly transcribed this calibration parameter ($\alpha_{\text{mon}} = 0.010$) into the confirmatory holdout hypothesis $H_1$, stating $\le 0.01$.
- **Verification of Ground Truth:**  
  - In `docs/v9_experiment_protocol.md` (Section 3.1.1, line 15): *"All primary safety claims operate at nominal confidence level $1 - \delta = 0.95$ ($\delta = 0.05$) with primary selective-risk target $\alpha = 0.05$ (`5.0%`)."*
  - In `experiments/v9_evaluate_holdout.py` (lines 666–670):
    ```python
    h1_precondition_met = m >= 59
    h1_ucb95 = clopper_pearson_one_sided_ucb(fs, m, delta=0.05) if m > 0 else float("nan")
    h1_passed = bool(h1_precondition_met and not math.isnan(h1_ucb95) and h1_ucb95 <= 0.05)
    ```
  - In Report 20's own technical markdown body (line 140) and LaTeX source (line 140): *"tests 1-sided exact Clopper--Pearson 95\% UCB $U_{\text{CP}}(K, M; 0.05) \le 0.05$."*
- **Denominator Zero Handling:**  
  When $M = 0$ (total abstention), $R_{\text{sel}}$ is evaluated as `"UNDEFINED"` and `h1_ucb95` evaluates to `NaN`. Because `h1_precondition_met = (0 >= 59) = False`, $H_1$ evaluates to `passed = False` with status `"INSUFFICIENT_COVERAGE"`, failing certification cleanly and fail-closed without runtime exceptions.

### 4.2 Resolution of Hypothesis $H_4$ (Task Coverage Floor Precondition)

- **The Registered Target:** $C_{\min} = 0.35$ ($35.0\%$).
- **The Decision Rule:**
  $$\text{Pass } H_4 \iff \hat{C} = \frac{M}{N} \ge 0.35 \quad (M \ge 504 \text{ on } N = 1,440)$$
- **Why $\ge 0.95$ was Incorrectly Cited in Summary Text:**  
  In conformal prediction literature, set coverage is frequently formulated at confidence level $1 - \alpha = 0.95$. The summary author conflated this inferential confidence level ($95\%$) with selective classification task coverage ($\hat{C} = M/N$). In certified runtime assurance with an abstention option, requiring $95\%$ task coverage would penalize the policy for safely abstaining on dangerous fault scenarios, completely subverting the safety monitor.
- **Verification of Ground Truth:**  
  - In `docs/v9_experiment_protocol.md` (Section 3.1.1, line 22): *"and empirical holdout coverage $\hat{C}_{\text{test}}^{\text{mix}}(\hat{\pi}) \ge C_{\min} = 0.35$."*
  - In `docs/v9_m4_readiness_review.md` (Table 3, line 56): *"$\hat{C}(\hat{\pi}; \mathcal{P}_{12}) \ge C_{\min} = 0.35$ (target $\ge 0.45$)."*
  - In `experiments/v9_evaluate_holdout.py` (lines 673–674):
    ```python
    h4_passed = bool(cov >= 0.35)
    h4_status = "PASS_ADEQUATE_UTILITY" if h4_passed else "FAIL_COVERAGE_DEGENERATE"
    ```
  - In Report 20's own technical markdown body (line 162) and LaTeX source (line 143): *"Point estimate $\widehat{C} = M / N \ge 0.35$ on $\mathcal{D}_{\text{test}}^{\text{mix}}$ ($M \ge 504$)."*
- **Inferential Nature:**  
  $H_4$ is explicitly an **empirical sample proportion precondition** ($\hat{C} \ge 0.35$), not an inferential lower confidence bound. A two-sided Wilson score $95\%$ confidence interval is reported alongside for descriptive utility uncertainty, but does not govern the pass/fail precondition.

### 4.3 Resolution of Scenario Holdout Partition Allocation & $H_5$ Design

- **The Registered Scenario Grid:**
  The scenario holdout partition $\mathcal{D}_{\text{test}}^{\text{scen}}$ is a deterministic stratified grid over all 12 scenarios:
  $$\mathcal{S}_{12} = \mathcal{S}_{10} \cup \mathcal{S}_{\text{ext}}$$
  - **$\mathcal{S}_{10}$ Core Suite (10 scenarios):** `NOMINAL`, `PRIMARY_BIAS`, `INDEPENDENT_BIAS`, `CORRELATED_BIAS`, `SENSOR_DRIFT`, `OUTLIER_BURSTS`, `SENSOR_DROPOUT`, `FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, `COMPOUND_HOLDOUT_EXTREME`.
  - **$\mathcal{S}_{\text{ext}}$ Extended Stress Suite (2 scenarios):** `COMPOUND_DRIFT_DROPOUT`, `COMPOUND_ANTIPODAL_RANGE_SHIFT`.
- **Per-Scenario Sample Size:** Exactly **$N_s = 120$ episodes per scenario**.
- **Reserved Seed Range:** Seeds $75000..75119$ ($75119 - 75000 + 1 = 120$ unique seeds).
- **Total Scenario Holdout Episodes:**
  $$N_{\text{total}}^{\text{scen}} = 12 \text{ scenarios} \times 120 \text{ seeds/scenario} = \mathbf{1,440} \text{ episodes}$$
- **Origin of the False Rationalizations in Report 20:**  
  Because Hypothesis $H_3$ is evaluated exclusively on the 10 core scenarios of $\mathcal{S}_{10}$, its sample size is $10 \times 120 = \mathbf{1,200}$ matched pairs. The author of Report 20 remembered the number $1,200$ and mistakenly assumed the entire scenario holdout partition had $1,200$ episodes. To reconcile this false total, the author invented two conflicting narrative rationalizations:
  1. In the conversational summary table and manifest: *"across 6 scenarios with $N = 200$ each"* ($6 \times 200 = 1,200$).
  2. In the markdown body (line 167) and LaTeX source (line 144): *"across all 12 scenarios ($N_s = 100$ episodes per scenario)"* ($12 \times 100 = 1,200$).
- **Refutation by Code and Preflight Tests:**  
  - `experiments/v9_evaluate_holdout.py` (lines 808–814) strictly executes:
    ```python
    scenarios = build_v9_s12_scenarios()  # returns exactly 12 scenarios
    expected_total = len(scenarios) * expected_seeds_per_scenario  # 12 * 120 = 1440
    if len(records) != expected_total:
        raise ValueError(f"Stratified scenario record count mismatch: expected {expected_total}...")
    ```
  - And lines 827–830 strictly enforce that every scenario has $n_s = 120$:
    ```python
    if n_s != expected_seeds_per_scenario:  # expected_seeds_per_scenario = 120
        raise ValueError(f"Scenario '{scen.name}' episode count mismatch: expected 120, got {n_s}.")
    ```
  Any run with $N = 1,200$, $N_s = 100$, or $N_s = 200$ **fails closed immediately with `ValueError`**. The code and protocol require unequivocally $12 \times 120 = 1,440$ episodes.

### 4.4 Resolution of Hypothesis $H_3$ Sample Size Scope

- **Hypothesis $H_3$ Objective:** True-Success Rate (TSR) Noninferiority against V8.1 Martingale (primary baseline) and V7 MPC (auxiliary co-evaluated baseline) at margin $\Delta_{\mathrm{NI}} = -0.05$.
- **Target Subsample:** Strictly the **$\mathcal{S}_{10}$ block** (`scen.suite == "S_10"`).
- **Matched Pair Count:**
  $$N_{H_3} = 10 \text{ scenarios} \times 120 \text{ episodes/scenario} = \mathbf{1,200} \text{ matched pairs}$$
- **Controlling Decision Rule:**
  $$\text{Pass } H_3 \iff \mathrm{LCB}_{95}(\Delta\mathrm{TSR}) = \overline{d} - t_{0.95, 1199} \frac{s_d}{\sqrt{1200}} > -0.05 \quad \text{AND} \quad \widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$$
- **Sensitivity Analysis:** Newcombe Method 10 paired profile-score lower bound is reported alongside with boolean concurrence indicator `sensitivity_newcombe_concurs`. It does not override the Student's $t$ Wald decision.
- **Independence from $\mathcal{S}_{\text{ext}}$:**  
  Preflight test `test_55_h3_s10_block_restriction` verifies that modifying outcomes in scenarios 11 and 12 ($\mathcal{S}_{\text{ext}}$) produces $0.0000000$ change in $H_3$ statistics. $H_3$ operates strictly on the $1,200$ matched pairs of $\mathcal{S}_{10}$.

---

## 5. Full Statistical Decision Rule Reference Table

| Hypothesis | Target Partition | Candidate Metric & Estimand | Sample Size | Decision Rule / Test Statistic | Passing Threshold | Implementation File & Function |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$H_1$** | $\mathcal{D}_{\text{test}}^{\text{mix}}$ | Selective False-Success Risk $R_{\text{sel}} = K / M$ | $N = 1,440$ ($M \ge 59$) | Exact 1-sided Clopper–Pearson 95% UCB | $U_{\mathrm{CP}, 1}(K, M; 0.05) \le 0.05$ | `experiments/v9_evaluate_holdout.py`: `evaluate_mixture_holdout` |
| **$H_2$** | $\mathcal{D}_{\text{test}}^{\text{mix}}$ | Unconditional FS Incidence Reduction vs V8.1 & V7 | $N = 1,440$ matched pairs | Exact paired McNemar test & Newcombe paired CI | $n_{10} < n_{01} \land p_{\mathrm{McNemar}} < 0.05$ | `experiments/v9_evaluate_holdout.py`: `evaluate_mixture_holdout` |
| **$H_3$** | $\mathcal{D}_{\text{test}}^{\text{scen}} \cap \mathcal{S}_{10}$ | Paired TSR Difference vs V8.1 (Primary) & V7 (Auxiliary) | $N = 1,200$ matched pairs | Paired Student's $t$ Wald 95% LCB & nominal TSR | $\mathrm{LCB}_{95} > -0.05 \land \widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$ | `experiments/v9_evaluate_holdout.py`: `evaluate_scenario_holdout` |
| **$H_4$** | $\mathcal{D}_{\text{test}}^{\text{mix}}$ | Task Coverage Floor Precondition $\hat{C} = M / N$ | $N = 1,440$ | Sample proportion point estimate | $\hat{C} \ge 0.35$ ($M \ge 504$) | `experiments/v9_evaluate_holdout.py`: `evaluate_mixture_holdout` |
| **$H_5$** | $\mathcal{D}_{\text{test}}^{\text{scen}}$ | Worst-Case Scenario Safety across 12 Scenarios | $12 \times 120 = 1,440$ episodes | Berger Intersection–Union Test & Holm–Šidák step-down | $\max_{s \in \mathcal{S}_{12}}(p_{\mathrm{inc}, s}) \le 0.05$ ($p_s = \operatorname{binom.cdf}$) | `experiments/v9_evaluate_holdout.py`: `evaluate_scenario_holdout` |

---

## 6. Regression Testing & Pipeline Integrity

The test suites were executed under clean isolated environments:
1. **Focused Preflight Suite:**  
   `PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py`  
   **Result:** **62 passed** in 1.44s (Exit code: `0`).
2. **Full Repository Regression Suite:**  
   `PYTHONPATH=src uv run pytest -q`  
   **Result:** **173 passed** in 31.44s (Exit code: `0`).

All 62 preflight tests specifically validate:
- Exact Clopper–Pearson inversion for $H_1$ under $M \ge 59$ and threshold $0.05$ (`test_1`, `test_7`).
- Fail-closed handling of undefined selective risk ($M = 0$).
- Strict coverage floor precondition at $\ge 0.35$ (`test_1`, `test_33`).
- Rejection of mismatched scenario record counts and enforcement of $12 \times 120 = 1,440$ (`test_8`, `test_18`).
- Strict $S_{10}$ restriction for $H_3$ ($N = 1,200$ pairs) (`test_55`).
- Berger IUT conjunction across all 12 scenarios with sequential step-down Holm–Šidák (`test_20`, `test_21`).
- Execution guards: secret authorization token gate, single-shot collision refusal, mock simulator refusal (`test_10`, `test_31`, `test_32`, `test_35`).

---

## 7. Holdout Isolation Verification

All reserved holdout file paths remain completely absent from the file system:
- `results/v9/manifests/test_mix_manifest_r1.json`: **ABSENT (`False`)**
- `results/v9/manifests/test_scen_manifest_r1.json`: **ABSENT (`False`)**
- `results/v9/test_mix/`: **ABSENT (`False`)**
- `results/v9/test_scen/`: **ABSENT (`False`)**
- Reserved seed blocks $73000..74439$ and $75000..75119$: **Untouched / Uninstantiated**.

Zero production holdout data has been created, accessed, loaded, or evaluated.

---

## 8. Corrections Required and Owner Decision Roadmap

### Summary of Required Narrative Corrections
The following errata in Report 20 (`docs/reports/v9_m4_statistical_audit/20_v9_m4_owner_authorization_readiness.*` and `report_manifest_owner_readiness.json`) are formally documented and superseded by this Report 21:
1. **$H_1$ Threshold:** Replace any mention of $\le 0.01$ with the authoritative threshold $U_{\mathrm{CP}, 1}(K, M; 0.05) \le 0.05$ on $M \ge 59$.
2. **$H_4$ Threshold:** Replace any mention of coverage $\ge 0.95$ with the authoritative point-estimate precondition $\hat{C} = M / N \ge 0.35$ ($M \ge 504$).
3. **Scenario Holdout Partition Size:** Clarify that the total Scenario Holdout partition contains $12 \text{ scenarios} \times 120 \text{ seeds} = \mathbf{1,440}$ episodes ($N = 1,440$), not $1,200$.
4. **$H_5$ Scenario Allocation:** Clarify that $H_5$ evaluates unconditional incidence across all **12 scenarios** with **$N_s = 120$ episodes per scenario**, refuting the spurious narrative phrases *"6 scenarios with $N=200$"* and *"12 scenarios with $N_s=100$"*.
5. **$H_3$ Sample Size Scope:** Confirm that $N = 1,200$ is exclusively the matched-pair count of the 10-scenario core block ($\mathcal{S}_{10}$), not the total partition size.

### Required Owner Decision
Before the project owner executes or authorizes Milestone V9-M4:
1. The project owner must formally accept the reporting corrections documented in this Report 21.
2. The project owner must confirm that authorization will proceed under the authoritative preregistered protocol ($H_1$ threshold $\le 0.05$, $H_4$ threshold $\ge 0.35$, Scenario Holdout size $1,440$ episodes, $H_5$ across 12 scenarios $\times$ 120 episodes, and $H_3$ across 1,200 matched pairs on $S_{10}$).
3. Execution remains blocked pending the owner's separate, explicit delivery of an authorized execution token.
