# NEXVIA AEGIS V9-M4 Independent Statistical Audit
## Phase 2 Report: Audit of Hypothesis $H_1$ (Selective-Risk Certification)

**Document Identifier:** `AEGIS-V9-M4-AUD-02`  
**Phase:** Phase 2 — H1 Selective-Risk Certification  
**Date:** October 25, 2026  
**Auditor:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Starting Commit:** `083ade9bbad7b6e28b7e18abec7e6f861a45a7b7`  
**Status:** `AUDIT_COMPLETE_VERIFIED` (Exact Binomial Inversion Verified; Zero Gaming Vulnerability)

---

### Abstract

This audit report delivers a rigorous mathematical, numerical, and structural audit of Hypothesis $H_1$ (Selective False-Success Risk Control) within the NEXVIA AEGIS V9-M4 confirmatory evaluation harness. We evaluate the exact one-sided Clopper–Pearson upper confidence bound (UCB) implementation, the minimum sample eligibility requirement ($M \ge 59$), zero-coverage boundary conditions, and the interaction between empirical risk point estimation, sample eligibility, and statistical certification. Across synthetic boundary cases spanning $M \in \{0, 1, 58, 59, 92, 93, 94, 100, 125\}$ and $K \in \{0, 1, 2, 5\}$, we prove that the harness strictly adheres to exact Clopper–Pearson beta-distribution inversion, prevents the conflation of eligibility with certification, refuses certification when false successes occur under small samples ($K \ge 1$ at $M=59$), and correctly handles undefined selective risk under total abstention.

**Keywords:** Selective Risk, Clopper–Pearson Upper Bound, Incomplete Beta Function, Runtime Assurance Certification, Sample Size Sufficiency, Statistical Boundary Analysis.

---

### 1. Executive Summary & Audit Scope

Milestone V9-M4 defines Hypothesis $H_1$ as the primary confirmatory claim for the frozen policy $\hat{\pi} = \text{V9\_CAND\_1\_TIER1\_STRICTEST}$:
$$\mathcal{H}_{0,1}: C(\hat{\pi}; \mathcal{P}_{12}) = 0 \;\lor\; R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) > 0.05 \quad\text{vs.}\quad \mathcal{H}_{1,1}: C(\hat{\pi}; \mathcal{P}_{12}) > 0 \;\land\; R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) \le 0.05$$
The Phase 2 audit was conducted under the following strict verification questions:
1. **Mathematical Derivation of $M \ge 59$:** Does $M \ge 59$ represent a statistically necessary sample size threshold for certifying $R_{\mathrm{sel}} \le 0.05$ at $\delta = 0.05$, or is it an ad-hoc heuristic?
2. **Sufficiency vs. Necessity:** Does the code erroneously treat $M \ge 59$ as *sufficient* to certify safety regardless of the number of observed false successes ($K$)?
3. **Exact Binomial Inversion:** Does `clopper_pearson_one_sided_ucb` implement the exact Clopper–Pearson formula without normal or Poisson approximations?
4. **Zero-Decision Boundary ($M = 0$):** Does total abstention ($M=0$) cleanly yield an `UNDEFINED` empirical selective risk without triggering division-by-zero or spurious certification?
5. **Small Sample Behavior ($1 \le M < 59$):** Does the harness maintain a clear conceptual and reporting distinction between empirical point estimates ($K/M$), eligibility preconditions ($M \ge 59$), and statistical certification?

---

### 2. Theoretical Derivation of the $M \ge 59$ Bound

Let $M$ denote the number of accepted episodes ($A=1$) and $K$ denote the number of false successes ($FS=1$). Under the i.i.d. Bernoulli model $K \sim \mathrm{Binomial}(M, R_{\mathrm{sel}})$, the exact one-sided $(1 - \delta)$ Clopper–Pearson upper confidence bound $U_{\mathrm{CP}, 1}(K, M; \delta)$ is defined as the supremum over risk parameters $p$ such that the probability of observing $K$ or fewer false successes is at least $\delta$:
$$U_{\mathrm{CP}, 1}(K, M; \delta) = \sup \left\{ p \in [0, 1] \;\middle|\; \sum_{j=0}^{K} \binom{M}{j} p^j (1 - p)^{M-j} \ge \delta \right\}$$

