# NEXVIA AEGIS V5.0 — Experimental Protocol & Evaluation Benchmark

**Author:** Autonomous Systems & Robotics Research Group  
**Project:** NEXVIA AEGIS (Physical AI Research Initiative)  
**Version:** 5.0  
**Date:** October 16, 2026  
**Status:** Validated & Audited  

---

## 1. Overview and Scientific Motivation

NEXVIA AEGIS is a self-verifying decision framework designed to guarantee safety and reliability in physical autonomous systems operating under sensor degradation, stochastic noise, and distribution shift.

In AEGIS V4.0, geometric cross-modal verification between redundant vector sensors ($\mathbf{z}_t$) and scalar range sensors ($r_t$) enabled the robot to reliably detect sensor faults and abstain from catastrophic action. While V4 successfully suppressed false-success rates to near zero under adversarial conditions, it suffered severe **task coverage collapse**: when any sensor sustained a persistent bias or drift, the system permanently halted, achieving 0%–2% task coverage.

**AEGIS V5.0** introduces **Online Cross-Modal Recalibration and Safe Recovery**. Instead of treating sensor disagreement as an immediate halting signal, V5.0 leverages robot motion displacement and scalar range measurements to formulate an online non-linear inverse problem, estimating sensor bias vector $\mathbf{b} \in \mathbb{R}^2$ in real time.

This document establishes the formal, reproducible experimental protocol for evaluating AEGIS V5.0 across 10 simulation scenarios and 6 policy variants (3,000 matched policy-episodes).

---

## 2. Formal Research Hypotheses

The experimental evaluation is structured around five falsifiable scientific hypotheses:

- **Hypothesis 1 (Autonomous Task Coverage Improvement):**  
  *Online cross-modal recalibration recovers significant autonomous task coverage over pure abstention (AEGIS V4 Full) under identifiable sensor bias and drift faults, while bounding false-success rates within acceptable risk limits.*

- **Hypothesis 2 (Huber M-Estimation vs OLS Robustness):**  
  *Under contaminated, heavy-tailed measurement distributions (outlier bursts), robust M-estimation with Huber loss achieves lower bias estimation RMSE and higher true task recovery than Ordinary Least Squares (OLS).*

- **Hypothesis 3 (Observability Qualification Gate):**  
  *Conditioning checks on the Fisher Information Matrix ($\lambda_{\min}(\mathbf{F}) \ge \tau_\lambda$, $\kappa(\mathbf{F}) \le \tau_\kappa$) prevent degenerate calibration updates under collinear, near-stationary, or unobservable trajectories, preventing false-success escalations.*

- **Hypothesis 4 (Dynamic Drift Tracking):**  
  *Continuous receding-horizon recalibration enables tracking of time-varying sensor drift, allowing the robot to complete navigation targets without terminal divergence.*

- **Hypothesis 5 (Compromised Reference Sensor Limits):**  
  *When cross-modal reference assumptions are violated (e.g., corrupted scalar range sensor), the system's qualification and residual gates reject the calibration estimate, safely reverting to abstention rather than accepting a hallucinated trajectory.*

---

## 3. Evaluated Policy Variants

To rigorously measure individual component contributions, six policy variants are evaluated under identical conditions:

1. **`AEGIS_V4_FULL` (Pure Abstention Baseline):**  
   The frozen V4 self-verifying decision policy. Performs cross-modal consistency checks between primary and secondary vector sensors and scalar range. If disagreement exceeds residual thresholds, the policy permanently halts (`ABSTAIN`). Has no calibration mechanism.

2. **`AEGIS_V5_OLS` (Linear Initialization + OLS Optimization):**  
   V5 recovery policy utilizing algebraic linearization followed by unweighted quadratic least-squares minimization:
   $$\min_{\mathbf{b}} \sum_{t} \left(\|\mathbf{z}_t - \mathbf{b}\|_2 - r_t\right)^2$$
   Does not use robust loss functions.

