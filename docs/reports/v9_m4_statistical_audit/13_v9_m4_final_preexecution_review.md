# NEXVIA AEGIS V9-M4 — Final Pre-Execution Review, Baseline Integrity Audit, and Production Readiness Report
**Document ID:** AEGIS-V9-M4-REV-13  
**Phase:** Final Pre-Execution Review & Baseline Integrity Audit  
**Target Branch:** `v9.0-runtime-assurance`  
**Evaluation Baseline Commit:** `a66bcc9`  
**Final Readiness Recommendation:** `M4_READY_WITH_QUALIFICATIONS`  
**Date:** October 25, 2026  
**Author:** Autonomous Verification Subsystem (Google DeepMind Antigravity)

---

## Strict Research Governance Notice
> **CRITICAL NON-AUTHORIZATION DIRECTIVE:**  
> This comprehensive document constitutes an independent pre-execution technical review and baseline integrity audit of the NEXVIA AEGIS V9-M4 confirmatory holdout evaluation pipeline. **This document does NOT constitute authorization to execute Milestone V9-M4.** No real holdout manifests or episode datasets were generated, loaded, or inspected. The reserved holdout seed blocks (`73000..74439` for mixture holdout and `75000..75119` for scenario holdout) remain completely uninstantiated, untouched, and pristine. Execution of V9-M4 requires an explicit, separate instruction and authorization decision from the project owner.

---

## Abstract
This report delivers the final pre-execution audit of Milestone V9-M4 (Confirmatory Holdout Evaluation) for the NEXVIA AEGIS runtime assurance architecture. We systematically examine: (1) cryptographic provenance and parameter immutability of the selected policy `V9_CAND_1_TIER1_STRICTEST`; (2) mathematical and statistical consistency of confirmatory decision rules for Hypotheses $H_1$ through $H_5$; (3) baseline integrity, provenance, and pairing readiness for V8.1 and V7 reference controllers; (4) single-shot execution guards, read-only preflight operations, and directory isolation; and (5) regression test reproducibility across 140 unit and subsystem tests. We confirm that the evaluation harness in `experiments/v9_evaluate_holdout.py` satisfies all preregistered inferential requirements, that all historical audit findings (M4-F01, M4-F02, M4-F03, and H5 numerical reconciliation) are fully resolved, and that holdout partitions remain completely untouched. Based on this evidence, the autonomous verification subsystem issues the final recommendation: **M4_READY_WITH_QUALIFICATIONS**.

---

## Executive Summary

### Executive Summary (English)
1. **Frozen Policy Integrity:** The selected runtime assurance policy is verified at `results/v9/cal_r2/selected_policy.json` with raw SHA-256 digest `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`. All parameters (`alpha_mon = 0.01`, `h_cusum = 6.0`, `tau_diff = 3.2`, `tau_ar = 3.8`, `tau_val = 0.1`, `tau_stop = 0.36`) match the calibrated configuration bit-for-bit without post-calibration tuning.
2. **Decision-Rule Consistency ($H_1$–$H_5$):** All five confirmatory hypotheses strictly adhere to the preregistered protocol. $H_5$ correctly evaluates unconditional false-success incidence on $N_s = 120$ via Berger's Intersection–Union Test ($\max p_s \le 0.05$), with auxiliary Holm–Šidák step-down enforcing the sequential break stopping rule. Selective risk remains strictly distinct and undefined when coverage is zero.
3. **Baseline Integrity & Pairing ($H_2$, $H_3$):** Baseline implementations for V8.1 (`AegisNextController`, commit `4d891c7`) and V7 (`AegisV7MPCBaselineController`) are verified and share the identical simulation dynamics and outcome algebra. The bijective pairing function `align_and_pair_records` enforces order-invariant matching on `(seed, scenario)` fail-closed across 8 dedicated unit tests (`test_22`–`test_29`).
4. **Execution Safeguards:** The production harness enforces defense-in-depth: default preflight read-only inspection, prohibited seed range validation, single-shot directory overwrite blocks, and a fail-closed execution authorization token barrier. Holdout isolation is 100% verified (no real manifests or output directories exist).
5. **Readiness Determination:** The pipeline is determined to be **M4_READY_WITH_QUALIFICATIONS**. Live simulation is intentionally blocked in preflight (`raise NotImplementedError`) to guarantee zero accidental holdout execution. Upon formal project-owner authorization, production execution requires wiring the simulator loop to execute the frozen policy alongside the registered baseline controllers over the authorized holdout manifests.

### บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)
1. **ความสมบูรณ์ของนโยบายที่ถูกตรึง (Policy Immutability):** นโยบายควบคุมที่ผ่านการสอบเทียบ (`results/v9/cal_r2/selected_policy.json`) ได้รับการยืนยันค่าแฮช SHA-256 แบบ Raw ตรงกับ `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` อย่างสมบูรณ์ ไม่มีการดัดแปลงค่าพารามิเตอร์ใดๆ ภายหลังการสอบเทียบ
2. **ความสอดคล้องของสมมติฐาน $H_1$–$H_5$:** กฎการตัดสินใจทางสถิติทั้ง 5 ข้อเป็นไปตามระเบียบวิธีวิจัยที่ลงทะเบียนไว้ล่วงหน้าอย่างเคร่งครัด โดย $H_5$ ประเมินความเสี่ยงอุบัติการณ์แบบไม่มีเงื่อนไข (Unconditional Incidence) บนขนาดตัวอย่าง $N_s = 120$ ด้วยการทดสอบ Berger IUT ($\max p_s \le 0.05$) พร้อมระบบ Holm–Šidák step-down ที่หยุดการปฏิเสธทันทีเมื่อพบความล้มเหลวแรก และรักษาคำนิยาม Selective Risk เป็น `UNDEFINED` เมื่อไม่มีการยอมรับภารกิจ
3. **ความพร้อมของระบบเปรียบเทียบ Baseline ($H_2, H_3$):** ตัวควบคุมอ้างอิง V8.1 (`AegisNextController`, commit `4d891c7`) และ V7 (`AegisV7MPCBaselineController`) มีประวัติความถูกต้องชัดเจน ใช้ระบบพลศาสตร์และคำจำกัดความผลลัพธ์เดียวกัน ฟังก์ชันจับคู่ `align_and_pair_records` ผ่านการทดสอบความถูกต้องอย่างเข้มงวด 8 รูปแบบ
4. **กลไกป้องกันการรันโดยไม่ได้รับอนุญาต:** มีระบบป้องกันหลายชั้น คำสั่ง CLI เริ่มต้นในโหมด Read-only Preflight, มีระบบบล็อก Seed ต้องห้าม, ป้องกันการเขียนทับไฟล์ผลลัพธ์, และระบบตรวจจับ Token ควบคุมการรัน นอกจากนี้ได้รับการยืนยันว่าไม่มีการสร้างไฟล์ Manifest หรือโฟลเดอร์ผลลัพธ์ Holdout จริงในระบบ
5. **ข้อสรุปความพร้อม:** ผลการประเมินคือ **M4_READY_WITH_QUALIFICATIONS** ระบบมีความพร้อมทางสถิติและซอฟต์แวร์ครบถ้วน แต่มีข้อกำหนดทางเทคนิคว่า Live Simulator ถูกบล็อกไว้ในขั้นตอน Preflight เพื่อป้องกันอุบัติเหตุ เมื่อเจ้าของโครงการอนุมัติการรันจริง ระบบจะต้องเปิดใช้งาน Simulator loop เพื่อรันทั้งนโยบาย V9 และ Baselines ควบคู่กันบน Holdout Manifests

---

## 1. Traceability Matrix: Preregistered Protocol to Implementation

Table~\ref{tab:traceability} provides the comprehensive traceability mapping linking authoritative protocol specifications to executable code, statistical estimands, decision thresholds, and unit regression tests.

