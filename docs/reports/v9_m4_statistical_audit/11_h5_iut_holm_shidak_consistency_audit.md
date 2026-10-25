# NEXVIA AEGIS V9-M4 — Final H5 IUT / Holm–Šidák Consistency Audit
**Document ID:** AEGIS-V9-M4-AUD-11  
**Phase:** Preregistered Multiplicity and Decision Rule Verification  
**Target Branch:** `v9.0-runtime-assurance`  
**Latest Remediation Commit:** `ffa8acf`  
**Audit Finding:** `H5_CONSISTENCY_CONFIRMED_WITH_QUALIFICATIONS`  
**Date:** October 25, 2026  
**Author:** Autonomous Verification Subsystem (Google DeepMind Antigravity)

---

## Strict Research Governance Notice
> **CRITICAL GOVERNANCE INVARIANT:**  
> This document reports an independent statistical and algorithmic consistency audit of the NEXVIA AEGIS V9-M4 confirmatory holdout evaluation harness, focusing specifically on the interaction between the Berger Intersection–Union Test (IUT), the Holm–Šidák step-down procedure, and synthetic boundary test fixtures. **This document does NOT constitute authorization to execute V9-M4.** No real holdout manifests or episode data have been generated, loaded, or inspected. The reserved holdout seed blocks (`73000..74439` and `75000..75119`) remain completely uninstantiated and untouched. All evaluations reported herein are strictly based on synthetic fixtures, mathematical derivations, and unit regression tests.

---

## 1. Executive Summary and Audit Determination

This audit provides a narrow, mathematically rigorous verification of Hypothesis $H_5$ (Worst-Case Scenario Safety Envelope) across the preregistered experiment protocol, the implementation in `experiments/v9_evaluate_holdout.py`, and the synthetic regression test suite in `tests/test_v9_holdout_preflight.py`.

### Primary Audit Findings

1. **Authoritative Specification Alignment:**
   - The primary confirmatory objective of Hypothesis $H_5$ is a **single global conjunctive claim**:
     $$H_{1,5}: \bigcap_{s=1}^{12} \left\{ R_{\mathrm{inc}, s}(\hat{\pi}) \le 0.05 \right\} \quad \text{versus} \quad H_{0,5}: \bigcup_{s=1}^{12} \left\{ R_{\mathrm{inc}, s}(\hat{\pi}) > 0.05 \right\}$$
   - Under the classical Intersection–Union Test principle (Berger, 1982), rejecting $H_{0,5}$ requires that **all 12 scenario nulls be rejected at unadjusted level $\alpha = 0.05$**:
     $$\text{Decision Rule:} \quad \max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc}, s} \le 0.05$$
   - The size of this test is bounded above by $\alpha = 0.05$ without any multiplicity adjustment. Testing each component at $\alpha = 0.05$ rigorously guarantees Familywise Type I Error control for the global conjunctive hypothesis.

2. **Role of Holm–Šidák Step-Down Procedure:**
   - The protocol (`docs/v9_experiment_protocol.md`, Section 3.1.1, Item 5) specifies Holm–Šidák step-down and Šidák allocation ($\delta_{\mathrm{Šidák}} = 1 - 0.95^{1/12} \approx 0.004265$) as an **auxiliary multiplicity control framework** for reporting simultaneous 95% Clopper–Pearson upper bounds and certifying **individual scenario-level claims** under FWER control.
   - It is **not** the decision rule for the global confirmatory status `h5_status`. Requiring all 12 scenarios to pass Holm–Šidák step-down would correspond to testing an intersection of hypotheses under a union-intersection framework, which would be severely over-conservative for an intersection-union objective.

