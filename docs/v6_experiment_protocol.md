# NEXVIA AEGIS V6.0 — Experimental Protocol & Evaluation Benchmark

**Author:** Autonomous Systems & Robotics Research Group  
**Project:** NEXVIA AEGIS (Physical AI Research Initiative)  
**Version:** 6.0  
**Date:** October 16, 2026  
**Status:** Validated, Audited, and Benchmark-Verified  

---

## 1. Overview and Scientific Objectives

NEXVIA AEGIS V6.0 investigates whether **multi-hypothesis sensor diagnosis** and **active risk-constrained trajectory planning** can improve recovery from sensor faults compared with the V5.0 recalibration architecture, without introducing an unacceptable increase in false-success decisions or safety violations.

This protocol establishes the formal, reproducible benchmark specifications across:
- **10 Simulation Scenarios** (MuJoCo 3.14.0 continuous-time physics).
- **6 Policy Variants** (from V5 baseline to hypothesis-discriminative planning).
- **50 Matched Episodes per Policy-Scenario Pair** (3,000 total policy-episodes).
- **7 Component Ablations** across 5 stress scenarios (2,000 ablation runs).

---

## 2. Formal Research Hypotheses

- **Hypothesis 1 (Active Diagnosis Benefit):**  
  *Under test conditions where competing sensor-fault hypotheses are distinguishable from available measurements, an active diagnosis strategy reduces fault-identification error and calibration error relative to fixed or non-informative probing trajectories.*

- **Hypothesis 2 (Recovery Efficiency):**  
  *Under comparable task conditions and operating budgets, the V6 architecture improves task completion and coverage compared with V5.0 without materially increasing false-success incidence.*

- **Hypothesis 3 (Observability-Aware Planning):**  
  *Selecting trajectories using an explicit observability or information objective provides superior calibration outcomes to unguided or random exploration.*

- **Hypothesis 4 (Multi-Hypothesis Diagnosis Advantage):**  
  *Maintaining multiple fault hypotheses and explicitly representing uncertainty reduces incorrect fault attribution relative to committing immediately to a single bias estimate.*

- **Hypothesis 5 (Safe Recovery & Compromised Reference Bounds):**  
  *The V6 architecture safely halts and bounds false-success incidence to zero or near-zero when the reference sensor is corrupted ($H_3$) or when geometry is unobservable ($H_6$).*

---

## 3. Evaluated Policy Variants

1. **`AEGIS_V5_ROBUST` (V5 Production Baseline):**  
   The frozen V5 recalibration architecture. Employs fixed two-phase orthogonal probing (16 steps $u_\perp$, 16 steps $u_\parallel$), algebraic linearization, bounded Huber loss minimization, FIM observability gate, and held-out validation. Assumes all fault is primary vector bias.
2. **`AEGIS_V6_FIXED_PROBE` (Multi-Hypothesis with Fixed Trajectory):**  
   Integrates the V6 multi-hypothesis diagnosis engine ($H_0$–$H_6$) with V5's fixed orthogonal probing pattern (Strategy A). Isolates the contribution of multi-hypothesis diagnosis independent of trajectory change.
3. **`AEGIS_V6_CIRCULAR` (Multi-Hypothesis with Circular Orbit):**  
   V6 architecture executing continuous tangential orbital motion around the target line of sight (Strategy B) to maximize angular viewpoint diversity.
4. **`AEGIS_V6_FIGURE_EIGHT` (Multi-Hypothesis with Figure-Eight Lissajous):**  
   V6 architecture executing harmonic 2D Lissajous paths (Strategy C), producing rich spatial curvature with minimal net drift.
5. **`AEGIS_V6_FIM_GUIDED` (Multi-Hypothesis with Local FIM Maximization):**  
   V6 architecture selecting actions that maximize the smallest eigenvalue of the projected Fisher Information Matrix (Strategy E).
6. **`AEGIS_V6_FULL_DISCRIMINATIVE` (Full V6 Production Policy):**  
   The complete V6 architecture combining multi-hypothesis diagnosis with **Hypothesis-Discriminative Active Probing** (Strategy F), actively steering the robot along directions that maximize measurement divergence between competing hypotheses while enforcing workspace bounds.

---

## 4. Evaluated Simulation Scenarios

All scenarios are executed in the continuous-time MuJoCo physics engine (`AegisPhysicalWorld`, $m = 1.0\text{ kg}$, $r = 0.20\text{ m}$, $\Delta t = 0.02\text{ s}$, max steps $T_{\max} = 300$):

