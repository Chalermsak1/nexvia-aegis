# NEXVIA AEGIS V9-M4 — Final Owner Authorization Readiness Review

**Document ID:** `AEGIS-V9-M4-RDY-20`  
**Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`  
**Git Branch:** `v9.0-runtime-assurance`  
**Starting Commit:** `1c505af6408993ccc85c77573a2557279e216788`  
**Ending Commit:** `(to be recorded upon commit)`  
**Audit Date:** October 26, 2026  
**Auditor:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Readiness Recommendation:** `M4_READY_FOR_OWNER_AUTHORIZATION`  

---

> [!CAUTION]
> ### CRITICAL NON-AUTHORIZATION DIRECTIVE
> This report evaluates technical, methodological, and provenance readiness for Milestone V9-M4 (Confirmatory Holdout Evaluation). **This document does NOT constitute authorization to execute Milestone V9-M4, nor does it provide or invoke any execution token.** All evaluations in this review were conducted strictly using synthetic test fixtures, in-memory models, and read-only inspection of existing calibration and validation artifacts. Production holdout manifests (`test_mix_manifest_r1.json` and `test_scen_manifest_r1.json`) and output directories (`results/v9/test_mix/` and `results/v9/test_scen/`) do not exist. Reserved holdout seed blocks (`73000..74439` for mixture holdout and `75000..75119` for scenario holdout) remain completely uninstantiated and untouched. Live execution requires an explicit, separate authorization decision and delivery of an authorization token by the project owner.

---

## 1. Abstract & Executive Summary

### 1.1 Abstract

This comprehensive readiness review establishes whether Milestone V9-M4 (Confirmatory Holdout Evaluation) of the NEXVIA AEGIS runtime assurance subsystem is ready for a separate project-owner authorization decision. We audit the repository across ten dimensions: (1) actual Git working tree and commit state, (2) authoritative M2R2 frozen policy provenance and exact parameter-vector reconciliation, (3) Hypotheses $H_1$ through $H_5$ statistical formulation and implementation fidelity, (4) primary V8.1 and auxiliary V7 baseline comparison semantics, (5) $H_3$ confidence-bound decision rule governance and sensitivity reporting, (6) Common Random Numbers (CRN) architectural coupling and variance-reduction claim boundaries, (7) production pipeline execution guards and isolation mechanisms, (8) full repository synthetic regression suite performance, (9) physical holdout file-system isolation verification, and (10) artifact hashing and provenance preservation.

The review confirms that:
- The certified frozen policy artifact is uniquely identified at `results/v9/cal_r2/selected_policy.json` (Candidate `V9_CAND_1_TIER1_STRICTEST`, raw SHA-256 `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`, canonical payload SHA-256 `90dc5c0068bb62187415bba57fbf9cafc1f18e111ad5790b0214961490902034`).
- All candidate parameter values are reconciled across the frozen candidate family (`configs/v9_candidates_frozen_r1.json`), the calibration run config (`results/v9/cal_r2/calibration_run_config_frozen_r2.json`), validation records (`results/v9/val_r1/validation_report.json`), and source code (`src/aegis/v9/risk_statistics.py:110-119`): $\alpha_{\text{mon}}=0.010$, $h=6.0$, $\tau_{\text{diff}}=3.20$, $\tau_{\text{ar}}=3.80$, $\tau_{\text{val}}=0.10$, $\tau_{\text{stop}}=0.36$. Any previous mention of $\tau_{\text{ar}}=4.0$ or $\tau_{\text{stop}}=0.35$ is formally documented as a stale narrative transcription error.
- The $H_3$ decision rule in `experiments/v9_evaluate_holdout.py` is strictly governed by the prespecified paired Student's $t$ Wald lower confidence bound ($\mathrm{LCB}_{95} > -0.05$ on $S_{10}$ and $\widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$), while Newcombe Method 10 is reported as a prespecified sensitivity analysis with boolean concurrence, avoiding both ad-hoc conjunction penalties and post-hoc method shopping.
- The production execution pipeline is fully locked behind a secret authorization token gate, single-shot directory collision checks, fail-closed manifest validation, and mock-simulator isolation.
- The reserved holdout datasets, manifests, and output directories are verified 100% absent, and reserved seed blocks (`73000..74439` and `75000..75119`) remain completely uninstantiated.
- Focused preflight tests achieve 62/62 passing (1.32s), and full repository regression tests achieve 173/173 passing (32.35s).

The subsystem is technically, methodologically, and procedurally ready for the project owner to consider authorization.

### 1.2 Executive Summary (English)

1. **Readiness Recommendation:** `M4_READY_FOR_OWNER_AUTHORIZATION`. All technical prerequisites, protocol checks, baseline pairing mechanisms, execution guards, and test suites are fully verified and pass without defects.
2. **Repository State:** Current branch `v9.0-runtime-assurance` at commit `1c505af`, cleanly aligned with `origin/v9.0-runtime-assurance`. Untracked historical artifacts in `results/v9/cal/`, `results/v9/cal_r2/`, and `results/v9/val_r1/` are preserved untouched.
3. **Policy Parameter Reconciliation:** Confirmed candidate parameters for `V9_CAND_1_TIER1_STRICTEST` are $\tau_{\text{ar}}=3.80$, $\tau_{\text{stop}}=0.36$, $\tau_{\text{diff}}=3.20$, $\tau_{\text{val}}=0.10$, $\alpha_{\text{mon}}=0.010$, $h=6.0$. Discrepant narrative mentions ($\tau_{\text{ar}}=4.0$, $\tau_{\text{stop}}=0.35$) were informal conversational transcription errors; the underlying JSON artifacts and source code are 100% consistent.
4. **Authoritative $H_3$ Decision Rule:** Anchored strictly to Student's $t$ Wald paired LCB on $S_{10}$ with $\delta_0 = -0.05$ and nominal TSR requirement $\ge 0.94$. Newcombe Method 10 is reported as sensitivity analysis with recorded concurrence.
5. **Common Random Numbers (CRN):** Episode-level pairing, matched $t=0$ initial conditions, and independent stream derivations are verified. Theoretical and empirical distinction between historical correlation ($\rho \approx 0.593$, SE reduction 36.21%) and prospective holdout variance reduction is rigorously maintained.
6. **Execution Guards & Holdout Isolation:** Execution token gate, mock isolation guard, and single-shot file write protections are active. Production holdout manifests and directories are confirmed absent (`exists = False`).
7. **Regression Status:** 62/62 preflight tests pass (1.32s); 173/173 repository tests pass (32.35s). Zero test failures.

### 1.3 บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)

1. **ข้อเสนอแนะความพร้อมขั้นสุดท้าย:** `M4_READY_FOR_OWNER_AUTHORIZATION` ระบบย่อยมีความพร้อมอย่างสมบูรณ์ในทุกมิติ ทั้งด้านความสอดคล้องตามพิธีสาร การจับคู่ข้อมูลพื้นฐาน การแยกแยะกฎการตัดสินทางสถิติ และระบบป้องกันการรันโดยไม่ได้ตั้งใจ เพื่อให้เจ้าของโครงการพิจารณาตัดสินใจอนุมัติเป็นการเฉพาะ
2. **สถานะคลังรหัสต้นฉบับ (Repository State):** สาขา `v9.0-runtime-assurance` ที่คอมมิต `1c505af` ตรงกับต้นทาง `origin` ทุกประการ ไฟล์ประวัติศาสตร์การปรับเทียบและการตรวจสอบความถูกต้องใน `results/v9/` ได้รับการเก็บรักษาไว้โดยไม่มีการลบ ดัดแปลง หรือเขียนทับ
3. **การพิสูจน์เวกเตอร์พารามิเตอร์ของนโยบายคงที่:** ยืนยันพารามิเตอร์จริงของนโยบายรอบ M2R2 (`V9_CAND_1_TIER1_STRICTEST`) คือ $\tau_{\text{ar}}=3.80$, $\tau_{\text{stop}}=0.36$, $\tau_{\text{diff}}=3.20$, $\tau_{\text{val}}=0.10$, $\alpha_{\text{mon}}=0.010$, $h=6.0$ ซึ่งตรงกัน 100% ระหว่างไฟล์โครงร่าง (`configs/`), ไฟล์ผลการรันปรับเทียบ (`cal_r2/`), ไฟล์ผลการตรวจสอบ (`val_r1/`) และรหัสต้นฉบับ (`src/aegis/v9/risk_statistics.py`) ข้อความในบทสนทนาก่อนหน้าที่กล่าวถึง $\tau_{\text{ar}}=4.0$ หรือ $\tau_{\text{stop}}=0.35$ ได้รับการบันทึกว่าเป็นข้อผิดพลาดในการพิมพ์เชิงบรรยาย (Narrative Transcription Error)
4. **เกณฑ์การตัดสินสมมติฐาน $H_3$:** เกณฑ์การตัดสินชี้ขาดเป็นไปตามพิธีสารที่ลงทะเบียนไว้ล่วงหน้าอย่างเคร่งครัด โดยใช้ paired Student's $t$ Wald LCB ($> -0.05$ บน $S_{10}$ ร่วมกับ $\widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$) และรายงาน Newcombe Method 10 เป็นการวิเคราะห์ความไว (Sensitivity Analysis) พร้อมตัวบ่งชี้ความสอดคล้อง
5. **ขอบเขตการลดความแปรปรวนของ CRN:** ยืนยันโครงสร้างการจับคู่ระดับเอพิโซด ($t=0$ Bitwise Match) แต่คงข้อจำกัดทางวิชาการว่า การลดความแปรปรวนจริงเป็นคุณสมบัติเชิงประจักษ์ที่ต้องรอการวัดผลหลังได้รับอนุมัติ
6. **การแยกส่วนชุดข้อมูล Holdout:** ยืนยันความไม่มีอยู่จริงของไฟล์ Manifest และไดเรกทอรี Holdout ทั้งหมด (`exists = False`) โดยบล็อก Seed สงวนทั้งสองช่วง (`73000..74439` และ `75000..75119`) ยังคงไม่ถูกแตะต้อง 100%
7. **ผลการทดสอบระบบ:** ชุดทดสอบ Preflight ผ่าน 62/62 รายการ (1.32 วินาที) และชุดทดสอบเต็มของทั้งคลังผ่าน 173/173 รายการ (32.35 วินาที)

---

## 2. Actual Repository State & Git Provenance

Inspection conducted on October 26, 2026:
- **Current Branch:** `v9.0-runtime-assurance`
- **Starting HEAD Commit:** `1c505af6408993ccc85c77573a2557279e216788`
- **Remote Tracking:** Up to date with `origin/v9.0-runtime-assurance`
- **Git Status (`git status --short`):**
  - Modified: `tests/test_v9_validation.py` (single trailing whitespace edit made in active editor session)
  - Untracked: Historical experiment directories `results/v9/cal/`, `results/v9/cal_r2/`, `results/v9/val_r1/`, and `results/v9/manifests/cal_manifest.json` (preserved without staging or deletion)
- **Commit History:**
  - `1c505af`: Report 19 (Frozen-Policy Provenance and H3 Decision-Method Audit)
  - `f3ede86`: Report 18 (H3 Confidence-Bound and CRN Variance-Reduction Audit)
  - `0d8350c`: Report 17 (CRN Semantics and Dual-Baseline Decision-Rule Audit)
  - `dc39f36`: Report 16 (H3 Baseline Consistency and CRN Audit)
  - `372576c`: Reports 14 & 15 (Execution Path Implementation and Mock Verification)

---

## 3. Final Policy Identity & Parameter Reconciliation

### 3.1 Provenance Verification of the Selected Policy
The authoritative certified policy artifact was inspected:
- **File Path:** `results/v9/cal_r2/selected_policy.json`
- **File Existence:** Verified present (79 lines, 2,774 bytes)
- **Raw File SHA-256:** `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`
- **Canonical Payload SHA-256:** `90dc5c0068bb62187415bba57fbf9cafc1f18e111ad5790b0214961490902034`
- **Selected Candidate ID:** `V9_CAND_1_TIER1_STRICTEST`
- **Tier Index & Label:** `1`, `Tier 1 (Strictest)`
- **Calibration Certification:** `certified: true`, `calibration_status: "V9_CALIBRATION_CERTIFIED"`
- **Stopping Reason:** `ALL_6_CANDIDATES_CERTIFIED_NO_EARLY_STOP`

### 3.2 Parameter Vector Reconciliation
Table 1 provides an exhaustive comparison across all governing specifications and artifacts:

| Parameter | Frozen Configs (`configs/v9_candidates_frozen_r1.json`) | Cal Run Config (`results/v9/cal_r2/calibration_run_config_frozen_r2.json`) | Certified Policy (`results/v9/cal_r2/selected_policy.json`) | Val Report (`results/v9/val_r1/validation_report.json`) | Source Code (`src/aegis/v9/risk_statistics.py`) | Reconciled Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `candidate_id` | `V9_CAND_1_TIER1_STRICTEST` | `V9_CAND_1_TIER1_STRICTEST` | `V9_CAND_1_TIER1_STRICTEST` | `V9_CAND_1_TIER1_STRICTEST` | `V9_CAND_1_TIER1_STRICTEST` | **MATCH** |
| `tier_index` | 1 | 1 | 1 | 1 | 1 | **MATCH** |
| `alpha_mon` | 0.010 | 0.010 | 0.010 | 0.010 | 0.010 | **MATCH** |
| `h_cusum` | 6.0 | 6.0 | 6.0 | 6.0 | 6.0 | **MATCH** |
| `tau_diff` | 3.20 | 3.20 | 3.20 | 3.20 | 3.20 | **MATCH** |
| **`tau_ar`** | **3.80** | **3.80** | **3.80** | **3.80** | **3.80** | **MATCH (3.80)** |
| `tau_val` | 0.10 | 0.10 | 0.10 | 0.10 | 0.10 | **MATCH** |
| **`tau_stop`** | **0.36** | **0.36** | **0.36** | **0.36** | **0.36** | **MATCH (0.36)** |
| `gamma_ville` | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **MATCH** |
| `probing_steps`| 36 | 36 | 36 | 36 | 36 | **MATCH** |
| `fit_start` | 1 | 1 | 1 | 1 | 1 | **MATCH** |
| `fit_end` | 22 | 22 | 22 | 22 | 22 | **MATCH** |
| `gap_start` | 23 | 23 | 23 | 23 | 23 | **MATCH** |
| `gap_end` | 24 | 24 | 24 | 24 | 24 | **MATCH** |
| `val_start` | 25 | 25 | 25 | 25 | 25 | **MATCH** |
| `val_end` | 36 | 36 | 36 | 36 | 36 | **MATCH** |
| `n_fit_min` | 10 | 10 | 10 | 10 | 10 | **MATCH** |
| `n_val_min` | 6 | 6 | 6 | 6 | 6 | **MATCH** |
| `lambda_fim_min`| 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | **MATCH** |
| `arrival_tol_m`| 0.22 | 0.22 | 0.22 | 0.22 | 0.22 | **MATCH** |
| `chord_min_m` | 0.40 | 0.40 | 0.40 | 0.40 | 0.40 | **MATCH** |
| `chord_steps` | 10 | 10 | 10 | 10 | 10 | **MATCH** |
| `max_queries` | 4 | 4 | 4 | 4 | 4 | **MATCH** |

### 3.3 Resolution of the Parameter Inconsistency
- **Finding:** The candidate parameters are completely unanimous across all JSON configuration artifacts, calibration reports, validation reports, and Python source code. The exact ground-truth values are $\tau_{\text{ar}} = 3.80$ and $\tau_{\text{stop}} = 0.36$.
- **Source of Ambiguity:** The values $\tau_{\text{ar}} = 4.0$ and $\tau_{\text{stop}} = 0.35$ appeared solely in informal conversational summaries where $\tau_{\text{ar}}$ was informally rounded and $\tau_{\text{stop}}$ was conflated with the coverage floor $C_{\min} = 0.35$ or V8's geometric threshold $0.35$.
- **Conclusion:** There is zero artifact mismatch or implementation defect. The production evaluator loads and validates the exact vector with $\tau_{\text{ar}} = 3.80$ and $\tau_{\text{stop}} = 0.36$.

### 3.4 Historical R1 Artifact Separation
The historical artifact `results/v9/cal/selected_policy.json` contains Candidate `V9_CAND_2_TIER2_VERY_STRICT` ($\tau_{\text{ar}} = 4.20, \tau_{\text{stop}} = 0.38$, raw SHA-256 `1c316d2d...`). If supplied to `experiments/v9_evaluate_holdout.py`, the loader executes `verify_and_load_selected_policy` and raises:
```text
ValueError: Selected policy candidate ID mismatch: expected `V9_CAND_1_TIER1_STRICTEST`, got `V9_CAND_2_TIER2_VERY_STRICT`.
```
This fail-closed defense is verified by preflight test `test_60`.

---

## 4. Final H1–H5 Protocol & Implementation Check

We verified the implementation of all five preregistered hypotheses in `experiments/v9_evaluate_holdout.py`:

### H1 — Selective False-Success Risk Control
- **Estimand:** $R_{\text{sel}}(\widehat{\pi}) = \mathbb{P}(\mathrm{FS} = 1 \mid A = 1)$ over mixture partition $\mathcal{D}_{\text{test}}^{\text{mix}}$ ($N = 1,440$).
- **Sample Estimator:** $\widehat{R}_{\text{sel}} = K / M$ where $K = \sum \mathrm{FS}_i$ and $M = \sum A_i$.
- **Eligibility Precondition:** $M \ge 59$ (the minimum sample size required to certify $R_{\text{sel}} \le 0.05$ under zero errors). $M \ge 59$ is checked as a necessary precondition, not treated as sufficient by itself.
- **Inferential Criterion:** 1-sided exact Clopper-Pearson 95% upper confidence bound $U_{\text{CP}}(K, M; 0.05) \le 0.05$.
- **Zero Accepted Decisions ($M = 0$):** $R_{\text{sel}}$ is evaluated as `"UNDEFINED"`. Fails certification without crashing.
- **Status Classification:** `"CONFIRMATORY_PASS"`, `"FAILED_UCB"`, or `"INSUFFICIENT_COVERAGE"`.

### H2 — Unconditional False-Success Incidence Reduction vs Baselines
- **Estimand:** Paired comparison of unconditional false-success incidence $R_{\text{inc}} = \mathrm{FS} / N$ against V8.1 Martingale and V7 MPC.
- **Matching Primitive:** Strict episode-level pairing via `align_and_pair_records` over `(seed, scenario)`.
- **Test Statistics:** McNemar exact discordant-pair test $p_{\text{McNemar}} = \text{binomtest}(\min(n_{10}, n_{01}), n_{10} + n_{01}, 0.5)$ and Newcombe paired difference 95% confidence interval.
- **Decision Rule:** Significant reduction if $n_{10} < n_{01}$ and $p_{\text{McNemar}} < 0.05$. Fail-closed handling for mismatched, missing, or duplicated records.

### H3 — TSR Noninferiority vs Baselines
- **Primary Baseline:** V8.1 Martingale.
- **Auxiliary Baseline:** V7 MPC (co-evaluated).
- **Domain:** Scenario block $S_{10}$ ($N = 1,200$ matched pairs, 120 per scenario across 10 non-extended scenarios).
- **Noninferiority Margin:** $\delta_0 = -0.05$.
- **Authoritative Decision Method:** 1-sided 95% paired Student's $t$ Wald lower confidence bound:
  $$\mathrm{LCB}_{95}(\Delta\mathrm{TSR}) = \overline{d} - t_{0.95, N-1} \frac{s_d}{\sqrt{N}} > -0.05 \quad \text{AND} \quad \widehat{\mathrm{TSR}}_{\mathrm{nominal}} \ge 0.94$$
- **Prespecified Sensitivity Method:** Newcombe Method 10 profile-score paired difference LCB is reported alongside the complete $2 \times 2$ contingency table with boolean indicator `sensitivity_newcombe_concurs`.
- **Decoupling Verification:** Neither method overrides the other post-hoc; the authoritative pass/fail decision is governed strictly by the prespecified Wald LCB and nominal TSR floor.

### H4 — Task Coverage Floor Precondition
- **Estimand:** Empirical mixture coverage $\widehat{C} = M / N$ on $\mathcal{D}_{\text{test}}^{\text{mix}}$ ($N = 1,440$).
- **Decision Rule:** Point estimate $\widehat{C} \ge 0.35$ ($M \ge 504$). Distinct from an inferential lower confidence bound.
- **Supplementary Metric:** 2-sided Wilson score 95% confidence interval reported.
- **Anti-Gaming Logic:** If $\widehat{C} < 0.35$, the evaluation harness classifies the controller as `"CONSERVATIVE_RISK_COVERAGE_TRADEOFF"` rather than certified improvement, preventing trivial abstention gaming.

### H5 — Worst-Case Scenario Safety
- **Estimand:** Unconditional false-success incidence $R_{\text{inc}, s} = \mathrm{FS}_s / N_s$ across all 12 scenarios ($N_s = 100$ episodes per scenario in $D_{\text{test}}^{\text{scen}}$).
- **Test Statistic:** Component Binomial CDF $p_{\text{inc}, s} = \operatorname{binom.cdf}(\mathrm{FS}_s, N_s, 0.05)$ under the null boundary $R_{\text{inc}, s} = 0.05$.
- **Confirmatory Global Test:** Berger Intersection-Union Test (IUT) requiring $\max_{s \in S_{12}}(p_{\text{inc}, s}) \le 0.05$.
- **Multiple Comparison Adjustment:** Sequential step-down Holm-Šidák algorithm with early stopping at the first non-rejection.
- **Selective Risk Distinction:** Scenario-level selective risk $R_{\text{sel}, s}$ is evaluated as `"UNDEFINED"` when $M_s = 0$. Zero observed false successes correctly yields $p \approx 0.0059 \le 0.05$, distinguishing rejection of the risk null from zero underlying physical risk.

---

## 5. Common Random Numbers (CRN) & Paired Analysis Audit

We audited the CRN implementation and verified the preservation of critical scientific qualifications:
1. **Model A Semantics Confirmed:** NumPy `SeedSequence` spawn keys decouple child streams at $t = 0$. The initial environment state, target position, obstacle geometry, and sensor disturbance seeds are bit-identical across paired controllers.
2. **Independent Mutable PRNG Streams:** Each controller operates on its own mutable PRNG stream. When a controller invokes active anchor queries, its PRNG state advances, causing subsequent closed-loop noise draws to diverge from a baseline that did not query anchors.
3. **Empirical Nature of Variance Reduction:** Paired evaluation reduces sample variance if and only if $\operatorname{Cov}(Y_\pi, Y_{\text{base}}) > 0$. Historical benchmark data ($N = 500$) confirms strong positive correlation ($\rho = 0.5931$, standard error reduction of 36.21%). However, on the unexecuted holdout partition, covariance cannot be guaranteed a priori and remains an empirical outcome to be quantified post-authorization.
4. **Validity of Paired Comparison Primitive:** `align_and_pair_records` matches records strictly on `(seed, scenario)`. Mismatches in seed, scenario name, record counts, or duplicate keys trigger immediate fail-closed exceptions (`ValueError`), preventing invalid pairing.

---

## 6. Production Pipeline & Execution Guard Audit

We statically inspected the production workflow in `experiments/v9_evaluate_holdout.py`:
1. **Authorization Token Guard:** Live production execution requires `--authorized-execution-token` matching `REQUIRED_EXECUTION_TOKEN = "AEGIS_V9_M4_HOLDOUT_AUTHORIZATION_20261025"`. In the absence of this token, `execute_production_holdout_pipeline` immediately aborts with `RuntimeError("UNAUTHORIZED_EXECUTION: ...")`.
2. **Single-Shot Collision Protection:** If target output directories exist, the pipeline refuses execution unless explicit cleanup is pre-authorized.
3. **Partial Failure Dumping:** If simulation fails mid-run, partial results are written to `_PARTIAL.csv` and metadata to `INCOMPLETE_INVALID.json` with non-zero exit code. No falsely successful report is ever generated.
4. **Mock Simulator Isolation:** Mock simulation requires explicit parameter `allow_mock_simulation=True`. The production pipeline refuses custom or mock simulators by default.
5. **Read-Only Preflight Mode:** Default CLI execution runs `run_preflight_checks` in read-only mode, verifying policy and manifest hashes without creating output files or consuming holdout RNG seeds.

---

## 7. Synthetic Regression Test Suite Results

We executed both test suites against the current repository state:

### 7.1 Focused Holdout Preflight Suite
```text
PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py
============================== 62 passed in 1.32s ==============================
```
- Total tests: **62 passed, 0 failed, 0 skipped** (Exit code: `0`)
- Key verified properties:
  - `test_1`–`test_14`: Outcome algebra, manifest schema, policy hash, single-shot guard, read-only preflight.
  - `test_15`–`test_21`: $H_5$ unconditional incidence, Berger IUT, Holm-Šidák step-down.
  - `test_22`–`test_29`: Record alignment, key pairing, discordant pair counts.
  - `test_30`–`test_44`: Mock simulator determinism, production pipeline token guard, partial failure dumping.
  - `test_45`–`test_55`: $H_3$ dual baseline evaluation, baseline substitution rejection, CRN independence.
  - `test_56`–`test_59`: Newcombe paired LCB boundary cases, Student's $t$ Wald concordance, CRN covariance distinction.
  - `test_60`: M2R2 certified policy provenance, raw hash `5a89d606...`, canonical hash `90dc5c00...`, and fail-closed rejection of historical R1 artifact.
  - `test_61`: Authoritative $H_3$ decision rule governed strictly by Student's $t$ Wald LCB with Newcombe sensitivity reporting.
  - `test_62`: Boundary envelope discordance qualification on $N = 1,200$.

### 7.2 Full Repository Regression Suite
```text
PYTHONPATH=src uv run pytest -q
........................................................................ [ 41%]
........................................................................ [ 83%]
.............................                                            [100%]
173 passed in 32.35s
```
- Total tests: **173 passed, 0 failed, 0 skipped** (Exit code: `0`)

---

## 8. Final Holdout Isolation Verification

Physical file-system checks conducted across all reserved production paths:

| Reserved Production Artifact | Expected State | Actual File-System Status | Isolation Verified |
| :--- | :---: | :---: | :---: |
| `results/v9/manifests/test_mix_manifest_r1.json` | Absent | `exists = False` | **PASS** |
| `results/v9/manifests/test_scen_manifest_r1.json` | Absent | `exists = False` | **PASS** |
| `results/v9/test_mix/` | Absent | `exists = False` | **PASS** |
| `results/v9/test_scen/` | Absent | `exists = False` | **PASS** |
| Seed Block `73000..74439` (Mixture Holdout) | Uninstantiated | Zero stream instantiations | **PASS** |
| Seed Block `75000..75119` (Scenario Holdout) | Uninstantiated | Zero stream instantiations | **PASS** |

Zero real holdout data was accessed, generated, or simulated.

---

## 9. Comprehensive Findings & Classification

Table 2 summarizes all audit findings across Phases 13–20:

| ID | Domain | Description | Severity | Resolution / Status |
| :---: | :--- | :--- | :---: | :--- |
| **F-01** | Provenance | Report 18 clerical path citation to `cal/selected_policy.json` | Minor (Clerical) | Reconciled in Reports 19 & 20; M2R2 path `cal_r2` verified |
| **F-02** | Provenance | Discrepant narrative mentions of $\tau_{\text{ar}}=4.0, \tau_{\text{stop}}=0.35$ | Minor (Clerical) | Reconciled in Report 20; ground truth $\tau_{\text{ar}}=3.80, \tau_{\text{stop}}=0.36$ |
| **F-03** | Methodology | Ad-hoc dual conjunction (`Student_t and Newcombe`) in $H_3$ | Moderate | Decoupled in `v9_evaluate_holdout.py`; Student's $t$ controls |
| **F-04** | Methodology | 100% concordance claim between Student's $t$ and Newcombe | Minor | Qualified in Reports 19 & 20; 1.11% discordance at boundary |
| **F-05** | Scientific Claim | CRN "guaranteed" variance reduction narrative | Minor | Qualified in Reports 16–20; covariance requirement established |
| **F-06** | Execution Guard | Authorization token gate and simulator isolation | Critical | Fully verified in source code and preflight tests 31–32 |
| **F-07** | Holdout Isolation | Preservation of reserved seed blocks and manifests | Critical | Verified 100% absent; zero holdout execution occurred |

---

## 10. Remaining Limitations

1. **Empirical Variance Reduction:** While the CRN architecture enforces bit-identical initial states at $t=0$, whether variance reduction is achieved on the holdout partition depends on empirical outcome correlation ($\rho > 0$) between controllers.
2. **Physical Hardware Safety:** Certification of selective risk ($R_{\text{sel}} \le 0.05$) applies strictly to the 12-scenario MuJoCo simulation environment ($P_{12}$) under the registered disturbance models. It does not certify unmodeled physical hardware dynamics, unmodeled distribution shifts, or zero underlying risk.
3. **Single-Shot Finality:** Milestone V9-M4 is an unrepeatable single-shot evaluation. Once executed, no retuning, parameter adjustment, or re-running is permitted.

---

## 11. Final Recommendation & Non-Authorization Directive

### 11.1 Final Recommendation

$$\mathbf{M4\_READY\_FOR\_OWNER\_AUTHORIZATION}$$

The NEXVIA AEGIS V9-M4 confirmatory holdout evaluation harness is technically, methodologically, and procedurally verified. All known discrepancies have been resolved, execution guards are active, and test suites pass with zero defects. The project is ready for a separate project-owner decision on whether to authorize execution.

### 11.2 Explicit Non-Authorization Statement
**This report does NOT authorize the execution of Milestone V9-M4.**  
No execution token has been supplied or invoked. The production evaluator remains safely locked. Live execution may only proceed upon explicit, separate authorization by the project owner.

---

## 12. Artifact Hashes & Verification Appendix

| Artifact | File Path | SHA-256 Digest |
| :--- | :--- | :--- |
| **M2R2 Frozen Policy** | `results/v9/cal_r2/selected_policy.json` | `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` |
| **M2R2 Calibration Config** | `results/v9/cal_r2/calibration_run_config_frozen_r2.json` | `f3e582b13c7903ea8974a621379b3ee42a530eb7ca5da5394ef3519b7dca09f1` |
| **Frozen Candidates Family** | `configs/v9_candidates_frozen_r1.json` | `346f95929f244b4e93f14d784e7dd1d9b5ce0168404745925eac80a5cd11bf18` |
| **Historical R1 Policy** | `results/v9/cal/selected_policy.json` | `1c316d2d97ccf1a93f2dcd4c4196aefbb3817f7bc951dee5b0290468f7de7b87` |
| **M3 Validation Report** | `results/v9/val_r1/validation_report.json` | `a84baea0cae9be1c54b6fb7914f17730e7fc40fdfc9ee839f8d5500e572620ca` |
| **Readiness Report 20 (TeX)** | `docs/reports/.../20_v9_m4_owner_authorization_readiness.tex` | `1d9a00c70e23c1c2acd9989c123ba8327c553850aefc94c614ee3535618430ae` |
| **Readiness Report 20 (PDF)** | `docs/reports/.../20_v9_m4_owner_authorization_readiness.pdf` | `6a38063c7cd4af5e33ad93ba0063abd630ff4b438d32dc327657543c9ce64443` |
| **Owner Readiness Manifest** | `docs/reports/.../report_manifest_owner_readiness.json` | `8d233e64c48d8f6e052a7b278e8164be60ba5571040d8f75dd96cd8e64b6cc5c` |
| **Readiness Report 20 (MD)** | `docs/reports/.../20_v9_m4_owner_authorization_readiness.md` | *(Finalized upon commit)* |

