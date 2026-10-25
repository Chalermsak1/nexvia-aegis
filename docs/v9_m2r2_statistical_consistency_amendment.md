# NEXVIA AEGIS V9-M2R2 — Statistical Consistency Amendment: Option A (Empirical Eligibility Only)

**Amendment Identifier:** `docs/v9_m2r2_statistical_consistency_amendment.md`  
**Protocol Version:** `v9.0-preregistered-2026-10-amendment-r2-stat-consistency`  
**Base Commit Reference:** `50e70b4274c3d319ea99ee69a538258e5e8e8113`  
**Date:** October 2026  
**Status:** PREREGISTERED PROTOCOL AMENDMENT (Committed prior to calibration authorization)

---

## 1. Context & Purpose

In the pre-calibration statistical review, an interpretive ambiguity was identified between:
1. The statistical null hypothesis governing the test statistic $p^{\mathrm{sel}}(\lambda)$, and
2. The empirical sample-size eligibility guardrail requiring $M \ge 336$ ($\hat{C} \ge 0.35$).

A narrative summary in a recent audit review informally described the null hypothesis as:
$$\tilde{H}_0 = \{C(\pi) < 0.35\} \cup \{C(\pi) \ge 0.35 \text{ and } R_{\mathrm{sel}}(\pi) \ge 0.05\}$$
However, returning $p = 1.0$ when the empirical acceptance count $M < 336$ does **not** constitute a valid statistical test of the population-level hypothesis $C(\pi) \ge 0.35$. Under a hypothetical policy with $C(\pi) = 0.349$ and $R_{\mathrm{sel}}(\pi) = 0.0$, the empirical count $M$ would satisfy $M \ge 336$ with probability $\approx 0.48$, falsely rejecting $\tilde{H}_0$ at rate $\approx 48\% \gg 5\%$.

This protocol amendment resolves this ambiguity by formally re-affirming and ratifying **Option A (Empirical Eligibility Only)**, which has been the authoritative mathematical definition in all committed design documents and code implementations.

---

## 2. Definitive Protocol Specification (Option A: Empirical Eligibility Only)

### 2.1 The Statistical Null and Alternative Hypotheses
In strict alignment with `docs/v9_risk_calibration_design.md` (Theorem 2.1), `docs/v9_m2r1_protocol_amendment.md` (Section 5), and `src/aegis/v9/risk_statistics.py` (line 198), the statistical hypothesis tested for each candidate $\lambda \in \Lambda$ is:

$$\mathbf{H_0^{\mathrm{sel}}(\lambda) \;:\; \big\{C(\pi_\lambda; \mathcal{P}_{12}) = 0\big\} \;\cup\; \big\{C(\pi_\lambda; \mathcal{P}_{12}) > 0 \;\land\; R_{\mathrm{sel}}(\pi_\lambda; \mathcal{P}_{12}) \ge \alpha\big\}}$$

$$\mathbf{H_1^{\mathrm{sel}}(\lambda) \;:\; \big\{C(\pi_\lambda; \mathcal{P}_{12}) > 0 \;\land\; R_{\mathrm{sel}}(\pi_\lambda; \mathcal{P}_{12}) < \alpha\big\}}$$

where $\alpha = 0.05$ (`5.0%`).

### 2.2 Role of $C_{\min} = 0.35$ ($M \ge 336$)
The condition $M \ge 336$ ($\hat{C} \ge 0.35$ on $N = 960$) is **strictly an empirical calibration eligibility guardrail** (an operational sample size / utility floor). It is **not** a statistical test of a population hypothesis $C(\pi) \ge 0.35$.

The effective minimum accepted-decision threshold is:
$$m_{\mathrm{eff}} = \max\left(\left\lceil \frac{\ln \delta}{\ln(1 - \alpha)} \right\rceil, \lceil c_{\min} N \rceil\right) = \max(59, \lceil 0.35 \times 960 \rceil) = 336$$

The calibration p-value is defined as:
$$p^{\mathrm{sel}}(\lambda; \mathcal{D}_{\text{cal}}) := \begin{cases} 
1.0, & \text{if } M < 336, \\[6pt]
\displaystyle\sum_{j=0}^{K} \binom{M}{j} \alpha^j (1 - \alpha)^{M - j}, & \text{if } M \ge 336.
\end{cases}$$