3. **`AEGIS_V5_ROBUST` (Full V5 Production Policy):**  
   The proposed complete V5 architecture combining:
   - Active two-phase orthogonal probing excitation ($u_\perp, u_\parallel$).
   - Closed-form linear algebraic initialization.
   - Bounded multi-start optimization with Huber robust loss ($\delta = 0.15\text{ m}$).
   - Fisher Information Matrix observability qualification gate ($\lambda_{\min} \ge 0.0005, \kappa \le 15000$).
   - Finite-difference velocity damping ($k_d = 0.25$) to prevent momentum overshoot.
   - Held-out validation gate and continuous residual monitoring.

4. **`AEGIS_V5_NO_OBS_GATE` (Ablation: Observability Gate Disabled):**  
   Full V5 policy with the Fisher Information Matrix conditioning checks bypassed. Calibrates whenever the window size threshold is satisfied, regardless of trajectory collinearity.

5. **`AEGIS_V5_NO_VALIDATION` (Ablation: Validation Gate Disabled):**  
   Full V5 policy with the held-out validation gate bypassed. Calibration parameters are certified solely on in-sample fitting residual.

6. **`ORACLE_CALIB_UPPER_BOUND` (Theoretical Performance Bound):**  
   An idealized policy supplied with the true analytical sensor bias vector $\mathbf{b}^*$ at simulation runtime. Demonstrates the ceiling of achievable task performance under perfect calibration.

---

## 4. Evaluated Simulation Scenarios

Ten simulated scenarios are executed in the high-fidelity MuJoCo physics engine (`MuJoCo 3.14.0`, simulation timestep $\Delta t = 0.02\text{ s}$, max episode length $T_{\max} = 300$ steps):

| Scenario ID | Primary Sensor State | Range Reference State | Spatial/Dynamic Conditions | Target Fault Injection |
|---|---|---|---|---|
| **`NOMINAL`** | Nominal Gaussian noise ($\sigma = 0.02$) | Nominal Gaussian noise ($\sigma = 0.02$) | Random target in $[-2.0, 2.0]^2$ | Zero bias ($\mathbf{b} = [0, 0]$) |
| **`PRIMARY_BIAS`** | Static additive bias $\mathbf{b} = [0.8, -0.6]^T$ | Nominal | Disagreement detected at step $t=1$ | Constant vector offset ($\|\mathbf{b}\| = 1.0\text{ m}$) |
| **`INDEPENDENT_BIAS`** | Bias $\mathbf{b}_1 = [0.6, 0.4]^T$ | Nominal | Secondary sensor has $\mathbf{b}_2 = [-0.5, 0.5]^T$ | Independent sensor biases |
| **`CORRELATED_BIAS`** | Bias $\mathbf{b}_1 = [0.7, 0.5]^T$ | Nominal | Secondary sensor shares $\mathbf{b}_2 = [0.6, 0.4]^T$ | Correlated common-mode vector bias |
| **`SENSOR_DRIFT`** | Linear drift $\mathbf{b}(t) = \mathbf{r}_{\text{drift}} \cdot t$ | Nominal | Drift rate $\|\mathbf{r}_{\text{drift}}\| \approx 0.005\text{ m/step}$ | Continuous non-stationary drift |
| **`OUTLIER_BURSTS`** | Laplace/Cauchy bursts ($\sigma_{\text{outlier}} = 1.5$) | Nominal | 15% probability burst contamination | Heavy-tailed non-Gaussian noise |
| **`SENSOR_DROPOUT`** | Signal drops to $[0.0, 0.0]$ | Nominal | Dropouts occur with $p = 0.20$ | Zero-vector dropout / loss of packet |
| **`COMPOUND_HOLDOUT`** | Bias $\mathbf{b} = [0.9, -0.7]^T$ + bursts | Nominal | Combined bias, drift, and outlier bursts | Multi-modal stress benchmark |
| **`FAULTY_REFERENCE_SENSOR`** | Static bias $\mathbf{b} = [0.8, -0.5]^T$ | Range bias $r_t = D_t + 1.0\text{ m}$ | Reference sensor systematically corrupted | Corrupted reference (violates cross-modal assumption) |
| **`LOW_OBSERVABILITY`** | Static bias $\mathbf{b} = [0.8, -0.6]^T$ | Nominal | Robot restricted to 1D collinear path | Degenerate Fisher Information ($\lambda_{\min} \approx 0$) |

---

## 5. Statistical Rigor and Matched Seeds

