# V9-M4 Statistical Reviewer Package

**Review Status:** `REMEDIATED CANDIDATE BASELINE — READY FOR INDEPENDENT STATISTICAL SIGN-OFF`  
**Gate B Disposition:** `BLOCKED — GATE_B_NOT_AUTHORIZED`  
**Date:** 2026-10-28 (Asia/Bangkok)  

---

## 1. Reviewer Overview & Scope

This package compiles the necessary statistical documentation, code implementations, and verified regression test evidence for the independent statistical reviewer evaluating the scientific rigor and claim integrity of NEXVIA AEGIS V9-M4.

**Required Reference Documents:**
1. [`docs/reports/v9_m4_release_remediation/V9_M4_SCI01_OWNER_DECISION_BRIEF.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_release_remediation/V9_M4_SCI01_OWNER_DECISION_BRIEF.md)
2. `docs/reports/v9_m4_release_remediation/V9_M4_SYNTHETIC_TEST_SPECIFICATION.md` (preserved in commit `822c1b2e7e89b5850d2ddbb616c89acf00e0573e`)
3. [`docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md)
4. [`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md) & Owner Decision Record 22 ([`docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md))
5. Evaluator implementation: [`experiments/v9_evaluate_holdout.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_evaluate_holdout.py)
6. Preflight Confirmatory Test Suite: [`tests/test_v9_holdout_preflight.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py)

---

## 2. Seven Core Scientific Decisions & Implemented Remediations

### Item 1: Hypothesis H1 Coverage Formulation (SCI-01)
- **Protocol Definition (`protocol:19-22`):** Three-part conjunction required for formal certification:
  1. $M \ge 59$ accepted episodes under i.i.d. sampling.
  2. Exact one-sided 95% Clopper–Pearson upper confidence bound $U_{\mathrm{CP},1}(K, M; 0.05) \le 0.05$.
  3. Empirical mixture coverage $\hat{C} = M / N \ge 0.35$.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:975-993`):** Option A formally enforced. Evaluator requires all three conjuncts; failure of the coverage floor yields `FAILED_COVERAGE_FLOOR`.
- **Test Verification:** [`test_65_h1_conjunctive_option_a_and_h2_sequential_gate`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2620-L2685) verifies that at $N=1440, M=59, K=0$, selective risk is $0.0495 \le 0.05$, but low coverage ($4.09\% \ll 35\%$) is rejected fail-closed.

### Item 2: Hypothesis H2 Estimand and Sequential Gating (SCI-02)
- **Protocol Definition (`protocol:17, 24-26`):** $H_2$ is gatekept in a fixed-sequence hierarchical testing procedure; $H_2$ may only be evaluated/claimed if $H_1$ passes at $\alpha = 0.05$.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:1081-1090`):** Sequential gate strictly enforced. If $H_1$ fails, $H_2$ immediately assigns `passed = False` and `status = "BLOCKED_BY_H1_GATE"`.
- **Test Verification:** Verified in `test_65`.

### Item 3: Hypothesis H3 Controlling Confidence Interval & Baseline Substitution (SCI-03)
- **Protocol Definition (`protocol:28-30`):** Secondary paired true-success noninferiority on $\mathcal{S}_{10}$ ($N = 1,200$) with primary comparator V8.1 and auxiliary co-evaluation vs V7.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:1315-1324`):** Mandatory primary V8.1 baseline enforced. If V8.1 is absent, $H_3$ fails closed with `NOT_EVALUATED_NO_PRIMARY_V8_BASELINE` and refuses to allow V7 to substitute as the primary pass.
- **Test Verification:** [`test_66_h3_missing_v8_cannot_silently_pass_primary_with_v7`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2688-L2727) verifies that missing V8.1 records reject primary noninferiority even when V7 is favorable.

### Item 4: Hypothesis H4 Compound-Fault Safety (SCI-04)
- **Protocol Definition (`protocol:32-34`):** Secondary compound-fault false-success incidence reduction on $\mathcal{S}_{\mathrm{comp}} = \{\text{INDEPENDENT\_BIAS}, \text{COMPOUND\_HOLDOUT\_EXTREME}, \text{COMPOUND\_DRIFT\_DROPOUT}, \text{COMPOUND\_ANTIPODAL\_RANGE\_SHIFT}\}$ ($4 \times 120 = 480$ matched episodes). Requires exact two-sided paired McNemar test $p < 0.05$ with favorable direction ($n_{10} < n_{01}$) vs V8.1, reported alongside paired bootstrap 95% CI for $\Delta R_{\mathrm{sel}}$.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:1364-1440`):** Full compound comparison restored in `evaluate_scenario_holdout` using `mcnemar_exact_test` and `paired_bootstrap_selective_risk_difference_ci`.
- **Test Verification:** [`test_68_h4_compound_fault_evaluation_and_v8_pairing`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2748-L2835) verifies favorable reduction passes, unfavorable fails, and missing V8.1 fails closed.

