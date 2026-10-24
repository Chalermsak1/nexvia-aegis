# NEXVIA AEGIS V6.0 — Repository Research Audit & Architectural Baseline

**Author:** Autonomous Systems & Robotics Research Group  
**Project:** NEXVIA AEGIS (Self-Verifying Decision Layer for Physical AI)  
**Version:** 6.0  
**Date:** October 16, 2026  
**Status:** Audited, Verified, and Grounded in Source Code  

---

## 1. Executive Summary & Audit Scope

This document provides a comprehensive, source-grounded research audit of the NEXVIA AEGIS codebase prior to implementing the V6.0 architecture. 

In accordance with Section 4 of the V6.0 Master Prompt, this audit inspects all physical models, sensor fault generators, calibration algorithms, controllers, benchmark scripts, and test suites across V1 through V5. It verifies mathematical representations, pinpoints operational limitations, guarantees strict preservation of historical artifacts, and establishes the formal architectural blueprint for AEGIS V6.0.

---

## 2. Environment & Dependency Audit

- **Operating System:** Darwin (macOS 15.x / Apple Silicon, aarch64, 16 GB unified memory).
- **Python Runtime:** Python 3.12.14 managed via `uv` (`pyproject.toml`, `uv.lock`).
- **Core Scientific Stack:**
  - `mujoco == 3.14.0` (high-fidelity continuous-time physics simulation).
  - `numpy >= 1.26.0` (vectorized kinematics and numerical algebra).
  - `scipy >= 1.13.0` (non-linear bounded optimization, matrix conditioning).
  - `gymnasium >= 0.29.0` (RL environment interfaces).
  - `matplotlib >= 3.8.0` (300 DPI publication graphics).
  - `pytest == 9.1.1` (automated unit and regression testing).
- **Test Suite Status:** 26/26 tests passing in 0.38 seconds (`uv run pytest tests/ -v`).

---

## 3. Historical Artifact Inventory & Preservation Audit

All prior research artifacts are accounted for, verified for size and integrity, and frozen:

| Version | Directory / Artifact | Description | Status |
|---|---|---|---|
| **V1.0** | `src/aegis/policies.py`, `tests/test_v1_env_and_policies.py` | 2D inspection environment & baseline policies | **FROZEN / UNTOUCHED** |
| **V2.0** | `src/aegis/sensing.py`, `tests/test_v2_mujoco_and_decision.py` | Early MuJoCo physics & sensor arbitration | **FROZEN / UNTOUCHED** |
| **V3.0** | `src/aegis/v3/`, `tests/test_v3_agent_and_verification.py` | Closed-loop agent, cross-modal verification | **FROZEN / UNTOUCHED** |
| **V4.0** | `results/v4/v4_benchmark_episodes.csv` (2,000 runs) | Episode-level cross-modal verification benchmark | **PRESERVED & AUDITED** |
| | `results/v4/v4_benchmark_summary.csv` | Summary statistics with Wilson score CIs | **PRESERVED & AUDITED** |
| | `tests/test_v4_benchmark.py` | V4 regression test suite | **PRESERVED & AUDITED** |
| **V5.0** | `src/aegis/calibration.py` | Online bias estimator (Huber + FIM gate) | **FUNCTIONAL BASELINE** |
| | `src/aegis/v5/recovery_controller.py` | Safe recovery controller with orthogonal probing | **FUNCTIONAL BASELINE** |
| | `src/aegis/v5/agent_v5.py` | V5 closed-loop MuJoCo agent | **FUNCTIONAL BASELINE** |
| | `results/v5/v5_benchmark_episodes.csv` (3,000 runs) | Full 10-scenario x 6-policy benchmark dataset | **PRESERVED & AUDITED** |
| | `results/v5/v5_benchmark_summary.csv` | Full 60-row aggregate summary table | **PRESERVED & AUDITED** |
| | `results/v5/figures/` (4 figures) | 300 DPI research figures (fig1–fig4) | **PRESERVED & AUDITED** |
| | `tests/test_v5_calibration.py` (13 tests) | Mathematical & integration test suite | **100% PASSING** |
| | `docs/v5_*.md` (4 docs) | Calibration design, protocol, failure analysis, summary | **COMPLETE & VALIDATED** |

---

## 4. Source-Grounded Answers to Audit Questions (Section 4.1)

### Q1: Which existing V5 modules are functional?
- `src/aegis/calibration.py`: Fully functional. Implements `OnlineBiasEstimator`, algebraic linear initialization, multi-start bounded L-BFGS-B optimization with Huber loss, Fisher Information Matrix observability checks, and held-out validation.
- `src/aegis/v5/recovery_controller.py`: Fully functional. Manages state machine (`NOMINAL` $\to$ `PROBING` $\to$ `CALIBRATED` / `ABSTAIN`), two-phase orthogonal probing, finite-difference velocity damping, and dropout safeguards.
- `src/aegis/v5/agent_v5.py`: Fully functional closed-loop execution harness.