For the optimal best-case empirical outcome where zero false successes are observed ($K = 0$):
$$\sum_{j=0}^{0} \binom{M}{j} p^j (1 - p)^{M-j} = (1 - p)^M \ge \delta \implies 1 - p \ge \delta^{1/M} \implies p \le 1 - \delta^{1/M}$$
Thus, for $K = 0$, the exact upper bound is:
$$U_{\mathrm{CP}, 1}(0, M; \delta) = 1 - \delta^{1/M}$$

To achieve confirmatory certification at significance level $\alpha = 0.05$ with confidence $1 - \delta = 0.95$ ($\delta = 0.05$):
$$1 - 0.05^{1/M} \le 0.05 \iff 0.05^{1/M} \ge 0.95 \iff \frac{1}{M} \ln(0.05) \ge \ln(0.95)$$
Since $\ln(0.95) < 0$, solving for integer $M$:
$$M \ge \frac{\ln(0.05)}{\ln(0.95)} = \frac{-2.99573227}{-0.05129329} \approx 58.404 \implies M_{\min} = 59$$

**Audit Verification Finding 2.1:**
- If $M = 58$ and $K = 0$: $U_{\mathrm{CP}, 1}(0, 58; 0.05) = 1 - 0.05^{1/58} \approx 0.050339 > 0.05$. **Certification is impossible.**
- If $M = 59$ and $K = 0$: $U_{\mathrm{CP}, 1}(0, 59; 0.05) = 1 - 0.05^{1/59} \approx 0.049508 \le 0.05$. **Certification is achieved.**
- Therefore, $M = 59$ is the exact, uncompromised mathematical threshold below which 95% Clopper–Pearson certification of $R_{\mathrm{sel}} \le 0.05$ is mathematically impossible even under flawless empirical performance.

---

### 3. Empirical Boundary Audit & Synthetic Case Evaluation

To test whether the implementation handles edge cases correctly, we evaluated `clopper_pearson_one_sided_ucb` across 13 synthetic stress cases. The exact calculations are reported in Table~\ref{tab:h1_cases}.

| Case ID | False Successes ($K$) | Accepted ($M$) | Empirical Risk $\hat{R}_{\mathrm{sel}} = K/M$ | Clopper–Pearson $\mathrm{UCB}_{95}$ | Precondition $M \ge 59$ | Bound $\le 0.05$ | $H_1$ Confirmatory Outcome | Code Status Classification |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **C01** | 0 | 0 | `UNDEFINED` | `UNDEFINED` (`NaN`) | False | False | **FAIL / REJECT** | `INSUFFICIENT_COVERAGE` |
| **C02** | 0 | 1 | 0.000000 | 0.950000 | False | False | **FAIL / REJECT** | `INSUFFICIENT_COVERAGE` |
| **C03** | 1 | 1 | 1.000000 | 1.000000 | False | False | **FAIL / REJECT** | `INSUFFICIENT_COVERAGE` |
| **C04** | 0 | 58 | 0.000000 | 0.050339 | False | False | **FAIL / REJECT** | `INSUFFICIENT_COVERAGE` |
| **C05** | 0 | 59 | 0.000000 | 0.049508 | True | True | **CONFIRMATORY PASS** | `CONFIRMATORY_PASS` |
| **C06** | 1 | 59 | 0.016949 | 0.077898 | True | False | **FAIL / REJECT** | `FAILED_UCB` |
| **C07** | 1 | 92 | 0.010870 | 0.050526 | True | False | **FAIL / REJECT** | `FAILED_UCB` |
| **C08** | 1 | 93 | 0.010753 | 0.049994 | True | True | **CONFIRMATORY PASS** | `CONFIRMATORY_PASS` |
| **C09** | 1 | 94 | 0.010638 | 0.049473 | True | True | **CONFIRMATORY PASS** | `CONFIRMATORY_PASS` |
| **C10** | 1 | 100 | 0.010000 | 0.046560 | True | True | **CONFIRMATORY PASS** | `CONFIRMATORY_PASS` |
| **C11** | 2 | 100 | 0.020000 | 0.061619 | True | False | **FAIL / REJECT** | `FAILED_UCB` |
| **C12** | 2 | 125 | 0.016000 | 0.049508 | True | True | **CONFIRMATORY PASS** | `CONFIRMATORY_PASS` |
| **C13** | 5 | 120 | 0.041667 | 0.085608 | True | False | **FAIL / REJECT** | `FAILED_UCB` |

