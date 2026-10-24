# NEXVIA AEGIS V8.1 — Baseline Fairness & Comparative Audit

**Author / Roles:** Robotics Assurance Engineer, Experimental Methodology Auditor  
**Scope:** Source-level audit of baseline implementations in `src/aegis/next/baselines.py`, evaluation of EKF low-coverage pathology, and paired V7-to-V8 noninferiority testing  
**Date:** October 2026  
**Status Tag:** Independently reproduced and verified (with baseline pathology and noninferiority limits documented)  

---

## 1. Executive Summary

This audit evaluates the integrity, fairness, and implementation quality of the seven baseline controllers in `src/aegis/next/baselines.py` evaluated against `AegisNextController`.

### Key Audit Findings:
1. **Information Isolation:** None of the 8 controllers receive ground-truth robot position, ground-truth target position, or fault labels. All policies operate strictly on `SensorReading`, `RangeReading`, and `AnchorReading` objects.
2. **EKF Consistency Pathology (Section 8):** The Extended Kalman Filter consistency monitor's reported "0.0% Covered Risk" is an artifact of **extreme, near-total abstention (97.0% abstention rate, 3.0% coverage)**. In 6 out of 10 scenarios, EKF accepted zero decisions. Even under nominal noise, EKF abstained on 78.0% of episodes due to permanent single-step innovation latching. EKF is completely Pareto-dominated by AEGIS-Next.
3. **Paired V7 vs. V8 Noninferiority (Section 9):** The reported True Success rate difference between V7 (53.4%) and V8 (50.2%) is $-3.20\%$ (McNemar exact $p = 0.1371$). However, the 95% Wald CI for the paired difference is **$[-7.15\%, +0.75\%]$**. Because the lower bound ($-7.15\%$) is worse than a standard $5.0\%$ noninferiority margin ($\Delta_{\text{NI}} = -0.05$), **noninferiority is NOT formally established at the 5% margin**.
4. **Safety & Cost Trade-Off:** The 3.2 percentage point drop in True Success purchased a **$64.7\%$ reduction in false-success events** (17 down to 6) and a **$70.8\%$ reduction in anchor query costs** (0.1440 down to 0.0421, paired $t$-test $p = 5.85 \times 10^{-76}$).

---

## 2. Policy-by-Policy Implementation Audit (Section 11)

| Controller | Intended Classical Method | Implementation Fidelity | Information Isolation | Weakened or Handicapped? |
|---|---|---|---|---|
| **1. Unshielded Always Act** | Proportional pursuit, zero verification | High | Strict: uses raw inverse-variance vector | No (Standard naive pursuit baseline) |
| **2. Chi-Square NIS Gating** | Inter-sensor Normalized Innovation Squared ($\chi_2^2 \le 5.991$) | High | Strict: vector difference only | No (Properly filters transient glitches via 2 consecutive breaches) |
| **3. EKF Consistency Monitor** | EKF state tracking with range innovation gating ($r_{\text{innov}}^2 / S \le 9.0$) | Medium (Lacks recovery / unlatch) | Strict: vector + range innovations | Yes: Single step $> 3\sigma$ triggers permanent latching |
| **4. AEGIS V4 Passive Verify** | Cross-modal geometric threshold ($|\|z_v\| - r| \le 0.35\text{ m}$) | High | Strict: vector norm vs range | No (Authentic V4 implementation) |
| **5. AEGIS V5 Huber Calibrate** | Fixed 2-phase orthogonal probing + Huber M-estimator | High | Strict: observations + FIM gate | No (Authentic V5 implementation) |
| **6. AEGIS V6 Discriminative** | 7-hypothesis Bayesian diagnosis + active probing | High | Strict: multi-hypothesis engine | No (Authentic V6 implementation) |
| **7. AEGIS V7 MPC Baseline** | Quadratic pseudo-MPC + on-demand anchor query | High | Strict: anchor gate + MPC | No (Authentic V7 implementation) |
| **8. AEGIS-Next (V8)** | Martingale monitor + velocity controller + event-anchor | High | Strict: martingale wealth gating | No |

---

## 3. The Low-Coverage Baseline: EKF Consistency Monitor (Section 8)

In the original benchmark report, `EKF_CONSISTENCY_MONITOR` is recorded with `covered_risk = 0.0000` ($0.0\%$), creating the misleading impression that it is the safest policy.

### 3.1 Mechanistic Pathology
Inspection of lines 196–220 in `src/aegis/next/baselines.py` reveals the structural cause of this failure:
```python
215: innov = norm_est - range_reading.distance
216: norm_innov_sq = (innov**2) / max(S_range, 1e-8)
217: if norm_innov_sq > self.gate_threshold:
218:     self.mode = "ABSTAIN"
219:     return np.zeros(2), "ABSTAIN", self.d_hat, False
```
1. **Instantaneous Single-Step Trigger:** The innovation gate threshold is set to $3\sigma$ ($\text{gate\_threshold} = 9.0$). In a 300-step episode, the probability of at least one nominal Gaussian sample exceeding $3\sigma$ is:
   $$1 - (1 - 0.0027)^{300} \approx 1 - 0.444 = \mathbf{55.6\%}.$$
2. **Permanent Latch without Recovery:** Once `self.mode = "ABSTAIN"` is set, the controller permanently stops moving and never re-evaluates innovation, even if subsequent measurements are healthy.
3. **Finite-Difference Velocity Drift:** `_velocity` is estimated via finite differences of noisy vector measurements, inducing high-frequency chatter in the kinematic prediction step ($d_{k+1} = d_k - v \Delta t$), which artificially inflates the innovation variance.

