# NEXVIA AEGIS V9-M4 — D_dev Benchmark Results

**Document Version:** 1.0.0  
**Project:** NEXVIA AEGIS  
**Milestone:** V9-M4 — Autonomous Safety & Research Integrity Verification Subsystem  
**Governance Status:** `BLOCKED — GATE_B_NOT_AUTHORIZED`  
**Execution Timestamp:** 2026-10-29T00:42:04Z  
**Execution Environment:** macOS, Python 3.12.14, Git SHA `a37d1d9bc93cf5ed60c702a2c753b74f925b6bf2`  
**Partition Evaluated:** Authorized Development Grid ($\mathcal{D}_{\text{dev,r1}}$, Seeds `77000..77029`)

---

## 1. Execution Log & Provenance Record

The benchmark was executed in strict accordance with the approved benchmark plan ([V9_M4_DDEV_BENCHMARK_PLAN.md](file:///Users/chalermsak/Desktop/nexvia-aegis-main/V9_M4_DDEV_BENCHMARK_PLAN.md)) under isolated output routing to prevent any modification or overwriting of historical artifacts.

### 1.1 Execution Command & Parameters

```bash
PYTHONPATH=src uv run python experiments/v9_evaluate_dev.py \
    --seeds-start 77000 \
    --seeds-count 30 \
    --suffix _assessment \
    --out-dir results/v9/dev
```

- **Exit Code:** `0` (Success)
- **Episodes Planned:** 2,880 episodes total (360 episodes per policy $\times$ 8 policies; 1,800 episodes across the 5 primary comparison policies)
- **Episodes Completed:** 2,880 / 2,880 (100.0% completion rate)
- **Crashes / Unhandled Exceptions:** 0
- **Elapsed Real Time:** 152.12 seconds (~2.5 minutes)

### 1.2 Generated Artifact Registry & Cryptographic Hashes

All generated files were placed in non-conflicting paths with suffix `_assessment`:

| Artifact Path | Format | Raw SHA-256 Digest | Status |
|---|:---:|:---:|:---:|
| [`results/v9/dev/dev_episodes_assessment.csv`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/dev/dev_episodes_assessment.csv) | CSV (2,880 rows) | `1faf4379e43182e3c49299675d51e218056b469b656bedb726b6c31d1a6dc37e` | COMPLETE_VALID |
| [`results/v9/dev/dev_policy_summary_assessment.csv`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/dev/dev_policy_summary_assessment.csv) | CSV (8 policies) | `9091a156435a319b4cbe4246de2bbedec72f236cc507fbe4885cb845f2a0ed93` | COMPLETE_VALID |
| [`results/v9/dev/dev_scenario_summary_assessment.csv`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/dev/dev_scenario_summary_assessment.csv) | CSV (96 rows) | `8bb02966be3a4775a2e1da0fd269726f3d20d52572fda6f72129225992086a09` | COMPLETE_VALID |
| [`results/v9/dev/dev_ordering_report_assessment.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/dev/dev_ordering_report_assessment.json) | JSON | `fedc21b5acb5470dca34e25232ec1514eca7369ff4df3417067c1ac92e076f1b` | COMPLETE_VALID |
| [`results/v9/manifests/dev_manifest_assessment.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/dev_manifest_assessment.json) | JSON | `285d908b677160e9adb22c4257a5c9a9be94cf7d06077bb5839f56b1b2d7b897` | COMPLETE_VALID |
| [`research/v9_m4_ddev_benchmark/benchmark_statistical_analysis.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/research/v9_m4_ddev_benchmark/benchmark_statistical_analysis.json) | JSON | `b8a73752fae802095f9c961e687e07a3c7ef233ca3214da9ea0ba6b757e84ba2` | COMPLETE_VALID |

---

## 2. Policy-Level Evaluation Summary

The table below summarizes the observed outcomes across all $N=360$ episodes per policy on the development partition ($\mathcal{D}_{\text{dev}}$).

| Policy Identifier | Total $N$ | Accepted $M$ | Coverage $\hat{C}$ | True Success $TS$ | Task Success Rate $\text{TSR}$ | False Success $FS$ | Selective Risk $\hat{R}_{\text{sel}}$ | Explicit Abstain | Timeouts $TO$ | Mean Step ms | Mean Anchor Cost |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`V9_CAND_1_TIER1_STRICTEST`** | 360 | 205 | 56.94% | 205 | **56.94%** | **0** | **0.00%** | 148 | 7 (1.94%) | 0.1338 | 0.0842 |
| **`V9_CAND_2_TIER2_VERY_STRICT`** | 360 | 205 | 56.94% | 205 | **56.94%** | **0** | **0.00%** | 148 | 7 (1.94%) | 0.1344 | 0.0839 |
| **`V9_CAND_3_TIER3_BALANCED_STRICT`** | 360 | 204 | 56.67% | 204 | **56.67%** | **0** | **0.00%** | 147 | 9 (2.50%) | 0.1381 | 0.0833 |
| `V9_CAND_4_TIER4_BALANCED` | 360 | 203 | 56.39% | 203 | 56.39% | 0 | 0.00% | 147 | 10 (2.78%) | 0.1396 | 0.0832 |
| `V9_CAND_5_TIER5_MODERATE` | 360 | 203 | 56.39% | 203 | 56.39% | 0 | 0.00% | 149 | 8 (2.22%) | 0.1416 | 0.0832 |
| `V9_CAND_6_TIER6_PERMISSIVE` | 360 | 201 | 55.83% | 201 | 55.83% | 0 | 0.00% | 150 | 9 (2.50%) | 0.1441 | 0.0829 |
| **`AEGIS_NEXT_MARTINGALE` (V8.1)** | 360 | 160 | 44.44% | 156 | **43.33%** | **4** | **2.50%** | 176 | 24 (6.67%) | 1.2631 | 0.0486 |
| **`AEGIS_V7_MPC_BASELINE` (V7)** | 360 | 150 | 41.67% | 140 | **38.89%** | **10** | **6.67%** | 102 | **108 (30.00%)** | 1.3938 | 0.1521 |

> [!NOTE]
> **Denominator Definitions:**
> - $\text{TSR} = TS / N = TS / 360$
> - $\text{Coverage} = M / N = (TS + FS) / 360$
> - $\hat{R}_{\text{sel}} = FS / M$ (Undefined if $M=0$; here $M \ge 150$, so $\hat{R}_{\text{sel}}$ is defined for all policies).
> - $\hat{R}_{\text{inc}} = FS / N = FS / 360$

---

## 3. Confidence Intervals for Primary Metrics

Exact two-sided 95% Clopper-Pearson confidence intervals for the 5 target policies:

| Policy | Task Success Rate (95% CI) | Coverage (95% CI) | Selective Risk (95% CI) |
|---|:---:|:---:|:---:|
| **`V9_CAND_1`** | **56.94%** [51.65%, 62.12%] | **56.94%** [51.65%, 62.12%] | **0.00%** [0.00%, 1.78%] |
| **`V9_CAND_2`** | **56.94%** [51.65%, 62.12%] | **56.94%** [51.65%, 62.12%] | **0.00%** [0.00%, 1.78%] |
| **`V9_CAND_3`** | **56.67%** [51.37%, 61.85%] | **56.67%** [51.37%, 61.85%] | **0.00%** [0.00%, 1.79%] |
| **`AEGIS_NEXT_MARTINGALE` (V8.1)** | **43.33%** [38.15%, 48.63%] | **44.44%** [39.24%, 49.74%] | **2.50%** [0.69%, 6.28%] |
| **`AEGIS_V7_MPC_BASELINE` (V7)** | **38.89%** [33.82%, 44.14%] | **41.67%** [36.52%, 46.95%] | **6.67%** [3.24%, 11.92%] |

---

## 4. Per-Scenario Performance Breakdown ($N=30$ seeds / scenario)

### 4.1 True Success Count ($TS / 30$) Across Scenarios

| Scenario | `V9_CAND_1` | `V9_CAND_2` | `V9_CAND_3` | `AEGIS_NEXT` (V8) | `AEGIS_V7` (V7) |
|---|:---:|:---:|:---:|:---:|:---:|
| `NOMINAL` | 29 | **30** | **30** | **30** | 28 |
| `PRIMARY_BIAS` | **29** | **29** | **29** | 13 | 15 |
| `INDEPENDENT_BIAS` | **29** | **29** | **29** | 14 | 13 |
| `CORRELATED_BIAS` | **28** | **28** | **28** | 25 | 16 |
| `SENSOR_DRIFT` | **25** | 24 | 24 | 5 | 23 |
| `OUTLIER_BURSTS` | 24 | 22 | 23 | **29** | 22 |
| `SENSOR_DROPOUT` | **30** | **30** | **30** | **30** | 21 |
| `FAULTY_REFERENCE_SENSOR` | 0 | 0 | 0 | 0 | 0 |
| `CORRUPTED_ANCHOR_STRESS` | 0 | 0 | 0 | 1 | 0 |
| `COMPOUND_HOLDOUT_EXTREME` | 0 | 0 | 0 | 0 | 0 |
| `COMPOUND_DRIFT_DROPOUT` | 11 | **13** | 11 | 9 | 2 |
| `COMPOUND_ANTIPODAL_RANGE_SHIFT` | 0 | 0 | 0 | 0 | 0 |
| **Total True Successes** | **205** | **205** | **204** | **156** | **140** |

### 4.2 False Success Count ($FS / 30$) Across Scenarios

| Scenario | `V9_CAND_1` | `V9_CAND_2` | `V9_CAND_3` | `AEGIS_NEXT` (V8) | `AEGIS_V7` (V7) |
|---|:---:|:---:|:---:|:---:|:---:|
| `NOMINAL` | 0 | 0 | 0 | 0 | 0 |
| `PRIMARY_BIAS` | **0** | **0** | **0** | 1 | 2 |
| `INDEPENDENT_BIAS` | **0** | **0** | **0** | 1 | 6 |
| `CORRELATED_BIAS` | **0** | **0** | **0** | 0 | 0 |
| `SENSOR_DRIFT` | **0** | **0** | **0** | 0 | 0 |
| `OUTLIER_BURSTS` | **0** | **0** | **0** | 0 | 0 |
| `SENSOR_DROPOUT` | **0** | **0** | **0** | 0 | 0 |
| `FAULTY_REFERENCE_SENSOR` | **0** | **0** | **0** | 0 | 0 |
| `CORRUPTED_ANCHOR_STRESS` | **0** | **0** | **0** | 0 | 0 |
| `COMPOUND_HOLDOUT_EXTREME` | **0** | **0** | **0** | 2 | 2 |
| `COMPOUND_DRIFT_DROPOUT` | **0** | **0** | **0** | 0 | 0 |
| `COMPOUND_ANTIPODAL_RANGE_SHIFT` | **0** | **0** | **0** | 0 | 0 |
| **Total False Successes ($K$)** | **0** | **0** | **0** | **4** | **10** |

### 4.3 Timeout Count ($TO / 30$) Across Scenarios

| Scenario | `V9_CAND_1` | `V9_CAND_2` | `V9_CAND_3` | `AEGIS_NEXT` (V8) | `AEGIS_V7` (V7) |
|---|:---:|:---:|:---:|:---:|:---:|
| `NOMINAL` | 1 | **0** | **0** | **0** | 2 |
| `PRIMARY_BIAS` | **0** | **0** | **0** | 4 | 13 |
| `INDEPENDENT_BIAS` | **0** | **0** | **0** | 2 | 11 |
| `CORRELATED_BIAS` | 1 | 1 | 1 | **0** | 14 |
| `SENSOR_DRIFT` | **0** | **0** | **0** | **0** | 7 |
| `OUTLIER_BURSTS` | 3 | 4 | 6 | **0** | 8 |
| `SENSOR_DROPOUT` | **0** | **0** | **0** | **0** | 9 |
| `FAULTY_REFERENCE_SENSOR` | 2 | 2 | 2 | 16 | 20 |
| `CORRUPTED_ANCHOR_STRESS` | **0** | **0** | **0** | **0** | 1 |
| `COMPOUND_HOLDOUT_EXTREME` | **0** | **0** | **0** | **0** | 2 |
| `COMPOUND_DRIFT_DROPOUT` | **0** | **0** | **0** | 2 | 19 |
| `COMPOUND_ANTIPODAL_RANGE_SHIFT` | **0** | **0** | **0** | **0** | 2 |
| **Total Timeouts** | **7** | **7** | **9** | **24** | **108** |

---

## 5. Candidate Ordering Verification Check

As recorded in [`results/v9/dev/dev_ordering_report_assessment.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/dev/dev_ordering_report_assessment.json):
- **Tier-1 Precheck Passed:** `True` (Tier-1 Coverage = $56.94\% \ge 42.0\%$ minimum threshold).
- **All 6 Candidates Admissible:** `True` (Coverage $\ge 0.35$, Nominal TSR $\ge 0.94$).
- **Ordering Conservatism Invariant:** Preserved strictly across all 6 tiers.

---

*Results officially recorded. Confirmatory release status remains `BLOCKED — GATE_B_NOT_AUTHORIZED`.*
