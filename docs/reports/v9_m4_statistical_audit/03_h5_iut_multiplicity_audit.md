# NEXVIA AEGIS V9-M4 Independent Statistical Audit
## Phase 3 Report: Audit of Hypothesis $H_5$ (Intersection-Union Test and Multiplicity Handling)

**Document Identifier:** `AEGIS-V9-M4-AUD-03`  
**Phase:** Phase 3 — H5 Intersection-Union and Multiplicity  
**Date:** October 25, 2026  
**Auditor:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Starting Commit:** `083ade9bbad7b6e28b7e18abec7e6f861a45a7b7`  
**Status:** `AUDIT_COMPLETE_WITH_FINDINGS` (High-Severity Finding M4-F02 Identified: Estimand Inversion in IUT)

---

### Abstract

This audit report conducts an exhaustive mathematical and implementation audit of Hypothesis $H_5$ (Worst-Case Scenario Safety) within the NEXVIA AEGIS V9-M4 confirmatory evaluation harness. We evaluate the inferential structure of $H_5$, examining whether it represents a single conjunctive claim or multiple individual claims, and assess the implementation of Berger's Intersection-Union Test (IUT) and the step-down Holm–Šidák multiplicity procedure. Our audit uncovers a critical, high-severity statistical discrepancy (**Finding M4-F02**): whereas the authoritative protocol specifies the Berger IUT over *unconditional false-success incidence* $R_{\mathrm{inc}, s} = K_s / N_s$ ($N_s = 120$), the current implementation in `experiments/v9_evaluate_holdout.py` computes the binomial $p$-values over *accepted selective decisions* ($M_s$) and assigns a punitive fallback of $p = 1.0$ whenever safe abstention yields $M_s = 0$. This implementation inadvertently penalizes safe abstention in catastrophic fault scenarios, causing the Berger IUT to fail even when the agent achieves zero false successes ($FS=0$). We document the exact mathematical consequences and outline the required protocol-aligned remediation.

**Keywords:** Worst-Case Safety, Berger Intersection-Union Test, Holm–Šidák Procedure, Familywise Error Rate, Unconditional Incidence vs. Selective Risk, Safe Abstention Penalty.

---

### 1. Executive Summary & Inferential Objective

Hypothesis $H_5$ addresses the worst-case safety envelope across the 12-scenario stratified grid $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ ($12 \times 120 = 1,440$ episodes). In statistical testing, establishing safety across multiple distinct operational regimes can be formulated in two distinct ways:
1. **A Global Conjunction (Single Composite Hypothesis):** Testing that *all* 12 scenarios simultaneously satisfy the safety condition.
2. **Multiple Disjoint Inferences:** Testing individual scenario safety claims, requiring simultaneous familywise error rate (FWER) control.

**Audit Finding 3.1 (Inferential Architecture):**  
We verified that the preregistered protocol (`docs/v9_experiment_protocol.md` Section 3.1.1, line 37, and `docs/v9_m4_readiness_review.md` Section 3, line 57) explicitly establishes a **dual-objective framework**:
- The **primary inferential claim** is the global conjunction: establishing that worst-case false-success incidence across all 12 scenarios is bounded at $\le 0.05$.
- The **secondary reporting framework** provides simultaneous 12-scenario confidence intervals with familywise error rate controlled at $\le 0.05$ via the step-down Holm–Šidák procedure.

---

### 2. Mathematical Foundations of the Berger Intersection-Union Test

Let $s \in \{1, \dots, 12\}$ index the 12 scenarios. The global confirmatory safety claim is formulated as:
$$\mathcal{H}_{0,5}: \bigcup_{s=1}^{12} \{R_s > 0.05\} \quad\text{versus}\quad \mathcal{H}_{1,5}: \bigcap_{s=1}^{12} \{R_s \le 0.05\}$$

#### 2.1 The Berger IUT Theorem (Berger, 1982)
Let $T_s$ be a level-$\alpha$ test of the individual scenario null hypothesis $\mathcal{H}_{0, s}: R_s > 0.05$ against $\mathcal{H}_{1, s}: R_s \le 0.05$, with corresponding $p$-value $p_s$. Consider the Intersection-Union Test that rejects $\mathcal{H}_{0,5}$ if and only if **every individual scenario null hypothesis is rejected at level $\alpha$**:
$$\text{Reject } \mathcal{H}_{0,5} \iff \max_{s \in \{1, \dots, 12\}} p_s \le \alpha$$

