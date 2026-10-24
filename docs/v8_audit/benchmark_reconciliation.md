# NEXVIA AEGIS V8.1 — Benchmark Reconciliation & Recalculation Audit

**Author / Roles:** Senior Statistical Research Scientist, Experimental Methodology Auditor  
**Scope:** Raw data audit of `results/next/benchmark_episodes.csv`, recalculation of `results/next/benchmark_summary.csv`, and statistical sensitivity verification  
**Date:** October 2026  
**Status Tag:** Independently reproduced and verified (with zero-coverage notation correction and scenario sensitivity identified)  

---

## 1. Executive Summary

This audit independently reconciles all 4,000 policy-episode records from `results/next/benchmark_episodes.csv` with the reported summary tables. All calculations were executed from scratch via `experiments/audit_v8_metrics.py`, and the resulting verified metrics are archived in `results/v8_audit/metrics_recalculated.csv`.

### Key Verification Findings:
1. **Episode Accounting:** Exactly 4,000 episodes exist across 10 scenarios, 8 policies, and 50 matched random seeds (`60000` to `60049`). No duplicates or missing runs were detected.
2. **Terminal State Integrity:** In 100.0% of episodes ($4,000/4,000$), the terminal condition strictly satisfied:
   $$\text{True Success} + \text{False Success} + \text{Abstain} = 1.$$
3. **Wilson Interval Recalculation:** The reported pooled Covered Risk for AEGIS-Next ($6/257 = 2.3346\%$) yields a two-sided 95% Wilson Score upper bound of **$4.9989\%$** ($0.049989$). While technically below $5.0\%$, it clears the threshold by only **$0.0011$ percentage points**.
4. **Clopper-Pearson Exact Sensitivity:** Under the exact Clopper-Pearson (Beta distribution) confidence interval, the 95% upper bound is **$5.0120\%$**, which **exceeds** the $5.0\%$ target!
5. **Zero-Coverage Defect in Original Summary:** In 19 scenario-policy instances where coverage was zero ($TS + FS = 0$), the original summary CSV recorded `covered_risk = 0.0`. In the recalculated audit, these are correctly designated as `undefined`.
6. **Per-Scenario Risk Disparity:** The 2.33% risk claim is purely a pooled average. In the held-out stress scenario `COMPOUND_HOLDOUT_EXTREME`, AEGIS-Next accepted 3 decisions and suffered 2 false successes, yielding a per-scenario Covered Risk of **$66.7\%$** ($2/3$). In `INDEPENDENT_BIAS`, risk was **$12.5\%$** ($4/32$).

---

## 2. Complete Recalculated Summary Table

The table below reports the verified pooled statistics across all 500 episodes per policy:

| Policy Architecture | Evaluated Episodes | True Success Count (Rate) | False Success Count (Incidence) | Abstention Count (Rate) | Accepted Decisions (Coverage) | Covered Risk ($FS / \text{Cov}$) | 95% Wilson Score CI for Covered Risk | 95% Clopper-Pearson Exact CI for Covered Risk | Mean Anchor Cost | Mean Max Overshoot (m) |
|---|---|---|---|---|---|---|---|---|---|---|
| **AEGIS_NEXT_MARTINGALE** | 500 | 251 (50.2%) | 6 (1.2%) | 243 (48.6%) | 257 (51.4%) | **2.33%** (6/257) | [0.0107, 0.04999] | [0.0086, 0.05012] | 0.0421 | 0.0751 |
| **AEGIS_V7_MPC_BASELINE** | 500 | 267 (53.4%) | 17 (3.4%) | 216 (43.2%) | 284 (56.8%) | **5.99%** (17/284) | [0.0377, 0.0938] | [0.0352, 0.0942] | 0.1440 | 0.0687 |
| **AEGIS_V6_DISCRIMINATIVE** | 500 | 218 (43.6%) | 29 (5.8%) | 253 (50.6%) | 247 (49.4%) | **11.74%** (29/247) | [0.0827, 0.1639] | [0.0801, 0.1648] | 0.0000 | 0.1545 |
| **AEGIS_V5_HUBER_CALIBRATE** | 500 | 182 (36.4%) | 29 (5.8%) | 289 (57.8%) | 211 (42.2%) | **13.74%** (29/211) | [0.0969, 0.1912] | [0.0939, 0.1919] | 0.0000 | 0.0585 |
| **AEGIS_V4_PASSIVE_VERIFY** | 500 | 129 (25.8%) | 8 (1.6%) | 363 (72.6%) | 137 (27.4%) | **5.84%** (8/137) | [0.0299, 0.1110] | [0.0256, 0.1118] | 0.0000 | 0.0013 |
| **CHISQUARE_NIS_GATING** | 500 | 49 (9.8%) | 56 (11.2%) | 395 (79.0%) | 105 (21.0%) | **53.33%** (56/105) | [0.4384, 0.6256] | [0.4334, 0.6310] | 0.0000 | 0.0307 |
| **UNSHIELDED_ALWAYS_ACT** | 500 | 198 (39.6%) | 162 (32.4%) | 140 (28.0%) | 360 (72.0%) | **45.00%** (162/360) | [0.3992, 0.5019] | [0.3979, 0.5031] | 0.0000 | 0.1045 |
| **EKF_CONSISTENCY_MONITOR** | 500 | 15 (3.0%) | 0 (0.0%) | 485 (97.0%) | 15 (3.0%) | **0.00%** (0/15) | [0.0000, 0.2041] | [0.0000, 0.2180] | 0.0000 | 0.0000 |

---

## 3. Detailed Audit of the Wilson Interval (Section 6)

The report states:
> *"AEGIS-Next produced 6 false-success events among 257 accepted decisions (2.33%), with a 95% Wilson upper bound of 4.98%."*

### 3.1 Mathematical Recalculation
Let $k = 6$, $n = 257$, $\hat{p} = k / n = 0.0233463$.
For a two-sided $95\%$ confidence level, the standard normal quantile is:
$$z_{1 - \alpha/2} = z_{0.975} = 1.95996398454.$$

The standard Wilson score interval formula without continuity correction is:
$$\tilde{n} = n + z^2 = 257 + 3.841459 = 260.841459$$
$$\tilde{p} = \frac{k + \frac{z^2}{2}}{\tilde{n}} = \frac{6 + 1.920729}{260.841459} = \frac{7.920729}{260.841459} = 0.030366$$
$$\text{Margin} = \frac{z}{\tilde{n}} \sqrt{\frac{k(n - k)}{n} + \frac{z^2}{4}} = \frac{1.959964}{260.841459} \sqrt{\frac{6 \times 251}{257} + 0.960365} = \frac{1.959964 \times \sqrt{5.859922 + 0.960365}}{260.841459} = \frac{1.959964 \times 2.611568}{260.841459} = 0.019623$$

Interval endpoints:
$$p_{\text{lower}} = \tilde{p} - \text{Margin} = 0.030366 - 0.019623 = \mathbf{0.010743} \quad (1.074\%)$$
$$p_{\text{upper}} = \tilde{p} + \text{Margin} = 0.030366 + 0.019623 = \mathbf{0.049989} \quad (4.9989\%)$$

### 3.2 Evaluation of the Reported Value "4.98%"
- The actual unrounded Wilson upper bound is **$4.99894\%$**, not $4.98\%$.
- $4.99894\% < 5.00000\%$ is technically true by a margin of only $0.0000106$ ($1.06 \times 10^{-5}$).
- When rounded to two decimal places, $4.9989\%$ rounds to **$5.00\%$**, not $4.98\%$.
- Citing "4.98%" appears to have been an informal approximation or slight misquotation.

