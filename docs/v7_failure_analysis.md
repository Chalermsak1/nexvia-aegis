# NEXVIA AEGIS V7.0 — Systematic Failure Analysis & Boundary Regimes
**Title:** Deep-Dive Failure Modes, Unidentifiable Regimes, and Safety Diagnostics  
**Document:** Official Failure Analysis & Diagnostic Case Studies  

---

## 1. Executive Summary

This failure analysis investigates anomalous episodes, edge cases, and architectural boundaries in AEGIS V7.0 across 3,000 main benchmark episodes and 2,000 component ablation evaluations.

We systematically classify failure modes into three primary operational categories:
1. **Dynamic & Control Failures:** Prediction horizon truncation, constraint fighting, and actuator saturation.
2. **Diagnostic & Estimation Failures:** Underdetermined common-mode ambiguities without anchor access, non-stationary drift tracking limits.
3. **Sensor Modality & Anchoring Failures:** Corrupted anchor attacks, false symmetry breaking, and radar-anchor inconsistency rejections.

---

## 2. Taxonomy of Analyzed Failure Modes

| Case Study | Scenario | Policy Variant | Manifestation | Root Cause | Architectural Defense |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Case 1** | `PRIMARY_BIAS` | `ABLATION_B_NO_TERMINAL_BRAKING` | Kinetic Overshoot past target | Unconstrained rolling momentum in MuJoCo | Active terminal velocity penalty ($w_{\text{term}} \|\mathbf{v}_N\|^2$) |
| **Case 2** | `CORRELATED_BIAS` | `AEGIS_V7_MPC_NO_ANCHOR` | Conservative Abstention ($98\%$) | Unidentifiable 2-sensor geometry ($H_4$) | Event-triggered 3rd modality query (AEGIS-Anchor) |
| **Case 3** | `CORRUPTED_ANCHOR_STRESS` | `ABLATION_F_NO_ANCHOR_GATE` | False Success ($R_{\text{cov}} = 38\%$) | Poisoned anchor (+1.2m bias) accepted blindly | Anchor Integrity Gate cross-check against radar range |
| **Case 4** | `FAULTY_REFERENCE_SENSOR` | `AEGIS_V7_MPC_ON_DEMAND` | Planned Abstention ($0.0\%$ False Success)| Range sensor biased (+1.0m); anchor disagrees | $H_3$ Veto Gate prevents corrupted recalibration |
| **Case 5** | `LOW_OBSERVABILITY` | `AEGIS_V7_MPC_GENERIC_FIM` | Premature Abort | Collinear 1D motion yields $\text{rank}(\mathbf{F}) = 1$ | Transverse spatial excitation & $H_6$ Ambiguity code |

---

## 3. Deep-Dive Case Studies

### 3.1 Case 1: The Rolling Sphere Momentum Overshoot
- **Observation:** In `ABLATION_B_NO_TERMINAL_BRAKING`, the terminal velocity penalty is zeroed ($w_{\text{term}} = 0.0$).
- **Physics Trace:**
  - During the 32 probing steps, lateral thrust accelerates the robot to $\sim 0.38\text{ m/s}$.
  - At step 32, calibration succeeds with low bias error ($\|\hat{\mathbf{b}} - \mathbf{b}^*\| = 0.08\text{ m}$).
  - However, because the sphere has nearly zero rolling friction on the MuJoCo plane, it enters the approach phase with high transverse velocity.
  - The single-step approach planner issues braking forces, but due to the $1.0\text{ N}$ force limit and $m=1.0\text{ kg}$, maximum deceleration is $a_{\max} = 1.0\text{ m/s}^2$. The robot requires $\Delta x_{\text{brake}} = \frac{v^2}{2a} \approx 0.07\text{ m}$ to stop.
  - The robot overshoots the $0.22\text{ m}$ target zone, tripping the cross-modal residual monitor ($r > 0.45\text{ m}$) and forcing an emergency abort.
- **V7 Full Resolution:** Enforcing $w_{\text{term}} = 12.0$ inside the MPC cost forces the optimizer to schedule counter-thrust during steps $N-2$ to $N$, ensuring the robot finishes probing with terminal velocity $\|\mathbf{v}_N\| \le 0.06\text{ m/s}$.

---

### 3.2 Case 2: Common-Mode Vector Corruption ($H_4$) Without Anchor
- **Observation:** In `AEGIS_V7_MPC_NO_ANCHOR`, both vector sensors are biased by $\mathbf{b} = [+0.7, +0.7]^T$, and the anchor sensor is disabled.
- **Mathematical Boundary:**
  - Vector discrepancy: $\|\mathbf{z}_a - \mathbf{z}_b\| = 0.02\text{ m}$ (within noise).
  - Cross-modal residual: $|\|\mathbf{z}_v\| - z_r| \approx 0.72\text{ m}$.
  - Without an independent absolute reference, the system cannot mathematically distinguish whether:
    $$\text{Hypothesis A: } \mathbf{b}_v = [0.7, 0.7]^T, b_r = 0 \quad \text{vs.} \quad \text{Hypothesis B: } \mathbf{b}_v = [0, 0]^T, b_r = -0.72\text{ m}$$
- **V7 Defense:** The agent correctly identifies that this fault is algebraically unidentifiable, maintains high diagnostic entropy ($\mathcal{H} = 1.34\text{ nats}$), and issues `ABSTAIN_H4_CORRELATED_BIAS`. False success is strictly maintained at $0.0\%$.

---

### 3.3 Case 3: Adversarial / Corrupted Anchor Attack
- **Observation:** In `CORRUPTED_ANCHOR_STRESS`, vector sensors are biased by $[+0.7, +0.7]^T$, but the queried anchor is also corrupted with an adversarial bias $\mathbf{b}_{\text{anchor}} = [+1.2, -1.0]^T$.
- **Vulnerability Under Ablation F (No Anchor Gate):**
  - If the controller naively trusts the anchor, it infers vector bias $\hat{\mathbf{b}} = \mathbf{z}_v - \mathbf{z}_{\text{anchor}} = [-0.5, 1.7]^T$.
  - The calibrated vector drives the robot into empty space, resulting in False Success ($R_{\text{cov}} = 38\%$).
- **V7 Full Defense (Anchor Integrity Gate):**
  - The Anchor Integrity Gate computes:
    $$\Delta_{\text{range}} = |\|\mathbf{z}_{\text{anchor}}\| - z_{\text{range}}| = |3.12 - 2.01| = 1.11\text{ m}$$
  - Since $1.11\text{ m} > \text{tolerance} = 0.35\text{ m}$, the gate rejects the anchor:
    `REJECTED_ANCHOR_RANGE_INCONSISTENT`
  - The controller detects that the anchor is untrustworthy, rejects calibration, and transitions to safe `ABSTAIN`. False success remains at **$0.0\%$**.

---

## 4. Key Takeaways for Operational Deployment

1. **Physical Dynamics Must Constrain Information Gathering:**
   A trajectory that optimizes information gain on paper is useless if the accumulated kinetic energy causes control failure at the transition boundary.
2. **Anchor Modalities Must Be Verified, Never Assumed Perfect:**
   Adding an independent sensor resolves unidentifiable regimes, but introduces a new failure surface (anchor poisoning). Multi-modal cross-checking is essential.
3. **Selective Anchoring Preserves System Lifetime:**
   Calling the anchor on every step provides zero additional recovery benefit over selective event-triggered queries, while increasing operational costs by over $300\%$.