3. **Algorithmic Defect Identified and Remediated:**
   - Prior to this audit, line 895 of `experiments/v9_evaluate_holdout.py` computed `holm_rejections` via an elementwise list comprehension without the canonical sequentially rejective break condition. If step-down failed at step $r$, the loop continued and could falsely record rejections at higher indices $j > r$ if $p_{(j)} \le \alpha_{(j)}$.
   - This defect has been resolved by implementing the strict sequentially rejective stopping rule:
     $$k^* = \min \{ j \in \{1, \dots, 12\} : p_{(j)} > \alpha_{(j)} \}$$
     Once $p_{(j)} > \alpha_{(j)}$, testing halts and all subsequent hypotheses are declared non-rejected.

4. **Synthetic Boundary Verification (`test_20`):**
   - Synthetic test `test_20` was refactored and expanded to cover five exhaustive boundary configurations (Cases A–E). All cases confirm exact theoretical agreement with independent statistical calculations.

### Final Audit Determination
$$\mathbf{AUDIT\ CONCLUSION:\ H5\_CONSISTENCY\_CONFIRMED\_WITH\_QUALIFICATIONS}$$

---

## 2. Authoritative Specification Audit

### 2.1 Preregistered Protocol Text
The authoritative specification is defined in `docs/v9_experiment_protocol.md` (Section 3.1.1, Item 5, and Section 3.1.2):

> **docs/v9_experiment_protocol.md (Section 3.1.1, Item 5):**  
> *"Report simultaneous 95% one-sided Clopper–Pearson bounds across all 12 scenarios using Šidák allocation $\delta_{\mathrm{Šidák}} = 1 - 0.95^{1/12} \approx 0.004265$ (and Holm step-down) for both $R_{\mathrm{inc},s}$ and $R_{\mathrm{sel},s}$ (explicitly marking $M_s = 0$ as `UNDEFINED`), plus Berger's Intersection–Union test ($\max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc},s} \le 0.05$) for worst-case unconditional incidence $\max_{s \in \mathcal{S}_{12}} R_{\mathrm{inc},s}(\hat{\pi}) \le 0.05$."*

> **docs/v9_experiment_protocol.md (Section 3.1.2):**  
> *"Confirmatory success requires passing all of H1, H2 (vs V8 and vs V7), H3, H4, and H5 simultaneously."*

### 2.2 Mathematical Structure of the Hypotheses

| Level | Hypothesis Statement | Rejection Condition | Multiplicity Correction |
| :--- | :--- | :--- | :--- |
| **Component** | $H_{0,5,s}: R_{\mathrm{inc}, s} > 0.05 \quad \text{vs} \quad H_{1,5,s}: R_{\mathrm{inc}, s} \le 0.05$ | $p_{\mathrm{inc}, s} \le 0.05$ | None (Tested at $\alpha = 0.05$) |
| **Global Conjunction ($H_5$)** | $H_{0,5}: \bigcup_{s=1}^{12} \{ R_{\mathrm{inc}, s} > 0.05 \} \quad \text{vs} \quad H_{1,5}: \bigcap_{s=1}^{12} \{ R_{\mathrm{inc}, s} \le 0.05 \}$ | $\max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc}, s} \le 0.05$ | Berger IUT (Size $\le 0.05$) |
| **Individual Scenario Claims** | Separate reporting of individual scenario safety claims | $p_{(j)} \le \alpha_{(j)} \quad \forall j \le r$ | Holm–Šidák Step-Down |

### 2.3 Statistical Theory: Berger (1982) Intersection–Union Principle
Let $\Theta_0 = \bigcup_{s=1}^K \Theta_{0,s}$ and $\Theta_1 = \bigcap_{s=1}^K \Theta_{1,s}$. An Intersection–Union Test (IUT) rejects $H_0: \theta \in \Theta_0$ in favor of $H_1: \theta \in \Theta_1$ if and only if each component null hypothesis $H_{0,s}$ is rejected.