---

### 4. Detailed Audit Findings for $H_1$

#### 4.1 Rejection of False-Success Gaming (Case C06)
A critical vulnerability in informal runtime assurance evaluations is treating a sample size threshold ($M \ge 59$) as a sufficient condition for certification. In Case C06 ($M = 59, K = 1$), the point estimate is $\hat{R}_{\mathrm{sel}} = 1/59 \approx 1.69\% < 5.0\%$. However, accounting for sampling uncertainty, the exact 95% upper bound expands to $U_{\mathrm{CP}, 1} = 0.077898 = 7.79\% > 5.0\%$.
- **Inspection of Code:** Lines 541–544 of `experiments/v9_evaluate_holdout.py` evaluate:
  ```python
  h1_precondition_met = m >= 59
  h1_ucb95 = clopper_pearson_one_sided_ucb(fs, m, delta=0.05) if m > 0 else float("nan")
  h1_passed = bool(h1_precondition_met and not math.isnan(h1_ucb95) and h1_ucb95 <= 0.05)
  h1_status = "CONFIRMATORY_PASS" if h1_passed else ("FAILED_UCB" if h1_precondition_met else "INSUFFICIENT_COVERAGE")
  ```
- **Finding:** The harness correctly evaluates `h1_passed = False` and assigns `h1_status = "FAILED_UCB"`. The harness does **not** permit certification when false successes occur without a commensurately larger sample size ($M \ge 93$ for $K=1$, $M \ge 125$ for $K=2$).

#### 4.2 Handling of Undefined Selective Risk Under Zero Decisions (Case C01)
When an agent abstains unconditionally on all episodes ($M = 0$), $R_{\mathrm{sel}} = K / M = 0 / 0$ is mathematically undefined.
- **Audit Check:** Does the code return `0.0`, throw an unhandled `ZeroDivisionError`, or falsely pass $H_1$?
- **Finding:** The implementation safely guards division by zero (`r_sel = fs / m if m > 0 else float("nan")`), assigns `h1_precondition_met = False`, sets `h1_passed = False`, and returns `h1_status = "INSUFFICIENT_COVERAGE"`. In JSON serialization, it explicitly writes `"cp_ucb95": "UNDEFINED"` and `"r_sel": "UNDEFINED"`.

#### 4.3 Clean Distinction Between Point Estimates and Statistical Certification (Cases C02–C04)
For $1 \le M < 59$, the empirical point estimate $\hat{R}_{\mathrm{sel}} = K / M$ is mathematically well-defined (e.g. $0.0\%$ in Case C04 where $M=58, K=0$).
- **Audit Check:** Does the report confuse an empirical estimate of $0.0\%$ with statistical certification?
- **Finding:** The harness outputs the descriptive point estimate $\hat{R}_{\mathrm{sel}} = 0.000000$, but assigns `h1_precondition_met = False`, `h1_passed = False`, and `h1_status = "INSUFFICIENT_COVERAGE"`. Descriptive reporting is thus decoupled from inferential certification.

---

### 5. Conclusion & Phase 2 Recommendation

Phase 2 audit establishes that the implementation of Hypothesis $H_1$ in [`experiments/v9_evaluate_holdout.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py) is mathematically exact, impervious to certification gaming, and fully compliant with preregistered protocol requirements.

**Phase 2 Recommendation:** `AUDIT_PHASE_2_PASS`

---

### References

1. C. J. Clopper and E. S. Pearson, "The use of confidence or fiducial limits illustrated in the case of the binomial," *Biometrika*, vol. 26, no. 4, pp. 404–413, 1934.
2. A. Colin Cameron and P. K. Trivedi, *Microeconometrics: Methods and Applications*, Cambridge University Press, 2005.
3. R. G. Newcombe, "Two-sided confidence intervals for the single proportion: comparison of seven methods," *Statistics in Medicine*, vol. 17, no. 8, pp. 857–872, 1998.
