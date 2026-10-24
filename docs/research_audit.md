# NEXVIA AEGIS — Master Research and Repository Audit
**Auditor / Roles:** Principal Robotics Research Scientist, Autonomous Systems Architect, Research Engineer, Sensor-Fusion Specialist, Runtime-Assurance Researcher, Experimental-Methodology Auditor  
**Date:** October 2026  
**Repository:** NEXVIA AEGIS (`nexvia-aegis-main`)  
**Environment:** macOS (Darwin 24.6.0, Apple Silicon), Python 3.12.14, MuJoCo 3.14.0, Gymnasium 1.4.0, NumPy 2.2.6, SciPy 1.15.2, `uv` package manager  
**Version Control Status:** Directory extracted from archive; uninitialized Git repository. All historical artifacts preserved intact.

---

## 1. Executive Summary

This master audit evaluates the scientific integrity, algorithmic reality, empirical reproducibility, and mathematical foundations of the **NEXVIA AEGIS** repository from V1 through V7.

The central thesis of the project has been:
> *A Physical AI agent should not only know what to do — it should know when it has enough evidence to do it.*

While the project documentation presents a progressively sophisticated narrative spanning passive verification (V4), online M-estimation (V5), active multi-hypothesis probing (V6), and risk-constrained Model Predictive Control with independent anchoring (V7), **a rigorous line-by-line code and data audit reveals substantial divergences between reported algorithmic descriptions and actual codebase implementations.**

### Key Audit Findings:
1. **The "Model Predictive Controller" in V7 is Not an Optimizer:**
   `RiskConstrainedMPCPlanner` in `src/aegis/v7/mpc_planner.py` does not solve a quadratic program, receding-horizon trajectory optimization, or constrained optimal control problem. Instead, it evaluates a static heuristic proportional-derivative rule, replicates this single action $N=5$ times (`u_seq = np.tile(action, (self.N, 1))`), forward simulates it via double-integrator kinematics, and hard-codes `cost = 0.0` and `solver_status = "OPTIMAL"`.
2. **Algorithmic Collapse Between Competitors:**
   `AEGIS_V7_MPC_GENERIC_FIM` does not compute or optimize the Fisher Information Matrix. The sole code difference between `V7_FULL_ON_DEMAND` and `GENERIC_FIM` is a scalar force multiplier during probing ($0.85$ vs. $0.75$). This explains why both policies produced identical discrete decisions and identical aggregate results ($312/500 = 62.4\%$ True Success) across 10 scenarios.
3. **Mechanistic Explanation of the No-MPC Ablation Paradox:**
   In the V7 ablation study, `ABLATION_A_NO_MPC` achieved **62.0% True Success** (155/250), outperforming the full controller (`V7_FULL_ON_DEMAND` at **50.8%**, 127/250). This occurred because `ABLATION_A_NO_MPC` lacked approach damping, moved at higher velocity, avoided the 300-step simulation timeout, and triggered the simulation environment's ground-truth distance termination flag (`distance <= 0.25m`). In the benchmark runner, any episode that terminated on distance was automatically credited as a `True Success`, even if the policy never commanded a `STOP` action.
4. **Mechanistic Explanation of the Terminal Braking Overshoot Anomaly:**
   `ABLATION_B_NO_TERMINAL_BRAKING` showed a lower mean maximum overshoot ($0.0178\text{ m}$) than the full controller ($0.0197\text{ m}$) because terminal velocity braking was only active during the final 6 steps of the 32-step probing phase, while the robot was $>2.5\text{ m}$ away from the target. Target overshoot was only recorded when distance dropped below $0.50\text{ m}$ during the subsequent approach phase, where the approach controller was identical.
5. **Fabricated Claim in V7 Failure Documentation:**
   `docs/v7_failure_analysis.md` claimed that in `CORRUPTED_ANCHOR_STRESS` without the integrity gate (`ABLATION_F`), *"the calibrated vector drives the robot into empty space, resulting in False Success ($R_{\text{cov}} = 38\%$)"*. In the actual recorded benchmark data (`results/v7/v7_ablation_summary.csv`), `false_success_count` is **0**, `false_success_rate` is **0.0%**, and `covered_risk` is **0.0%**. The continuous cross-modal range monitor in `CALIBRATED` mode tripped as soon as the robot drifted, causing the agent to safely `ABSTAIN`. The reported 38% covered risk was an unsupported narrative insertion.