Let $R_s$ be the level-$\alpha$ rejection region for $H_{0,s}$. The overall rejection region is $R = \bigcap_{s=1}^K R_s$. Then:
$$\sup_{\theta \in \Theta_0} P_\theta(R) = \sup_{s=1,\dots,K} \sup_{\theta \in \Theta_{0,s}} P_\theta\left(\bigcap_{j=1}^K R_j\right) \le \sup_{s=1,\dots,K} \sup_{\theta \in \Theta_{0,s}} P_\theta(R_s) \le \alpha$$
Thus, **no multiplicity correction is required for the global confirmatory decision rule**. Applying a Bonferroni or Holm–Šidák correction to the component tests of an IUT is mathematically inappropriate and would induce extreme conservatism, driving the true Type I error rate toward $\alpha^K \approx (0.05)^{12} \approx 2.4 \times 10^{-16}$.

---

## 3. Implementation Logic Trace

In `experiments/v9_evaluate_holdout.py`:

```
evaluate_scenario_holdout(records, baseline_records)
  │
  ├── 1. Scenario Stratification: Validate exactly 12 scenarios with N_s = 120 (total N = 1,440)
  │
  ├── 2. Component P-Value Calculation:
  │      p_inc,s = scipy.stats.binom.cdf(FS_s, n=120, p=0.05)
  │      p_values_for_iut.append(p_inc,s)
  │
  ├── 3. Global Berger IUT:
  │      iut_passed = berger_intersection_union_test(p_values_for_iut, alpha=0.05)
  │      --> Returns: max(p_values_for_iut) <= 0.05
  │      h5_status = "CONFIRMATORY_PASS_IUT" if iut_passed else "RETAIN_SAFETY_NULL"
  │
  └── 4. Auxiliary Holm–Šidák Step-Down:
         holm_thresholds = holm_shidak_adjusted_thresholds(12, alpha=0.05)
         sorted_p = sorted(p_values_for_iut)
         stopped = False
         for p, thresh in zip(sorted_p, holm_thresholds):
             if not stopped and p <= thresh:
                 holm_rejections.append(True)
             else:
                 stopped = True
                 holm_rejections.append(False)
         holm_shidak_rejections_count = sum(holm_rejections)
```

The overall status `h5_status` is determined **exclusively** by `berger_intersection_union_test(p_values_for_iut, alpha=0.05)`, exactly matching the registered protocol.

---

## 4. Independent Synthetic Boundary Audit (`test_20`)

For $N_s = 120$ episodes per scenario and $p_0 = 0.05$, the exact binomial cumulative probabilities $P(X \le k)$ are:
- $k = 0$: $p = (0.95)^{120} \approx 0.00212214$
- $k = 1$: $p = 0.00212214 + 120(0.05)(0.95)^{119} \approx 0.01552277$
- $k = 2$: $p \approx 0.05750489$
- $k = 3$: $p \approx 0.148197$

The 12 Holm–Šidák step-down thresholds $\alpha_{(r)} = 1 - (1 - 0.05)^{1/(13 - r)}$ are:
$$\begin{aligned}
\alpha_{(1)} &= 0.004265, \quad \alpha_{(2)} = 0.004652, \quad \alpha_{(3)} = 0.005116, \quad \alpha_{(4)} = 0.005684, \\
\alpha_{(5)} &= 0.006394, \quad \alpha_{(6)} = 0.007301, \quad \alpha_{(7)} = 0.008512, \quad \alpha_{(8)} = 0.010206, \\
\alpha_{(9)} &= 0.012741, \quad \alpha_{(10)} = 0.016952, \quad \alpha_{(11)} = 0.025321, \quad \alpha_{(12)} = 0.050000
\end{aligned}$$

### Detailed Results Across Cases A–E

