# NEXVIA AEGIS V9-M4 — Confirmatory Holdout Readiness Review

**Milestone:** V9-M4 (Confirmatory Holdout Evaluation Readiness)  
**Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`  
**Branch:** `v9.0-runtime-assurance`  
**Target Policy:** `V9_CAND_1_TIER1_STRICTEST` (Frozen selection from Milestone V9-M2R2)  
**Selection Artifact:** [`results/v9/cal_r2/selected_policy.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/cal_r2/selected_policy.json)  
**Status:** **NON-EXECUTABLE REVIEW ONLY** (Holdout execution is strictly prohibited)  
**Recommendation:** **`M4_READY_WITH_QUALIFICATIONS`**

---

## 1. Executive Summary

Following the completion of calibration (Milestone V9-M2R2) and operational validation (Milestone V9-M3), this document establishes the readiness criteria, formal protocol specifications, statistical analysis plans, and execution safeguards for the final milestone: **Milestone V9-M4 (Confirmatory Holdout Evaluation)**.

> [!IMPORTANT]
> **STRICT EXECUTION BLOCK:** This readiness review does NOT constitute authorization to generate holdout manifests, instantiate holdout RNG streams, or execute holdout episodes. The reserved holdout partitions remain completely untouched.

---

## 2. Intended Holdout Evaluation Objectives

Milestone V9-M4 represents the final confirmatory step in the NEXVIA AEGIS V9 research journey. Its purpose is to test the locked, calibrated policy $\hat{\pi} =$ `V9_CAND_1_TIER1_STRICTEST` on genuinely unobserved holdout data that has never been accessed during development, calibration, or validation.

### 2.1 The Two Registered Holdout Partitions
In accordance with [`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md) Section 3.6.1 items 5 & 6 and [`docs/v9_risk_calibration_design.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_risk_calibration_design.md) Section 2.5.2:

1. **Final Holdout — Pooled Mixture ($\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$):**
   - **Sample Size:** $N = 1,440$ episodes.
   - **Sampling Law:** Independent and identically distributed (i.i.d.) draws from the uniform 12-scenario mixture $\mathcal{P}_{12} = \frac{1}{12}\sum_{s=1}^{12} \mathcal{P}_s$.
   - **Reserved Seed Range:** `73000 .. 74439` (1,440 seeds).
   - **PRNG Partition Branch:** $p = \text{PARTITION\_BRANCH\_TEST\_MIXTURE} = 4$.
   - **Target Manifest:** `results/v9/manifests/test_mix_manifest_r1.json` (**not yet created**).
   - **Target Output Directory:** `results/v9/test_mix/`.

2. **Final Holdout — Stratified Per-Scenario ($\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$):**
   - **Sample Size:** $N = 1,440$ episodes ($12 \text{ scenarios} \times 120 \text{ seeds/scenario}$).
   - **Sampling Law:** Stratified deterministic grid $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}} = \{(s, \text{seed}) \mid s \in \mathcal{S}_{12}, \; \text{seed} \in [75000, 75120)\}$.
   - **Reserved Seed Range:** `75000 .. 75119` (120 seeds per scenario).
   - **PRNG Partition Branch:** $p = \text{PARTITION\_BRANCH\_TEST\_SCENARIO} = 5$.
   - **Target Manifest:** `results/v9/manifests/test_scen_manifest_r1.json` (**not yet created**).
   - **Target Output Directory:** `results/v9/test_scen/`.

---

## 3. Preregistered Confirmatory Statistical Hypotheses