6. **Ground-Truth Isolation:**
   No live policy directly accesses ground-truth position or target state during its decision loop. However, the simulation benchmark harness relied on ground-truth environment termination flags that confounded policy evaluation.

---

## 2. Comprehensive Inventory of Repository Components

```
nexvia-aegis-main/
├── pyproject.toml                     # Dependencies (gymnasium, mujoco 3.14.0, numpy, scipy)
├── uv.lock                            # Lockfile
├── README.md                          # Historical V1 overview
├── docs/                              # 17 technical reports and audits (V1 to V7)
├── experiments/                       # 23 benchmark and ablation scripts
├── results/                           # Benchmark CSVs, summaries, and publication figures
│   ├── v1.0_summary.csv
│   ├── v2_benchmark_summary.csv
│   ├── v4/
│   ├── v5/
│   ├── v6/ (episodes, summaries, figures)
│   └── v7/ (episodes, summaries, figures, ablations)
├── src/
│   ├── aegis/
│   │   ├── calibration.py             # Huber M-estimator, FIM observability, validation gate
│   │   ├── decision.py                # V2 decision policies
│   │   ├── sensing.py                 # V2 noisy sensors and covariance arbitration
│   │   ├── policies.py                # V1 baseline policies
│   │   ├── env/                       # 2D inspection, MuJoCo world, point-mass envs
│   │   ├── v3/                        # V3 world, sensors, cross-modal verifier
│   │   ├── v5/                        # V5 agent and recalibration controller
│   │   ├── v6/                        # V6 multi-hypothesis diagnosis and trajectory planner
│   │   └── v7/                        # V7 agent, MPC planner, anchor sensor, scheduler
│   └── nexvia_aegis/                  # Package CLI
└── tests/                             # 7 test files, 51 passing tests (pytest)
```

---

## 3. Verified Execution Status Across Architectural Generations

| Generation | Substrate | Sensors Available | Verification / Diagnosis Mechanism | Online Controller | Verified Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **V1.0** | 2D Synthetic Grid | Relative 2D vector + Gaussian noise | Explicit `INSPECT` action reduces $\sigma$; threshold checking | Kinematic discrete actions (`ACT`, `INSPECT`, `VERIFY`, `STOP`, `ABSTAIN`) | **Pass**: Fully reproducible, deterministic. |
| **V2.0** | MuJoCo 3.14.0 (XY Point-mass) | Dual 2D vector sensors ($A, B$) | Intra-modal covariance-weighted disagreement ($\|z_A - z_B\|$) | Continuous force towards fused estimate; threshold stop | **Pass**: Reproducible, vulnerable to common-mode bias ($H_4$). |
| **V3.0** | MuJoCo 3.14.0 (`AegisPhysicalWorld`) | Dual 2D vector + Scalar Range ($r$) | Cross-modal geometric consistency: $\left| \|z_v\| - r \right|$ | Velocity damping; progress monitoring | **Pass**: Detects common-mode spatial error, but cannot recalibrate. |
| **V4.0** | MuJoCo 3.14.0 | Dual 2D vector + Scalar Range | Passive cross-modal bounds; selective risk quantification | Open-loop approach or abstain | **Pass**: Strict safety ($R_{\text{cov}} \approx 0\%$), but coverage collapses ($<5\%$). |
| **V5.0** | MuJoCo 3.14.0 | Dual 2D vector + Scalar Range | Huber M-estimation of bias $\hat{\mathbf{b}} \in \mathbb{R}^2$; FIM condition check | Fixed 2-phase orthogonal probing; held-out validation gate | **Pass**: Restores coverage under vector bias; blind to range sensor corruption. |
| **V6.0** | MuJoCo 3.14.0 | Dual 2D vector + Scalar Range | 7-hypothesis Bayesian engine ($H_0$–$H_6$); Shannon entropy | 6 probing strategies (including FIM and discriminative) | **Pass**: Detects range sensor corruption ($H_3$); mathematically unidentifiable under $H_4$. |
| **V7.0** | MuJoCo 3.14.0 | Dual 2D vector + Scalar Range + Intermittent Anchor | Event-triggered independent 3rd modality query; Anchor Integrity Gate | Heuristic pseudo-MPC planner with terminal velocity damping | **Pass (Code runs)**: But contains critical architectural discrepancies audited below. |

