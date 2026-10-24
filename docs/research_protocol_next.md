# NEXVIA AEGIS — Pre-Registered Experimental Protocol (AEGIS-Next / V8)
**Document:** Formal Scientific Protocol, Hypotheses, Baselines, Fault Taxonomy, and Statistical Methodology  
**Author / Roles:** Principal Robotics Research Scientist, Experimental-Methodology Auditor  
**Date:** October 2026  
**Status:** Pre-Registered (Frozen Prior to Final Benchmark Execution)  

---

## 1. Protocol Objective and Scope

This document specifies the frozen experimental protocol for evaluating **AEGIS-Next (V8: Sequential Risk-Calibrated Runtime Assurance and Event-Triggered Recovery)** against an extensive suite of established classical, statistical, and architectural baselines.

The protocol enforces:
1. **Strict separation** of development tuning parameters from final held-out evaluation distributions.
2. **Ground-truth isolation** during online execution.
3. **Matched initial condition seeds** while correctly logging policy-divergent observation sequences.
4. **Unambiguous metric definitions** with explicitly declared numerators and denominators.
5. **Pre-registered statistical tests** and confidence intervals.

---

## 2. Formal Hypotheses to be Tested

### Hypothesis 1 ($H_1$): Rigorous Selective Risk Bounding
- **Claim:** Under both stationary and non-stationary sensor corruptions, the anytime-valid sequential martingale monitor guarantees that the empirical Covered Risk satisfies:
  $$R_{\text{cov}} = \frac{FS}{TS + FS} \le \alpha_{\text{target}} = 0.05 \quad (5.0\%)$$
  with 95% confidence, whereas classical innovation chi-square gating and unshielded estimation violate this bound ($R_{\text{cov}} > 10.0\%$).
- **Falsification Condition:** If $R_{\text{cov}}$ exceeds $0.05$ with lower Wilson confidence bound $> 0.05$ across the aggregate benchmark, $H_1$ is rejected.

