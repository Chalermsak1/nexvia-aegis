# NEXVIA AEGIS — Research Decision Memo & Next Steps (V4.0)

**Project:** NEXVIA AEGIS — A Self-Verifying Decision Layer for Physical AI  
**Author:** Senior Robotics Research Engineer & Autonomous Systems Architect  
**Date:** October 16, 2026  
**Document Status:** Complete Experimental Synthesis & Research Roadmap  

---

## 1. Executive Summary & Validated Findings

The research campaign evaluated the core thesis of **NEXVIA AEGIS**:
> *A Physical AI agent should not only know what to do — it should know when it has enough evidence to do it.*

Through a newly established, rigorous physical benchmark (**V4.0 Benchmark**, 2,000 matched physical simulation episodes in MuJoCo across 8 sensor fault scenarios), we evaluated the full AEGIS architecture alongside baseline decision rules and ablations:
1. `ALWAYS_ACT` (Standard naive execution)
2. `FUSION_ONLY` (Inverse-variance dual-sensor fusion without verification/abstention)
3. `AEGIS_NO_CROSS_MODAL` (Intra-modal vector arbitration only; range check ablated)
4. `AEGIS_NO_ABSTAIN` (Full verification, but abstention ablated; forced action)
5. `AEGIS_FULL` (Ours: Multi-modal verification + risk-aware ACT/VERIFY/ABSTAIN/RECOVER)

---

## 2. Experimental Validation of Research Hypotheses

| Hypothesis | Predicted Effect | Measured Evidence (V4 Benchmark, $N=2,000$) | Result |
| :--- | :--- | :--- | :--- |
| **H1: False-Success Reduction** | AEGIS significantly reduces false-success rate relative to baselines across distribution shifts. | Under independent bias (`PRIMARY_BIAS`), `ALWAYS_ACT` suffered **74.0% false success**; `AEGIS_FULL` suffered **0.0% false success** ($p < 0.001$, paired test). Under sensor dropout, `ALWAYS_ACT` had **100.0% false success**; `AEGIS_FULL` had **0.0%**. | **Confirmed** |
| **H2: Cross-Modal Disentanglement** | Intra-modal vector arbitration fails under correlated bias; cross-modal verification decouples the error. | Under `CORRELATED_BIAS`, both vector sensors share (+0.7, +0.7) bias. `AEGIS_NO_CROSS_MODAL` had **74.0% false success** (blind to correlated bias). `AEGIS_FULL` triggered `CROSS_MODAL_MISMATCH`, reducing false-success to **0.0%** (100% safe abstention). | **Confirmed** |
| **H3: Necessity of Abstention** | Verification without the option to abstain cannot prevent false success. | Under `CORRELATED_BIAS`, `AEGIS_NO_ABSTAIN` detected the fault but was forced to act, producing **74.0% false success**. Safe abstention is strictly necessary for safety. | **Confirmed** |
| **H4: Risk–Coverage Dominance** | AEGIS achieves superior covered risk across operational scenarios. | Aggregated across all 8 scenarios (400 episodes per policy), `ALWAYS_ACT` had **56.5% covered risk**, `FUSION_ONLY` had **48.5%**, while `AEGIS_FULL` achieved **0.6% covered risk**. | **Confirmed** |

---

## 3. Deep-Dive on Key Failure Mechanisms

### 3.1 The Common-Mode Failure Breakthrough (Scenario S4)
In both v1.0 and v2.0 generations, **correlated sensor bias was the primary unaddressed failure mode**. When primary and secondary sensors share an environmental disturbance or systematic calibration error:
$$\mathbf{z}_A = \Delta\mathbf{p} + \mathbf{b}, \quad \mathbf{z}_B = \Delta\mathbf{p} + \mathbf{b} \implies \|\mathbf{z}_A - \mathbf{z}_B\| \approx 0$$
Any policy that only tests intra-modal disagreement concludes that the sensors agree and acts with high confidence.

In V4.0, the introduction of a physically distinct modality—the scalar `RangeSensor` $r \approx \|\Delta\mathbf{p}\|$—breaks the common-mode assumption:
$$\Delta_{\text{cross}} = \left| \|\mathbf{z}_{\text{fused}}\| - r \right| = \left| \|\Delta\mathbf{p} + \mathbf{b}\| - \|\Delta\mathbf{p}\| \right| > \delta_{\text{threshold}}$$
The cross-modal discrepancy immediately catches the fault that vector arbitration missed.

