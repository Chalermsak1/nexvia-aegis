# NEXVIA AEGIS V9-M4 Independent Statistical Audit
## Phase 4 Report: Audit of Hypotheses $H_2$ and $H_3$ (Paired Comparisons and Noninferiority)

**Document Identifier:** `AEGIS-V9-M4-AUD-04`  
**Phase:** Phase 4 — H2/H3 Paired Comparisons  
**Date:** October 25, 2026  
**Auditor:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Starting Commit:** `083ade9bbad7b6e28b7e18abec7e6f861a45a7b7`  
**Status:** `AUDIT_COMPLETE_WITH_FINDINGS` (Medium-Severity Finding M4-F03: Implicit Key Pairing Assumption)

---

### Abstract

This audit report evaluates the comparative statistical methodology implemented in the NEXVIA AEGIS V9-M4 confirmatory evaluation harness for Hypotheses $H_2$ (Unconditional False-Success Incidence Reduction vs. Baselines) and $H_3$ (True-Success Rate Noninferiority vs. V7). We review the mathematical formulation and numerical accuracy of exact two-sided McNemar testing, Newcombe's paired difference score intervals (Method 10), and one-sided Student's $t$ lower confidence bounds for noninferiority testing. Across synthetic paired datasets, we verify that the statistical estimators behave in accordance with established biometric theory. However, our audit identifies a notable implementation finding (**Finding M4-F03**, Severity: Medium): the paired evaluation loops currently rely on list ordering via Python `zip()` rather than asserting explicit `(seed, scenario)` dictionary key equality, creating a vulnerability to silent alignment errors if input record arrays are inadvertently permuted. We propose an explicit key-matching assertion to ensure foolproof pairing integrity.

**Keywords:** Paired Comparisons, McNemar Exact Test, Newcombe Score Interval, Noninferiority Margin, True-Success Rate, Pairing Alignment Vulnerability.

---

### 1. Executive Summary & Audit Mandate

Confirmatory evaluation requires comparing the frozen candidate policy $\hat{\pi}$ against historical reference baselines on matched episodes:
- **Baseline 1:** `AEGIS_NEXT_MARTINGALE` (V8.1 Baseline, implemented in `src/aegis/next/agent_next.py`).
- **Baseline 2:** `AEGIS_V7_MPC_BASELINE` (V7 Baseline, implemented in `src/aegis/next/baselines.py`).

Phase 4 of the independent audit evaluates:
1. **Hypothesis $H_2$ Mathematical Fidelity:** Does the exact McNemar test and Newcombe paired difference confidence interval correctly test whether $\hat{\pi}$ achieves a statistically significant reduction in false-success incidence?
2. **Hypothesis $H_3$ Noninferiority Margin:** Is the noninferiority margin $\Delta_{\mathrm{NI}} = -0.05$ evaluated correctly via a one-sided 95% paired Student's $t$ lower confidence bound on the core $S_{10}$ scenario block ($N = 1,200$)?
3. **Nominal Utility Co-Criterion:** Does the harness enforce $\widehat{\mathrm{TSR}}_{\mathrm{NOMINAL}} \ge 0.94$ alongside the noninferiority bound?
4. **Episode Matching and Alignment:** Does the harness ensure that episodes are matched bit-for-bit on scenario, environment geometry, and PRNG seeds?

---

### 2. Hypothesis $H_2$: Unconditional False-Success Incidence Reduction

#### 2.1 Contingency Table & Exact McNemar Test
Let $(Y_{\hat{\pi}, i}, Y_{\mathrm{base}, i}) \in \{0, 1\}^2$ denote the binary false-success indicators on episode $i \in \{1, \dots, N\}$. The $2 \times 2$ paired contingency table is defined as:

| | Baseline $Y_{\mathrm{base}} = 1$ | Baseline $Y_{\mathrm{base}} = 0$ | Total |
| :--- | :---: | :---: | :---: |
| **Policy $\hat{\pi}$ ($Y_{\hat{\pi}} = 1$)** | $n_{11}$ | $n_{10}$ | $n_{1\cdot}$ |
| **Policy $\hat{\pi}$ ($Y_{\hat{\pi}} = 0$)** | $n_{01}$ | $n_{00}$ | $n_{0\cdot}$ |
| **Total** | $n_{\cdot 1}$ | $n_{\cdot 0}$ | $N$ |

The discordant pairs are $b = n_{10}$ (false success under $\hat{\pi}$ only) and $c = n_{01}$ (false success under baseline only). Under the null hypothesis of equal incidence $\mathcal{H}_{0,2}: \mathbb{P}(Y_{\hat{\pi}} = 1) = \mathbb{P}(Y_{\mathrm{base}} = 1)$, conditional on $b + c$:
$$b \mid (b + c) \sim \mathrm{Binomial}\left(b + c, \, \frac{1}{2}\right)$$
The exact two-sided $p$-value implemented in `mcnemar_exact_test(b, c)` (lines 383–397) is:
$$p = \min\left(1.0, \; 2 \sum_{k=0}^{\min(b, c)} \binom{b + c}{k} \left(\frac{1}{2}\right)^{b + c}\right)$$

