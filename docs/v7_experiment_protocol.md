# NEXVIA AEGIS V7.0 — Experimental Protocol
**Evaluation Framework:** Risk-Constrained Model Predictive Control and Intermittent Independent Sensor Anchoring  
**Document:** Official Research Benchmark & Evaluation Protocol  
**Scale:** 10 Scenarios $\times$ 6 Policies $\times$ 50 Matched Seeds = 3,000 Main Benchmark Episodes (+ 2,000 Ablation Runs)  

---

## 1. Research Questions & Hypotheses

The V7.0 experimental campaign evaluates five formal scientific hypotheses:

### Hypothesis H1 — Predictive Control Improves Physical Feasibility
*By explicitly accounting for predictive momentum dynamics and imposing a terminal velocity braking penalty ($w_{\text{term}} \|\mathbf{v}_N\|^2$), risk-constrained MPC reduces physical overshoot, terminal velocity at the transition point, and post-calibration residual aborts compared with V6 open-loop probing under identical initial conditions.*

### Hypothesis H2 — Hypothesis-Aware MPC Improves Diagnosis
*An MPC trajectory objective tailored to separate candidate sensor-fault hypotheses ($H_1$ constant bias vs. $H_2$ non-stationary drift) achieves lower bias-estimation error and higher recovery success than a purely geometric FIM-maximizing MPC planner.*

### Hypothesis H3 — Intermittent Independent Anchoring Resolves Common-Mode Ambiguity
*In the presence of correlated common-mode vector sensor bias ($H_4$) where two-sensor geometry is algebraically unidentifiable, querying an independent 3rd observation modality (AEGIS-Anchor) breaks fault symmetry and enables recovery with $0.0\%$ false-success risk.*

### Hypothesis H4 — Risk-Constrained Recovery Improves Operational Performance
*The full V7 architecture (Policy C: MPC with On-Demand Anchor) improves overall task success and coverage across the 10-scenario benchmark relative to V6 Baseline without exceeding predefined false-success risk thresholds ($R_{\text{cov}} \le 10\%$).*

### Hypothesis H5 — Event-Triggered Anchoring Outperforms Unconditional Anchoring
*An event-triggered query policy that calls the anchor sensor only under high diagnostic entropy ($\mathcal{H} > 1.0$) or persistent unresolvable mismatch reduces anchor query costs by $\ge 70\%$ while achieving statistically indistinguishable recovery success from an unconditional always-on anchor.*

---

## 2. Benchmark Comparison Policies

| Identifier | Policy Name | Motion Control | Sensing Modalities | Anchor Query Schedule |
| :--- | :--- | :--- | :--- | :--- |
| **Policy A** | `AEGIS_V6_BASELINE` | Open-loop Probing + Damping | Vector A, Vector B, Range | No Anchor (V6 Reference) |
| **Policy B** | `AEGIS_V7_MPC_NO_ANCHOR` | Receding-Horizon MPC ($N=5$) | Vector A, Vector B, Range | No Anchor |
| **Policy C** | `AEGIS_V7_MPC_ON_DEMAND` | Receding-Horizon MPC ($N=5$) | Vector A, Vector B, Range, Anchor | Event-Triggered ($\mathcal{H} > 1.0$, $H_4$ suspicion) |
| **Policy D** | `AEGIS_V7_MPC_ALWAYS_ON` | Receding-Horizon MPC ($N=5$) | Vector A, Vector B, Range, Anchor | Unconditional (Every Probing Step) |
| **Policy E** | `AEGIS_V7_MPC_GENERIC_FIM` | Receding-Horizon MPC ($N=5$) | Vector A, Vector B, Range, Anchor | Event-Triggered (Generic FIM Objective) |
| **Policy F** | `AEGIS_V7_MPC_FIXED_PROBE` | Receding-Horizon MPC ($N=5$) | Vector A, Vector B, Range, Anchor | Event-Triggered (Fixed Orthogonal Pattern) |

---

## 3. Evaluated Scenarios (10 Scenarios)

