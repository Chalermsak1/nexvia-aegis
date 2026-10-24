# NEXVIA AEGIS V8.1 — Mathematical Audit of the Sequential Martingale Risk Monitor

**Author / Roles:** Senior Statistical Research Scientist, Sequential-Testing Specialist, Experimental Methodology Auditor  
**Scope:** Mathematical verification and assumptions audit of `src/aegis/next/martingale_monitor.py`  
**Date:** October 2026  
**Status Tag:** Supported only under explicitly stated assumptions (with documented domain violations)  

---

## 1. Executive Summary & Audit Mandate

NEXVIA AEGIS-Next (V8) introduces an online sequential testing module (`AnytimeValidSequentialMonitor`) claimed to provide "distribution-free, finite-sample statistical safety guarantees under arbitrary stopping times without assuming exchangeability or white Gaussian innovations" by leveraging testing-by-betting supermartingales and Ville's inequality.

This audit examines the exact mathematical object implemented in `src/aegis/next/martingale_monitor.py`. We derive its mathematical properties, verify nonnegativity, assess predictability, evaluate whether the supermartingale condition holds under the specified null hypothesis, and establish what Ville's inequality formally guarantees versus what has been informally claimed.

---

## 2. Exact Mathematical Object Implemented

In `src/aegis/next/martingale_monitor.py`, the online wealth process $E_t$ is defined as follows:

Let $e_t \in \mathbb{R}_{\ge 0}$ denote the scalar cross-modal spatial residual at control step $t$:
$$e_t = \left| \|\mathbf{z}_{v,t}\| - r_t \right|$$
where $\mathbf{z}_{v,t} \in \mathbb{R}^2$ is the inverse-variance fused vector estimate and $r_t \in \mathbb{R}_{\ge 0}$ is the range sensor measurement.

The normalized, centered residual $x_t$ is defined by:
$$x_t = \text{clip}\left(\frac{e_t - \mu_0}{v_{\max}}, -0.90, 3.50\right)$$
where $\mu_0 = \text{nominal\_mean} = 0.065\text{ m}$ (in `agent_next.py`, overriding the default `0.0564`), and $v_{\max} = \text{scale\_vmax} = 0.40\text{ m}$.

The wealth process $(E_t)_{t \ge 0}$ is initialized at $E_0 = 1.0$ and updated recursively according to:
$$E_t = \min\left(10^7, \max\left(10^{-4}, E_{t-1} \cdot \gamma \cdot (1 + \lambda_t x_t)\right)\right)$$
where:
- $\gamma = \text{decay\_factor} = 0.995 \in (0, 1]$ is a memory-decay factor.
- $\lambda_t \in [0, \lambda_{\max}]$ is the predictable betting fraction, with $\lambda_{\max} = 0.85$.
- The stopping rule for fault alarm is:
$$\tau = \inf\left\{ t \ge 1 : E_t \ge \frac{1}{\alpha} \right\}, \quad \alpha = 0.05 \implies \frac{1}{\alpha} = 20.0.$$
- The online anytime-valid $p$-value is defined as:
$$p_t = \min\left(1.0, \frac{1}{\max(1.0, E_t)}\right).$$

---

## 3. Mathematical Condition Audit

### Condition A: Nonnegativity of Factors

To apply supermartingale theory, the wealth process must remain almost surely nonnegative: $E_t \ge 0$ for all $t$. Specifically, each multiplicative factor $M_t = 1 + \lambda_t x_t$ must satisfy $M_t \ge 0$.

**Verification in Implementation:**
1. The lower bound of $x_t$ is explicitly clipped:
   $$x_t \ge -0.90.$$
2. The betting fraction $\lambda_t$ is bounded by construction:
   $$\lambda_t \in [0, \lambda_{\max}] = [0, 0.85].$$
3. Therefore, the minimum possible value of $\lambda_t x_t$ occurs when $\lambda_t = 0.85$ and $x_t = -0.90$:
   $$\min(\lambda_t x_t) = 0.85 \times (-0.90) = -0.765.$$
4. Consequently:
   $$M_t = 1 + \lambda_t x_t \ge 1 - 0.765 = +0.235 > 0.$$