| Scenario ID | Ground-Truth Fault | Primary Vector Sensor | Secondary Vector Sensor | Scalar Range Sensor |
|---|---|---|---|---|
| **`NOMINAL`** | $H_0$ (Nominal) | $\sigma = 0.05$ | $\sigma = 0.05$ | $\sigma = 0.05$, nominal |
| **`PRIMARY_BIAS`** | $H_1$ (Vector Bias) | Bias $\mathbf{b} = [0.8, -0.6]^T$ | Nominal | Nominal |
| **`INDEPENDENT_BIAS`**| $H_1$ (Vector Bias) | Bias $\mathbf{b}_1 = [0.6, 0.4]^T$ | Bias $\mathbf{b}_2 = [-0.5, 0.5]^T$ | Nominal |
| **`CORRELATED_BIAS`** | $H_4$ (Correlated) | Shared $\mathbf{b} = [0.7, 0.7]^T$ | Shared $\mathbf{b} = [0.7, 0.7]^T$ | Nominal |
| **`SENSOR_DRIFT`** | $H_2$ (Vector Drift)| Drift $\mathbf{r} = [0.003, 0.0015]$ | Nominal | Nominal |
| **`OUTLIER_BURSTS`** | $H_1$ (Vector Bias) | Bursts ($p=0.15, \text{scale}=6.0$) | Nominal | Nominal |
| **`SENSOR_DROPOUT`** | $H_5$ (Dropout) | Dropout ($p = 0.20$) | Dropout ($p = 0.20$) | Nominal |
| **`COMPOUND_HOLDOUT`**| $H_4$ (Correlated) | Bias $[0.5, 0.5]$ + drift + bursts | Bias $[0.5, 0.5]$ | Nominal |
| **`FAULTY_REFERENCE`**| $H_3$ (Reference Fault)| Shared $\mathbf{b} = [0.7, 0.7]^T$ | Shared $\mathbf{b} = [0.7, 0.7]^T$ | **Range bias $+1.0\text{ m}$** |
| **`LOW_OBSERVABILITY`**| $H_6$ (Ambiguous) | Shared $\mathbf{b} = [0.7, 0.7]^T$ | Shared $\mathbf{b} = [0.7, 0.7]^T$ | **Collinear 1D motion** |

---

## 5. Statistical Rigor and Matched Seeds

### 5.1 Matched Seed Schedule
To ensure fair paired comparisons:
$$\text{Seed}_i = 56000 + i, \quad i \in \{0, 1, \dots, 49\}$$
For episode $i$, all six policy variants encounter:
- Identical initial robot position $\mathbf{p}_0 = [-2.0, -2.0]^T$.
- Identical target position $\mathbf{p}_{\text{target}} \in [-3.0, 3.0]^2$.
- Identical stochastic noise realizations $\boldsymbol{\epsilon}_t, \nu_t$.
- Identical outlier burst and packet dropout occurrence steps.

### 5.2 Performance Metrics & Statistical Formulations

- **True Success Rate ($S$):** Fraction of episodes reaching terminal stop within true target ball ($D_{\text{final}} \le 0.45\text{ m}$).
- **False Success Rate ($F$):** Fraction of episodes declaring `STOP` where true distance exceeds target ball ($D_{\text{final}} > 0.45\text{ m}$).
- **Abstention Rate ($A$):** Fraction of episodes safely halting via `ABSTAIN`.
- **Autonomous Task Coverage ($C$):** Fraction of covered decisions: $C = 1 - A = S + F$.
- **Covered Risk ($R_{\text{cov}}$):** Selective risk conditioned strictly on covered episodes ($F / C$ when $C > 0$; strictly reported as `N/A` when $C = 0$).
- **Diagnostic Classification Accuracy:** Fraction of episodes where $\hat{H} = H_{\text{true}}^*$.
- **Mean Diagnostic Entropy:** Average Shannon entropy $\mathcal{H}$ of the posterior probability distribution.
- **Mean Bias Error:** Average parameter estimation error $\|\hat{\mathbf{b}} - \mathbf{b}^*\|_2$ over calibrated episodes.
- **Distance Traveled:** Cumulative Euclidean distance moved during episode.
- **95% Wilson Score Confidence Intervals:** Calculated for all binomial proportions ($S, F, A, C$).

---

## 6. Execution and Reproduction Protocol

All evaluations run in the managed virtual environment (`uv`):

### 1. Main Benchmark (3,000 Policy-Episodes)
```bash
PYTHONPATH=src uv run python experiments/research_benchmark_v6.py
```
Outputs:
- `results/v6/v6_benchmark_episodes.csv`
- `results/v6/v6_benchmark_summary.csv`

### 2. Component Ablations (2,000 Episodes)
```bash
PYTHONPATH=src uv run python experiments/ablation_v6.py
```
Output:
- `results/v6/v6_ablation_summary.csv`

### 3. Figure Generation
```bash
PYTHONPATH=src uv run python experiments/plot_v6_results.py
```
Outputs in `results/v6/figures/`:
- `fig1_v6_success_and_coverage.png`
- `fig2_v6_diagnostic_accuracy_and_entropy.png`
- `fig3_v6_bias_rmse_by_trajectory.png`
- `fig4_v6_ablation_contributions.png`

### 4. Unit & Regression Tests
```bash
uv run pytest tests/ -v
```
Verifies all 42 tests across V1 through V6.
