# NEXVIA AEGIS V9-M4 Independent Statistical Audit
## Phase 7 Report: Full Regression Verification, Diff Integrity, and Finding Severity Register

**Document Identifier:** `AEGIS-V9-M4-AUD-07`  
**Phase:** Phase 7 — Regression Verification and Integrated Findings  
**Date:** October 25, 2026  
**Auditor:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Starting Commit:** `083ade9bbad7b6e28b7e18abec7e6f861a45a7b7`  
**Status:** `AUDIT_COMPLETE_WITH_FINDINGS` (125 Regression Tests Passing; Severity Register Established)

---

### Abstract

This audit report details the comprehensive regression testing, source code diff audit, and integrated findings severity register for Milestone V9-M4 of the NEXVIA AEGIS runtime assurance architecture. We record empirical results from the focused 14-test synthetic preflight test suite and the complete 125-test repository regression suite (`PYTHONPATH=src uv run pytest -q`), confirming zero test failures across all components. We inspect the repository Git working tree to ensure that no modifications have compromised the frozen selected policy, controller dynamics, sensor models, calibration routines, or historical calibration/validation artifacts. Finally, we consolidate all audit findings into a formal, prioritized Finding Severity Register with concrete remediation specifications.

**Keywords:** Regression Testing, Git Diff Verification, Software Quality Assurance, Finding Severity Register, Invariant Protection, Holdout Provenance.

---

### 1. Executive Summary & Audit Mandate

Phase 7 serves as the synthesizing audit phase:
1. **Empirical Test Verification:** Execute the full automated regression suite to ensure algorithmic stability and prevent regression errors.
2. **Repository Diff & Invariant Audit:** Inspect all tracked files to verify that frozen policies, controller parameters, sensor models, and historical datasets have not been altered.
3. **Finding Severity Categorization:** Formalize and rank all discovered findings according to standardized research quality criteria (Critical, High, Medium, Low).

---

### 2. Empirical Regression Test Outcomes

#### 2.1 Focused Synthetic Preflight Suite
We executed the 14 targeted preflight test cases in `tests/test_v9_holdout_preflight.py`:
- **Execution Command:** `PYTHONPATH=src uv run pytest -v tests/test_v9_holdout_preflight.py`
- **Recorded Result:** 14 passed in 0.99 seconds (Exit Code: 0).
- **Coverage:** Tested outcome algebra invariants, manifest and policy corruption detection, configuration tampering rejection, undefined selective risk handling, isolated mixture and scenario evaluation, single-shot overwrite guards, fail-closed execution barriers, seed boundary checks, and read-only CLI status.

#### 2.2 Full Repository Regression Suite
We executed the full automated regression suite across the entire codebase:
- **Execution Command:** `PYTHONPATH=src uv run pytest -q`
- **Recorded Result:** 125 passed in 30.72 seconds (Exit Code: 0).
- **Failure Count:** 0 failures, 0 errors, 0 warnings.
- **Component Breakdown:**
  - Core kinematic controllers and MPC baselines: Verified.
  - Multi-hypothesis Bayesian diagnosis and Ville martingales: Verified.
  - LTT calibration and fixed-sequence testing algorithms: Verified.
  - V9-M3 operational validation regression baseline: Verified.
  - V9-M4 confirmatory evaluation harness preflight: Verified.

---

### 3. Repository Working-Tree & Invariant Audit

We audited the repository working tree against starting commit `083ade9bbad7b6e28b7e18abec7e6f861a45a7b7`:
- **Policy Invariance:** The calibrated policy `results/v9/cal_r2/selected_policy.json` remains identical to commit `150629a` (raw SHA-256: `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`).
- **Controller Dynamics & Sensor Models:** No modifications in `src/aegis/v9/` or `src/aegis/next/`.
- **Calibration Engine:** `src/aegis/v9/risk_statistics.py` and `experiments/v9_calibrate_ltt.py` unmodified.
- **Historical Validation Artifacts:** `results/v9/val_r1/` artifacts remain bit-for-bit identical.
- **Holdout Data Integrity:** Confirmed that no holdout manifests or output folders have been created.