### Hypothesis 2 ($H_2$): Anchoring Resource Efficiency
- **Claim:** Martingale-gated event-triggered anchor scheduling achieves a $\ge 50\%$ reduction in mean anchor query cost relative to unconditional (always-on) querying ($C_{\text{mean}} \le 0.125$ vs. $0.250$), while suffering no statistically significant loss in True Success (two-sided McNemar's test $p \ge 0.05$).
- **Falsification Condition:** If query cost reduction is $< 50\%$ or True Success drops by $> 3.0\%$ absolute margin, $H_2$ is rejected.

### Hypothesis 3 ($H_3$): Resolution of the V7 Dynamics-Timeout Bottleneck
- **Claim:** Replacing the over-damped approach law with a continuous velocity-profile controller with critical damping ($k_v = 0.50$) increases True Success by $\ge 8.0\%$ absolute margin over AEGIS V7 Full across the benchmark suite, while maintaining mean maximum overshoot below $0.015\text{ m}$.
- **Falsification Condition:** If True Success gain is $< 8.0\%$ or mean overshoot exceeds $0.015\text{ m}$, $H_3$ is rejected.

---

## 3. Baseline Suite (8 Competing Architectures)

To ensure a fair, rigorous, and competitive evaluation, the benchmark tests eight distinct policy architectures under identical task conditions:

| ID | Policy Identifier | Architecture & Description | Monitoring / Gating Principle | Recovery & Action |
| :--- | :--- | :--- | :--- | :--- |
| **B1** | `UNSHIELDED_ALWAYS_ACT` | Naive proportional pursuit using inverse-variance fused vector sensors | None. Blindly trusts sensor measurements | Direct approach; stops when estimated distance $\le 0.25\text{ m}$ |
| **B2** | `CHISQUARE_NIS_GATING` | Classical innovation residual monitoring (Mehra & Peschon, 1971; Willsky, 1976) | Normalized Innovation Squared (NIS): $\mathbf{r}_t^T \mathbf{S}_t^{-1} \mathbf{r}_t > \chi_{2, 0.95}^2$ | Halts/abstains upon chi-square innovation breach |
| **B3** | `EKF_CONSISTENCY_MONITOR` | Extended Kalman Filter with online covariance consistency check | Mahalanobis state-estimation residual gating | Switches to open-loop emergency braking if residual exceeds $3\sigma$ |
| **B4** | `AEGIS_V4_PASSIVE_VERIFY` | Passive geometric cross-modal verification (AEGIS V4) | Geometric bound: $\left| \|\mathbf{z}_v\| - r \right| > \tau_{\text{geom}}$ | Safe `ABSTAIN` (zero recalibration, zero anchor) |
| **B5** | `AEGIS_V5_HUBER_CALIBRATE`| Online Huber M-estimation with fixed orthogonal probing (AEGIS V5) | FIM condition number $\kappa(\mathbf{F}) \le 40$ & held-out validation gate | Fixed 2-phase open-loop probing $\to$ Huber recalibration $\to$ Approach |
| **B6** | `AEGIS_V6_DISCRIMINATIVE` | Multi-hypothesis diagnosis ($H_0$–$H_6$) with hypothesis-directed probing | Bayesian posterior likelihoods and Shannon entropy $\mathcal{H} > 1.45\text{ nats}$ | Hypothesis-discriminative probing; abstains on $H_4$ |
| **B7** | `AEGIS_V7_MPC_BASELINE` | Risk-constrained pseudo-MPC with on-demand anchor (AEGIS V7) | Heuristic mismatch counter + Anchor Integrity Gate | Heuristic pseudo-MPC approach with terminal damping |
| **V8** | `AEGIS_NEXT_MARTINGALE` | **Proposed Method:** Anytime-valid sequential martingale monitor + Event-triggered anchor | Non-negative betting supermartingale $E_t \ge 1/\alpha$ + entropy trigger | Calibrated velocity-profile approach; martingale-gated anchor |

---

## 4. Fault Taxonomy and Scenario Catalog (10 Scenarios)

The evaluation suite tests ten scenarios spanning nominal noise, isolated sensor faults, non-stationary temporal degradation, multi-sensor common-mode attacks, and unannounced held-out regimes:

### 4.1 Development Scenarios (Tuning and Parameter Selection)
1. **`NOMINAL`**: Zero-mean Gaussian noise on all sensors ($\sigma_v = 0.05\text{ m}$, $\sigma_r = 0.05\text{ m}$). Fault label: $H_0$.
2. **`PRIMARY_BIAS`**: Static spatial bias on primary sensor A ($\mathbf{b}_A = [+0.8, -0.6]\text{ m}$), sensor B nominal. Fault label: $H_1$.
3. **`INDEPENDENT_BIAS`**: Independent non-identical biases on vector sensor A ($\mathbf{b}_A = [+0.6, +0.4]\text{ m}$) and sensor B ($\mathbf{b}_B = [-0.5, +0.5]\text{ m}$). Fault label: $H_1$.
4. **`CORRELATED_BIAS`**: Identical common-mode spatial bias on both vector sensors ($\mathbf{b}_A = \mathbf{b}_B = [+0.7, +0.7]\text{ m}$), range sensor nominal. Fault label: $H_4$ (algebraically unidentifiable without anchor).

### 4.2 Stress and Degradation Scenarios
5. **`SENSOR_DRIFT`**: Non-stationary dynamic drift on sensor A ($\dot{\mathbf{b}} = [0.003, 0.0015]\text{ m/step}$), sensor B nominal. Fault label: $H_2$.
6. **`OUTLIER_BURSTS`**: Heavy-tailed noise with random outlier bursts ($p = 0.12$, scale factor $4.5\times$). Fault label: $H_1$/$H_6$.
7. **`SENSOR_DROPOUT`**: Intermittent complete hardware packet loss ($p = 0.40$) on sensor A, sensor B nominal. Fault label: $H_5$.
8. **`FAULTY_REFERENCE_SENSOR`**: Correlated vector bias ($\mathbf{b}_v = [+0.7, +0.7]\text{ m}$) AND range sensor bias ($b_r = +1.0\text{ m}$). Fault label: $H_3$.

### 4.3 Adversarial and Certified Held-Out Scenarios (Zero Development Tuning)
9. **`CORRUPTED_ANCHOR_STRESS`**: Correlated vector bias ($\mathbf{b}_v = [+0.7, +0.7]\text{ m}$) AND anchor sensor maliciously spoofed ($\mathbf{b}_{\text{anchor}} = [+1.2, -1.0]\text{ m}$). Tests Anchor Integrity Gate.
10. **`COMPOUND_HOLDOUT_EXTREME`**: Held-out compound stress scenario:
    - Non-stationary drift on vector A ($\dot{\mathbf{b}} = [0.002, 0.002]\text{ m/step}$)
    - Heavy-tailed Student-$t$ noise (degrees of freedom $\nu = 3$)
    - Scalar range sensor calibration shift ($b_r = -0.40\text{ m}$)
    - Initial spatial separation $3.5\text{ m}$ (outside nominal $2.8\text{ m}$ range).

---

## 5. Explicit Metric Definitions and Denominators

Every recorded metric possesses an explicit mathematical definition and denominator:

1. **True Success Rate ($TS$):**
   $$\text{TS Rate} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Decision}_i = \text{STOP} \land \|\mathbf{p}_i - \mathbf{p}^*\| \le 0.45)}{N}$$
   Denominator: Total episodes $N = 50$ per scenario-policy pair.