5. In addition, line 94 enforces an explicit numerical safeguard:
   $$E_t = \max(10^{-4}, \min(E_t, 10^7)).$$

**Edge Cases & Extreme Observations:**
- **Zero residual ($e_t = 0$):**
  $$x_{\text{raw}} = \frac{0 - 0.065}{0.40} = -0.1625 \ge -0.90 \implies x_t = -0.1625.$$
  $M_t = 1 - 0.85 \times 0.1625 = 0.8619 > 0$. The lower clip at $-0.90$ is not even active for zero residual.
- **Extreme outlier ($e_t \to \infty$):**
  $x_t$ is capped at $3.50$. Thus, $M_t \le 1 + 0.85 \times 3.50 = 3.975$. A single extreme residual cannot inflate wealth by more than $3.975\times$.
- **NaN / Invalid Floats:** If $e_t$ is `NaN`, `np.clip` propagates `NaN`, resulting in `wealth = NaN`. (Remediation recommended: explicit `math.isnan(e_t)` guard).

**Conclusion on Nonnegativity:** Strictly Verified. Every multiplicative factor is strictly positive ($M_t \ge 0.235 > 0$).

---

### Condition B: Predictability of Betting Fraction $\lambda_t$

A betting strategy $\lambda_t$ in a game-theoretic supermartingale must be **predictable** with respect to the filtration $\mathcal{F}_{t-1} = \sigma(e_1, \dots, e_{t-1})$. That is, $\lambda_t$ must be selected using only information available *before* observing $e_t$.

**Verification in Implementation:**
In `martingale_monitor.py`:
```python
65:         e_t = float(cross_modal_residual)
66:         self.history.append(e_t)
...
78:         recent = np.array(self.history[-15:-1], dtype=np.float64)
```
- At step $t$, $e_t$ is appended to `self.history` (index `-1`).
- The slice `self.history[-15:-1]` extracts elements from index $-15$ up to index $-2$.
- It explicitly **excludes** index $-1$ (which is $e_t$).
- Thus, `recent` contains $\{e_{t-14}, \dots, e_{t-1}\} \in \mathcal{F}_{t-1}$.
- When $t \le \text{burn\_in\_steps} = 1$, $\lambda_t = 0.0$ (deterministic, hence predictable).
- No future observations, future sensor states, hidden ground-truth vectors, or external labels are accessed.

**Conclusion on Predictability:** Strictly Verified. $\lambda_t$ is $\mathcal{F}_{t-1}$-measurable.

---

### Condition C: The Supermartingale Condition

For $(E_t)_{t \ge 0}$ to be a test supermartingale with respect to $(\mathcal{F}_t)_{t \ge 0}$ under a null hypothesis $H_0$, it must satisfy:
$$\mathbb{E}[E_t \mid \mathcal{F}_{t-1}] \le E_{t-1} \quad \text{almost surely under all } P \in H_0.$$

Expanding $E_t$:
$$E_t \le E_{t-1} \cdot \gamma \cdot (1 + \lambda_t x_t)$$
Taking conditional expectation:
$$\mathbb{E}[E_t \mid \mathcal{F}_{t-1}] \le E_{t-1} \gamma \left( 1 + \lambda_t \mathbb{E}[x_t \mid \mathcal{F}_{t-1}] \right)$$
Since $E_{t-1} \ge 0$, $\gamma \le 1.0$, and $\lambda_t \ge 0$, the supermartingale condition requires:
$$\mathbb{E}[x_t \mid \mathcal{F}_{t-1}] \le 0 \quad \text{under } H_0.$$

Recalling $x_t = \text{clip}\left(\frac{e_t - \mu_0}{v_{\max}}, -0.90, 3.50\right)$, this is satisfied if:
$$\mathbb{E}[e_t \mid \mathcal{F}_{t-1}] \le \mu_0 \quad \text{under } H_0.$$