---

### 4. Consolidated Finding Severity Register

Table~\ref{tab:severity_register} details all verified findings identified across Phases 1 through 7 of the independent statistical audit.

\begin{table}[h!]
\centering
\small
\begin{tabularx}{\textwidth}{p{1.2cm}cp{3.8cm}Xp{2.2cm}}
\toprule
\textbf{ID} & \textbf{Severity} & \textbf{Title / Area} & \textbf{Finding Description \& Practical Impact} & \textbf{Remediation Requirement} \\
\midrule
\textbf{M4-F01} & Low & Protocol Evolution in Hypothesis Indexing ($H_2$ vs $H_4$) & Early draft narrative labeled $H_2$ as core-10 mixture risk and $H_4$ as compound McNemar. Finalized M4 review formalized $H_2$ as unconditional FS reduction and $H_4$ as coverage floor. Harness correctly follows finalized M4 review. & Fully reconciled in audit documentation. \\
\addlinespace
\textbf{M4-F02} & \textbf{High} & Estimand Inversion in Berger Intersection-Union Test ($H_5$) & Protocol specifies IUT over unconditional incidence $R_{\mathrm{inc}, s}$ on $N_s=120$. Harness evaluates selective risk on $M_s$, setting $p=1.0$ when $M_s=0$. This penalizes safe abstention in catastrophic fault scenarios and guarantees IUT failure. & Update IUT $p$-value to $p_{\mathrm{inc}, s} = \mathrm{binom.cdf}(fs, n_s, 0.05)$ prior to execution. \\
\addlinespace
\textbf{M4-F03} & Medium & Implicit Key Ordering in Paired Comparisons ($H_2, H_3$) & Paired loops in lines 555--559 and 755--760 use \texttt{zip()} without asserting matching seeds and scenarios. If record arrays are permuted, mismatched episodes are paired silently. & Add explicit assertions: \texttt{assert r["seed"] == v["seed"] and r["scenario"] == v["scenario"]}. \\
\bottomrule
\end{tabularx}
\caption{Consolidated finding severity register for Milestone V9-M4 preflight audit.}
\label{tab:severity_register}
\end{table}

---

### 5. Detailed Analysis of Finding Severity

1. **Critical Findings (Count: 0):**  
   No critical defects were identified. The execution guards strictly fail closed, holdout partitions remain completely untouched, and no unauthorized live execution has occurred.
2. **High Severity (Count: 1 — Finding M4-F02):**  
   Evaluating the Berger IUT on selective decisions with a fallback of $p = 1.0$ when $M_s = 0$ is a material statistical discrepancy. Because runtime assurance is designed to abstain in catastrophic fault scenarios, this implementation defect would cause the confirmatory evaluation to falsely reject safety ($H_5$) even if the policy operates flawlessly with zero false successes. Remediation before production execution is mandatory.
3. **Medium Severity (Count: 1 — Finding M4-F03):**  
   Relying on `zip()` for matched-pair comparisons is an unnecessary operational risk that can be eliminated by adding explicit key assertions.
4. **Low Severity (Count: 1 — Finding M4-F01):**  
   Historical documentation evolution, fully resolved by audit Phase 1.

---

### 6. Conclusion & Phase 7 Recommendation

Phase 7 confirms 100% regression pass rates across all 125 test suites. The finding severity register provides an actionable, transparent roadmap for pre-execution readiness.

\noindent \textbf{Phase 7 Recommendation:} \texttt{AUDIT\_PHASE\_7\_PASS\_WITH\_QUALIFICATIONS}

---

### References

1. IEEE Standard for Software Quality Assurance Processes, *IEEE Std 730-2014*, IEEE, 2014.
2. R. L. Berger, "Multiparameter hypothesis testing and acceptance sampling," *Technometrics*, vol. 24, no. 4, pp. 295–300, 1982.
3. Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947.