1. **`NOMINAL`:** Baseline operation under Gaussian sensor noise ($\sigma = 0.05\text{ m}$).
2. **`PRIMARY_BIAS`:** Static spatial bias on primary sensor A ($\mathbf{b}_a = [+0.8, -0.6]^T\text{ m}$).
3. **`INDEPENDENT_BIAS`:** Independent distinct biases on sensor A ($[+0.6, +0.4]^T$) and B ($[-0.5, +0.5]^T$).
4. **`CORRELATED_BIAS`:** Common-mode correlated bias ($[+0.7, +0.7]^T$) on both vector sensors. *Key test for Anchor Hypothesis H3.*
5. **`SENSOR_DRIFT`:** Progressive non-stationary drift ($0.003 \cdot t, 0.0015 \cdot t$) on primary sensor A.
6. **`OUTLIER_BURSTS`:** 15% heavy-tail Cauchy outlier bursts (scale = 6.0) on vector sensor A.
7. **`SENSOR_DROPOUT`:** 20% intermittent packet dropout on vector sensors.
8. **`COMPOUND_HOLDOUT`:** Correlated bias ($[+0.5, +0.5]^T$) + drift + 10% outliers.
9. **`FAULTY_REFERENCE_SENSOR`:** Correlated vector bias AND range sensor corrupted ($+1.0\text{ m}$ bias).
10. **`CORRUPTED_ANCHOR_STRESS`:** Correlated vector bias + corrupted anchor ($+1.2\text{ m}$ bias). *Verifies Anchor Integrity Gate.*

---

## 4. Formal Research Metric Definitions

### 4.1 Decision & Task Performance
- **True Success ($S$):** Agent issues `STOP` and true physical distance to target satisfies $\|\mathbf{p}^* - \mathbf{p}_{\text{final}}\| \le 0.45\text{ m}$.
  $$\text{True Success Rate} = \frac{S}{N_{\text{total}}}$$
- **False Success ($F$):** Agent issues `STOP` when true physical distance to target $\|\mathbf{p}^* - \mathbf{p}_{\text{final}}\| > 0.45\text{ m}$.
  $$\text{False Success Rate} = \frac{F}{N_{\text{total}}}$$
- **Task Coverage ($C$):** Fraction of episodes where the agent makes an affirmative terminal commitment:
  $$\text{Coverage Rate} = \frac{S + F}{N_{\text{total}}}$$
- **Covered Risk ($R_{\text{cov}}$):** False-success risk conditioned on making an affirmative decision:
  $$R_{\text{cov}} = \begin{cases} \frac{F}{S + F} & \text{if } S + F > 0 \\ \text{N/A} & \text{if } S + F = 0 \end{cases}$$
- **Safe Abstention ($A$):** Agent transitions to `ABSTAIN` or halts when evidence is insufficient or unresolvable:
  $$\text{Abstention Rate} = \frac{A}{N_{\text{total}}} = 1.0 - \text{Coverage Rate}$$

### 4.2 Dynamic & Physical Metrics
- **Overshoot Distance ($d_{\text{over}}$):** Maximum distance overshoot beyond target radius during or immediately following probing:
  $$d_{\text{over}} = \max_{t \ge t_{\text{probe}}} \|\mathbf{p}_t - \mathbf{p}^*\| - R_{\text{target}}$$
- **Terminal Velocity at Probing Completion ($v_{\text{term}}$):** Velocity magnitude $\|\mathbf{v}_{t_{\text{probe}}}\|$ at the transition from probing to calibrated navigation.
- **Mean Episode Steps:** Average simulation steps to completion.

### 4.3 Diagnostic & Anchoring Metrics
- **Mean Bias Error:** Average Euclidean error $\|\hat{\mathbf{b}} - \mathbf{b}^*\|$ against ground truth (offline evaluation only).
- **Diagnostic Entropy ($\mathcal{H}$):** Shannon entropy of hypothesis posterior distribution $\mathcal{H} = -\sum P(H_k) \ln P(H_k)$.
- **Anchor Query Count ($N_{\text{queries}}$):** Total number of queries sent to the anchor sensor.
- **Anchor Query Cost ($C_{\text{anchor}}$):** Accumulated query overhead: $C_{\text{anchor}} = N_{\text{queries}} \times C_{\text{query}}$ ($C_{\text{query}} = 0.05$).

---

## 5. Statistical Rigor Protocol

1. **Seed Matching:** Every scenario runs 50 matched seeds ($57000$ to $57049$). In each matched seed, the target location, sensor noise realization, fault onset, and disturbance sequence are identically generated.
2. **Confidence Intervals:** All binomial proportions ($S/N$, $F/N$, $C/N$) are reported with exact 95% Wilson Score intervals:
   $$\text{CI}_{95\%} = \frac{\hat{p} + \frac{z^2}{2N} \pm z \sqrt{\frac{\hat{p}(1-\hat{p})}{N} + \frac{z^2}{4N^2}}}{1 + \frac{z^2}{N}}, \quad z = 1.95996$$
3. **Continuous Uncertainty:** Continuous metrics (Mean Steps, Bias Error, Overshoot) are reported with sample means and standard errors.