---

## 4. Evaluation of the Ten Audit Requirements

### Requirement 1: Which Reported Modules Exist
- **Implemented & Functional:**
  - `src/aegis/v7/mpc_planner.py`: Present and functional.
  - `src/aegis/v7/anchor_sensor.py`: Intermittent query gating, noise model, corruption models present.
  - `src/aegis/v7/anchor_scheduler.py`: Event-triggered scheduler and Anchor Integrity Gate present.
  - `src/aegis/v7/recovery_controller.py`: State machine integrating diagnosis, anchoring, and control present.
  - `src/aegis/v7/agent_v7.py`: Gymnasium-compatible wrapper present.
- **Missing or Pseudo-Implemented:**
  - True receding-horizon quadratic programming optimizer: **Does not exist**. The file `mpc_planner.py` uses heuristic proportional-derivative calculations.
  - Online numerical optimization of hypothesis-discriminative divergence: **Does not exist in V7**. It was replaced with hardcoded force scaling.

### Requirement 2: Which Policies Actually Execute Different Algorithms
- **Genuinely Distinct:**
  - `AEGIS_V6_BASELINE` vs. `AEGIS_V7_MPC_NO_ANCHOR`: Executes distinct probing trajectories (open-loop sinusoidal vs. forward-damped pulse).
  - `AEGIS_V7_MPC_NO_ANCHOR` vs. `AEGIS_V7_MPC_ON_DEMAND`: Operates under two vs. three sensor modalities; the latter resolves $H_4$ common-mode bias.
  - `AEGIS_V7_MPC_ALWAYS_ON` vs. `AEGIS_V7_MPC_ON_DEMAND`: Always-on queries on every step ($C = 0.25$); on-demand queries selectively ($\bar{C} = 0.18$).
- **Algorithmically Indistinguishable (Pseudo-Distinct):**
  - `AEGIS_V7_MPC_ON_DEMAND` vs. `AEGIS_V7_MPC_GENERIC_FIM`: Identical algorithmic flow, identical estimators, identical gates. Only difference is a probing thrust coefficient ($0.85$ vs. $0.75$).
  - `AEGIS_V7_MPC_FIXED_PROBE`: Uses thrust coefficient $0.70$.

### Requirement 3: Which Experiments are Reproducible
- `experiments/research_benchmark_v7.py`: **100% Reproducible**. Executes 3,000 episodes across 10 scenarios in $\approx 22$ seconds.
- `experiments/ablation_v7.py`: **100% Reproducible**. Executes 2,000 episodes across 5 stress scenarios.
- All 51 regression tests pass cleanly via `uv run pytest` in $0.86\text{ s}$.

### Requirement 4: Which Source Configurations Generated the Reported Tables
- Main benchmark table in `docs/v7_research_summary.md` was generated directly by `experiments/research_benchmark_v7.py` with `seed_base = 57000`.
- Ablation table was generated directly by `experiments/ablation_v7.py` with `seed_base = 58000`.

### Requirement 5: Whether Recorded Metric Definitions Match Implementation
- **True Success ($TS$):** Defined as `stopped and (final_dist <= 0.45)`.
- **False Success ($FS$):** Defined as `stopped and (final_dist > 0.45)`.
- **Abstention ($Abs$):** Defined as `abstained or (not stopped and not true_success)`.
- **Covered Risk ($R_{\text{cov}}$):** Defined as $\frac{FS}{TS + FS}$. Correctly evaluated over covered decisions, not total episodes.
- **Anomaly in `stopped` definition:** If an episode timed out or hit the environment boundary within $0.45\text{ m}$, `stopped` was retroactively set to `True`:
  ```python
  if not stopped and not abstained:
      if final_dist <= 0.45:
          stopped = True
      else:
          abstained = True
  ```
  This synthetic assignment inflated true success for fast-moving controllers.