**Theorem (Berger, 1982; Casella \& Berger, 2002):**  
The size of the overall Intersection-Union Test satisfies:
$$\sup_{\theta \in \Theta_0} \mathbb{P}_\theta\big(\text{Reject } \mathcal{H}_{0,5}\big) \le \alpha$$
*Proof Outline:* Under any parameter configuration $\theta \in \Theta_0 = \bigcup_{s=1}^{12} \Theta_{0, s}$, there exists at least one scenario index $s^*$ for which $\mathcal{H}_{0, s^*}$ is true. The rejection event of the IUT implies that the component test for $s^*$ rejected:
$$\{\text{Reject } \mathcal{H}_{0,5}\} = \bigcap_{s=1}^{12} \{p_s \le \alpha\} \subseteq \{p_{s^*} \le \alpha\}$$
Therefore:
$$\mathbb{P}_\theta(\text{Reject } \mathcal{H}_{0,5}) \le \mathbb{P}_\theta(p_{s^*} \le \alpha) \le \alpha$$
Consequently, **no multiple-testing adjustment (such as Bonferroni or Šidák) is required for the IUT conjunction**. The overall Type-I error is rigorously protected at $\alpha = 0.05$.

---

### 3. High-Severity Finding M4-F02: Estimand Inversion in IUT Implementation

#### 3.1 Protocol Specification
In `docs/v9_experiment_protocol.md` Section 3.1.1 (lines 37 and 123), the protocol explicitly defines the estimand for the multi-scenario safety envelope:
> *"plus Berger's Intersection–Union test ($\max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc}, s} \le 0.05$) for worst-case **unconditional incidence** $\max_{s \in \mathcal{S}_{12}} R_{\mathrm{inc}, s}(\hat{\pi}) \le 0.05$."*  
> *(Section 3.1.1, line 37)*

And at line 123:
> *"In `FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, and `COMPOUND_HOLDOUT_EXTREME`, safe runtime assurance should abstain on most or all episodes ($M_s \approx 0\text{--}15$); V9 will therefore certify **per-scenario unconditional incidence $R_{\mathrm{inc}, s} \le 0.05$** ($120 \ge 107$ when $K_s = 0$) and report exact selective-risk CIs (`UNDEFINED` when $M_s = 0$) without claiming per-scenario selective certification where $M_s$ is insufficient."*

#### 3.2 Implementation Divergence in `experiments/v9_evaluate_holdout.py`
In `experiments/v9_evaluate_holdout.py`, lines 694–705 implement scenario-level risk calculation as follows:
```python
if m_s > 0:
    r_sel_s = fs_s / m_s
    r_sel_status = "DEFINED"
    ucb95_s = clopper_pearson_one_sided_ucb(fs_s, m_s, delta=0.05)
    p_val_s = float(binom.cdf(fs_s, m_s, 0.05))
else:
    r_sel_s = float("nan")
    r_sel_status = "UNDEFINED"
    ucb95_s = float("nan")
    p_val_s = 1.0  # conservative p-value for zero coverage

p_values_for_iut.append(p_val_s)
```
And lines 772–773 evaluate the IUT:
```python
iut_passed = berger_intersection_union_test(p_values_for_iut, alpha=0.05)
h5_status = "CONFIRMATORY_PASS_IUT" if iut_passed else "RETAIN_SAFETY_NULL"
```

#### 3.3 Mathematical Impact of Finding M4-F02
This implementation inadvertently inverts the statistical hypothesis:
1. **Penalization of Flawless Abstention:** In catastrophic fault scenarios (such as `FAULTY_REFERENCE_SENSOR` or `CORRUPTED_ANCHOR_STRESS`), a sound runtime assurance policy identifies sensor corruption and abstains on 100% of episodes ($M_s = 0, K_s = 0$). Under total abstention:
   - True unconditional false-success incidence is $R_{\mathrm{inc}, s} = 0 / 120 = 0.0\%$.
   - The true binomial $p$-value for testing $H_0: R_{\mathrm{inc}, s} > 0.05$ with $N_s = 120$ and $K_s = 0$ is:
     $$p_{\mathrm{inc}, s} = \sum_{j=0}^{0} \binom{120}{j} 0.05^j (0.95)^{120-j} = (0.95)^{120} \approx 0.002122 \le 0.05$$
   - Since $0.002122 \le 0.05$, the unconditional safety null is decisively rejected!
2. **Artificial Failure under Line 703:** However, because line 698 conditions on $M_s$ rather than $N_s$, line 703 assigns `p_val_s = 1.0`. Consequently:
   $$\max_{s \in \mathcal{S}_{12}} p_s \ge 1.0 \implies \text{IUT is guaranteed to fail!}$$
3. **Small Sample Rejection:** Even if an agent accepts a small number of episodes in a fault scenario (e.g. $M_s = 5, K_s = 0$), $p_{\mathrm{sel}} = (0.95)^5 \approx 0.7738 > 0.05$, causing the IUT to fail even though the unconditional incidence is bounded at $0 / 120 = 0.0\%$.

