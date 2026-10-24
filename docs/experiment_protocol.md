# NEXVIA AEGIS — Research Experiment Protocol (V4.0)

**Project:** NEXVIA AEGIS — Fault-Tolerant Decision Layer for Physical AI  
**Author:** Autonomous Systems & Robotics Research Group  
**Date:** October 16, 2026  
**Document Status:** Approved Research Specification  

---

## 1. Research Objectives & Hypotheses

### 1.1 Central Research Question
Can an autonomous decision layer combining intra-modal sensor arbitration, independent cross-modal verification, and risk-aware abstention eliminate catastrophic false-success decisions under sensor distribution shift and common-mode sensor faults, while preserving operational efficiency?

### 1.2 Formal Hypotheses
- **H1 (Primary — False-Success Reduction):** Under sensor distribution shifts (including bias, drift, outliers, and dropouts), the full AEGIS architecture achieves a significantly lower false-success rate than Always Act and Sensor Fusion baselines ($p < 0.001$, paired test), while maintaining positive task completion on nominal and recoverable scenarios.
- **H2 (Cross-Modal Disentanglement):** Under **correlated common-mode faults** (where both 2D vector sensors share an identical bias), intra-modal sensor arbitration fails (producing near-zero disagreement), whereas cross-modal scalar range verification detects geometric discrepancy ($\Delta_{\text{cross}} = \left| \|\hat{v}\| - r \right|$), reducing false-success to zero via safe abstention.
- **H3 (Ablation Value of Abstention):** Removing the abstention option (forcing action under unresolved uncertainty) converts unverified episodes directly into false-success events, demonstrating that abstention is a strictly necessary component of safety under partial observability.
- **H4 (Risk–Coverage Dominance):** Across confidence thresholds, AEGIS demonstrates a superior risk–coverage profile (lower covered risk at any given coverage level) compared to fixed-rule policies.

---

## 2. Benchmark Environment & Physical Task

### 2.1 Physics Engine & Substrate
All evaluations in the V4 protocol are conducted in the **MuJoCo physical simulation** (`AegisPhysicalWorld`, `src/aegis/v3/env/world.py`):
- **Agent:** Point-mass robot ($m = 1.0\text{ kg}$, $r = 0.20\text{ m}$) moving in a bounded 2D arena ($6.0\text{ m} \times 6.0\text{ m}$).
- **Actuation:** 2D continuous force control $F \in [-1.0, 1.0]^2\text{ N}$, simulation timestep $dt = 0.02\text{ s}$.
- **Target Distribution:** Hidden target placed uniformly within $[-2.0, 2.0]^2\text{ m}$ relative to origin. Initial distance $d_0 \approx 2.5 - 4.5\text{ m}$.
- **Success Radius:** $r_{\text{success}} = 0.25\text{ m}$.
- **Max Steps:** $T_{\max} = 300$ steps per episode.

### 2.2 Sensor Modalities Available to Agent
The agent never observes ground-truth coordinates ($x_{\text{robot}}, y_{\text{robot}}, x_{\text{target}}, y_{\text{target}}$). It only receives:
1. **Vector Sensor A (Primary 2D):** $\mathbf{z}_A = \Delta\mathbf{p}_{\text{true}} + \mathbf{b}_A + \mathbf{d}_A(t) + \boldsymbol{\epsilon}_A$, where $\boldsymbol{\epsilon}_A \sim \mathcal{N}(0, \sigma_A^2 \mathbf{I})$.
2. **Vector Sensor B (Secondary 2D):** $\mathbf{z}_B = \Delta\mathbf{p}_{\text{true}} + \mathbf{b}_B + \mathbf{d}_B(t) + \boldsymbol{\epsilon}_B$, where $\boldsymbol{\epsilon}_B \sim \mathcal{N}(0, \sigma_B^2 \mathbf{I})$.
3. **Range Sensor C (Cross-Modal 1D):** Scalar distance measurement $r = \|\Delta\mathbf{p}_{\text{true}}\| + \epsilon_r$, where $\epsilon_r \sim \mathcal{N}(0, \sigma_r^2)$.

---

## 3. Evaluated Policy Variants

To evaluate H1–H3 fairly, five matched policies are tested on the exact same physical world and sensor streams:

### Policy 1: Always Act (`ALWAYS_ACT`)
- **Logic:** Direct navigation along the primary sensor reading $\mathbf{z}_A$. Issues maximum force towards $\mathbf{z}_A$.
- **Stopping Rule:** Declares task complete when $\|\mathbf{z}_A\| \le r_{\text{success}}$.
- **Abstention:** None. Always commits to action.

### Policy 2: Dual Sensor Fusion Only (`FUSION_ONLY`)
- **Logic:** Computes standard inverse-variance weighted fusion of $\mathbf{z}_A$ and $\mathbf{z}_B$:
  $$\mathbf{z}_{\text{fused}} = \frac{\sigma_A^{-2}\mathbf{z}_A + \sigma_B^{-2}\mathbf{z}_B}{\sigma_A^{-2} + \sigma_B^{-2}}$$
- **Stopping Rule:** Declares task complete when $\|\mathbf{z}_{\text{fused}}\| \le r_{\text{success}}$.
- **Abstention:** None. Continues moving towards $\mathbf{z}_{\text{fused}}$ regardless of disagreement.