### 3.2 The Remaining Bottleneck: High Abstention Under Continuous Drift
While `AEGIS_FULL` achieved near-zero false success across all scenarios, its task success under continuous drift (`SENSOR_DRIFT`) was 24.0% with 74.0% abstention. 
- **Diagnosis:** The agent correctly identifies that the measurements are diverging and drifting, but because it only has passive abstention and localized recovery, it stops moving once drift exceeds threshold.
- **Research Opportunity for V5:** Instead of merely abstaining, the agent can use temporal observations of the range sensor to **recalibrate the drifting vector sensor online**.

---

## 4. Scientific Literature Positioning

| Field / Related Work | Representative Works | Key Mechanism | Relationship / Distinction to NEXVIA AEGIS |
| :--- | :--- | :--- | :--- |
| **Next-Best-View & Active Perception** | NeU-NBV (2023), View-Planning-Sim (2024) | Information gain optimization for 3D reconstruction | Focused on passive reconstruction rather than closed-loop physical decision safety and abstention. |
| **Selective Prediction & Abstention** | Geifman & El-Yaniv (2017, 2019), Chow et al. | Rejecting classification when confidence is below threshold | Developed for static vision/NLP; AEGIS extends selective decision-making to **continuous closed-loop physical dynamical systems** with sensor arbitration. |
| **Safe RL & Shielding** | Alshiekh et al. (2018), Safety-Gymnasium (2023) | Formal safety shields restricting unsafe actions | Standard shields assume perfect state observation; AEGIS addresses safety when the **sensor stream providing state estimates is itself compromised**. |
| **Fault-Tolerant Multi-Sensor Fusion** | Gustafsson et al., Isermann (2006) | Residual monitoring & Generalized Likelihood Ratio tests | Classical Kalman residual methods require linear/Gaussian assumptions. AEGIS combines geometric cross-modal verification with state-aware behavioral policies. |

---

## 5. Architectural Recommendation for Next Development Milestone (V5.0)

Based on the empirical evidence, we recommend **one primary research direction** for the next milestone:

### Primary Direction: Online Sensor Recalibration via Cross-Modal Consistency (AEGIS-Calib)
- **Problem:** Currently, when sensor drift or bias is detected, the agent safely abstains, sacrificing task completion (coverage drops to 26% under drift).
- **Proposed Solution:** Over an inspection window of $K$ steps ($K \approx 10-20$), the agent collects paired measurements $(r_t, \mathbf{z}_{A, t}, \mathbf{z}_{B, t})$ along its trajectory $\Delta \mathbf{x}_t$.
- By solving a lightweight online optimization:
  $$\hat{\mathbf{b}} = \arg\min_{\mathbf{b}} \sum_{t=1}^K \left( \|\mathbf{z}_{A, t} - \mathbf{b}\| - r_t \right)^2$$
  the agent can estimate the bias vector $\hat{\mathbf{b}}$, subtract it from subsequent sensor readings, restore sensor confidence, and proceed to complete the task instead of abstaining.
- **Hypothesis for V5:** Online cross-modal calibration will increase task success under drift from 24% to $>80\%$ while maintaining false-success rate $\le 2\%$.

---

## 6. Deliverable & Artifact Summary

The initial research milestone is complete with the following verified artifacts:
1. **Research Audit:** [`docs/research_audit.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/research_audit.md)
2. **Experiment Protocol:** [`docs/experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/experiment_protocol.md)
3. **Reproducible Benchmark:** [`experiments/research_benchmark_v4.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/research_benchmark_v4.py)
4. **Episode-Level Dataset:** [`results/v4/v4_benchmark_episodes.csv`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v4/v4_benchmark_episodes.csv) (2,000 episode rows)
5. **Aggregate Metrics Summary:** [`results/v4/v4_benchmark_summary.csv`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v4/v4_benchmark_summary.csv) (40 scenario-policy pairs with 95% Wilson CIs)
6. **Publication Figures:** 
   - False-Success Rate: [`results/v4/figures/false_success_vs_scenario.png`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v4/figures/false_success_vs_scenario.png)
   - Task Success Rate: [`results/v4/figures/task_success_vs_scenario.png`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v4/figures/task_success_vs_scenario.png)
   - Correlated Fault Ablation: [`results/v4/figures/ablation_correlated_bias.png`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v4/figures/ablation_correlated_bias.png)
   - Risk vs. Coverage: [`results/v4/figures/risk_coverage_curve.png`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v4/figures/risk_coverage_curve.png)
7. **Regression Test Suite:** [`tests/`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/) (13/13 passing tests)
8. **Research Decision Memo:** [`docs/research_next_steps.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/research_next_steps.md)