---

### 4. Remediation Proposal for Finding M4-F02

To restore mathematical consistency between the evaluation harness and the preregistered protocol:

1. **Calculate $p_{\mathrm{inc}, s}$ on $N_s = 120$ for IUT:**
   The binomial $p$-value for the Berger IUT must be computed using unconditional false-success count $K_s$ over the full scenario sample size $N_s = 120$:
   $$p_{\mathrm{inc}, s} = \mathrm{binom.cdf}(fs_s, n_s, 0.05)$$
   When $K_s = 0$ on $N_s = 120$, $p_{\mathrm{inc}, s} \approx 0.002122 \le 0.05$.
2. **Preserve Selective Risk Reporting in Breakdown Table:**
   Continue reporting descriptive selective risk point estimates ($\hat{R}_{\mathrm{sel}, s} = K_s / M_s$) and Clopper–Pearson selective UCBs in the scenario breakdown table, maintaining `"r_sel": "UNDEFINED"` when $M_s = 0$.
3. **Dual Reporting in JSON Summary:**
   Report both `p_value_unconditional_incidence_005` (used for IUT) and `p_value_selective_risk_005` (descriptive) in `test_scen_summary.csv` and `test_scen_report.json`.

---

### 5. Multiplicity Control via Step-Down Holm–Šidák

For exploratory and descriptive reporting of individual scenario performance, the harness computes step-down Holm–Šidák thresholds:
$$\alpha_{(r)} = 1 - (1 - \alpha)^{1 / (12 - r + 1)}, \quad r = 1, \dots, 12$$
Evaluating this sequence for $\alpha = 0.05$ and $K = 12$ yields the exact threshold ladder in Table~\ref{tab:holm_thresholds}.

| Step $r$ | Effective Tests Remaining ($12 - r + 1$) | Exact Holm–Šidák Threshold $\alpha_{(r)}$ | Bonferroni Equivalent $\alpha / (12 - r + 1)$ |
| :---: | :---: | :---: | :---: |
| 1 | 12 | 0.004265 | 0.004167 |
| 2 | 11 | 0.004650 | 0.004545 |
| 3 | 10 | 0.005116 | 0.005000 |
| 4 | 9 | 0.005685 | 0.005556 |
| 5 | 8 | 0.006391 | 0.006250 |
| 6 | 7 | 0.007301 | 0.007143 |
| 7 | 6 | 0.008512 | 0.008333 |
| 8 | 5 | 0.010206 | 0.010000 |
| 9 | 4 | 0.012741 | 0.012500 |
| 10 | 3 | 0.016952 | 0.016667 |
| 11 | 2 | 0.025321 | 0.025000 |
| 12 | 1 | 0.050000 | 0.050000 |

**Audit Verification Finding 3.2:**  
The implementation `holm_shidak_adjusted_thresholds` in line 439 matches the exact mathematical formula. However, because the input $p$-values were computed on selective decisions ($M_s$) with a $1.0$ fallback rather than unconditional incidence ($N_s = 120$), the Holm–Šidák rejections are currently distorted by Finding M4-F02. Correcting the $p$-value input to $p_{\mathrm{inc}, s}$ resolves both the Berger IUT and the Holm–Šidák procedure.

---

### 6. Conclusion & Phase 3 Recommendation

Phase 3 audit identified a material statistical discrepancy (**Finding M4-F02**, Severity: High). The implementation currently penalizes safe abstention in catastrophic fault scenarios by evaluating the Berger IUT on selective decisions ($M_s$) rather than unconditional incidence ($N_s = 120$). This discrepancy must be remediated prior to confirmatory holdout execution.

\noindent \textbf{Phase 3 Recommendation:} `AUDIT_PHASE_3_PASS_WITH_QUALIFICATIONS` (Requires Remediation of Finding M4-F02)

---

### References

1. R. L. Berger, "Multiparameter hypothesis testing and acceptance sampling," *Technometrics*, vol. 24, no. 4, pp. 295–300, 1982.
2. G. Casella and R. L. Berger, *Statistical Inference*, 2nd ed., Duxbury Press, 2002.
3. S. Holm, "A simple sequentially rejective multiple test procedure," *Scandinavian Journal of Statistics*, vol. 6, no. 2, pp. 65–70, 1979.
4. Z. Šidák, "Rectangular confidence regions for the means of multivariate normal distributions," *Journal of the American Statistical Association*, vol. 62, no. 318, pp. 626–633, 1967.
5. M. J. Silvapulle and P. K. Sen, *Constrained Statistical Inference: Inequality, Order, and Shape Restrictions*, John Wiley \& Sons, 2005.