| Case | Scenario FS Counts | Ordered Component $p$-Values | Step-Down Decisions | H-Š Rejections | Berger IUT Decision | Overall $H_5$ Status |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| **Case A** | All 12 scenarios $FS = 0$ | $p_{(1..12)} = 0.002122$ | $p_{(j)} \le \alpha_{(j)}$ for all $j \in \{1..12\}$ | **12 / 12** | $\max p = 0.002122 \le 0.05$ | `CONFIRMATORY_PASS_IUT` |
| **Case B** | All 12 scenarios $FS = 1$ | $p_{(1..12)} = 0.015523$ | $p_{(1)} = 0.015523 > \alpha_{(1)} = 0.004265$ (halts) | **0 / 12** | $\max p = 0.015523 \le 0.05$ | `CONFIRMATORY_PASS_IUT` |
| **Case C** | 6 $FS = 0$, 6 $FS = 1$ | $p_{(1..6)} = 0.002122$, $p_{(7..12)} = 0.015523$ | Rejects $j=1..6$; halts at $j=7$ ($0.015523 > 0.008512$) | **6 / 12** | $\max p = 0.015523 \le 0.05$ | `CONFIRMATORY_PASS_IUT` |
| **Case D** | 11 $FS = 0$, 1 $FS = 2$ | $p_{(1..11)} = 0.002122$, $p_{(12)} = 0.057505$ | Rejects $j=1..11$; halts at $j=12$ ($0.057505 > 0.050000$) | **11 / 12** | $\max p = 0.057505 > 0.05$ | `RETAIN_SAFETY_NULL` |
| **Case E** | 1 $FS = 0$, 11 $FS = 1$ | $p_{(1)} = 0.002122$, $p_{(2..12)} = 0.015523$ | Rejects $j=1$; halts at $j=2$ ($0.015523 > 0.004652$) | **1 / 12** | $\max p = 0.015523 \le 0.05$ | `CONFIRMATORY_PASS_IUT` |

### Critical Analytical Insight on Case B
Case B demonstrates the fundamental difference between the **global conjunctive IUT** and **individual scenario certifications**:
- Every individual scenario has $FS = 1$ ($R_{\mathrm{inc}} = 1/120 = 0.83\%$), which is well below the 5% tolerance threshold.
- The component $p$-value $p = 0.015523$ is strictly less than 0.05.
- Therefore, the global Berger IUT is satisfied ($\max p_s \le 0.05$), and `CONFIRMATORY_PASS_IUT` is correctly assigned.
- However, because all 12 scenarios have identical $p$-values exceeding the first Šidák step-down threshold ($\alpha_{(1)} = 0.004265$), **zero individual scenarios can be individually claimed under FWER control**.
- This proves why the condition `FS <= 1 for all scenarios` guarantees an overall confirmatory pass under the registered IUT, but does *not* guarantee scenario-level rejections under Holm–Šidák.

---

## 5. Regression and Test Suite Results

The modified test suite in `tests/test_v9_holdout_preflight.py` (`test_20`) and the full regression suite were executed:
- **Focused Preflight Suite (`test_v9_holdout_preflight.py`):** 29 passed in 1.20s.
- **Full Repository Regression Suite (`pytest -q`):** 140 passed in 32.06s.

---

## 6. Audit Conclusion and Qualification

### Final Audit Conclusion
$$\mathbf{H5\_CONSISTENCY\_CONFIRMED\_WITH\_QUALIFICATIONS}$$

### Qualifications
1. **Algorithmic Defect Remediated:** The sequential stopping logic in line 895 of `experiments/v9_evaluate_holdout.py` has been corrected to ensure that `holm_shidak_rejections_count` strictly reflects the sequentially rejective step-down algorithm.
2. **Dual Reporting Invariant:** Confirmatory certification of $H_5$ via `CONFIRMATORY_PASS_IUT` certifies the global intersection hypothesis $\max_s R_{\mathrm{inc}, s} \le 0.05$ at familywise level $\alpha \le 0.05$. It does not imply that all 12 scenarios are certified as individual post-hoc claims under FWER control unless `holm_shidak_rejections_count == 12`. Both metrics must be reported transparently in research publications.
3. **No Protocol Amendment Required:** Because `evaluate_scenario_holdout` already uses the unadjusted Berger IUT for the overall confirmatory decision, the implementation is fully faithful to the registered protocol.