2. **False Success Rate ($FS$):**
   $$\text{FS Rate} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Decision}_i = \text{STOP} \land \|\mathbf{p}_i - \mathbf{p}^*\| > 0.45)}{N}$$
   Denominator: Total episodes $N = 50$.

3. **Task Coverage Rate ($\text{Cov}$):**
   $$\text{Coverage Rate} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Decision}_i = \text{STOP})}{N} = \text{TS Rate} + \text{FS Rate}$$
   Denominator: Total episodes $N = 50$.

4. **Abstention Rate ($Abs$):**
   $$\text{Abstention Rate} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Decision}_i = \text{ABSTAIN})}{N}$$
   Denominator: Total episodes $N = 50$. Note: $\text{Coverage} + \text{Abstention} = 1.0$.

5. **Covered Risk ($R_{\text{cov}}$):**
   $$R_{\text{cov}} = \begin{cases} \frac{\text{FS Count}}{\text{TS Count} + \text{FS Count}}, & \text{if } \text{TS Count} + \text{FS Count} > 0 \\ \text{Undefined (reported as 0.0 with 0% coverage)}, & \text{otherwise} \end{cases}$$
   Denominator: Number of accepted decisions ($\text{TS} + \text{FS}$).

6. **Anchor Query Cost ($C_{\text{anchor}}$):**
   $$C_{\text{anchor}} = \frac{1}{N} \sum_{i=1}^N \left( \sum_{t=1}^{T_i} c_{\text{query}} \mathbb{I}(\text{Query}_t = \text{True}) \right), \quad c_{\text{query}} = 0.05$$

7. **Mean Maximum Target Overshoot ($O_{\max}$):**
   $$O_{\max} = \frac{1}{N} \sum_{i=1}^N \max\left(0, \sup_{t \ge t_{\text{approach}}} (\|\mathbf{p}_t - \mathbf{p}^*\| - \inf_{s \le t} \|\mathbf{p}_s - \mathbf{p}^*\|)\right)$$
   Evaluated along the trajectory when minimum reached distance is $\le 0.50\text{ m}$.

8. **Mean Bias Estimation Error ($E_{\text{bias}}$):**
   $$E_{\text{bias}} = \frac{1}{N_{\text{cal}}} \sum_{i \in \text{Calibrated}} \|\hat{\mathbf{b}}_i - \mathbf{b}^*\|_2$$
   Denominator: Number of calibrated episodes $N_{\text{cal}}$.

---

## 6. Execution Protocol and Statistical Reporting

1. **Scale:** 10 scenarios $\times$ 8 policies $\times$ 50 matched episodes = **4,000 total policy-episodes**.
2. **Seed Determinism:**
   - Base evaluation seed: `seed_base = 60000`.
   - Episode $i$ uses `seed = 60000 + i` across all 8 policies.
   - Sensor noise streams are seeded deterministically per episode.
3. **Statistical Analysis:**
   - Binomial 95% confidence intervals computed via **Wilson score interval** without continuity correction.
   - Pairwise binary comparison between policies evaluated using **McNemar's exact test** for paired nominal data.
   - Continuous metric distributions (steps, overshoot, anchor cost) tested using two-sided **Mann-Whitney U tests**.
4. **Artifact Storage:**
   - Raw episode-level CSV: `results/next/benchmark_episodes.csv` (4,000 rows).
   - Scenario aggregate summary: `results/next/benchmark_summary.csv` (80 rows).
   - Publication figures (300 DPI): `results/next/figures/`.