| Hyp. | Claim Name | Population & Sample Size | Estimand & Metric | Decision Rule | Implementation Location | Unit Tests | Status |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **$H_1$** | Selective Risk Control | $\mathcal{D}_{\text{test}}^{\text{mix}}$ ($N=1,440$) | $R_{\mathrm{sel}} = FS / M$ | 1-sided 95% Clopper–Pearson UCB $\le 0.05$ subject to $M \ge 59$ | `v9_evaluate_holdout.py:626-631` | `test_1`, `test_7` | **CONFIRMATORY READY** |
| **$H_2$** | Unconditional FS Incidence Reduction | $\mathcal{D}_{\text{test}}^{\text{mix}}$ ($N=1,440$) | $R_{\mathrm{inc}} = FS / N$ vs V8.1 and V7 | Exact 2-sided McNemar $p < 0.05$ with $n_{10} < n_{01}$ | `v9_evaluate_holdout.py:636-672` | `test_22`–`test_29` | **CONFIRMATORY READY** |
| **$H_3$** | Operational Utility & TSR Noninferiority | $\mathcal{D}_{\text{test}}^{\text{scen}}$ on $\mathcal{S}_{10}$ ($N=1,200$) | $\Delta \text{TSR} = \text{TSR}_{\pi} - \text{TSR}_{\text{V7}}$ | 1-sided 95% LCB($\Delta \text{TSR}$) $> -0.05$ and $\widehat{\text{TSR}}_{\text{NOM}} \ge 0.94$ | `v9_evaluate_holdout.py:863-888` | `test_8`, `test_22`–`test_29` | **CONFIRMATORY READY** |
| **$H_4$** | Coverage Floor Precondition | $\mathcal{D}_{\text{test}}^{\text{mix}}$ ($N=1,440$) | $\widehat{\text{Cov}} = M / N$ | Empirical point estimate $\widehat{\text{Cov}} \ge 0.35$ | `v9_evaluate_holdout.py:632-635` | `test_1`, `test_8` | **CONFIRMATORY READY** |
| **$H_5$** | Worst-Case Scenario Safety Envelope | $\mathcal{D}_{\text{test}}^{\text{scen}}$ ($12 \times 120$) | $R_{\mathrm{inc}, s} = FS_s / 120$ across $\mathcal{S}_{12}$ | Berger IUT $\max_s p_{\mathrm{inc}, s} \le 0.05$ on exact Binomial CDF | `v9_evaluate_holdout.py:801-810, 891-906` | `test_15`–`test_21` | **CONFIRMATORY READY** |

---

## 2. Research Provenance & Frozen Policy Audit

### 2.1 Cryptographic Immutability of Selected Policy
The frozen selected policy artifact at `results/v9/cal_r2/selected_policy.json` was audited:
- **Raw SHA-256 Digest:** `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` (Matches registered expected hash bit-for-bit).
- **Canonical Payload Digest:** `90dc5c0068bb62187415bba57fbf9cafc1f18e111ad5790b0214961490902034`.
- **Policy Identity:** `V9_CAND_1_TIER1_STRICTEST` (Tier 1 Strictest candidate).
- **Parameter Vector:**
  $$\begin{aligned}
  \alpha_{\mathrm{mon}} &= 0.01, & h_{\mathrm{cusum}} &= 6.0, & \tau_{\mathrm{diff}} &= 3.2, & \tau_{\mathrm{ar}} &= 3.8, \\
  \tau_{\mathrm{val}} &= 0.1, & \tau_{\mathrm{stop}} &= 0.36, & \gamma_{\mathrm{ville}} &= 1.0, & N_{\mathrm{probe}} &= 36, \\
  \lambda_{\mathrm{fim},\min} &= 0.001, & d_{\mathrm{arr},\mathrm{tol}} &= 0.22, & d_{\mathrm{chord},\min} &= 0.40, & Q_{\mathrm{anchor},\max} &= 4
  \end{aligned}$$
- **Provenance Lineage:** Calibrated on Milestone V9-M2R2 under manifest `cal_manifest_r2.json` (`9154ec5a...`) with certified status `V9_CALIBRATION_CERTIFIED` ($M_{\mathrm{cal}} \ge 336$, $p_{\mathrm{sel}} \le 0.05$).

### 2.2 Historical Artifact Immutability
All prerequisite milestone artifacts were verified to ensure zero retroactive modification:
- `results/v9/cal_r2/calibration_report.json`: `a91b9b008d7486e421be016ef3d55169992b1525a720dc55f848dd37397ef050`
- `results/v9/val_r1/validation_report.json`: `c97fffa626d70eb47d34be24aa4693b047530e14cce316d296c095ec40daec4e`
- `results/v9/manifests/cal_manifest_r2.json`: `9154ec5a26c8b9195d24dbe39f8f4a13824b2210a4ceb3dd43644265ca5970c7`
- `results/v9/manifests/val_manifest_r1.json`: `d6ae0837f6ebca02ae9cf714f346b978939a9ceba533cf2ea56c3da87a71871f`

---

## 3. Statistical Decision-Rule Consistency & Numerical Reconciliation