### 2.3 Mathematical Proof of Valid Super-Uniformity Under Option A
By Theorem 2.1 of `docs/v9_risk_calibration_design.md`:
1. **Under $C(\pi_\lambda) = 0$:** $M = 0 < 336$ almost surely. Thus $p^{\mathrm{sel}} = 1.0$ almost surely, and $\mathbb{P}(p^{\mathrm{sel}} \le u) = 0 \le u$ for all $u \in [0, 1)$.
2. **Under $C(\pi_\lambda) > 0$ and $r := R_{\mathrm{sel}}(\pi_\lambda) \ge \alpha$:**
   Conditioning on the random accepted count $M = m \ge 336$, the false success count $K \sim \mathrm{Binomial}(m, r)$. Since $r \ge \alpha$, $F_{\mathrm{Bin}(m, \alpha)}(K) \ge F_{\mathrm{Bin}(m, r)}(K)$. By probability integral transform:
   $$\mathbb{P}\big(F_{\mathrm{Bin}(m, \alpha)}(K) \le u \mid M = m\big) \le \mathbb{P}\big(F_{\mathrm{Bin}(m, r)}(K) \le u \mid M = m\big) \le u.$$
   Integrating across $m$:
   $$\mathbb{P}_{H_0^{\mathrm{sel}}}\big(p^{\mathrm{sel}} \le u\big) = \sum_{m=336}^{N} \mathbb{P}(M = m) \, \mathbb{P}\big(F_{\mathrm{Bin}(m, \alpha)}(K) \le u \mid M = m\big) \le u \sum_{m=336}^N \mathbb{P}(M = m) \le u.$$
Hence, $p^{\mathrm{sel}}(\lambda)$ is an exact finite-sample super-uniform p-value for $H_0^{\mathrm{sel}}(\lambda)$ for any choice of $m_{\mathrm{eff}} \ge 1$, including $m_{\mathrm{eff}} = 336$.

### 2.4 Multiplicity and Fixed-Sequence LTT Guarantee
Under the pre-registered fixed sequence $\lambda^{(1)} \rightarrow \dots \rightarrow \lambda^{(6)}$, testing stops at the first candidate where $p^{\mathrm{sel}} > \delta$ ($\delta = 0.05$). By standard fixed-sequence testing theory (Bauer et al., 1991; Mauri et al., 1995; Angelopoulos et al., 2025):
$$\mathbb{P}\Big(\exists \pi \in \hat{\Lambda}_{\mathrm{FST}} : \pi \in H_0^{\mathrm{sel}}\Big) \le \delta = 0.05.$$
This provides an **exact finite-sample Family-Wise Error Rate (FWER) guarantee** bounding selective risk:
$$\mathbb{P}\Big(R_{\mathrm{sel}}(\hat{\pi}) \ge 0.05 \text{ or } C(\hat{\pi}) = 0\Big) \le 0.05.$$

---

## 3. Supported vs. Disclaimed Population-Level Claims

### A. Supported Population-Level Claims
1. **Selective Risk Control:** With probability at least $0.95$, the selected policy $\hat{\pi}$ satisfies $R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) < 0.05$ given positive coverage $C(\hat{\pi}; \mathcal{P}_{12}) > 0$.
2. **Zero-Coverage Exclusion:** A policy with zero population coverage ($C(\pi) = 0$) cannot be certified, except with probability $0 \le 0.05$.
3. **Finite-Sample FWER:** The probability of certifying any candidate in $\Lambda$ that violates the selective risk bound is strictly $\le 0.05$.

### B. Explicitly Disclaimed Claims
1. **Population Coverage Bound:** The procedure **DOES NOT** guarantee that $C(\hat{\pi}; \mathcal{P}_{12}) \ge 0.35$ at confidence level $0.95$.
2. **Empirical vs. Population Coverage:** Empirical coverage $\hat{C}_{\mathrm{cal}} \ge 0.35$ ($M \ge 336$) is an eligibility precondition for calibration, not a certified population guarantee. Population coverage will be reported as an empirical point estimate with an exact two-sided Clopper-Pearson confidence interval, but no statistical hypothesis test on $C(\pi) \ge 0.35$ is performed.

---

## 4. Preservation of Frozen Configurations & Manifests

This amendment is purely an interpretive and mathematical clarification of the existing protocol. It requires:
- **NO change** to `configs/v9_candidates_frozen_r1.json` or its SHA-256 digests.
- **NO change** to `results/v9/manifests/cal_manifest_r2.json` or its SHA-256 digests.
- **NO change** to `results/v9/cal/calibration_run_config_frozen_r2.json` or its SHA-256 digests (which already registers `c_min_role` as an `EMPIRICAL_CALIBRATION_ELIGIBILITY_GUARDRAIL`).
- **NO change** to `src/aegis/v9/risk_statistics.py` (which already implements Option A).
- **NO change** to `experiments/v9_calibrate_ltt.py`.