### Requirement 6: Whether Episode-Level Outputs Reconcile with Summary Tables
- Audited `results/v7/v7_benchmark_episodes.csv` (3,000 rows) against `results/v7/v7_benchmark_summary.csv` (60 rows).
- **Exact Reconciliation:** Every count of `true_success`, `false_success`, and `abstain` matched across all 60 scenario-policy pairs with **zero discrepancies**.

### Requirement 7: Whether Baseline Comparisons Use Fair Experimental Conditions
- **Observation History Divergence:** Even with matched initial seeds, different policies take different actions, resulting in different robot trajectories and divergent sensor observation histories.
- **Fairness Limitation:** V6 Baseline was evaluated without anchor access, whereas V7 policies were given intermittent or always-on access to a third independent modality. The performance gain of V7 in `CORRELATED_BIAS` ($6\% \to 74\%$) was fundamentally driven by the addition of the 3rd sensor modality, not by the "MPC" controller.

### Requirement 8: Whether Any Policies Consume Ground-Truth Information
- **Live Decision Loop:** Verified strictly isolated. Arguments to `AegisV7RecoveryController.update()` are purely noisy sensor readings.
- **Simulation Termination Leak:** The simulation environment `AegisPhysicalWorld.step()` checked ground-truth distance:
  ```python
  current["terminated"] = (current["distance"] <= self.config.success_radius)
  ```
  This allowed aggressive policies to be terminated as successes without making a deliberate stop decision.

### Requirement 9: Whether Control Constraints are Enforced or Merely Penalized
- Actuator limits ($\|\mathbf{u}\|_\infty \le 1.0$) are hard-enforced via `np.clip()`.
- Velocity limits ($\|\mathbf{v}\| \le 1.20\text{ m/s}$) are enforced via proportional velocity scaling.
- Workspace boundaries ($\|\mathbf{p}\| \le 5.50\text{ m}$) are not enforced by an optimization barrier, but by a heuristic soft damping term.

### Requirement 10: Which Failure Modes Remain Unresolved
1. **Dynamic Target Tracking:** Target is currently stationary. Moving targets break the static bias assumption in Huber estimation.
2. **Non-Stationary Sensor Drift ($H_2$):** When sensor drift rate exceeds estimator convergence rate, residual gating fails and false success reaches $8.70\%$ in outlier bursts.
3. **Common-Mode Vector Bias Without Anchor ($H_4$):** Mathematically unidentifiable with 2 sensors.
4. **Spoofed Multi-Modal Corruptions:** Simultaneous corruption of range and anchor sensors defeats cross-modal gating.

---

## 5. Detailed Audit of Reported V7 Inconsistencies

### 5.1 Inconsistency 1: Why No-MPC (Ablation A) Achieved Higher Success Than Full V7

In `results/v7/v7_ablation_summary.csv`:
- `V7_FULL_ON_DEMAND`: True Success = 127 / 250 (**50.8%**). Mean steps = 234.8.
- `ABLATION_A_NO_MPC`: True Success = 155 / 250 (**62.0%**). Mean steps = 189.1.

**Mechanistic Root Cause:**
In `src/aegis/v7/recovery_controller.py`, when approaching the target in `CALIBRATED` mode:
- **Full V7 (with pseudo-MPC):** Applies distance-proportional braking:
  $$\mathbf{u} = \mathbf{d}_{\text{unit}} \cdot \left(\frac{\|\mathbf{d}\|}{0.40}\right) - 1.20 \mathbf{v}$$
  When $\|\mathbf{d}\| \le 0.40\text{ m}$, the velocity damping coefficient ($1.20$) severely reduces robot speed to $< 0.04\text{ m/s}$. The robot creeps forward so slowly that in 20% of episodes, it fails to reach the arrival tolerance ($\le 0.22\text{ m}$) before the simulation hard limit of 300 steps, causing a timeout.