### 3.2 Quantitative Impact
- **Total Episodes:** 500
- **Total Accepted Decisions:** **15** ($3.0\%$ coverage)
- **Total Abstained Episodes:** **485** ($97.0\%$ abstention rate)
- **True Successes in Nominal:** Only 11 out of 50 episodes completed ($22.0\%$ coverage in benign noise!).
- **True Successes across all 9 Fault Scenarios:** Exactly 4 episodes out of 450 completed ($0.88\%$).

### 3.3 Risk–Coverage Pareto Analysis
A policy that achieves zero false successes by refusing to operate on 97% of tasks cannot be claimed to be safer than a policy that achieves 51.4% task coverage with a 2.33% risk profile. On the Risk–Coverage frontier:
- EKF achieves $(3.0\% \text{ coverage}, 0.0\% \text{ risk})$.
- AEGIS-Next achieves $(51.4\% \text{ coverage}, 2.33\% \text{ risk})$.
AEGIS-Next completes **$17.1\times$ more tasks** while maintaining rigorous empirical risk control.

---

## 4. Paired Statistical Comparison: V7 vs. AEGIS-Next (Section 9)

The report states:
> *"AEGIS-Next achieved 50.2% True Success vs 53.4% for V7, with no statistically significant drop (McNemar $p = 0.32$)."*

This audit re-evaluated all 500 matched seed pairs using exact statistical tests.

### 4.1 Contingency Table for True Success (500 Matched Episodes)

| | AEGIS-Next Failed ($TS=0$) | AEGIS-Next Succeeded ($TS=1$) | Total V7 |
|---|---|---|---|
| **V7 Failed ($TS=0$)** | $n_{00} = 190$ | $n_{01} = \mathbf{43}$ (V8 win) | 233 |
| **V7 Succeeded ($TS=1$)** | $n_{10} = \mathbf{59}$ (V7 win) | $n_{11} = 208$ | 267 |
| **Total AEGIS-Next** | 249 | 251 | **500** |

- Concordant pairs ($n_{00} + n_{11}$): $190 + 208 = 398$ ($79.6\%$).
- Discordant pairs ($b = n_{01}, c = n_{10}$): $43 + 59 = 102$ ($20.4\%$).

### 4.2 McNemar Test Recalculation
Under the exact two-sided binomial test on discordant pairs:
$$p = \text{binomtest}(43, 102, 0.5) = \mathbf{0.1371}.$$
- The previously reported $p = 0.32$ is **incorrect**. The exact $p$-value is $0.1371$.
- While $p = 0.1371 > 0.05$ indicates that the difference is not statistically significant at the 5% level, **failing to reject superiority is NOT proof of noninferiority**.

### 4.3 Noninferiority Analysis
Let $\Delta = p_{\text{V8}} - p_{\text{V7}}$ denote the true paired difference in success rate.
- Point estimate: $\hat{\Delta} = 50.2\% - 53.4\% = \mathbf{-3.20\%}$.
- Standard error of paired difference:
  $$\text{SE}(\hat{\Delta}) = \frac{\sqrt{b + c - (b - c)^2 / N}}{N} = \frac{\sqrt{102 - 16^2 / 500}}{500} = \frac{\sqrt{102 - 0.512}}{500} = \mathbf{0.02015} \quad (2.02\%).$$
- Two-sided 95% Wald Confidence Interval:
  $$\hat{\Delta} \pm 1.95996 \times \text{SE} = -3.20\% \pm 3.95\% = \mathbf{[-7.15\%, +0.75\%]}.$$

**Pre-declared Noninferiority Margin Test:**
- If the noninferiority margin is pre-declared at $\Delta_{\text{NI}} = 5.0\%$ (i.e. we require $95\%$ confidence that V8 is not worse than V7 by more than 5 percentage points):
  $$\text{Lower Bound} = -7.15\% < -5.00\%.$$
  **Result:** Noninferiority **FAILS** at the 5% margin!
- To claim noninferiority, the tolerance margin would need to be widened to at least $\Delta_{\text{NI}} = 7.15\%$.

### 4.4 The Full Trade-Off Matrix

| Metric | V7 Baseline | AEGIS-Next (V8) | Net Change | Statistical Significance |
|---|---|---|---|---|
| **True Success Rate** | 53.4% (267/500) | 50.2% (251/500) | $-3.20\%$ | McNemar exact $p = 0.1371$ (95% CI: $[-7.15\%, +0.75\%]$) |
| **False Success Count** | 17 episodes (3.4%) | 6 episodes (1.2%) | **$-64.7\%$** | Fisher exact $p = 0.033$ (Statistically significant reduction) |
| **Covered Risk ($FS / \text{Cov}$)** | 5.99% (17/284) | 2.33% (6/257) | **$-61.1\%$** | Significant improvement in decision safety |
| **Mean Anchor Cost** | 0.1440 | 0.0421 | **$-70.8\%$** | Paired $t$-test $p = 5.85 \times 10^{-76}$ (Extremely significant savings) |
| **Max Overshoot (m)** | 0.0687 m | 0.0751 m | $+0.0064\text{ m}$ | Paired $t$-test $p = 0.084$ (Not statistically significant) |

**Conclusion:** AEGIS-Next sacrifices 3.2 percentage points of task completion to achieve a massive $64.7\%$ reduction in hazardous false successes and a $70.8\%$ reduction in expensive auxiliary sensor queries. This trade-off must be reported transparently rather than claiming unproven equivalence.
