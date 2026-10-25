# NEXVIA AEGIS V9-M4 Independent Statistical Audit
## Comprehensive Scientific Audit Report: Confirmatory Holdout Evaluation Harness, Statistical Formulations, and Pre-Execution Readiness

**Document Identifier:** `AEGIS-V9-M4-AUD-FINAL`  
**Milestone:** V9-M4 Preflight Audit  
**Date of Audit:** October 25, 2026  
**Auditing Entity:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`  
**Git Branch:** `v9.0-runtime-assurance`  
**Base Commit:** `083ade9bbad7b6e28b7e18abec7e6f861a45a7b7`  
**Audit Recommendation:** `M4_STATISTICAL_AUDIT_PASS_WITH_QUALIFICATIONS`  
**Formal Execution Status:** `M4_EXECUTION_STRICTLY_BLOCKED_PENDING_REMEDIATION`

---

### Non-Authorization & Governance Statement

> **NOTICE:** This document reports an independent statistical, mathematical, and implementation audit of the NEXVIA AEGIS V9-M4 confirmatory holdout evaluation harness. **No real holdout execution was authorized or performed as part of this audit.** All empirical tests reported herein are based strictly on synthetic mock records or unit regression baselines. The reserved holdout seed blocks ($73000..74439$ for mixture holdout and $75000..75119$ for scenario holdout) and their corresponding simulation paths remain completely uninstantiated and 100% untouched. This audit report does NOT constitute authorization to execute V9-M4.

---

### Abstract

This comprehensive scientific audit report presents the complete findings, mathematical derivations, numerical validations, and architectural reviews conducted on the NEXVIA AEGIS V9-M4 confirmatory holdout evaluation harness (`experiments/v9_evaluate_holdout.py`). We audit the statistical foundations of preregistered Hypotheses $H_1$ through $H_5$, evaluating exact Clopper–Pearson confidence bound inversion, Berger Intersection-Union Tests (IUT), step-down Holm–Šidák familywise error control, exact McNemar testing, Newcombe paired difference intervals (Method 10), and empirical coverage guardrails.

Our audit confirms that the evaluation runner achieves high mathematical fidelity in its core estimators, passes all 125 full repository regression tests, enforces robust single-shot overwrite guards, and maintains complete isolation of reserved holdout partitions. However, our investigation identified one high-severity statistical discrepancy (**Finding M4-F02**): in evaluating the multi-scenario safety envelope ($H_5$), the harness calculates binomial $p$-values on accepted decisions ($M_s$) with a punitive fallback of $p=1.0$ under total abstention, rather than on unconditional incidence ($N_s = 120$) as specified in the preregistered protocol. This defect inadvertently penalizes safe runtime abstention in catastrophic fault scenarios, guaranteeing that the Berger IUT would fail even under zero false successes ($FS=0$). We provide complete mathematical proofs, synthetic boundary data, and an actionable remediation specification. We recommend a status of **`M4_STATISTICAL_AUDIT_PASS_WITH_QUALIFICATIONS`**, requiring the remediation of Finding M4-F02 and Finding M4-F03 prior to formal production holdout authorization.

**Keywords:** Certified Runtime Assurance, Selective Risk Control, Clopper–Pearson Exact Bounds, Berger Intersection-Union Test, Step-Down Holm–Šidák, Paired McNemar Testing, Holdout Data Governance.

---

### 1. Introduction, Background & Audit Objectives

#### 1.1 Context of the V9 Runtime Assurance Milestone
The NEXVIA AEGIS architecture provides certified runtime assurance for autonomous agents operating in safety-critical cyber-physical regimes subject to asymmetric, adversarial, and compound sensor corruptions. The project has evolved across multiple developmental and validation milestones:
- **V6–V7:** Proved the mathematical rank deficiency of two-sensor architectures under common-mode spatial bias and demonstrated the necessity of an independent third modality (AEGIS-Anchor).
- **V8.1:** Formulated Ville martingale e-processes for sequential fault detection, establishing empirical risk reductions but leaving formal finite-sample calibration incomplete.
- **V9-M1 & M2R2:** Derived a multi-layer runtime architecture combining sequential likelihood tests, vector-chord corroboration, and Learn-Then-Test (LTT) risk calibration, freezing the optimal certified candidate:
  $$\hat{\pi} = \text{V9\_CAND\_1\_TIER1\_STRICTEST}$$
  Anchored in `results/v9/cal_r2/selected_policy.json` (SHA-256: `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`).
- **V9-M3:** Conducted independent operational validation across $N=480$ episodes ($\mathcal{D}_{\mathrm{val}}$), confirming zero false successes on validation data.
- **V9-M4 (Current Milestone):** Confirmatory holdout evaluation across $N=1,440$ mixture episodes ($\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$) and $N=1,440$ stratified scenario episodes ($\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$).

#### 1.2 Audit Mandate & Scope
Under research governance protocols, holdout evaluation is strictly unrepeatable. To guarantee that the confirmatory evaluation is methodologically sound, reproducible, and immune to post-hoc adjustments, this independent pre-execution audit evaluates:
1. Traceability between preregistered hypotheses ($H_1$–$H_5$) and executable code.
2. Exactness and boundary behavior of statistical estimators and confidence bounds.
3. Behavior under edge cases (e.g. $M=0$, small $M$, extreme fault regimes).
4. Robustness of execution guards, single-shot protections, and seed isolation.
5. Algorithmic regressions across the full repository test suite.

---

### 2. Materials and Document Provenance

The audit is grounded in the authoritative project documentation and source code assets detailed in Table~\ref{tab:materials}.

| Asset Key | Path | Description & Provenance |
| :--- | :--- | :--- |
| `DOC-EXP-PROTO` | `docs/v9_experiment_protocol.md` | Authoritative preregistered experimental protocol. |
| `DOC-CAL-DESIGN`| `docs/v9_risk_calibration_design.md` | Risk calibration design, LTT theorems, and candidate definitions. |
| `DOC-M2R2-AMEND`| `docs/v9_m2r2_protocol_amendment.md` | Calibration R2 protocol amendment and PRNG disjointness model. |
| `DOC-M3-AUDIT`  | `docs/v9_m3_post_validation_audit.md` | V9-M3 post-validation audit and M4 readiness prerequisites. |
| `DOC-M4-READY`  | `docs/v9_m4_readiness_review.md` | Preregistered hypothesis definitions and architectural requirements for M4. |
| `SRC-RUNNER`    | `experiments/v9_evaluate_holdout.py` | Confirmatory holdout evaluation harness. |
| `SRC-TESTS`     | `tests/test_v9_holdout_preflight.py` | Synthetic preflight test suite for M4 runner. |
| `CFG-POLICY`    | `results/v9/cal_r2/selected_policy.json` | Calibrated policy artifact (`V9_CAND_1_TIER1_STRICTEST`). |

---

### 3. Hypothesis-to-Implementation Traceability Matrix

Table~\ref{tab:traceability} provides the definitive mapping between registered protocol claims and their implementation in `experiments/v9_evaluate_holdout.py`.

| Hyp. | Focus & Domain | Target Data Partition | Estimand & Target Metric | Statistical Decision Test | Registered Pass Threshold | Code Location (`v9_evaluate_holdout.py`) | Audit Status |
| :---: | :--- | :---: | :--- | :--- | :--- | :--- | :---: |
| **$H_1$** | **Selective Risk Certification** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ ($N=1440$) | $R_{\mathrm{sel}}(\hat{\pi}) = \mathbb{P}(FS=1 \mid A=1)$ on $\mathcal{P}_{12}$ | 1-sided exact Clopper–Pearson 95% UCB | $M \ge 59 \;\land\; U_{\mathrm{CP},1} \le 0.05 \;\land\; \hat{C} \ge 0.35$ | Lines 539–566 | **VERIFIED** |
| **$H_2$** | **Unconditional FS Reduction** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ ($N=1440$) | $\Delta R_{\mathrm{inc}} = R_{\mathrm{inc}}(\hat{\pi}) - R_{\mathrm{inc}}(\pi_{\mathrm{base}})$ | Exact 2-sided McNemar + Newcombe paired CI | $p_{\mathrm{McNemar}} < 0.05 \;\land\; \hat{R}_{\mathrm{inc}} < \hat{R}_{\mathrm{inc, base}}$ | Lines 568–615 | **VERIFIED** |
| **$H_3$** | **TSR Noninferiority** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ ($N=1200$ on $\mathcal{S}_{10}$) | $\Delta \mathrm{TSR} = \mathrm{TSR}(\hat{\pi}) - \mathrm{TSR}(\pi_{\mathrm{V7}})$ on $\mathcal{S}_{10}$ | 1-sided 95% paired difference Student's $t$ LCB | $\mathrm{LCB}_{95}(\Delta\mathrm{TSR}) > -0.05 \;\land\; \widehat{\mathrm{TSR}}_{\mathrm{NOM}} \ge 0.94$ | Lines 740–767 | **VERIFIED** |
| **$H_4$** | **Coverage Floor Precondition** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ ($N=1440$) | $C(\hat{\pi}) = \mathbb{P}(A=1)$ on $\mathcal{P}_{12}$ | Empirical point estimate $\hat{C} = M/N$ + Wilson CI | $\hat{C}(\hat{\pi}; \mathcal{P}_{12}) \ge 0.35$ (target $\ge 0.45$) | Lines 545–555 | **VERIFIED** |
| **$H_5$** | **Worst-Case Scenario Safety** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ ($12 \times 120$) | $R_{\mathrm{inc}, s} = \mathbb{P}(FS=1 \mid \text{scenario } s)$ for $s \in \mathcal{S}_{12}$ | Berger Intersection-Union Test + Holm–Šidák | $\max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc}, s} \le 0.05$ | Lines 652–774 | **FINDING M4-F02** |

---

### 4. Technical Audit Findings by Hypothesis

#### 4.1 Hypothesis $H_1$: Selective False-Success Risk Control
- **Exact Binomial Inversion:** Function `clopper_pearson_one_sided_ucb` implements exact beta-distribution quantile inversion without approximation.
- **Derivation of $M \ge 59$:** We derived that for $K = 0$, $U_{\mathrm{CP}, 1}(0, M; 0.05) = 1 - 0.05^{1/M}$. Setting $1 - 0.05^{1/M} \le 0.05$ proves that $M \ge \ln(0.05)/\ln(0.95) \approx 58.404 \implies M_{\min} = 59$.
- **Boundary Verification:**
  - $M = 58, K = 0$: $U_{\mathrm{CP}, 1} \approx 0.050339 > 0.05 \implies$ FAILS.
  - $M = 59, K = 0$: $U_{\mathrm{CP}, 1} \approx 0.049508 \le 0.05 \implies$ PASSES.
  - $M = 59, K = 1$: $U_{\mathrm{CP}, 1} \approx 0.077898 > 0.05 \implies$ FAILS.
- **Anti-Gaming Verification:** In Case C06 ($M = 59, K = 1$), the empirical point estimate is $1.69\% < 5.0\%$, but the harness correctly rejects certification because the sampling uncertainty expands the bound to $7.79\%$. Sample size $M \ge 59$ is necessary, but strictly not sufficient on its own.
- **Zero-Decision Clean Handling:** When $M = 0$, the harness returns `"r_sel": "UNDEFINED"`, avoids division-by-zero, and flags `INSUFFICIENT_COVERAGE`.

#### 4.2 Hypothesis $H_2$ & $H_3$: Paired Comparisons & Noninferiority
- **McNemar Exact Test:** Accurately computes two-sided exact binomial probabilities on discordant pairs.
- **Newcombe Score Interval (Method 10):** Accurately incorporates the sample phi-coefficient correlation $\hat{\phi}$ between paired binary outcomes.
- **Noninferiority Margin:** Correctly tests $\mathrm{LCB}_{95}(\Delta\mathrm{TSR}) > -0.05$ paired with $\widehat{\mathrm{TSR}}_{\mathrm{NOMINAL}} \ge 0.94$.
- **Finding M4-F03 (Severity: Medium):** In lines 555–559 and 755–760, paired loops use `zip(records, baseline_records)` without explicitly checking `assert r["seed"] == v["seed"] and r["scenario"] == v["scenario"]`. Adding explicit equality assertions will eliminate vulnerability to accidental array permutations.

#### 4.3 Hypothesis $H_4$: Task Coverage Floor Precondition
- **Decision Rule:** Evaluates empirical sample coverage $\hat{C} = M / N \ge 0.35$ as specified in the protocol, rather than an unapproved lower confidence bound.
- **Boundary Verification on $N = 1,440$:** $M = 503$ ($34.93\%$) fails; $M = 504$ ($35.00\%$) passes.
- **Anti-Gaming Hierarchy:** If $H_1$ passes but $H_4$ fails (e.g. $M = 60, K = 0$), the harness classifies the run as `"CONSERVATIVE_RISK_COVERAGE_TRADEOFF"` rather than `"CERTIFIED_OPERATIONAL_IMPROVEMENT"`.

#### 4.4 Hypothesis $H_5$: Multi-Scenario Worst-Case Safety (**Finding M4-F02**)
- **Inferential Objective:** The protocol specifies testing worst-case unconditional incidence $\max_{s \in \mathcal{S}_{12}} R_{\mathrm{inc}, s} \le 0.05$ using Berger's Intersection-Union Test.
- **The Defect:** In lines 698 and 703, the harness calculates $p$-values on selective decisions ($M_s$) rather than total episodes ($N_s = 120$), and sets $p = 1.0$ when $M_s = 0$.
- **The Consequence:** In catastrophic scenarios (e.g. `FAULTY_REFERENCE_SENSOR`), a safe policy abstains on 100% of episodes ($M_s = 0, K_s = 0$). Unconditional incidence is $0 / 120 = 0.0\%$, which achieves $p = (0.95)^{120} \approx 0.0021 \le 0.05$. However, the harness assigns $p = 1.0$, guaranteeing that the Berger IUT fails!
- **Remediation:** Update line 698 to compute $p_{\mathrm{inc}, s} = \mathrm{binom.cdf}(fs_s, n_s, 0.05)$ for the IUT, while continuing to report selective risk descriptively in the breakdown table.

---

### 5. Consolidated Finding Severity Register

Table~\ref{tab:severity} summarizes the formal findings of this independent audit.

\begin{table}[h!]
\centering
\small
\begin{tabularx}{\textwidth}{p{1.2cm}cp{3.8cm}Xp{2.2cm}}
\toprule
\textbf{ID} & \textbf{Severity} & \textbf{Title / Area} & \textbf{Finding Description \& Practical Impact} & \textbf{Remediation Requirement} \\
\midrule
\textbf{M4-F01} & Low & Protocol Evolution in Hypothesis Indexing ($H_2$ vs $H_4$) & Early draft narrative labeled $H_2$ as core-10 mixture risk and $H_4$ as compound McNemar. Finalized M4 review formalized $H_2$ as unconditional FS reduction and $H_4$ as coverage floor. Harness correctly follows finalized M4 review. & Reconciled in audit documentation. \\
\addlinespace
\textbf{M4-F02} & \textbf{High} & Estimand Inversion in Berger Intersection-Union Test ($H_5$) & Protocol specifies IUT over unconditional incidence $R_{\mathrm{inc}, s}$ on $N_s=120$. Harness evaluates selective risk on $M_s$, setting $p=1.0$ when $M_s=0$. This penalizes safe abstention in catastrophic fault scenarios and guarantees IUT failure. & Update IUT $p$-value to $p_{\mathrm{inc}, s} = \mathrm{binom.cdf}(fs, n_s, 0.05)$ prior to execution. \\
\addlinespace
\textbf{M4-F03} & Medium & Implicit Key Ordering in Paired Comparisons ($H_2, H_3$) & Paired loops in lines 555--559 and 755--760 use \texttt{zip()} without asserting matching seeds and scenarios. If record arrays are permuted, mismatched episodes are paired silently. & Add explicit assertions: \texttt{assert r["seed"] == v["seed"] and r["scenario"] == v["scenario"]}. \\
\bottomrule
\end{tabularx}
\caption{Formal Finding Severity Register for Milestone V9-M4.}
\label{tab:severity}
\end{table}

---

### 6. Regression Testing and Partition Isolation Audit

- **Regression Pass Rate:** 125 out of 125 tests passed in 30.72 seconds (100% pass rate).
- **Filesystem Cleanliness:** Automated directory inspections confirmed:
  - `results/v9/manifests/test_mix_manifest_r1.json` does not exist.
  - `results/v9/manifests/test_scen_manifest_r1.json` does not exist.
  - `results/v9/test_mix/` does not exist.
  - `results/v9/test_scen/` does not exist.
- **Fail-Closed Double Lock:** Confirmed that running without `--authorized-execution-token` raises `RuntimeError`, and live execution is blocked in preflight.

---

### 7. Recommendations and Next Actions

1. **Remediation of Finding M4-F02 (High Priority):**  
   Before requesting formal authorization to execute V9-M4, apply the protocol-aligned correction to `evaluate_scenario_holdout()` in `experiments/v9_evaluate_holdout.py`, ensuring that Berger IUT evaluates $p_{\mathrm{inc}, s} = \mathrm{binom.cdf}(fs_s, n_s, 0.05)$ on $N_s = 120$.
2. **Remediation of Finding M4-F03 (Medium Priority):**  
   Add explicit assertions validating matching seeds and scenarios in all paired evaluation loops.
3. **Execution Guard Maintenance:**  
   Maintain `--preflight-only` as the default execution mode.
4. **Final Recommendation Label:**  
   **`M4_STATISTICAL_AUDIT_PASS_WITH_QUALIFICATIONS`**

---

### References

1. C. J. Clopper and E. S. Pearson, "The use of confidence or fiducial limits illustrated in the case of the binomial," *Biometrika*, vol. 26, no. 4, pp. 404–413, 1934.
2. R. L. Berger, "Multiparameter hypothesis testing and acceptance sampling," *Technometrics*, vol. 24, no. 4, pp. 295–300, 1982.
3. S. Holm, "A simple sequentially rejective multiple test procedure," *Scandinavian Journal of Statistics*, vol. 6, no. 2, pp. 65–70, 1979.
4. Z. Šidák, "Rectangular confidence regions for the means of multivariate normal distributions," *Journal of the American Statistical Association*, vol. 62, no. 318, pp. 626–633, 1967.
5. Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947.
6. R. G. Newcombe, "Improved confidence intervals for the difference between binomial proportions based on paired data," *Statistics in Medicine*, vol. 17, no. 22, pp. 2635–2650, 1998.
7. E. B. Wilson, "Probable inference, the law of succession, and statistical inference," *Journal of the American Statistical Association*, vol. 22, no. 158, pp. 209–212, 1927.
8. G. Casella and R. L. Berger, *Statistical Inference*, 2nd ed., Duxbury Press, 2002.
9. IEEE Standard for Software Quality Assurance Processes, *IEEE Std 730-2014*, IEEE, 2014.