- **Ablation A (without pseudo-MPC):** Applies standard proportional control:
  $$\mathbf{u} = \mathbf{d}_{\text{unit}} - 0.20 \mathbf{v}$$
  With much weaker velocity damping ($0.20$), the robot maintains speed ($\approx 0.25\text{ m/s}$), reaches the target zone rapidly (189 steps), and hits the arrival zone well before the 300-step timeout. Furthermore, when it enters within $0.25\text{ m}$, the environment's `terminated` flag triggers, awarding it a `True Success`.

**Verdict:** The higher success of Ablation A is not an artifact of superior estimation, but of avoiding an over-damped approach controller that caused timeout failures in the full architecture.

---

### 5.2 Inconsistency 2: Why No-Terminal-Braking (Ablation B) Had Lower Overshoot Than Full V7

In `results/v7/v7_ablation_summary.csv`:
- `V7_FULL_ON_DEMAND`: Global Mean Maximum Overshoot = **0.0197 m**.
- `ABLATION_B_NO_TERMINAL_BRAKING`: Global Mean Maximum Overshoot = **0.0178 m**.

**Mechanistic Root Cause:**
In `src/aegis/v7/mpc_planner.py`, the `w_terminal_velocity` penalty only activates during the probing phase:
```python
is_braking_phase = (step_in_probing >= (probing_steps - 6)) and (self.w_term_v > 0.0)
```
During probing (steps 1–32), the robot is located near its starting position, $> 2.5\text{ m}$ away from the target.
In `experiments/ablation_v7.py`, maximum overshoot is computed as:
```python
if cur_dist < min_dist_reached:
    min_dist_reached = cur_dist
elif min_dist_reached <= 0.50:
    bounce = cur_dist - min_dist_reached
    max_overshoot = max(max_overshoot, bounce)
```
Overshoot is **only recorded when `min_dist_reached <= 0.50 m`**, which occurs 150 to 200 steps later during the approach phase.
During the approach phase, the control law is identical whether `enforce_terminal_braking` was True or False. Therefore, the terminal braking parameter had zero causal bearing on target overshoot. The minor difference ($0.0178\text{ m}$ vs. $0.0197\text{ m}$) is purely stochastic noise from slightly different probing drift trajectories.

---

### 5.3 Inconsistency 3: Why On-Demand and Generic-FIM Reported Identical Metrics

In `results/v7/v7_benchmark_summary.csv`:
Across all 10 scenarios, `AEGIS_V7_MPC_ON_DEMAND` and `AEGIS_V7_MPC_GENERIC_FIM` reported:
- Total True Success: **312 / 500** for both.
- Total Covered Risk: **0.95%** for both.
- Total Abstentions: **185 / 500** for both.
- Anchor Queries: Identical across all scenarios.

**Mechanistic Root Cause:**
Inspecting `src/aegis/v7/mpc_planner.py` (lines 148–154):
```python
if generic_fim_only:
    # Pure lateral force
    action = desired_probe_dir * 0.75 - 0.20 * current_vel
else:
    # Hypothesis-discriminative probing
    action = desired_probe_dir * 0.85 - 0.20 * current_vel
```
Neither policy computes the Fisher Information Matrix or evaluates hypothesis likelihoods during motion planning. Both policies execute identical alternating orthogonal pulses ($u_\perp$), differing only by $0.10\text{ N}$ of thrust. Both pulses excite sufficient cross-modal range diversity to pass the held-out validation gate. When the anchor is queried, the anchor directly provides the ground-truth vector difference, making the probing amplitude completely inconsequential.

---

### 5.4 Inconsistency 4: The Anchor Integrity Gate and False Success Discrepancy

In `docs/v7_failure_analysis.md`, line 59:
> *"The calibrated vector drives the robot into empty space, resulting in False Success ($R_{\text{cov}} = 38\%$)."*

In `results/v7/v7_ablation_summary.csv`, line 40:
- Scenario: `CORRUPTED_ANCHOR_STRESS`, Configuration: `ABLATION_F_NO_ANCHOR_GATE`.
- `false_success_count` = **0**, `false_success_rate` = **0.0%**, `covered_risk` = **0.0%**, `abstention_rate` = **0.98%**.