### Q2: Which APIs and observation formats are actually used?
- Vector reading: `SensorReading(estimate: np.ndarray(2,), sigma: float, valid: bool, anomaly: bool, dropped: bool, bias: np.ndarray, drift: np.ndarray)`.
- Scalar range reading: `RangeReading(distance: float, sigma: float, valid: bool, anomaly: bool, dropped: bool)`.
- Verification output: `UnifiedVerification(status: str, estimate: np.ndarray, confidence: float, sensor_disagreement: float, cross_modal_discrepancy: float, safe_to_act: bool)`.
- Control action: `np.ndarray(2,)` in $[-1.0, 1.0]^2$ passed to `world.step(action, rng)`.

### Q3: How does the vector sensor represent target geometry?
- As audited in `src/aegis/v3/sensors/sensors.py` line 133:
  $$\mathbf{z}_t = \mathbf{d}_t + \mathbf{b} + \boldsymbol{\epsilon}_t, \quad \text{where } \mathbf{d}_t = \mathbf{p}_{\text{target}} - \mathbf{p}_{\text{robot}}(t)$$
  The vector sensor reports the **relative displacement vector from robot to target in the robot's translational frame**, NOT absolute world coordinates.

### Q4: How does the range sensor generate observations?
- As audited in `src/aegis/v3/sensors/cross_modal.py` line 67:
  $$r_t = \max(0.0, \|\mathbf{d}_t\|_2 + \nu_t), \quad \nu_t \sim \mathcal{N}(0, \sigma_{\text{range}}^2)$$
  It reports true Euclidean distance with independent Gaussian noise and non-negative clipping.

### Q5: Are sensor faults independent, correlated, or common-mode?
The simulation supports:
- **Independent faults:** Each sensor has its own `SensorConfig(bias, drift_rate, outlier_probability, dropout_probability)`.
- **Correlated / common-mode faults:** `SharedFaultModel(bias)` adds an identical hidden bias vector to all sensors sharing a `shared_bias_group`.
- **Reference sensor faults:** Range sensor can sustain an additive distance bias ($r_t = \|\mathbf{d}_t\| + \beta_{\text{ref}}$).

### Q6: How does V5 estimate bias and evaluate observability?
- **Algebraic Linear Initialization:** Computes starting guess $\mathbf{x}_0$ from $2(\mathbf{z}_t - \mathbf{z}_0)^T \mathbf{b} = (\|\mathbf{z}_t\|^2 - r_t^2) - (\|\mathbf{z}_0\|^2 - r_0^2)$.
- **Optimization:** Minimizes $\sum_t \rho_\delta(\|\mathbf{z}_t - \mathbf{b}\|_2 - r_t)$ using Huber loss ($\delta = 0.15$).
- **Observability Evaluation:** Computes Fisher Information Matrix $\mathbf{F} = \sum_t \hat{\mathbf{u}}_t \hat{\mathbf{u}}_t^T$ (where $\hat{\mathbf{u}}_t = \frac{\mathbf{z}_t - \mathbf{b}}{\|\mathbf{z}_t - \mathbf{b}\|}$) and checks $\lambda_{\min}(\mathbf{F}) \ge 0.0005$ and $\kappa(\mathbf{F}) \le 15000$.

### Q7: How does calibration output enter the recovery controller?
- When certified, `cal_res.bias` is stored in `state.active_bias`.
- In `CALIBRATED` mode, the corrected target displacement is computed as:
  $$\hat{\mathbf{d}}_t = \mathbf{z}_t - \text{state.active\_bias}$$
- Actuation applies proportional force towards $\hat{\mathbf{d}}_t$ combined with finite-difference velocity damping: $\mathbf{u}_t = \hat{\mathbf{d}}_t / \|\hat{\mathbf{d}}_t\| - 0.25 \hat{\mathbf{v}}_t$.

### Q8: Which actions can the robot execute?
- The continuous action space is $\mathbf{u} \in [-1.0, 1.0]^2$. Applied force is $\mathbf{F} = \mathbf{u} \cdot F_{\max}$ ($F_{\max} = 1.0\text{ N}$).

### Q9: How are velocity, momentum, and actuator constraints modeled?
- Governed by MuJoCo continuous-time dynamics ($m = 1.0\text{ kg}$, $r = 0.20\text{ m}$, timestep $\Delta t = 0.02\text{ s}$).
- The sphere has zero joint friction; damping must be actively generated by the controller.
- Arena boundaries $[-6.0, 6.0]^2$ are bounded; robot positions beyond $[-3.0, 3.0]$ risk boundary wall collisions.