### Policy 3: AEGIS Intra-Modal Ablation (`AEGIS_NO_CROSS_MODAL`)
- **Logic:** Employs sensor arbitration between $\mathbf{z}_A$ and $\mathbf{z}_B$. Disagreement threshold $\delta_{\text{max}} = 0.35\text{ m}$. Abstains if $\|\mathbf{z}_A - \mathbf{z}_B\| > \delta_{\text{max}}$.
- **Ablation:** Deliberately disables the scalar `RangeSensor`. Checks only intra-modal vector consistency.

### Policy 4: AEGIS No-Abstention Ablation (`AEGIS_NO_ABSTAIN`)
- **Logic:** Full multi-modal verification (vector + range). However, if an irreconcilable fault or mismatch is detected, the agent is forced to act on the highest-confidence measurement rather than abstaining.
- **Ablation:** Measures whether verification without abstention provides safety.

### Policy 5: AEGIS Full Architecture (`AEGIS_FULL`)
- **Logic:** Complete unified verification layer (`VerificationController`):
  1. Computes intra-modal vector disagreement $\delta_{\text{vector}} = \|\mathbf{z}_A - \mathbf{z}_B\|$.
  2. Computes cross-modal geometric discrepancy $\delta_{\text{cross}} = \left| \|\mathbf{z}_{\text{fused}}\| - r \right|$.
  3. Fuses confidence from both checks: $c = c_{\text{vector}} \times c_{\text{cross}}$.
  4. Actions: `ACT` when verified and safe; `VERIFY` (hold position to filter transients); `ABSTAIN` (safe stop when cross-mismatch persists); `RECOVER` (probing retreat when progress stalls).

---

## 4. Fault and Distribution-Shift Protocols

The benchmark evaluates 8 distinct experimental scenarios:

| ID | Scenario Name | Description | Mathematical Fault Model |
| :--- | :--- | :--- | :--- |
| **S1** | `NOMINAL` | Standard operating conditions | $\sigma_A = \sigma_B = \sigma_r = 0.05\text{ m}$, zero bias, zero drift. |
| **S2** | `PRIMARY_BIAS` | Independent fault on Sensor A | $\mathbf{b}_A = (+0.7, +0.7)\text{ m}$, $\mathbf{b}_B = (0, 0)$, $b_r = 0$. |
| **S3** | `INDEPENDENT_BIAS` | Distinct faults on both vector sensors | $\mathbf{b}_A = (+0.6, +0.4)\text{ m}$, $\mathbf{b}_B = (-0.5, +0.5)\text{ m}$, $b_r = 0$. |
| **S4** | `CORRELATED_BIAS` | **Common-mode fault (both sensors share bias)** | $\mathbf{b}_A = \mathbf{b}_B = (+0.7, +0.7)\text{ m}$, $b_r = 0$. |
| **S5** | `SENSOR_DRIFT` | Progressive calibration degradation | $\mathbf{d}_A(t) = (0.003\cdot t, 0.0015\cdot t)\text{ m}$, Sensor B nominal. |
| **S6** | `OUTLIER_BURSTS` | Heavy-tailed transient spikes | $p_{\text{outlier}} = 0.15$, scale $= 6.0 \times \sigma$. |
| **S7** | `SENSOR_DROPOUT` | Intermittent packet loss | $p_{\text{drop}} = 0.20$ independently on vector streams. |
| **S8** | `COMPOUND_HOLDOUT` | **Unseen compound stress test** | Correlated bias $(+0.5, +0.5) + \text{drift} + \text{outliers}$. |

---

## 5. Metric Formulations

### 5.1 Primary Metric: False-Success Rate ($FSR$)
An episode is a **False Success** if the agent declares/commits to task completion (stopping near its belief target), but ground-truth distance is greater than the success radius ($d_{\text{true}} > r_{\text{success}}$):
$$FSR = \frac{\sum_{i=1}^N \mathbb{I}(\text{Declared Complete}_i \land d_{\text{true}, i} > r_{\text{success}})}{N_{\text{total}}}$$

### 5.2 Task Success Rate ($TSR$)
True ground-truth task completion:
$$TSR = \frac{\sum_{i=1}^N \mathbb{I}(d_{\text{true}, i} \le r_{\text{success}})}{N_{\text{total}}}$$

### 5.3 Abstention Rate ($AR$) & Operational Coverage ($Cov$)
$$AR = \frac{\sum_{i=1}^N \mathbb{I}(\text{Abstained}_i)}{N_{\text{total}}}, \quad Cov = 1 - AR$$

### 5.4 Covered Risk ($Risk_{\text{covered}}$)
The probability of a false success among the episodes where the agent decided to act:
$$Risk_{\text{covered}} = \frac{FSR}{Cov} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Declared Complete}_i \land d_{\text{true}, i} > r_{\text{success}})}{\sum_{i=1}^N \mathbb{I}(\text{Action Taken}_i)}$$

### 5.5 Operational Efficiency & Step Cost
$$\bar{T} = \frac{1}{N}\sum_{i=1}^N T_i, \quad \bar{d}_{\text{final}} = \frac{1}{N}\sum_{i=1}^N d_{\text{true}, i}^{\text{final}}$$

---

## 6. Random-Seed Protocol and Statistical Significance

- **Matched Episode Design:** For each scenario, episode $k$ is initialized with seed $S_k = \text{base\_seed} + k$.
- Target placement, initial velocity, external disturbances, and sensor noise realization for episode $k$ are strictly identical across all 5 evaluated policies.
- **Sample Budget:** 50 episodes per policy per scenario across 8 scenarios = 400 episodes per policy (Total 2,000 rigorous physical simulation runs).
- **Statistical Testing:** 
  - Binomial 95% Wilson score confidence intervals for all rates.
  - Paired McNemar tests for false-success differences between AEGIS and baselines.