**Mechanistic Root Cause:**
When the anchor gate was disabled, the robot indeed accepted the corrupted anchor bias ($\hat{\mathbf{b}} \approx [1.57, -1.0]\text{ m}$). However, once it entered `CALIBRATED` mode, line 345 of `src/aegis/v7/recovery_controller.py` executed:
```python
if range_reading.valid:
    current_residual = abs(calibrated_dist - range_reading.distance)
    if current_residual > 0.45:
        self.state.mode = "ABSTAIN"
        return np.zeros(2), "ABSTAIN", ...
```
As the robot steered toward the phantom target, the distance measured by the onboard radar range sensor ($r \approx 2.0\text{ m}$) diverged immediately from the calibrated target vector norm ($\|\mathbf{d}_{\text{cal}}\| \approx 3.5\text{ m}$). The secondary residual check exceeded $0.45\text{ m}$, forcing an emergency **`ABSTAIN`**. The robot stopped, never reached the phantom target, and never issued a `STOP` command.
Thus, `false_success` was mathematically 0 in the empirical data. The claim of $38\%$ covered risk in `v7_failure_analysis.md` was fabricated in the narrative documentation.

---

## 6. Mathematical Identifiability Audit

### 6.1 Two-Sensor Vector + Range Ambiguity ($H_4$)
Let $\mathbf{d}_t = \mathbf{p}^* - \mathbf{p}_t \in \mathbb{R}^2$ be the true target-relative position.
Suppose both vector sensors suffer identical spatial bias $\mathbf{b}_v \in \mathbb{R}^2$:
$$\mathbf{z}_{A, t} = \mathbf{d}_t + \mathbf{b}_v + \mathbf{w}_{A, t}, \quad \mathbf{z}_{B, t} = \mathbf{d}_t + \mathbf{b}_v + \mathbf{w}_{B, t}$$
The scalar range sensor measures:
$$r_t = \|\mathbf{d}_t\| + b_r + w_{r, t}$$
The vector disagreement is zero-mean: $\mathbb{E}[\mathbf{z}_{A, t} - \mathbf{z}_{B, t}] = \mathbf{0}$.
The cross-modal residual is:
$$e_t(\mathbf{b}) = \|\mathbf{z}_{v, t} - \mathbf{b}\| - r_t$$
If $b_r = 0$, $e_t(\mathbf{0}) = \|\mathbf{d}_t + \mathbf{b}_v\| - \|\mathbf{d}_t\| \neq 0$.
However, the observation sequence $\{(\mathbf{z}_{v, t}, r_t)\}_{t=1}^T$ can be equally explained by:
1. **Hypothesis 1:** Vector sensors biased by $\mathbf{b}_v$, range sensor nominal ($b_r = 0$).
2. **Hypothesis 2:** Vector sensors nominal ($\mathbf{b}_v = \mathbf{0}$), range sensor biased by $b_r(t) = -(\|\mathbf{d}_t + \mathbf{b}_v\| - \|\mathbf{d}_t\|)$.
3. **Hypothesis 3:** Both sensors rotated or scaled by a coupled transformation.

**Theorem (Rank Deficiency of 2-Sensor Relative Geometry):**
Under stationary translation without independent orientation references or known absolute anchor points, common-mode vector bias cannot be uniquely separated from time-varying range sensor distortion without active multi-axis motion that induces nonlinear line-of-sight curvature. Even with active motion, mirror-symmetry across the line of translation preserves ambiguity.
Therefore, V6's decision to abstain on $H_4$ was mathematically optimal for a 2-modality system. Breaking this ambiguity strictly requires an independent physical modality (such as the independent anchor introduced in V7).

---

## 7. Audit Conclusion & Next-Generation Directives

1. **Purge Unsupported Claims:** All references to "38% covered risk under corrupted anchor" and "hypothesis-discriminative MPC outperforming generic FIM" must be formally retracted in documentation.
2. **Implement Real Optimization-Based Control:** The next generation must implement either a genuine receding-horizon QP controller or transparently acknowledge proportional-derivative baselines.
3. **Reformulate the Research Question:** The next milestone must not claim novelty across four disjoint domains. It must define a single, rigorous, mathematically grounded research contribution tested against genuine competitive baselines.