### Q10: What information is available to the agent at decision time?
- Vector sensor measurements ($\mathbf{z}_A, \mathbf{z}_B$) and validity flags.
- Scalar range sensor measurement ($r_t$) and validity flag.
- Unified verification status and discrepancies.
- Step index $t$.
- Historical observation buffers maintained internally by the agent.

### Q11: Which ground-truth quantities are strictly evaluation-only?
- True robot position $\mathbf{p}_{\text{robot}}(t)$, true velocity $\dot{\mathbf{p}}(t)$, true target position $\mathbf{p}_{\text{target}}$, true distance $D_t$, true sensor bias $\mathbf{b}^*$, and fault labels. Live agents must never access these fields.

### Q12: Which V5 benchmarks can be reproduced from existing scripts?
- `experiments/research_benchmark_v5.py` reliably runs 3,000 policy-episodes in ~18 seconds.
- `experiments/plot_v5_results.py` generates the 4 benchmark figures in ~2 seconds.

### Q13: Identified architectural bottlenecks and limitations for V6 design:
1. **Blind Probing:** V5's orthogonal excitation is static and open-loop; it does not evaluate which direction yields the highest information gain or discriminates between hypotheses.
2. **Mirror-Symmetry Ambiguity:** In static bias scenarios, range-only trilateration over narrow angles produces dual mirror solutions across the line of sight. V5 cannot actively probe to disambiguate the mirror root before committing.
3. **Single-Hypothesis Commitment:** V5 assumes all inconsistency is primary vector bias, causing it to fail or over-probe when the range sensor itself is biased or when sensors experience intermittent dropouts.
4. **Lack of Risk-Constrained Planning:** Probing forces are applied without anticipating boundary violations or cumulative motion budget.

---

## 5. Architectural Blueprint for NEXVIA AEGIS V6.0

To overcome these fundamental limitations, AEGIS V6.0 will introduce:

1. **`src/aegis/v6/hypothesis_models.py`:**
   Formal mathematical definitions and likelihood/residual models for competing hypotheses:
   - $H_0$: Nominal behavior (Gaussian measurement noise).
   - $H_1$: Constant vector sensor bias ($\mathbf{b} \in \mathbb{R}^2$).
   - $H_2$: Dynamic linear drift ($\mathbf{b}(t) = \mathbf{r}_{\text{drift}} \cdot t$).
   - $H_3$: Corrupted reference sensor (scalar range bias $\beta_{\text{ref}}$).
   - $H_4$: Correlated / common-mode sensor bias ($\mathbf{z}_A \approx \mathbf{z}_B \neq \mathbf{d}$).
   - $H_5$: Intermittent sensor dropout (packet loss).
   - $H_6$: Unobservable / ambiguous geometry.

2. **`src/aegis/v6/diagnosis.py`:**
   Multi-hypothesis diagnosis engine maintaining Bayesian likelihoods and normalized posterior model scores $P(H_k \mid \mathcal{Z}_{1:t})$, tracking entropy/diagnostic ambiguity, and generating reason codes.

3. **`src/aegis/v6/active_probing.py` & `src/aegis/v6/trajectory_planner.py`:**
   Risk-constrained trajectory planner implementing:
   - Strategy A: Fixed Orthogonal (V5 Baseline).
   - Strategy B: Circular Orbit Probing (angular diversity).
   - Strategy C: Figure-Eight Lissajous Probing.
   - Strategy D: Random Safe Probing.
   - Strategy E: Local FIM-Guided Probing ($\max \det \mathbf{F}$ or $\max \lambda_{\min}$).
   - Strategy F: **Hypothesis-Discriminative Active Probing** ($\max \text{KL}(P(z \mid H_i) \parallel P(z \mid H_j))$), specifically choosing actions that break mirror symmetry and separate vector bias from reference bias.

4. **`src/aegis/v6/recovery_controller.py` & `agent_v6.py`:**
   Integrated closed-loop agent with state flow:
   `NOMINAL` $\to$ `FAULT_SUSPECTED` $\to$ `DIAGNOSIS` $\to$ `ACTIVE_PROBING` $\to$ `CALIBRATION` $\to$ `VALIDATION` $\to$ `RECOVERY` / `ABSTAIN`.

5. **`experiments/research_benchmark_v6.py` & `results/v6/`:**
   Comprehensive benchmark evaluating V5 vs V6 variants with matched seeds, reporting true success, false success, coverage, selective risk, bias RMSE, diagnostic accuracy, and trajectory cost.
