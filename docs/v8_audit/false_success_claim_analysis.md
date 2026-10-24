# NEXVIA AEGIS V8.1 — False-Success Risk Claim Audit & Gap Analysis

**Author / Roles:** Senior Statistical Research Scientist, Sequential-Testing Specialist, Robotics Assurance Auditor  
**Scope:** Deconstruction of the claimed mathematical link between Ville's inequality and robot Covered Risk  
**Date:** October 2026  
**Status Tag:** Contradicted by statistical theory (Conflation of Type-I Error with Posterior Decision Risk)  

---

## 1. Executive Summary

A central claim in the NEXVIA AEGIS-Next (V8) report is that:
> *"Ville's inequality ($P(\exists t \ge 1 : E_t \ge 1/\alpha) \le \alpha$) provides a distribution-free, finite-sample statistical safety guarantee strictly bounding Covered Risk below 5%."*

This audit proves that this claim represents a **fundamental category error** in statistical inference. 

Specifically, the report conflates **Type-I error control under a null hypothesis of healthy sensor operation** with **posterior selective risk control of a closed-loop robot terminal decision**.

While the empirical evaluation of AEGIS-Next across 4,000 policy-episodes produced a low empirical Covered Risk (2.33% pooled), this outcome is an **empirical property of the benchmark sample and the multi-stage recovery architecture**, **NOT** a theoretical corollary of Ville's inequality.

---

## 2. Dissection of the Operational Events

To establish clarity, we define the seven distinct stochastic events governing the AEGIS control architecture:

| Symbol | Event Name | Mathematical Definition | Controlled by Ville's Inequality? |
|---|---|---|---|
| $\mathcal{E}_{\text{anom}}$ | **Abnormal Residual Detection** | $\{ \exists t : e_t > \tau_e \}$ | No (depends on threshold $\tau_e$) |
| $\mathcal{E}_{\text{FA}}$ | **False Alarm under Nominal** | $\{ \exists t \ge 1 : E_t \ge 1/\alpha \mid H_0 \}$ | **YES: $\mathbb{P}(\mathcal{E}_{\text{FA}}) \le \alpha$ by Ville** |
| $\mathcal{E}_{\text{MD}}$ | **Missed Detection under Fault** | $\{ \forall t \le T : E_t < 1/\alpha \mid H_A \}$ | **NO (Type-II error / Power of test)** |
| $\mathcal{E}_{\text{attr}}$ | **Incorrect Fault Attribution** | $\{ \hat{H} \ne H^* \mid \text{Fault Detected} \}$ | **NO (Bayesian diagnostic error)** |
| $\mathcal{E}_{\text{accept}}$ | **Accepted Decision (Coverage)** | $\{ \text{Terminal Decision} = \text{STOP} \}$ | **NO (Policy decision logic)** |
| $\mathcal{E}_{\text{FS}}$ | **False Success** | $\{ \text{Decision} = \text{STOP} \} \cap \{ d_{\text{final}} > 0.45\text{ m} \}$ | **NO (Closed-loop task outcome)** |
| $\mathcal{R}_{\text{cov}}$ | **Covered Risk (Selective Risk)** | $\mathbb{P}(d_{\text{final}} > 0.45\text{ m} \mid \text{Decision} = \text{STOP})$ | **NO (Conditional posterior probability)** |

---

## 3. Mathematical Proof of the Missing Link

### 3.1 What the Martingale Actually Tests

The test supermartingale $E_t$ in `martingale_monitor.py` tests the null hypothesis:
$$H_0 : \mathbb{E}[e_t \mid \mathcal{F}_{t-1}] \le \mu_0 = 0.065\text{ m}.$$
Under $H_0$, sensors are nominal and uncorrupted. Ville's inequality establishes:
$$\mathbb{P}_{H_0}\left( \bigcup_{t=1}^\infty \{ E_t \ge 20.0 \} \right) \le 0.05.$$
This means: **If the world is completely healthy, the probability that the robot ever falsely believes a sensor is broken is at most 5%.**

### 3.2 What Covered Risk Actually Measures

Covered Risk (selective risk) is the conditional probability that a completed mission is unsafe:
$$\mathcal{R}_{\text{cov}} = \mathbb{P}\left( d_{\text{final}} > 0.45\text{ m} \;\middle|\; \text{Decision} = \text{STOP} \right) = \frac{\mathbb{P}(\text{False Success})}{\mathbb{P}(\text{Accepted Decision})}.$$

A False Success occurs when:
1. A sensor fault occurs ($H_A \in \{H_1, H_2, H_3, H_4, \dots\}$).
2. The robot makes a `STOP` decision (meaning it did **not** permanently `ABSTAIN`).
3. The robot's final physical position is farther than $0.45\text{ m}$ from the target.

### 3.3 Why Ville's Inequality Does Not Bound False Success

Let us formally evaluate the probability of False Success under a fault distribution $P_{H_A}$:

$$\mathbb{P}(\text{False Success}) = \mathbb{P}(\text{STOP} \cap d_{\text{final}} > 0.45) = \mathbb{P}_{H_0}(\text{STOP} \cap d > 0.45) \mathbb{P}(H_0) + \sum_{i=1}^M \mathbb{P}_{H_i}(\text{STOP} \cap d > 0.45) \mathbb{P}(H_i).$$

