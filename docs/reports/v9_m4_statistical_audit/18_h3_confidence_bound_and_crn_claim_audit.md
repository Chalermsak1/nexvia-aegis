# NEXVIA AEGIS V9-M4 — Final H3 Confidence-Bound and CRN Statistical Claim Audit

**Document ID:** `AEGIS-V9-M4-CRN-18`  
**Milestone:** V9-M4 Confirmatory Holdout Evaluation — Methodological Audit Addendum  
**Git Branch:** `v9.0-runtime-assurance`  
**Reported Prior Audit Commit:** `0d8350c` (incorporating `dc39f36`)  
**Date:** October 25, 2026  
**Final Status:** `H3_CI_CRN_CLAIMS_CONFIRMED_WITH_QUALIFICATIONS`  
**Holdout Data Accessed:** FALSE (Zero production holdout manifests, datasets, or RNG streams accessed)

---

## CRITICAL NON-AUTHORIZATION DIRECTIVE

This audit document resolves two specific methodological questions: (1) Does the H3 noninferiority confidence-bound implementation exactly match the authoritative registered protocol? (2) Are claims about variance reduction from the Common Random Numbers (CRN) design supported by empirical and theoretical evidence? **This document does NOT constitute authorization to execute Milestone V9-M4.** All empirical evaluations in this report were conducted strictly using synthetic test fixtures, in-memory models, and mock environments. Production holdout manifests (`test_mix_manifest_r1.json` and `test_scen_manifest_r1.json`) and output directories (`results/v9/test_mix/` and `results/v9/test_scen/`) do not exist. Reserved holdout seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) remain completely uninstantiated and untouched. Live execution requires explicit authorization from the project owner.

---

## Abstract

This audit resolves two foundational questions prior to production holdout authorization: (1) Does the implemented Hypothesis $H_3$ True-Success Rate (TSR) noninferiority confidence bound conform to the authoritative preregistered protocol? (2) Are claims regarding variance reduction attributable to the Common Random Numbers (CRN) design supported by available evidence?

First, comparing governing protocol texts ([docs/v9_experiment_protocol.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md)) with prior reports, we reconcile the protocol's dual parenthetical reference to *"Newcombe/Wald paired difference CI"* with the pre-execution report's specification of a paired-difference Student's $t$ lower confidence bound ($\mathrm{LCB}_{95}$). Mathematical analysis and synthetic boundary testing on the registered sample size $N = 1,200$ establish that the sample standard error $\frac{s_d}{\sqrt{N}}$ is the finite-sample Student's $t$ formulation of the paired Wald interval. At $N = 1,200$, the Student's $t$ LCB and Newcombe's profile-score LCB (Method 10, two-sided 90% confidence / one-sided 95% level) agree to within $\pm 0.00002$ ($0.002$ percentage points) across realistic discordant rates, yielding 100% decision concordance across all boundary cases. To ensure absolute protocol fidelity and eliminate ambiguity, we updated [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) to compute and report both bounds (`lcb95_delta_tsr` and `newcombe_lcb95_delta_tsr`) alongside the complete $2 \times 2$ contingency table.

Second, auditing CRN variance-reduction claims, we distinguish structural pairing mechanisms from empirical outcome distributions. While the CRN architecture enforces matched initial conditions ($t=0$) and shared scenario seeds, variance reduction $\operatorname{Var}(\overline{\Delta\mathrm{TSR}}) < \operatorname{Var}_{\text{unpaired}}$ mathematically requires positive covariance $\operatorname{Cov}(Y_{\pi}, Y_{\text{base}}) > 0$. On historical benchmark data ($N = 500$), empirical correlation was strongly positive ($\rho = 0.5931$), producing an empirical standard error reduction of $36.21\%$. However, on the unexecuted holdout partition ($\mathcal{D}_{\text{test}}^{\text{scen}}$), holdout data has not been generated or simulated. Consequently, variance reduction cannot be claimed as an established holdout fact or an unconditional architectural guarantee; rather, the CRN design *enables* paired evaluation and is *intended to exploit positive correlation*, but the actual reduction in uncertainty is an empirical property to be measured post-authorization.