#### 2.2 Newcombe Paired Difference Confidence Interval (Method 10)
Let $p_1 = (n_{11} + n_{10}) / N$ and $p_2 = (n_{11} + n_{01}) / N$. The difference is $\theta = p_1 - p_2$. Let $(l_1, u_1)$ and $(l_2, u_2)$ be the 95% Wilson score confidence limits for $p_1$ and $p_2$. Newcombe's paired score interval incorporates the sample correlation $\hat{\phi}$:
$$\hat{\phi} = \frac{n_{11} n_{00} - n_{10} n_{01}}{\sqrt{(n_{11} + n_{10})(n_{01} + n_{00})(n_{11} + n_{01})(n_{10} + n_{00})}}$$
The lower and upper bounds are computed as:
$$\text{Lower} = (p_1 - p_2) - \sqrt{(p_1 - l_1)^2 - 2\hat{\phi}(p_1 - l_1)(u_2 - p_2) + (u_2 - p_2)^2}$$
$$\text{Upper} = (p_1 - p_2) + \sqrt{(u_1 - p_1)^2 - 2\hat{\phi}(u_1 - p_1)(p_2 - l_2) + (p_2 - l_2)^2}$$
- **Verification:** When $n_{10} = 1$ and $n_{01} = 24$ on $N = 1,440$, the implementation yields:
  $$p_{\mathrm{McNemar}} = 1.55 \times 10^{-6}, \quad \mathrm{CI}_{95}(\Delta R_{\mathrm{inc}}) = [-0.024038, \, -0.009739]$$
  Since the upper bound is strictly negative ($\le -0.0097 < 0$), statistically significant reduction in false-success incidence is demonstrated.

---

### 3. Hypothesis $H_3$: True-Success Rate Noninferiority vs. V7

#### 3.1 Noninferiority Formulation & Test
Hypothesis $H_3$ evaluates operational task utility on the core ten scenarios $\mathcal{S}_{10}$ ($N = 1,200$ matched pairs):
$$\mathcal{H}_{0,3}: \mathrm{TSR}(\hat{\pi}; \mathcal{P}_{10}) - \mathrm{TSR}(\pi_{\mathrm{V7}}; \mathcal{P}_{10}) \le -0.05 \quad\text{vs.}\quad \mathcal{H}_{1,3}: \mathrm{TSR}(\hat{\pi}; \mathcal{P}_{10}) - \mathrm{TSR}(\pi_{\mathrm{V7}}; \mathcal{P}_{10}) > -0.05$$
Let $d_i = \mathbb{I}(TS_{\hat{\pi}, i} = 1) - \mathbb{I}(TS_{\mathrm{V7}, i} = 1) \in \{-1, 0, 1\}$. The sample mean difference is $\bar{d}$ and the sample standard deviation is $s_d$. The one-sided 95% lower confidence bound is:
$$\mathrm{LCB}_{95}(\Delta\mathrm{TSR}) = \bar{d} - t_{0.95, N-1} \frac{s_d}{\sqrt{N}}$$

#### 3.2 Dual Pass Criterion
In `experiments/v9_evaluate_holdout.py` (lines 765–766), the decision rule enforces:
$$\text{Pass } H_3 \iff \mathrm{LCB}_{95}(\Delta\mathrm{TSR}) > -0.05 \quad\land\quad \widehat{\mathrm{TSR}}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$$
- **Verification:** On a synthetic case where $\bar{d} = +0.008333$ and $s_d = 0.302$, the computed bound is $\mathrm{LCB}_{95} = -0.006054 > -0.05$, correctly confirming noninferiority. Conversely, when $\bar{d} = -0.058333$, the bound is $\mathrm{LCB}_{95} = -0.071054 < -0.05$, correctly rejecting noninferiority.

---

### 4. Implementation Finding M4-F03: Implicit Pairing Assumption

#### 4.1 Description of Finding
In `experiments/v9_evaluate_holdout.py`, the paired comparison loops in lines 555–559 and 755–760 pair policy and baseline records using Python's sequential `zip()` function:
```python
for r, v in zip(records, v8_records):
    # compares r["false_success"] and v["false_success"]
```
And:
```python
for r_pi, r_v7 in zip(records, v7_records):
    # compares r_pi["true_success"] and r_v7["true_success"]
```

#### 4.2 Potential Failure Mode
The `zip()` construct implicitly assumes that `records` and `baseline_records` are identically ordered by episode index. If an upstream baseline loader returns records ordered by scenario rather than global episode index, or if an asynchronous simulation runner writes episodes out of order:
- Disparate scenarios and seeds will be silently paired together.
- The paired correlation $\phi$ and paired differences $d_i$ will be corrupted without throwing an error.

#### 4.3 Proposed Remediation
To guarantee bulletproof pairing integrity, the comparison loops should explicitly validate episode identity on every iteration:
```python
if int(r["seed"]) != int(v["seed"]) or str(r["scenario"]) != str(v["scenario"]):
    raise ValueError(
        f"Paired record alignment mismatch: policy episode (seed={r.get('seed')}, "
        f"scen={r.get('scenario')}) != baseline episode (seed={v.get('seed')}, scen={v.get('scenario')})"
    )
```

---

### 5. Conclusion & Phase 4 Recommendation

Phase 4 audit confirms that the statistical implementations of exact McNemar testing, Newcombe score intervals, and Student's $t$ lower confidence bounds are mathematically exact and align with preregistered protocol requirements. Implementation Finding M4-F03 (Severity: Medium) should be addressed by adding explicit key assertions prior to live holdout execution.

\noindent \textbf{Phase 4 Recommendation:} `AUDIT_PHASE_4_PASS_WITH_QUALIFICATIONS` (Requires Explicit Key Alignment Check)

---

### References

1. Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947.
2. R. G. Newcombe, "Improved confidence intervals for the difference between binomial proportions based on paired data," *Statistics in Medicine*, vol. 17, no. 22, pp. 2635–2650, 1998.
3. S. C. Chow, J. Shao, H. Wang, and Y. Lokhnygina, *Sample Size Calculations in Clinical Research*, 3rd ed., CRC Press, 2017.