Under $H_0$, $d_{\text{final}} > 0.45$ can occur only due to Gaussian noise tails or dynamic control overshoot (which is small, typically $< 0.1\%$).
Under fault $H_i$, however:
$$\mathbb{P}_{H_i}(\text{STOP} \cap d > 0.45) \ge \mathbb{P}_{H_i}(\text{Missed Detection} \cap d > 0.45) + \mathbb{P}_{H_i}(\text{Bad Calibration} \cap \text{STOP} \cap d > 0.45).$$

Notice:
1. **Missed Detection:** If the fault preserves cross-modal agreement (e.g. Common-Mode Bias $H_4$ before anchoring, or subtle insidious bias $b = 0.15\text{ m}$ where $e_t \approx \mu_0$), then $E_t$ will **never** grow. The martingale will **never** alarm. The robot remains in `NOMINAL` mode, arrives at the phantom target position, and executes `STOP`. This produces a False Success with probability near 1.0!
2. **Post-Calibration Error:** Even if the martingale alarms and the robot enters `ACTIVE_PROBING`, the Huber estimator or anchor could resolve an incorrect bias vector $\hat{\mathbf{b}}$. If the post-calibration verification step fails to catch this error, the robot transitions to `CALIBRATED` and terminates with `STOP` at an unsafe position.
3. **No Bound on Power / Missed Detection:** Ville's inequality provides an upper bound on $\mathbb{P}_{H_0}(\text{Reject } H_0)$. It provides **strictly zero bound** on $\mathbb{P}_{H_A}(\text{Accept } H_0)$ (Type-II error).

Therefore:
$$\mathbb{P}(\text{False Success}) \text{ is completely unconstrained by Ville's inequality under } H_0.$$

Claiming that Ville's inequality guarantees $\mathcal{R}_{\text{cov}} \le 0.05$ is mathematically equivalent to claiming that a medical diagnostic test with a 5% false-positive rate on healthy patients is mathematically guaranteed to cure 95% of sick patients!

---

## 4. Origin of the Empirical Conflation

Why did the V8 documentation make this claim?

In the benchmark results:
- Pooled False Successes: $k = 6$
- Pooled Accepted Decisions: $n = 257$
- Empirical Covered Risk: $\hat{p} = 6 / 257 = 2.3346\%$
- Two-sided 95% Wilson Score Interval: $[0.0107, 0.04999]$

Because the upper bound of this fixed-sample confidence interval happened to be $0.04999 \approx 5.0\%$, and the monitor threshold was set to $1/\alpha = 20.0$ ($\alpha = 0.05$), the previous report incorrectly conflated the **online stopping threshold parameter $\alpha$** with the **empirical 95% confidence interval of the benchmark outcome**.

These two quantities are completely independent:
- $\alpha = 0.05$ is the nominal false-alarm probability threshold used in Ville's inequality for rejecting $H_0$.
- $2.33\%$ is the empirical ratio of false successes to accepted decisions on a sample of 4,000 episodes across 10 specific simulation scenarios.

---

## 5. Mathematically Defensible Reformulation for AEGIS

To maintain scientific integrity, AEGIS must reformulate its statistical claims into two distinct, mathematically sound categories:

### A. Online Test Component (Anytime-Valid Sensor Verification)
- **Claim:** The `AnytimeValidSequentialMonitor` is an online, anytime-valid test supermartingale for the null hypothesis of nominal cross-modal sensor consistency ($H_0 : \mathbb{E}[e_t \mid \mathcal{F}_{t-1}] \le 0.065\text{ m}$).
- **Guarantee:** By Ville's inequality, under nominal sensor conditions, the probability of ever raising an unwarranted recovery alarm over an infinite operational horizon is bounded by $\alpha = 0.05$:
$$\mathbb{P}_{H_0}\left(\exists t \ge 1 : E_t \ge \frac{1}{\alpha}\right) \le \alpha.$$
- **Benefit:** Eliminates false-alarm-induced task interruptions and unnecessary anchor queries during healthy operation.

### B. Offline / Conformal Risk Control Component (Selective Safety)
- **Claim:** Closed-loop Covered Risk control is a **selective classification / risk-control problem** (Geifman & El-Yaniv, 2017; Angelopoulos et al., 2021).
- **Proper Theoretical Tool:** If a finite-sample guarantee on Covered Risk $\mathbb{P}(d > 0.45 \mid \text{STOP}) \le \epsilon$ is desired across a specified deployment distribution, it must be formulated using:
  1. **Conformal Risk Control** (Angelopoulos, Bates, Candès, Jordan, & Malik, 2024), or
  2. **Learn-Then-Test (LTT)** calibration over a pre-declared calibration set of mission trajectories.
- **Current V8 Status:** In the absence of an explicit conformal calibration split for the terminal stopping threshold, the reported 2.33% Covered Risk must be reported strictly as an **empirical benchmark measurement**, with its exact 95% Wilson interval $[1.07\%, 4.99\%]$ and exact Clopper-Pearson interval $[0.86\%, 5.01\%]$.

---

## 6. Claim Status & Summary

| Claim | Audited Status | Required Scientific Correction |
|---|---|---|
| "Ville's inequality bounds Covered Risk to $\le 5\%$." | **CONTRADICTED** | Retract claim. Ville bounds only Type-I false alarm rate under $H_0$. |
| "Anytime-valid monitor prevents false alarms under nominal noise." | **REPRODUCED & VALID** | Retain. Mathematically supported by Ville (1939) and Ramdas et al. (2023). |
| "AEGIS-Next achieved 2.33% empirical Covered Risk on the 4,000-episode benchmark." | **REPRODUCED & VALID** | Report as an empirical evaluation on the 10-scenario benchmark suite. |