### 3.1 Hypothesis $H_5$ Estimand & Multiplicity Architecture
The narrow consistency audit (Report 11) and numerical reconciliation addendum (Report 12) established:
1. **Global Conjunctive IUT Decision:** $H_5$ represents a single global conjunction $\bigcap_{s=1}^{12} \{ R_{\mathrm{inc}, s} \le 0.05 \}$. By Berger (1982), testing each component at unadjusted nominal level $\alpha = 0.05$ guarantees overall Type I error $\le 0.05$. In `experiments/v9_evaluate_holdout.py`, line 904 strictly assigns `CONFIRMATORY_PASS_IUT` iff $\max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc}, s} \le 0.05$.
2. **Auxiliary Holm–Šidák Step-Down:** Preregistered for certifying simultaneous individual scenario claims under Familywise Error Rate (FWER) control. The sequential stopping defect (where elementwise comparisons failed to break on non-rejection) was remediated in commit `1da7d21` by enforcing $k^* = \min \{ j : p_{(j)} > \alpha_{(j)} \}$.
3. **Exact Binomial CDF Probabilities ($N_s = 120, p_0 = 0.05$):**
   - $K=0$: $0.0021224263786981585$ (Formatted: `"0.002122"`)
   - $K=1$: $0.015527224559949685$ (Formatted: `"0.015527"`)
   - $K=2$: $0.057505408338079490$ (Formatted: `"0.057505"`)
   - $K=3$: $0.144407613352453470$ (Formatted: `"0.144408"`)
   The production code computes exact 64-bit float values via `scipy.stats.binom.cdf`. Narrative discrepancies in Report 09 were traced to early Gaussian continuity approximations.
4. **Zero-Coverage Invariant:** When $M_s = 0$ (100% safe abstention), unconditional incidence $R_{\mathrm{inc}, s} = 0 / 120 = 0$ achieves $p = (0.95)^{120} \approx 0.002122 \le 0.05$, correctly passing without penalty, while selective risk $R_{\mathrm{sel}, s} = 0/0$ is explicitly reported as `UNDEFINED`.

---

## 4. Baseline Integrity Audit for $H_2$ and $H_3$

### 4.1 Provenance of Baseline Controllers
- **Baseline V8.1 (`AegisNextController`):** Located at `src/aegis/next/agent_next.py`. Provenance corresponds to audited snapshot commit `4d891c7500cfb4c8110f276038455bc62765ef3b` (`chore: snapshot audited V1-V8.1 workspace before V9.0`). Evaluates sequential Ville martingale monitoring with fixed orthogonal probing.
- **Baseline V7 (`AegisV7MPCBaselineController`):** Located at `src/aegis/next/baselines.py:423-455`. Evaluates risk-constrained pseudo-MPC with on-demand anchor queries via `AegisV7RecoveryController`.

### 4.2 Outcome Accounting & Dynamic Compatibility
Both baseline controllers interface with the identical simulation environment (`WorldConfig`, `SensorConfig`, `run_single_episode`), ensuring:
- Identical episode duration ($T=300$, $\Delta t = 0.02$).
- Identical arrival threshold ($d \le 0.22\text{ m}$) and terminal success criterion ($d \le 0.45\text{ m}$).
- Identical fail-unsafe crash accounting: unhandled exceptions log `crashed = 1`, penalized as false successes.

### 4.3 Bijective Record Pairing Primitives
The pairing primitive `align_and_pair_records` in `experiments/v9_evaluate_holdout.py:350-435` enforces:
1. Exact matching on `(int(seed), str(scenario))`.
2. Bijective 1-to-1 correspondence (rejects missing baseline records, missing policy records, and duplicate keys fail-closed).
3. Order-invariance (verified by `test_23` under reversed baseline row order).
4. Rejection of count mismatches and malformed identity fields (verified by `test_24`–`test_28`).

---

## 5. Execution Guard & Holdout Isolation Assessment

### 5.1 Verification of Defensive Guard Layers
1. **Default CLI Read-Only Preflight:** Running `experiments/v9_evaluate_holdout.py` without arguments defaults to `--preflight-only`, which executes non-destructive preflight checks and outputs JSON metadata without writing files or invoking simulation.
2. **Fail-Closed Execution Authorization Guard:** When invoked with `--no-preflight-only`, `execute_holdout_workflow` verifies that `authorized_execution_token == REQUIRED_EXECUTION_TOKEN`. Without this explicit token, it raises `RuntimeError` immediately.
3. **Preflight Hard Block:** In preflight mode (when synthetic records are not supplied), the function raises `NotImplementedError("Live simulator execution is blocked during preflight milestone.")`, preventing accidental simulator calls even if an execution token were provided.
4. **Single-Shot Overwrite Protection:** Checks for the presence of existing output artifacts (`test_*_episodes.csv`, `test_*_report.json`). If found, raises `RuntimeError` fail-closed.
5. **Token Privacy Invariant:** The authorization token string is treated strictly as a technical barrier. It is **never** logged, printed, or included in report artifacts.