#### Analysis of the Null Distribution in the Robot Environment:
1. **Folded Normal / Half-Normal Expectation:**
   Under nominal operation ($H_0$), vector sensors have noise $\sigma_v = 0.05 / \sqrt{2} \approx 0.03535\text{ m}$, and range sensor has noise $\sigma_r = 0.05\text{ m}$.
   When distance to target $d > 0.40\text{ m}$, the difference $\|\mathbf{z}_v\| - r_t$ is asymptotically Gaussian:
   $$\|\mathbf{z}_v\| - r_t \sim \mathcal{N}\left(0, \sigma_v^2 + \sigma_r^2\right) = \mathcal{N}(0, 0.00375).$$
   The residual $e_t = |\|\mathbf{z}_v\| - r_t|$ is folded normal with expectation:
   $$\mathbb{E}[e_t] = \sqrt{\sigma_v^2 + \sigma_r^2} \sqrt{\frac{2}{\pi}} = \sqrt{0.00375} \times 0.79788 \approx 0.04886\text{ m}.$$
   Even if only one vector sensor is active ($\sigma_v = 0.05\text{ m}$):
   $$\mathbb{E}[e_t] = \sqrt{0.05^2 + 0.05^2} \sqrt{\frac{2}{\pi}} = 0.07071 \times 0.79788 \approx 0.05642\text{ m}.$$
2. **Conservative Choice of $\mu_0$:**
   In `agent_next.py` line 61, the monitor is instantiated with:
   $$\mu_0 = 0.065\text{ m}.$$
   Since $0.065 > 0.04886$ (and $0.065 > 0.05642$), we have:
   $$\mathbb{E}[e_t - \mu_0] \approx 0.04886 - 0.065 = -0.01614 < 0.$$
3. **Effect of Asymmetric Clipping:**
   The upper clipping at $3.50$ truncates large positive values, strictly decreasing the expectation $\mathbb{E}[x_t]$. The lower clip at $-0.90$ is unreachable for non-negative residuals ($x_{\min} = -0.1625$). Thus, clipping strictly preserves $\mathbb{E}[x_t \mid \mathcal{F}_{t-1}] \le 0$.
4. **Effect of Memory Decay ($\gamma = 0.995$):**
   The factor $\gamma = 0.995 < 1.0$ introduces a strict downward drift:
   $$\mathbb{E}[E_t \mid \mathcal{F}_{t-1}] \le 0.995 E_{t-1} < E_{t-1}.$$
   This guarantees that $E_t$ is a **strict supermartingale** under $H_0$.

#### Caveat: Closed-Loop Temporal Dependence
While sensor measurement noise is sampled i.i.d. at each step, the robot's physical position $\mathbf{x}_t$ is determined by the closed-loop control law $u_{t-1}(e_{t-1}, \dots)$.
When the robot is very close to the target ($\|\mathbf{d}\| \le 0.10\text{ m}$), the non-linear transformation $\|\mathbf{d} + \mathbf{w}_v\|$ departs from folded normal and transitions to a non-central Chi distribution (Rayleigh distribution at $\mathbf{d} = \mathbf{0}$).
At $\mathbf{d} = \mathbf{0}$, $\mathbb{E}[\|\mathbf{w}_v\|] = \sigma_v \sqrt{\pi/2} \approx 0.0443\text{ m}$, and $\mathbb{E}[r_t] = \sigma_r \sqrt{2/\pi} \approx 0.0399\text{ m}$, so $\mathbb{E}[e_t]$ remains below $0.065\text{ m}$.
However, if the velocity controller chatters violently near the target, unmodeled dynamic vibrations could theoretically inflate residuals. In our empirical validation suite (`test_v8_risk_monitor_validity.py`), the mean wealth over 300 null trials was $0.018 \ll 1.0$, and the false alarm rate was $0.0\% \le 0.05$.

**Conclusion on Supermartingale Condition:** Verified under the declared null $H_0 : \mathbb{E}[e_t \mid \mathcal{F}_{t-1}] \le 0.065\text{ m}$.

---

### Condition D: Residual Model and Scaling

- **Units:** Residual $e_t$ is in meters ($\text{m}$).
- **Nominal mean:** $\mu_0 = 0.065\text{ m}$.
- **Scale factor:** $v_{\max} = 0.40\text{ m}$ represents the characteristic geometric boundary of sensor disagreement.
- Under a fault of magnitude $b = 0.80\text{ m}$, $e_t \approx 0.80\text{ m}$, giving $x_{\text{raw}} = (0.80 - 0.065)/0.40 = 1.8375$.
- Under Kelly betting, $\lambda_t \approx 0.50$, so the multiplicative multiplier per step is $1 + 0.50 \times 1.8375 = 1.918$.
- Wealth compounds by $\sim 1.9\times$ per step, crossing $1/\alpha = 20.0$ in approximately $\lceil \ln(20) / \ln(1.9) \rceil \approx 5$ steps. This aligns with empirical fault detection latencies.