Four dedicated synthetic regression tests (`test_56`–`test_59`) verify numerical convergence, boundary behavior, dual-bound reporting, and the empirical contingency of variance reduction. All 59 preflight tests and all 170 full repository tests pass with zero failures.

---

## 1. Executive Summary

### 1.1 Executive Summary (English)
1. **Confidence Bound Reconciliation:** Protocol Section 3.1.1 refers parenthetically to *"Newcombe/Wald paired difference CI"*, while Section 3.2.4 derives power from the Wald standard error $\mathrm{SE}_0 = \sqrt{q/N}$, and pre-execution reports specify a paired Student's $t$ bound. We prove that at $N = 1,200$, the finite-sample Student's $t$ Wald LCB and Newcombe's paired score LCB (Method 10) are virtually indistinguishable ($|\Delta| \le 0.00002$) and yield identical noninferiority decisions.
2. **Dual-Bound Implementation:** Updated `evaluate_scenario_holdout` in [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) to calculate and report both `lcb95_delta_tsr` (Student's $t$ Wald) and `newcombe_lcb95_delta_tsr` (Newcombe 10) for both V8.1 Martingale and V7 MPC, guaranteeing compliance under either interpretation.
3. **CRN Variance-Reduction Evidentiary Audit:** We formally qualify prior claims that CRN "guarantees" variance reduction. Mathematically, pairing reduces standard error if and only if $\operatorname{Cov}(Y_{\pi}, Y_{\text{base}}) > 0$. While historical data confirms $\rho \approx 0.593$ (yielding 36.2% SE reduction between V8 and V7), the correlation between V9 and baselines on holdout data remains an unmeasured empirical property until execution.
4. **Independent Synthetic Verification:** Verified all boundary cases on $N = 1,200$ matched pairs: all agreeing (100% and 50%), balanced discordant ($q = 0.204$), slight deficit ($\Delta = -0.015$), near boundary ($\Delta = -0.028333$ passes, $\Delta = -0.030$ fails), and nominal TSR failure ($112/120 = 0.9333 < 0.94$ fails).
5. **Synthetic Test Suite:** Added unit tests `test_56` through `test_59` in [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py). Preflight tests achieve 59/59 passing (1.90s); full regression suite achieves 170/170 passing (28.16s).
6. **Holdout Independence:** Zero production holdout manifests, datasets, or RNG streams were created or accessed. The frozen policy hash (`5a89d606...`) and calibration artifacts remain 100% identical.

### 1.2 บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)
1. **การพิสูจน์ความสอดคล้องของช่วงความเชื่อมั่น H3:** เอกสารพิธีสารหมวด 3.1.1 ระบุในวงเล็บถึง *"Newcombe/Wald paired difference CI"* ในขณะที่หมวด 3.2.4 คำนวณกำลังการทดสอบจาก Wald Standard Error และรายงานก่อนหน้าระบุเป็น Student's $t$ Lower Confidence Bound ($\mathrm{LCB}_{95}$) การพิสูจน์ทางคณิตศาสตร์และชุดข้อมูลสังเคราะห์ขนาด $N = 1,200$ ยืนยันว่าวิธี Student's $t$ Wald และวิธี Newcombe Method 10 ให้ผลลัพธ์ใกล้เคียงกันอย่างยิ่ง (ผลต่างไม่เกิน $0.00002$ หรือ $0.002\%$) และให้ผลการตัดสินความไม่ด้อยกว่าเหมือนกันทุกกรณี
2. **การรายงานช่วงความเชื่อมั่นคู่ขนาน:** ปรับปรุงฟังก์ชัน `evaluate_scenario_holdout` ใน [experiments/v9_evaluate_holdout.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) ให้คำนวณและรายงานทั้ง `lcb95_delta_tsr` (Student's $t$) และ `newcombe_lcb95_delta_tsr` (Newcombe Score) พร้อมตารางนับ $2 \times 2$ สำหรับทั้ง V8.1 และ V7 เพื่อขจัดความคลุมเครือและคงความสอดคล้องกับข้อกำหนดทุกประการ
3. **การตรวจสอบข้ออ้างการลดความแปรปรวนของ CRN:** ทำการแก้ไขข้อความในรายงานก่อนหน้าที่ระบุว่า CRN "รับประกัน" การลดความแปรปรวน โดยในทางสถิติ การจับคู่จะลด Standard Error ได้ก็ต่อเมื่อผลลัพธ์มีความสัมพันธ์เชิงบวก ($\operatorname{Cov} > 0$) เท่านั้น แม้ข้อมูลประวัติศาสตร์จะยืนยันค่า $\rho \approx 0.593$ (ลด SE ได้ 36.2%) แต่บนชุดข้อมูล Holdout จริงที่ยังไม่เคยรัน ค่าความสัมพันธ์นี้ยังถือเป็นตัวแปรเชิงประจักษ์ที่ต้องรอการวัดผลหลังได้รับอนุมัติ
4. **การคำนวณและทดสอบกรณีขอบเขต:** ทดสอบกรณีสังเคราะห์อย่างอิสระบนกลุ่มตัวอย่าง $N = 1,200$ ครบถ้วนทุกมิติ: ผลลัพธ์ตรงกันทั้งหมด, ผลลัพธ์ขัดแย้งแบบสมดุล, อัตราสำเร็จด้อยกว่าเล็กน้อย, ขอบเขตวิกฤตความไม่ด้อยกว่า ($\Delta = -0.028333$ ผ่าน, $\Delta = -0.030$ ไม่ผ่าน) และกรณี TSR สภาวะปกติไม่ถึงเกณฑ์ ($112/120 < 0.94$)
5. **การขยายชุดทดสอบเชิงสังเคราะห์:** เพิ่มการทดสอบ `test_56` ถึง `test_59` ส่งผลให้ชุดทดสอบ Preflight ผ่าน 59/59 รายการ (1.90 วินาที) และชุดทดสอบระบบรวมผ่าน 170/170 รายการ (28.16 วินาที)
6. **การคงความบริสุทธิ์ของข้อมูล Holdout:** ยืนยันว่าไม่มีการสร้างไฟล์ Manifest หรือรันซิมูเลชันบนข้อมูล Holdout จริง และค่าแฮชของนโยบายควบคุมยังคงเดิม 100%

---

## 2. Phase 1 — Audit of Registered H3 Confidence-Bound Method

### 2.1 Textual Evidence in Authoritative Repository Documents

A systematic examination of all repository documents was conducted to establish the exact registered H3 confidence-bound specification:

| Document Source | Section & Line | Exact Phrasing | Method Terminology |
| :--- | :--- | :--- | :--- |
| `docs/v9_experiment_protocol.md` | §3.1.1 (line 30) | *"One-sided 95% paired lower confidence bound (Newcombe/Wald paired difference CI on the 1,200 matched `(scenario, seed)` pairs) strictly exceeds -0.05, and `NOMINAL` true-success rate satisfies $\widehat{\mathrm{TSR}}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$."* | Dual designation: "Newcombe/Wald paired difference CI" |
| `docs/v9_experiment_protocol.md` | §3.2.4 (lines 112–118) | *"paired standard error under null equality is $\mathrm{SE}_0 = \sqrt{q / N}$, two-sided 95% CI half-width is $1.96\,\mathrm{SE}_0$, and MDE ... is $(z_{1-\alpha_{\mathrm{NI}}} + z_{1-\beta})\sqrt{q / N}$"* | Wald asymptotic paired difference formulation |
| `docs/v9_experiment_protocol.md` | Table 3.5.1 (line 247) | *"1-sided 95% paired LCB on $\Delta\mathrm{TSR} = \mathrm{TSR}(\hat{\pi}) - \mathrm{TSR}(\pi_{\mathrm{ref}})$ across $N=1,200$ matched $\mathcal{S}_{10}$ pairs (`D_test^scen`). Claim noninferiority iff $\mathrm{LCB}_{95\%}(\Delta\mathrm{TSR}) > -0.05$ AND $\widehat{\mathrm{TSR}}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$."* | 1-sided 95% paired LCB at margin $-0.05$ |
| Report 04 (`04_h2_h3_paired_comparison_audit.md`) | §2.2 vs §3.1 (lines 52–75) | §2.2 applies Newcombe Method 10 to $H_2$ ($\Delta R_{\mathrm{inc}}$). §3.1 applies Student's $t$ paired LCB $\bar{d} - t_{0.95, N-1} \frac{s_d}{\sqrt{N}}$ to $H_3$ ($\Delta\mathrm{TSR}$). | Newcombe Method 10 for $H_2$; Student's $t$ LCB for $H_3$ |
| Report 13 (`13_v9_m4_final_preexecution_review.md`) | §3.2 | Evaluated paired difference Student's $t$ lower bound for $H_3$. | Student's $t$ paired LCB |
| Report 16 & 17 | §2.1 & §4.1 | Confirmed V8.1 primary and V7 co-evaluation under paired LCB $> -0.05$ on $S_{10}$. | Paired LCB $> -0.05$ |

### 2.2 Reconciling "Newcombe/Wald" Dual Terminology

The parenthetical phrase `(Newcombe/Wald paired difference CI on the 1,200 matched (scenario, seed) pairs)` in Section 3.1.1 combines two well-known biometric procedures for paired binary differences:

1. **Wald Paired Difference Interval:**  
   Let $Y_{1, i}, Y_{2, i} \in \{0, 1\}$ represent binary outcomes on matched pair $i \in \{1, \dots, N\}$. The paired difference is $D_i = Y_{1, i} - Y_{2, i} \in \{-1, 0, 1\}$.  
   The sample mean difference is:
   $$\overline{D} = \frac{1}{N}\sum_{i=1}^N D_i = \widehat{\mathrm{TSR}}_1 - \widehat{\mathrm{TSR}}_2 = \frac{n_{10} - n_{01}}{N}$$
   The sample variance of differences is:
   $$s_D^2 = \frac{1}{N-1}\sum_{i=1}^N (D_i - \overline{D})^2 = \frac{N}{N-1}\left( \frac{n_{10} + n_{01}}{N} - \overline{D}^2 \right)$$
   The standard error of the mean difference is:
   $$\mathrm{SE}(\overline{D}) = \frac{s_D}{\sqrt{N}} = \sqrt{\frac{p_{10} + p_{01} - (p_{10} - p_{01})^2}{N-1}}$$
   The asymptotic Wald lower bound is $\overline{D} - z_{1-\alpha}\mathrm{SE}(\overline{D})$. In finite samples, substituting the Student's $t$ critical value $t_{1-\alpha, N-1}$ yields:
   $$\mathrm{LCB}_{95}^{\text{Wald-}t} = \overline{D} - t_{0.95, N-1} \frac{s_D}{\sqrt{N}}$$
   This is the exact formula implemented in `paired_difference_lcb`.

2. **Newcombe Paired Difference Interval (Method 10):**  
   Newcombe (1998, Method 10) forms the paired score interval from the individual Wilson score confidence intervals $[l_1, u_1]$ and $[l_2, u_2]$ for marginal proportions $p_1 = (n_{11} + n_{10})/N$ and $p_2 = (n_{11} + n_{01})/N$, coupled by the sample phi-coefficient correlation $\hat{\phi}$:
   $$\hat{\phi} = \frac{n_{11} n_{00} - n_{10} n_{01}}{\sqrt{(n_{11} + n_{10})(n_{01} + n_{00})(n_{11} + n_{01})(n_{10} + n_{00})}}$$
   The lower limit of the two-sided interval with coverage $1 - 2\alpha$ corresponds to the one-sided $1 - \alpha$ lower confidence bound:
   $$\mathrm{LCB}_{1-\alpha}^{\text{Newcombe}} = (p_1 - p_2) - \sqrt{(p_1 - l_1)^2 - 2\hat{\phi}(p_1 - l_1)(u_2 - p_2) + (u_2 - p_2)^2}$$
   where $l_1$ and $u_2$ are the Wilson limits at two-sided confidence $1 - 2\alpha = 0.90$.

---

## 3. Phase 2 — Mathematical Comparison and Synthetic Boundary Verification

### 3.1 Numerical Evaluation on Registered Sample Size ($N = 1,200$)

To establish whether the Student's $t$ Wald bound and the Newcombe score bound produce meaningfully different results, we independently computed both bounds across key synthetic boundary fixtures:

| Case | Scenario & Concordance | $n_{11}$ | $n_{10}$ | $n_{01}$ | $n_{00}$ | $\Delta\mathrm{TSR}$ | Student's $t$ $\mathrm{LCB}_{95}$ | Newcombe $\mathrm{LCB}_{95}$ | Difference ($t - \text{Newc}$) | Pass Criterion ($> -0.05$) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | All pairs agreeing (100% TS) | 1,200 | 0 | 0 | 0 | $0.0000$ | $0.000000$ | $-0.002250$ | $+0.002250$ | **PASS** (both) |
| **2** | All pairs agreeing (50% TS) | 600 | 0 | 0 | 600 | $0.0000$ | $0.000000$ | $0.000000$ | $0.000000$ | **PASS** (both) |
| **3** | Balanced discordant ($q = 0.204$) | 800 | 122 | 122 | 156 | $0.0000$ | $-0.021437$ | $-0.021421$ | $-0.000016$ | **PASS** (both) |
| **4** | Slight deficit ($\Delta = -0.015$) | 800 | 113 | 131 | 156 | $-0.0150$ | $-0.036425$ | $-0.036410$ | $-0.000015$ | **PASS** (both) |
| **5** | Near boundary (Pass: $\Delta = -0.0283$) | 800 | 105 | 139 | 156 | $-0.0283$ | $-0.049728$ | $-0.049713$ | $-0.000015$ | **PASS** (both) |
| **6** | Below boundary (Fail: $\Delta = -0.030$) | 800 | 104 | 140 | 156 | $-0.0300$ | $-0.051389$ | $-0.051374$ | $-0.000015$ | **FAIL** (both) |
| **7** | Nominal TSR failure ($\widehat{\mathrm{TSR}}_{\mathrm{nom}} < 0.94$) | 800 | 122 | 122 | 156 | $0.0000$ | $-0.021437$ | $-0.021421$ | $-0.000016$ | **FAIL** ($\mathrm{TSR}_{\mathrm{nom}} = 0.933$) |

### 3.2 Findings of the Mathematical Reconciliation
1. **Negligible Numerical Difference:** Across all non-degenerate cases ($q > 0$), the difference between the Student's $t$ Wald LCB and Newcombe LCB is less than $0.00002$ ($0.002\%$).
2. **Conservative Ordering:** In non-degenerate cases, the Student's $t$ LCB is slightly more conservative (lower) than the Newcombe bound because $t_{0.95, 1199} \approx 1.64613 > z_{0.95} \approx 1.64485$ and $s_D$ uses $N - 1 = 1199$ degrees of freedom.
3. **100% Decision Concordance:** In every evaluated case, both methods arrive at the identical binary pass/fail decision on the noninferiority margin $\Delta_{\mathrm{NI}} = -0.05$.
4. **Implementation Enhancement:** To guarantee that no ambiguity remains regarding protocol interpretation, `evaluate_scenario_holdout` in `experiments/v9_evaluate_holdout.py` now calculates and outputs both bounds:
   - `lcb95_delta_tsr`: Student's $t$ Wald paired LCB.
   - `newcombe_lcb95_delta_tsr`: Newcombe paired score LCB (Method 10).
   - `table_n11_n10_n01_n00`: Full $2 \times 2$ matched contingency counts.

---

## 4. Phase 3 — Audit of Common Random Numbers (CRN) Variance-Reduction Claims

### 4.1 Decomposition of CRN Guarantees

Prior reports (notably Report 17, Table 89) marked Guarantee G5 (Paired Variance Reduction) as `"YES: Guaranteed"`. We audit this claim by decomposing the random-number architecture into six distinct technical properties:

| Property | Description | Architectural Status | Evidentiary Basis |
| :--- | :--- | :---: | :--- |
| **1. Episode-Level Paired Identity** | Episodes across policies are matched by unique tuple `(scenario, seed)`. | **Enforced** | Key-equality assertion in `align_and_pair_records`. |
| **2. Matching Initial Conditions** | Target position $\mathbf{p}_{\mathrm{target}}$ and sensor noise at $t=0$ are bitwise identical. | **Enforced** | Deterministic derivation from `_derive_episode_rngs`. Proven in `test_49`. |
| **3. Separate Mutable RNG States** | Each controller receives an independent `Generator` instance in memory. | **Enforced** | Spawned via `SeedSequence.spawn(10)`. Proven in `test_48` and `test_50`. |
| **4. Timestep-Aligned Exogenous Noise** | Noise draws match at $t > 0$ regardless of actions or queries. | **Qualified (Model A)** | Sensor streams advance with queries; offsets occur upon anchor queries. |
| **5. Empirically Observed Correlation** | Paired success outcomes exhibit positive covariance $\operatorname{Cov}(Y_1, Y_2) > 0$. | **Empirical Property** | Strongly positive on historical data ($\rho = 0.593$); unmeasured on holdout. |
| **6. Variance Reduction ($\mathrm{Var}_{\text{paired}} < \mathrm{Var}_{\text{unpaired}}$)** | Pairing reduces uncertainty relative to independent sampling. | **Empirical Consequence** | Holds if and only if $\operatorname{Cov}(Y_1, Y_2) > 0$. Not an architectural guarantee. |

### 4.2 Statistical Derivation of Variance Reduction
For two binary success outcomes $Y_1, Y_2 \sim \mathrm{Bernoulli}$ across $N$ matched episodes:
$$\operatorname{Var}(\overline{D}) = \frac{\operatorname{Var}(Y_1) + \operatorname{Var}(Y_2) - 2\operatorname{Cov}(Y_1, Y_2)}{N}$$
Whereas for two independent (unpaired) samples of size $N$:
$$\operatorname{Var}(\overline{D}_{\text{unpaired}}) = \frac{\operatorname{Var}(Y_1) + \operatorname{Var}(Y_2)}{N}$$
Therefore:
$$\operatorname{Var}(\overline{D}) < \operatorname{Var}(\overline{D}_{\text{unpaired}}) \iff \operatorname{Cov}(Y_1, Y_2) > 0$$

### 4.3 Historical Empirical Evidence vs. Holdout Prospective Status

1. **Historical Benchmark Evidence ($N = 500$ on $\mathcal{S}_{10}$):**  
   In `results/next/benchmark_episodes.csv` (seeds $60000..60049$ across 10 scenarios), comparing V8.1 Martingale and V7 MPC yields:
   $$n_{11} = 208, \quad n_{10} = 43, \quad n_{01} = 59, \quad n_{00} = 190, \quad q = 0.2040$$
   $$\widehat{\mathrm{TSR}}_{\mathrm{V8}} = 0.5020, \quad \widehat{\mathrm{TSR}}_{\mathrm{V7}} = 0.5340$$
   $$\operatorname{Cov}(Y_{\mathrm{V8}}, Y_{\mathrm{V7}}) = +0.14793, \quad \rho = +0.5931$$
   $$\mathrm{SE}_{\text{unpaired}} = 0.03159, \quad \mathrm{SE}_{\text{paired}} = 0.02015 \quad (\text{SE reduction} = 36.21\%)$$
   This proves that CRN coupling successfully achieved substantial variance reduction on historical data.

2. **Prospective Status on Unexecuted Holdout Data ($\mathcal{D}_{\text{test}}^{\text{scen}}$):**  
   Because real holdout data has **never been simulated, generated, or loaded**, the empirical covariance $\operatorname{Cov}(Y_{\mathrm{V9}}, Y_{\mathrm{V8}})$ on $\mathcal{D}_{\text{test}}^{\text{scen}}$ has not been observed. While the CRN design is structurally intended to induce positive correlation through common target locations and shared scenario physics, claiming that variance reduction is an established fact on holdout data is premature and statistically unsound.

**Audit Correction:** Documentation and reports are hereby corrected to state:
> *"The Common Random Numbers (CRN) design enables paired comparisons and is structurally intended to exploit common initial conditions and shared scenario disturbances to induce positive correlation; however, the actual magnitude of variance reduction is an empirical property of the observed paired outcomes and will be measured empirically only upon authorized execution."*

---

## 5. Audit Findings and Severity Assessment

| Finding ID | Severity | Category | Description | Status & Action Taken |
| :--- | :---: | :---: | :--- | :--- |
| **M4-F04** | LOW | Estimator Ambiguity | Protocol refers parenthetically to "Newcombe/Wald paired difference CI", while earlier reports specified Student's $t$ paired LCB. | **RESOLVED:** Proved numerical convergence ($|\Delta| \le 0.00002$); updated evaluator to report both bounds simultaneously. |
| **M4-F05** | LOW | Statistical Claim | Prior Report 17 marked CRN variance reduction as an unconditional architectural guarantee (G5 = YES). | **RESOLVED:** Formally qualified that variance reduction requires $\operatorname{Cov} > 0$; verified historical reduction (36.2%) while clarifying holdout prospective status. |

---

## 6. Synthetic Regression Testing and Verification

### 6.1 Synthetic Test Implementations
Four new synthetic tests (`test_56` through `test_59`) were implemented in [tests/test_v9_holdout_preflight.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py):
- `test_56_newcombe_paired_difference_lcb_synthetic_boundary_cases`: Tests `newcombe_paired_difference_lcb` across 7 boundary fixtures.
- `test_57_h3_confidence_bound_student_t_and_newcombe_concordance`: Proves 100% decision concordance and $|\Delta| \le 0.00005$ across discordant grids.
- `test_58_evaluate_scenario_holdout_reports_both_lcb_methods_and_contingency_table`: Verifies that `evaluate_scenario_holdout` produces both LCB metrics and contingency tables summing to $N = 100$ (or $1,200$).
- `test_59_crn_variance_reduction_empirical_distinction`: Validates the mathematical condition $\operatorname{Var}_{\text{paired}} < \operatorname{Var}_{\text{unpaired}} \iff \operatorname{Cov} > 0$ using synthetic correlated, independent, and anti-correlated data.

### 6.2 Recorded Test Execution Results
```
PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py
============================== 59 passed in 1.90s ==============================
Exit Code: 0

PYTHONPATH=src uv run pytest -q
........................................................................ [ 42%]
........................................................................ [ 84%]
..........................                                               [100%]
170 passed in 28.16s
Exit Code: 0
```

---

## 7. Artifact Provenance and Checksums

| Artifact Path | SHA-256 Digest | Status |
| :--- | :--- | :---: |
| `results/v9/cal/selected_policy.json` | `1c316d2d97ccf1a93f2dcd4c4196aefbb3817f7bc951dee5b0290468f7de7b87` | UNCHANGED |
| `results/v9/cal/calibration_report.json` | `18ab85ab7d54625e4bb0d65de4786fe2896357768ed562cbfdee966a5d133337` | UNCHANGED |
| `experiments/v9_evaluate_holdout.py` | *(Current working tree)* | UPDATED |
| `tests/test_v9_holdout_preflight.py` | *(Current working tree)* | UPDATED |

---

## 8. Limitations and Scope Boundaries

1. **Evaluation Strictly Preflight:** All findings derive from mathematical analysis, historical benchmark archives ($N = 500$), and synthetic in-memory fixtures. No live holdout execution occurred.
2. **Holdout Partition Protection:** Production manifests (`test_mix_manifest_r1.json`, `test_scen_manifest_r1.json`) and output directories do not exist. Reserved seed blocks remain uninstantiated.
3. **Execution Prohibition:** This report does not grant authorization to execute V9-M4.

---

## 9. Final Conclusion and Recommendation

### Final Status Determination: `H3_CI_CRN_CLAIMS_CONFIRMED_WITH_QUALIFICATIONS`

**Justification:**
1. The H3 noninferiority confidence-bound implementation conforms to the registered protocol: the finite-sample Student's $t$ Wald LCB and Newcombe profile-score LCB converge to within $0.00002$ at $N = 1,200$, yielding 100% decision concordance. The evaluator has been updated to report both bounds simultaneously.
2. The CRN design is confirmed to enforce episode-level paired identity, bitwise matching initial conditions at $t=0$, and separate mutable RNG states. Claims of variance reduction are verified as historically demonstrated on benchmark data ($\rho = 0.593$, SE reduction $36.2\%$) and properly qualified as prospective empirical properties for the unexecuted holdout partition.
3. All 59 preflight tests and 170 repository regression tests pass with zero failures.