### 3.3 Methodological Sensitivity: Wilson vs. Clopper-Pearson Exact
Under the exact Clopper-Pearson method (using the Beta distribution quantiles $\text{Beta}(0.025, 6, 252)$ and $\text{Beta}(0.975, 7, 251)$):
$$\text{Exact 95\% CI} = [0.008615, 0.050120] \quad (\mathbf{0.861\% \text{ to } 5.012\%})$$
Notice that the exact Clopper-Pearson upper bound is **$5.012\%$**, which **exceeds $5.0\%$**!
Furthermore, if just **one** additional accepted episode had been a false success ($k = 7, n = 257$):
- Point estimate: $7 / 257 = 2.72\%$
- Wilson 95% CI: $[0.0132, \mathbf{0.0553}]$ ($5.53\%$ upper bound, failing the target).

**Conclusion:** The claim that Covered Risk is strictly bounded below 5% is **highly fragile** and sensitive to the confidence interval method used.

---

## 4. Per-Scenario vs. Pooled Risk Analysis (Section 10)

The table below breaks down AEGIS-Next performance across each of the 10 scenarios (50 episodes each):

| Scenario | Evaluated Episodes | True Success | False Success | Abstain | Accepted Decisions | Task Coverage Rate | Scenario Covered Risk ($FS / \text{Cov}$) | 95% Wilson Score CI |
|---|---|---|---|---|---|---|---|---|
| `NOMINAL` | 50 | 50 | 0 | 0 | 50 | 100.0% | **0.0%** (0/50) | [0.000, 0.071] |
| `SENSOR_DROPOUT` | 50 | 50 | 0 | 0 | 50 | 100.0% | **0.0%** (0/50) | [0.000, 0.071] |
| `OUTLIER_BURSTS` | 50 | 48 | 0 | 2 | 48 | 96.0% | **0.0%** (0/48) | [0.000, 0.074] |
| `CORRELATED_BIAS` | 50 | 37 | 0 | 13 | 37 | 74.0% | **0.0%** (0/37) | [0.000, 0.094] |
| `INDEPENDENT_BIAS` | 50 | 28 | 4 | 18 | 32 | 64.0% | **12.5%** (4/32) | **[0.0496, 0.279]** |
| `SENSOR_DRIFT` | 50 | 19 | 0 | 31 | 19 | 38.0% | **0.0%** (0/19) | [0.000, 0.168] |
| `PRIMARY_BIAS` | 50 | 17 | 0 | 33 | 17 | 34.0% | **0.0%** (0/17) | [0.000, 0.184] |
| `COMPOUND_HOLDOUT_EXTREME` | 50 | 1 | 2 | 47 | 3 | 6.0% | **66.7%** (2/3) | **[0.208, 0.939]** |
| `CORRUPTED_ANCHOR_STRESS` | 50 | 1 | 0 | 49 | 1 | 2.0% | **0.0%** (0/1) | [0.000, 0.793] |
| `FAULTY_REFERENCE_SENSOR` | 50 | 0 | 0 | 50 | 0 | 0.0% | **undefined** (0/0) | undefined |

### Critical Scientific Insights:
1. **Worst-Performing Scenario:** `COMPOUND_HOLDOUT_EXTREME`. The robot attempted 3 landings and suffered 2 false successes, resulting in a selective risk of **$66.7\%$** ($95\%$ Wilson CI $[0.208, 0.939]$).
2. **Second Failure Scenario:** `INDEPENDENT_BIAS`. AEGIS-Next accepted 32 decisions and suffered 4 false successes, resulting in **$12.5\%$ Covered Risk** ($95\%$ Wilson CI $[0.0496, 0.279]$).
3. **Lowest Coverage Scenario:** `FAULTY_REFERENCE_SENSOR`. Zero decisions were accepted (100% safe abstention). Covered risk is undefined.
4. **Origin of the Low Pooled Risk:** The pooled risk of 2.33% is dominated by the benign scenarios (`NOMINAL`, `SENSOR_DROPOUT`, `OUTLIER_BURSTS`, `CORRELATED_BIAS`), which contributed 185 out of the 257 accepted decisions (72.0% of the sample) with 0 false successes.
5. **Scientific Verdict:** The claim of "5% risk control" does **not** hold uniformly across scenarios. It holds only as an empirical weighted average under the specific 10-scenario mixture evaluated.