### 5.1 Matched Random Seeds
To eliminate variance due to target geometry and random initial conditions, all evaluations use **matched random seeds across policies**:
$$\text{Seed}_i = 52000 + i, \quad i \in \{0, 1, \dots, 49\}$$

For episode $i$, all six policy variants encounter:
- The exact same initial robot position $\mathbf{p}_0$.
- The exact same target position $\mathbf{p}_{\text{target}}$.
- The exact same sensor noise sequence $\boldsymbol{\epsilon}_t, \nu_t$.
- The exact same fault onset and outlier occurrences.

Total benchmark scale: 10 scenarios $\times$ 6 policies $\times$ 50 episodes = **3,000 policy-episodes**.

### 5.2 Performance Metrics & Statistical Formulations

Let $N = 50$ be the number of matched episodes for a given scenario-policy pair:
- **True Success ($N_{\text{ts}}$):** Episode terminated at the target ($D_{\text{final}} \le 0.45\text{ m}$) with certified stop decision:
  $$\text{True Success Rate } S = \frac{N_{\text{ts}}}{N}$$
- **False Success ($N_{\text{fs}}$):** Policy declared task completion (`STOP`), but true distance exceeded target radius ($D_{\text{final}} > 0.45\text{ m}$):
  $$\text{False Success Rate } F = \frac{N_{\text{fs}}}{N}$$
- **Abstention ($N_{\text{abs}}$):** Policy executed safe emergency stop or entered permanent abstention (`ABSTAIN`):
  $$\text{Abstain Rate } A = \frac{N_{\text{abs}}}{N}$$
- **Autonomous Task Coverage ($C$):** Fraction of non-abstained episodes:
  $$C = 1 - A = \frac{N_{\text{ts}} + N_{\text{fs}}}{N}$$
- **Covered Risk ($R_{\text{cov}}$):** Selective risk conditioned strictly on covered episodes. When $C = 0$, $R_{\text{cov}}$ is strictly undefined and reported as `N/A`:
  $$R_{\text{cov}} = \begin{cases} \frac{N_{\text{fs}}}{N_{\text{ts}} + N_{\text{fs}}} = \frac{F}{C}, & \text{if } C > 0 \\ \text{N/A}, & \text{if } C = 0 \end{cases}$$
- **Calibration Certification Rate:** Fraction of episodes where the online estimator successfully certified a calibration estimate through all gates.
- **Mean Bias Error:** Average Euclidean norm error $\|\hat{\mathbf{b}} - \mathbf{b}^*\|_2$ computed over certified episodes.

### 5.3 Confidence Intervals
All binomial rates ($S, F, A, C$) are presented with **95% Wilson Score Confidence Intervals**:
$$\text{CI}_{95\%} = \frac{\hat{p} + \frac{z^2}{2N} \pm z \sqrt{\frac{\hat{p}(1 - \hat{p})}{N} + \frac{z^2}{4N^2}}}{1 + \frac{z^2}{N}}$$
where $z = 1.95996$.

---

## 6. Execution and Reproduction Protocol

All experiments are executed in a managed Python virtual environment (`uv`).

### Benchmark Execution Command
```bash
uv run python experiments/research_benchmark_v5.py
```
Outputs generated:
- Episode-level log: `results/v5/v5_benchmark_episodes.csv` (3,000 rows).
- Summary table: `results/v5/v5_benchmark_summary.csv` (60 aggregated records).

### Research Figure Generation Command
```bash
uv run python experiments/plot_v5_results.py
```
Outputs generated in `results/v5/figures/`:
1. `fig1_v5_coverage_and_success.png`: True Success and Task Coverage across scenarios.
2. `fig2_v5_false_success_risk.png`: False Success Rate and Covered Risk profiles.
3. `fig3_v5_bias_rmse.png`: Bias Estimation Error distributions.
4. `fig4_v5_ablation_gates.png`: Impact of FIM Observability and Validation gates.

### Unit & Regression Test Suite
```bash
uv run pytest tests/test_v5_calibration.py tests/test_v4_benchmark.py -v
```
Verifies exact algebraic recovery, numerical stability, gate rejection thresholds, zero ground-truth leakage, and strict preservation of V4 regression baselines.