The statistical evaluation must follow the prespecified hypotheses defined in [`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md) Table 3.5.1:

| Hypothesis | Description | Test Partition | Primary Metric & Statistical Test | Confirmatory Pass Criterion |
| :--- | :--- | :---: | :--- | :--- |
| **$H_1$** | **Selective False-Success Risk Control** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ | 1-sided exact Clopper–Pearson 95% UCB on $R_{\mathrm{sel}} = P(FS=1 \mid A=1)$ | $M \ge 59$ and $U_{\mathrm{CP},1}(K, M; 0.05) \le 0.05$ |
| **$H_2$** | **Unconditional FS Incidence Reduction** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ | Exact 2-sided paired McNemar test + Newcombe paired CI vs. V7/V8 baselines | $U_{\mathrm{CP},1}(K, N; 0.05) \le 0.05$ and significant reduction on compound faults |
| **$H_3$** | **Operational Utility & TSR Noninferiority** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ | 1-sided 95% paired LCB on $\Delta TSR = TSR(\hat{\pi}) - TSR(\pi_{\mathrm{V7}})$ across $N=1,200$ matched $\mathcal{S}_{10}$ pairs | $\mathrm{LCB}_{95\%}(\Delta TSR) > -0.05$ ($-5.0\%$) AND $\widehat{TSR}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$ |
| **$H_4$** | **Coverage Floor Precondition** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ | Sample coverage $\hat{C} = M / N$ | $\hat{C}(\hat{\pi}; \mathcal{P}_{12}) \ge C_{\min} = 0.35$ (target $\ge 0.45$) |
| **$H_5$** | **Scenario Worst-Case Safety** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ | Holm–Šidák simultaneous 12-scenario CIs + Berger Intersection-Union Test | Explicit per-scenario breakdown across all 12 scenarios |

---

## 4. Preregistered Baseline Comparisons

To test noninferiority and safety improvements, the runner must evaluate matched-episode pairs against the two committed reference baselines:
1. **`AEGIS_NEXT_MARTINGALE` (V8.1 Baseline):** Reconstructed in `src/aegis/next/agent_next.py`.
2. **`AEGIS_V7_MPC_BASELINE` (V7 Baseline):** Reconstructed in `src/aegis/next/baselines.py`.

---

## 5. Architectural Requirements for the M4 Evaluation Harness

Before executing M4, a dedicated, auditable evaluation runner must be implemented:
`experiments/v9_evaluate_holdout.py`

### Mandatory Runner Guardrails:
1. **Immutable Policy Loading:** Must load exclusively from `results/v9/cal_r2/selected_policy.json`, verify its canonical SHA-256 integrity hash, and confirm candidate ID `V9_CAND_1_TIER1_STRICTEST`.
2. **Partition Guard:** Must reject any seed outside `73000..74439` (for mixture) or `75000..75119` (for scenario grid).
3. **Output Isolation:** Outputs must be written strictly to `results/v9/test_mix/` and `results/v9/test_scen/`.
4. **Single-Shot Guard:** Must refuse execution if outputs already exist.
5. **Decoupled PRNG Derivation:** Must instantiate environment and sensor streams from manifest items using `instantiate_episode_rngs_from_manifest_item` under branches $p=4$ and $p=5$.
6. **Pre-Execution Freeze:** Must provide `--freeze-only` mode to generate and verify `holdout_run_config_frozen_r1.json` before any episode is simulated.
7. **Comprehensive Unit Testing:** Must include unit tests that execute the full end-to-end pipeline (including all CSV formatting and report compilation) on synthetic mock records before holdout execution, preventing post-processing runtime exceptions.

---

## 6. Audit Qualifications and Prerequisite Checklist

Based on the V9-M3 post-validation audit, the following qualifications are formally established:

| Area | Status / Qualification | Action for M4 |
| :--- | :--- | :--- |
| **Policy Invariance** | Frozen selection `V9_CAND_1_TIER1_STRICTEST` verified bit-for-bit. | No threshold or parameter changes permitted. |
| **Runner Provenance** | Ensure evaluation harness is frozen and committed in Git before launching holdout simulation. | Commit harness, mock tests, manifests, and frozen config prior to execution. |
| **Reporting Robustness** | In M3, an `AttributeError` occurred on `mean_step_ms` post-simulation. | Harness must be tested end-to-end on synthetic data to ensure zero reporting bugs. |
| **Statistical Distinction** | M3 clarified that stratified sample bounds are descriptive references. | Keep mixture ($H_1$) and stratified ($H_3, H_5$) inferential analyses strictly separated. |
| **PRNG Independence** | Model accurately documented: PRNG streams are independent with negligible collision probability. | Continue partition-branched SeedSequence derivation ($p=4$ and $p=5$). |

---

## 7. Recommendation

### Recommendation: `M4_READY_WITH_QUALIFICATIONS`
The NEXVIA AEGIS V9 project is **operationally and methodologically ready** for Milestone V9-M4 confirmatory holdout evaluation, subject to the qualifications specified above.

**Next Step:** Submit M3 audit and M4 readiness review for user authorization. Do not execute holdout episodes until explicit authorization is granted.