### 5.2 Physical Partition Isolation Audit
A direct filesystem inspection verified the absence of production holdout paths:
- `results/v9/manifests/test_mix_manifest_r1.json`: **DOES NOT EXIST** (`exists=False`)
- `results/v9/manifests/test_scen_manifest_r1.json`: **DOES NOT EXIST** (`exists=False`)
- `results/v9/test_mix/`: **DOES NOT EXIST** (`exists=False`)
- `results/v9/test_scen/`: **DOES NOT EXIST** (`exists=False`)

The reserved holdout seed blocks (`73000..74439` and `75000..75119`) remain completely uninstantiated.

---

## 6. Regression Testing & Synthetic Evidence

The complete repository regression test suite was executed:
```bash
PYTHONPATH=src uv run pytest -q
```
- **Exit Code:** `0` (Success).
- **Execution Time:** 30.71 seconds.
- **Test Summary:** **140 passed** (0 failures, 0 errors, 0 skipped, 0 warnings).
- **Focused Preflight Suite (`test_v9_holdout_preflight.py`):** **29 passed** in 1.13 seconds, covering outcome algebra, coverage guardrails, Berger IUT boundaries (Cases A–E), Holm–Šidák thresholds, and paired record alignment.

---

## 7. Audit Findings Register

| ID | Severity | Category | Description | Remediation / Verification Status |
| :---: | :---: | :--- | :--- | :--- |
| **M4-F01** | LOW | Protocol | Evolution in hypothesis numbering between early narrative and finalized review. | **RESOLVED:** Traceability matrix establishes strict mapping; finalized specification followed. |
| **M4-F02** | HIGH | Statistical | $H_5$ evaluated selective risk $M_s$ with punitive $p=1.0$ fallback under total abstention. | **RESOLVED:** Decoupled unconditional incidence $R_{\mathrm{inc}, s}$ on $N_s = 120$; verified in `test_15`–`test_20`. |
| **M4-F03** | MEDIUM | Integrity | Paired comparisons in $H_2/H_3$ used naive sequential `zip()` loops. | **RESOLVED:** Implemented bijective, order-invariant `align_and_pair_records`; verified in `test_22`–`test_29`. |
| **M4-F04** | LOW | Numerical | Discrepancy in narrative reference probabilities ($0.148197$ vs $0.144408$ for $K=3$). | **RESOLVED:** Reconciled in Report 12; evaluator confirmed exact; `test_17` hardened to $10^{-12}$. |
| **M4-F05** | MEDIUM | Technical | Evaluator CLI currently blocks live simulator (`raise NotImplementedError`). | **QUALIFICATION:** Live simulation blocked in preflight by design; requires wiring upon authorization. |

---

## 8. Final Readiness Recommendation

Following exhaustive technical, mathematical, and algorithmic verification, the autonomous verification subsystem issues the following final readiness determination:

$$\mathbf{FINAL\ READINESS\ RECOMMENDATION:\ M4\_READY\_WITH\_QUALIFICATIONS}$$

### Specific Qualifications
1. **Live Simulator Unblocking Invariant:** The preflight block (`raise NotImplementedError`) in `execute_holdout_workflow` must be replaced with the production simulation loop upon authorization to execute the authorized holdout manifests.
2. **Paired Baseline Holdout Execution Invariant:** For $H_2$ and $H_3$ paired tests, the evaluation harness requires baseline holdout records (`v8_records` and `v7_records`). The production workflow must simulate or ingest these baseline runs over the exact same holdout seeds.
3. **Dual Reporting Invariant for $H_5$:** Confirmatory certification of $H_5$ via `CONFIRMATORY_PASS_IUT` certifies the global intersection hypothesis $\max_s R_{\mathrm{inc}, s} \le 0.05$ at familywise level $\alpha \le 0.05$. It does not imply that all 12 individual scenarios are certified as individual claims under FWER control unless `holm_shidak_rejections_count == 12`. Both metrics must be reported side by side.
4. **Physical Hardware Scope Invariant:** Confirmatory holdout results apply to the simulated 12-scenario environment under preregistered dynamics and sensor noise models; they do not certify unshielded physical hardware deployment.

---

## 9. Explicit Non-Authorization Statement
> **NON-AUTHORIZATION FORMAL DECLARATION:**  
> This readiness document certifies that the NEXVIA AEGIS V9-M4 confirmatory holdout evaluation pipeline is mathematically exact, technically hardened, and compliant with all preregistered protocols. **However, this document does NOT authorize execution of Milestone V9-M4.** Milestone V9-M4 production holdout execution is strictly reserved for an explicit, separate instruction and authorization decision from the project owner.