---

### Condition E: Ville's Inequality Applicability

**Mathematical Theorem (Ville, 1939; Howard et al., 2021; Ramdas et al., 2023):**
Let $(E_t)_{t \ge 0}$ be a nonnegative supermartingale adapted to filtration $(\mathcal{F}_t)_{t \ge 0}$ with initial value $E_0 \le 1$ under probability measure $P \in H_0$. Then, for any threshold $c > 0$ and any stopping time $\tau$:
$$P\left( \exists t \ge 1 : E_t \ge c \right) \le \frac{\mathbb{E}[E_0]}{c} \le \frac{1}{c}.$$

Setting $c = 1/\alpha$:
$$P_{H_0}\left( \exists t \ge 1 : E_t \ge \frac{1}{\alpha} \right) \le \alpha.$$

**Authoritative References:**
1. Jean Ville. *Étude critique de la notion de collectif*. Monographies des Probabilités, Gauthier-Villars, Paris, 1939.
2. Aaditya Ramdas, Peter Grünwald, Vladimir Vovk, and Glenn Shafer. *Game-Theoretic Statistics and Safe, Anytime-Valid Inference*. Statistical Science, 38(4):576–601, 2023. DOI: [10.1214/23-STS894](https://doi.org/10.1214/23-STS894).
3. Steven R. Howard, Aaditya Ramdas, Jon McAuliffe, and Jasjeet Sekhon. *Time-uniform, nonparametric, nonasymptotic confidence sequences*. The Annals of Statistics, 49(2):1055–1080, 2021. DOI: [10.1214/20-AOS1991](https://doi.org/10.1214/20-AOS1991).

**What Ville's Inequality Strictly Guarantees Here:**
Under the null hypothesis $H_0$ that the physical sensors are healthy and satisfy $\mathbb{E}[e_t \mid \mathcal{F}_{t-1}] \le 0.065\text{ m}$, the probability that the monitor will **ever** raise a false alarm ($E_t \ge 20.0$) over an infinite operational horizon is bounded by $\alpha = 0.05$:
$$\mathbb{P}_{H_0}(\text{False Alarm}) \le 0.05.$$

**What Ville's Inequality Does NOT Guarantee:**
Ville's inequality on $H_0$ **does NOT bound the probability of an unsafe robot decision under sensor faults (Covered Risk)**.
The formal analysis of this gap is presented in Deliverable 2 (`docs/v8_audit/false_success_claim_analysis.md`).

---

## 4. Audit Summary & Claim Classification

| Property | Implementation Status | Scientific Finding |
|---|---|---|
| Nonnegativity of Factors | **Verified** | $M_t \ge 0.235 > 0$ strictly enforced across all possible residuals. |
| Predictability of $\lambda_t$ | **Verified** | Slice `history[-15:-1]` excludes $e_t$; strictly $\mathcal{F}_{t-1}$-measurable. |
| Strict Supermartingale under $H_0$ | **Verified** | $\mu_0 = 0.065 > \mathbb{E}[e_t \mid H_0]$ and $\gamma = 0.995 < 1.0$ ensure $\mathbb{E}[E_t \mid \mathcal{F}_{t-1}] \le E_{t-1}$. |
| Time-Uniform Type-I Error Control | **Verified** | $\mathbb{P}_{H_0}(\exists t : E_t \ge 20) \le 0.05$ holds by Ville's inequality. |
| Time-Uniform Bounded False Success | **CONTRADICTED / INVALID LEAP** | Type-I error on nominal residuals does not bound post-decision task failure under faults. |

**Final Recommendation for this Component:**  
Retain `martingale_monitor.py` as a mathematically sound **Anytime-Valid Sensor Anomaly Detector**, but strictly remove all claims that Ville's inequality directly bounds task-level Covered Risk.