### Item 5: Hypothesis H5 Worst-Case Safety & Undefined Selective Risk (SCI-05)
- **Protocol Definition (`protocol:36-37, 252`):** Simultaneous one-sided CP bounds across all 12 scenarios using Šidák allocation and Holm step-down, Berger IUT on unconditional incidence ($\max_s p_{\mathrm{inc},s} \le 0.05$), and explicit handling of $M_s = 0$ as `UNDEFINED`.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:1180-1193, 1428-1440`):** Scenarios with $M_s = 0$ are recorded as `r_sel = "UNDEFINED"` and enumerated in `undefined_selective_risk_scenarios` with `all_selective_risk_defined = False`, ensuring no false claim of selective-risk control.
- **Test Verification:** [`test_69_h5_undefined_selective_risk_reporting`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2838-L2888) verifies an all-abstain scenario reports undefined selective risk fail-closed.

### Item 6: Strict Record Count Integrity (SCI-06)
- **Problem:** Denominator checks against `len(records)` rather than registered manifest count risked accepting shortened or truncated partitions.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:945-958`):** Explicit `expected_n` parameter added to verify partition record counts against registered manifests.
- **Test Verification:** [`test_67_evaluate_mixture_holdout_expected_n_mismatch`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2728-L2745) verifies that shortened record sets raise `ValueError`.

### Item 7: Secondary Multiplicity & Aggregate Claim Scoping (SCI-07)
- **Problem:** Emitting system-wide `CERTIFIED_OPERATIONAL_IMPROVEMENT` based only on Mixture Holdout was premature before Scenario Holdout was evaluated.
- **Remediated Implementation (`experiments/v9_evaluate_holdout.py:1091-1098`):** Classification in Mixture Holdout is strictly scoped to `"MIXTURE_CERTIFIED_OPERATIONAL_IMPROVEMENT"`, with overall system certification requiring joint evaluation across both partitions.
- **Test Verification:** [`test_70_mixture_does_not_overclaim_system_operational_improvement`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2891-L2905) verifies partition-level claim scoping.

---

## 3. Reviewer Checklist & Verification Baseline

To execute formal statistical sign-off:
1. **Automated Test Run:** Execute `uv run pytest tests/test_v9_holdout_preflight.py` to confirm all 71 confirmatory tests pass.
2. **Review Mathematical Formulas:** Verify Clopper-Pearson exact beta inversion (`clopper_pearson_one_sided_ucb`), exact McNemar binomial test (`mcnemar_exact_test`), Newcombe Method 10 paired difference interval (`newcombe_paired_difference_ci`), and Berger IUT (`berger_intersection_union_test`).
3. **Verify Boundary Conditions:** Confirm that boundary conditions ($M=58, 59$, Coverage $0.349, 0.350$, $M_s=0$) behave strictly fail-closed.
4. **Sign-off Record:**
   - Independent Statistical Reviewer: `PENDING APPOINTMENT & SIGNATURE`
   - Gate B Status: `BLOCKED — GATE_B_NOT_AUTHORIZED`
