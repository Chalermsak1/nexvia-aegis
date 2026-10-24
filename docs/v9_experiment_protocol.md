# NEXVIA AEGIS V9.0 — Preregistered Experiment Protocol (Step 3 of 3)

**Repository Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`
**Active Git Branch:** `v9.0-runtime-assurance`
**Protected V8.1 Baseline Commit:** `4d891c7500cfb4c8110f276038455bc62765ef3b`
**Companion Documents:** `docs/v9_research_audit.md` (Step 1), `docs/v9_risk_calibration_design.md` (Step 2)
**Preregistration Status:** **APPROVED PREREGISTRATION LOCKED PRIOR TO V9 IMPLEMENTATION (`[APPROVED-DECISION]`)**. Decisions 1–4 are formally approved and frozen; no V9 runtime code has been written, and no calibration or holdout seeds (`71000+`) have been generated or inspected.

---

## 3.1 Frozen Hypotheses, Estimands, Scenarios, and Decision Criteria

### 3.1.1 Primary and Hierarchical Secondary Hypotheses

All primary safety claims operate at nominal confidence level **$1 - \delta = 0.95$ ($\delta = 0.05$)** with primary selective-risk target **$\alpha = 0.05$ (`5.0%`)**, evaluated on the **single frozen V9 policy $\hat{\pi} = \pi_{\hat{\lambda}}$** selected once on $\mathcal{D}_{\text{cal}}$ via Fixed-Sequence LTT (`docs/v9_risk_calibration_design.md`, Section 2.4). If $\hat{\Lambda}_{\mathrm{FST}} = \emptyset$ on $\mathcal{D}_{\text{cal}}$, $\hat{\pi}$ is declared **`UNCERTIFIED`** and all confirmatory certification hypotheses (`H1`, `H2`) automatically evaluate to **NOT ESTABLISHED**.

To control familywise Type-I error across confirmatory claims at $\le 0.05$, `H1` and `H2` are ordered via **fixed-sequence hierarchical gatekeeping** (`H2` is formally claimed as certified only if `H1` passes at $\delta = 0.05$):

1. **Primary Hypothesis `H1` (Extended 12-Scenario Mixture Selective-Risk Certification on $\mathcal{D}_{\text{test}}^{\text{mix}}$):**
   - *Null $H_{0,1}$:* $C(\hat{\pi}; \mathcal{P}_{12}) = 0 \;\lor\; R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) > 0.05$.
   - *Alternative $H_{1,1}$:* $C(\hat{\pi}; \mathcal{P}_{12}) > 0 \;\land\; R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) \le 0.05$.
   - *Confirmatory Pass Criterion:* $M_{\text{test}}^{\text{mix}}(\hat{\pi}) \ge 59$ **and** exact one-sided 95% Clopper–Pearson upper bound $U_{\mathrm{CP},1}\big(K_{\text{test}}^{\text{mix}}(\hat{\pi}), M_{\text{test}}^{\text{mix}}(\hat{\pi}); 0.05\big) \le 0.05$ **and** empirical holdout coverage $\hat{C}_{\text{test}}^{\text{mix}}(\hat{\pi}) \ge C_{\min} = 0.35$.

2. **Gatekept Co-Primary Hypothesis `H2` (Backward-Compatible Core-10 Mixture Selective-Risk Certification on $\mathcal{D}_{\text{test}}^{\text{mix}} \cap \mathcal{S}_{10}$):**
   - *Null $H_{0,2}$:* $C(\hat{\pi}; \mathcal{P}_{10}) = 0 \;\lor\; R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{10}) > 0.05$.
   - *Confirmatory Pass Criterion (evaluated for formal certification iff `H1` passes):* On the $\mathcal{S}_{10}$ subsample of $\mathcal{D}_{\text{test}}^{\text{mix}}$, $M_{\text{test},10}^{\text{mix}}(\hat{\pi}) \ge 59$ and $U_{\mathrm{CP},1}\big(K_{\text{test},10}^{\text{mix}}(\hat{\pi}), M_{\text{test},10}^{\text{mix}}(\hat{\pi}); 0.05\big) \le 0.05$.

3. **Secondary Confirmatory Utility Hypothesis `H3` (Paired True-Success Noninferiority on $\mathcal{D}_{\text{test}}^{\text{scen}}$, $\mathcal{S}_{10}$ Block, $N = 1,200$):**
   - *Null $H_{0,3}$:* $TSR(\hat{\pi}; \mathcal{P}_{10}) - TSR(\pi_{\mathrm{V8}}; \mathcal{P}_{10}) \le \Delta_{\mathrm{NI}} = -0.05$ (and co-evaluated against $\pi_{\mathrm{V7}}$ at $\Delta_{\mathrm{NI}} = -0.05$).
   - *Pass Criterion:* One-sided 95% paired lower confidence bound (Newcombe/Wald paired difference CI on the `1,200` matched `(scenario, seed)` pairs) strictly exceeds $-0.05$, **and** `NOMINAL` true-success rate satisfies $\widehat{TSR}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$ (`>= 113 / 120`).

4. **Secondary Compound-Fault Hypothesis `H4` (Reduction of Compound-Fault False-Success Incidence on $\mathcal{D}_{\text{test}}^{\text{scen}}$):**
   - *Target Scenarios:* $\mathcal{S}_{\mathrm{comp}} = \{\text{\texttt{INDEPENDENT\_BIAS}},\, \text{\texttt{COMPOUND\_HOLDOUT\_EXTREME}},\, \text{\texttt{COMPOUND\_DRIFT\_DROPOUT}},\, \text{\texttt{COMPOUND\_ANTIPODAL\_RANGE\_SHIFT}}\}$ (`4 x 120 = 480` matched episodes).
   - *Pass Criterion:* Exact two-sided paired McNemar test on unconditional false-success incidence $FS(\hat{\pi})$ vs. $FS(\pi_{\mathrm{V8}})$ yields $p < 0.05$ with $\hat{R}_{\mathrm{inc}}(\hat{\pi}; \mathcal{S}_{\mathrm{comp}}) < \hat{R}_{\mathrm{inc}}(\pi_{\mathrm{V8}}; \mathcal{S}_{\mathrm{comp}})$, reported alongside paired episode-level bootstrap 95% CIs for $\Delta R_{\mathrm{sel}}$.

5. **Secondary Multi-Scenario Envelope `H5` (Simultaneous 12-Scenario Risk Reporting on $\mathcal{D}_{\text{test}}^{\text{scen}}$):**
   - Report simultaneous 95% one-sided Clopper–Pearson bounds across all `12` scenarios using Šidák allocation $\delta_{\mathrm{Šidák}} = 1 - 0.95^{1/12} \approx 0.004265$ (and Holm step-down) for both $R_{\mathrm{inc},s}$ and $R_{\mathrm{sel},s}$ (explicitly marking $M_s = 0$ as `UNDEFINED`), plus Berger's Intersection–Union test ($\max_{s \in \mathcal{S}_{12}} p_{\mathrm{inc},s} \le 0.05$) for worst-case unconditional incidence $\max_{s \in \mathcal{S}_{12}} R_{\mathrm{inc},s}(\hat{\pi}) \le 0.05$.

---

### 3.1.2 Frozen 12-Scenario Suite $\mathcal{S}_{12} = \mathcal{S}_{10} \cup \mathcal{S}_{\mathrm{ext}}$

Scenarios `1–10` ($\mathcal{S}_{10}$) preserve the exact parameters of `experiments/benchmark_next.py:71-160` (`WorldConfig` defaults: `timestep=0.02`, `max_steps=300`, `robot_mass=1.0`, `robot_radius=0.20`, `control_force=1.0`, `success_radius=0.25`, `d_safe=0.45 m`, `anchor_cfg: query_cost=0.05, noise_sigma=0.04, corrupted_bias=(1.2, -1.0)`). Scenarios `11–12` ($\mathcal{S}_{\mathrm{ext}}$) expand compound-fault stress coverage:

| # | Scenario Name | Suite | `vec_a` Config ($\sigma_a, \mathbf{b}_a, \mathbf{d}_{\mathrm{drift},a}, p_{\mathrm{out}}, p_{\mathrm{drop}}$) | `vec_b` Config ($\sigma_b, \mathbf{b}_b, p_{\mathrm{drop}}$) | Range Config ($\sigma_r, b_r, p_{\mathrm{drop},r}$) | Anchor Corrupted | Primary Failure Mode Tested |
| :-: | :--- | :---: | :--- | :--- | :--- | :---: | :--- |
| 1 | `NOMINAL` | $\mathcal{S}_{10}$ | `0.05, (0,0), (0,0), 0, 0` | `0.05, (0,0), 0` | `0.05, 0.0, 0` | `False` | Nominal Type-I alarm & arrival efficiency |
| 2 | `PRIMARY_BIAS` | $\mathcal{S}_{10}$ | `0.05, (+0.8,-0.6), (0,0), 0, 0` | `0.05, (0,0), 0` | `0.05, 0.0, 0` | `False` | Single-sensor static bias recovery |
| 3 | `INDEPENDENT_BIAS` | $\mathcal{S}_{10}$ | `0.05, (+0.6,+0.4), (0,0), 0, 0` | `0.05, (-0.5,+0.5), 0` | `0.05, 0.0, 0` | `False` | Inter-sensor disagreement (`\|\|b_fused\|\|=0.4528m`) |
| 4 | `CORRELATED_BIAS` | $\mathcal{S}_{10}$ | `0.05, (+0.7,+0.7), (0,0), 0, 0` | `0.05, (+0.7,+0.7), 0` | `0.05, 0.0, 0` | `False` | Common-mode vector bias + anchor resolution |
| 5 | `SENSOR_DRIFT` | $\mathcal{S}_{10}$ | `0.05, (0,0), (0.003,0.0015), 0, 0` | `0.05, (0,0), 0` | `0.05, 0.0, 0` | `False` | Time-varying ramp drift (`vec_a` only) |
| 6 | `OUTLIER_BURSTS` | $\mathcal{S}_{10}$ | `0.05, (0,0), (0,0), 0.12 (4.5x), 0` | `0.05, (0,0), 0` | `0.05, 0.0, 0` | `False` | Heavy-tailed contaminated Gaussian bursts |
| 7 | `SENSOR_DROPOUT` | $\mathcal{S}_{10}$ | `0.05, (0,0), (0,0), 0, 0.40` | `0.05, (0,0), 0` | `0.05, 0.0, 0` | `False` | Intermittent `40%` packet loss on `vec_a` |
| 8 | `FAULTY_REFERENCE_SENSOR` | $\mathcal{S}_{10}$ | `0.05, (+0.7,+0.7), (0,0), 0, 0` | `0.05, (+0.7,+0.7), 0` | `0.05, +1.0, 0` | `False` | Correlated vector bias + `+1.0 m` range fault |
| 9 | `CORRUPTED_ANCHOR_STRESS` | $\mathcal{S}_{10}$ | `0.05, (+0.7,+0.7), (0,0), 0, 0` | `0.05, (+0.7,+0.7), 0` | `0.05, 0.0, 0` | `True` | Correlated vector bias + corrupted anchor |
| 10 | `COMPOUND_HOLDOUT_EXTREME` | $\mathcal{S}_{10}$ | `0.06, (+0.5,+0.5), (0.002,0.002), 0, 0` | `0.06, (+0.5,+0.5), 0` | `0.06, -0.40, 0` | `False` | Drift + common bias + `-0.40 m` range spoofing |
| 11 | `COMPOUND_DRIFT_DROPOUT` | $\mathcal{S}_{\mathrm{ext}}$ | `0.05, (0,0), (0.0025,-0.0020), 0, 0.30` | `0.05, (-0.45,+0.35), 0` | `0.05, 0.0, 0.10` | `False` | Asymmetric drift + `vec_a` dropout + `10%` range dropout (tests arrival range-dropout bypass) |
| 12 | `COMPOUND_ANTIPODAL_RANGE_SHIFT` | $\mathcal{S}_{\mathrm{ext}}$ | `0.05, (+0.55,+0.40), (0,0), 0, 0` | `0.05, (-0.45,-0.35), 0.35` | `0.05, -0.30, 0` | `False` | Near-canceling antipodal biases (`b_fused=(0.05,0.025)`) + `vec_b` dropout bias jumps + `-0.30 m` range shift |

### 3.1.3 Episode Outcome & Exception Accounting Definitions

For every policy-episode $(s, \xi, \pi)$:
- `A = 1` iff policy returns `"STOP"` before truncation and raises no runtime exception; else `A = 0`.
- `TS = 1` iff `A == 1` and `final_distance <= 0.45` (and `crashed == 0`); else `0`.
- `FS = 1` iff (`A == 1` and `final_distance > 0.45`) **or** `crashed == 1` (fail-unsafe accounting: an unhandled runtime exception inside `ctrl.update` is logged with `crashed = 1` and penalized conservatively in risk audits rather than silently discarded!).
- `AB_exp = 1` iff policy returns `"ABSTAIN"` with `crashed == 0`; `TO = 1` iff `A == 0 and AB_exp == 0 and crashed == 0 and steps == 300`; `AB = 1 - A` (when `crashed == 0`).

---

## 3.2 Sample-Size, Power, and Minimum Detectable Effect Calculations (`[NEW-DERIVATION]`, `[VERIFIED]`)

### 3.2.1 Exact Minimum Accepted Decisions $m_{\mathrm{req}}(k; \alpha, \delta_{\mathrm{eff}})$ for $U_{\mathrm{CP},1}(k, m; \delta_{\mathrm{eff}}) \le 0.05$

By exact binomial inversion, $U_{\mathrm{CP},1}(k, m; \delta_{\mathrm{eff}}) \le \alpha \iff \sum_{j=0}^k \binom{m}{j}\alpha^j(1-\alpha)^{m-j} \le \delta_{\mathrm{eff}}$. For $\alpha = 0.05$, the exact minimum accepted decision count $m$ required as a function of observed false successes $k$ is:

| Correction / Inference Context | Effective $\delta_{\mathrm{eff}}$ | $k=0$ | $k=1$ | $k=2$ | $k=3$ | $k=4$ | $k=5$ | $k=6$ | $k=8$ | $k=10$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1-Sided 95% UCB (Frozen Policy / FST LTT)** | `0.050000` | **`59`** | **`93`** | **`124`** | **`153`** | **`181`** | **`208`** | **`234`** | **`286`** | **`336`** |
| **2-Sided 95% CP Upper Bound** | `0.025000` | `72` | `110` | `142` | `173` | `202` | `230` | `258` | `312` | `364` |
| **Holm Step-1 Across $J=6$ Policies** | `0.008333` | `94` | `135` | `170` | `203` | `234` | `264` | `293` | `350` | `405` |
| **Šidák Simultaneous Across $S=10$ Scenarios** | `0.005116` | `103` | `145` | `182` | `215` | `247` | `278` | `308` | `366` | `422` |
| **Holm Step-1 Across $S=10$ Scenarios** | `0.005000` | `104` | `146` | `182` | `216` | `248` | `279` | `309` | `367` | `423` |
| **Šidák Simultaneous Across $S=12$ Scenarios** | `0.004265` | **`107`** | `149` | `186` | `220` | `252` | `283` | `314` | `372` | `428` |
| **Holm Step-1 Across $S=12$ Scenarios** | `0.004167` | **`107`** | `150` | `187` | `221` | `253` | `284` | `314` | `373` | `429` |

*(Note: This table explains why V8's `6 / 257` had two-sided 95% Clopper–Pearson upper bound `0.05012 > 0.05`, since $257 < 258$, and why `NOMINAL` `0 / 50` had one-sided 95% UCB `0.05816 > 0.05`, since $50 < 59$!)*

### 3.2.2 Treatment of Zero Observed False Successes ($k = 0$) and Why Zero Empirical Error Never Proves Zero Risk

When $k = 0$ false successes are observed among $m \ge 1$ accepted decisions, $\hat{R}_{\mathrm{sel}} = 0/m = 0$, but the likelihood of observing $K = 0$ under true risk $r \in (0, 1)$ is $(1 - r)^m > 0$. Setting $(1 - r)^m = \delta$ yields the exact Rule-of-Three / Clopper–Pearson upper confidence limit:
$$U_{\mathrm{CP},1}(0, m; \delta) = 1 - \delta^{1/m} \approx \frac{-\ln \delta}{m} \quad (\text{e.g., } \approx \frac{2.9957}{m} \text{ at } 1-\delta = 0.95).$$
- At $m = 1$ (`AEGIS_NEXT` in `CORRUPTED_ANCHOR_STRESS`), $k = 0$ allows true selective risk up to **`95.0%`** at 95% confidence.
- At $m = 15$ (`EKF_CONSISTENCY_MONITOR` pooled), $k = 0$ allows true selective risk up to **`18.10%`**.
- At $m = 50$ (`NOMINAL` in V8), $k = 0$ allows true selective risk up to **`5.82% > 5.0%`**.
- Proving $R_{\mathrm{sel}} = 0$ is impossible from any finite sample ($U_{\mathrm{CP},1}(0, m; \delta) > 0$ for all finite $m$); certifying $R_{\mathrm{sel}} \le 0.05$ at 95% confidence requires **at least $m = 59$ accepted episodes with $0$ errors**—and **even $m \ge 59$ is NOT a universal certification guarantee**: $m = 59$ suffices *only* when $k = 0$ errors occur on a single prespecified hypothesis (or pre-ordered Fixed-Sequence LTT step) under exact i.i.d. episode sampling. Non-zero errors ($k = 1 \implies m \ge 93$, $k = 2 \implies m \ge 124$, $k = 6 \implies m \ge 234$), unordered candidate selection across $J = 6$ policies (`Holm-6` $\implies m \ge 94$ at $k = 0$), two-sided intervals ($m \ge 72$ at $k = 0$), or simultaneous 12-scenario certification ($m_s \ge 107$ per scenario at $k_s = 0$) strictly increase the required sample size.

### 3.2.3 Impact of Coverage $C$ and Exact Marginal Certification Power

Under i.i.d. mixture sampling of $N$ episodes with coverage $C = C(\pi; \mathcal{M})$ and true selective risk $r_{\mathrm{true}} < \alpha = 0.05$, $M \sim \mathrm{Binomial}(N, C)$ and $K \mid M = m \sim \mathrm{Binomial}(m, r_{\mathrm{true}})$. Exact marginal certification power is:
$$\mathrm{Power}(N, C, r_{\mathrm{true}}; \delta_{\mathrm{eff}}) = \sum_{m = m_{\min}}^{N} \binom{N}{m} C^m (1-C)^{N-m} \sum_{k=0}^{k_{\max}(m; \alpha, \delta_{\mathrm{eff}})} \binom{m}{k} r_{\mathrm{true}}^k (1 - r_{\mathrm{true}})^{m-k}.$$

| Partition & Total Episodes $N$ | True Coverage $C$ | Expected Accepted $\mathbb{E}[M]$ | Power at $r_{\mathrm{true}}=1.0\%$ (FST / Holm-6) | Power at $r_{\mathrm{true}}=1.5\%$ (FST / Holm-6) | Power at $r_{\mathrm{true}}=2.0\%$ (FST / Holm-6) | Power at $r_{\mathrm{true}}=2.5\%$ (FST / Holm-6) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **$\mathcal{D}_{\text{cal}}$ (`N = 960`, $\mathcal{P}_{12}$)** | `0.45` | `432.0` | `99.99% / 99.70%` | `99.53% / 95.33%` | **`95.66%` / `79.73%`** | `83.32% / 54.62%` |
| **$\mathcal{D}_{\text{cal}}$ (`N = 960`, $\mathcal{P}_{12}$)** | `0.50` | `480.0` | `100.0% / 99.90%` | `99.79% / 97.42%` | **`97.29%` / `85.23%`** | `87.19% / 61.23%` |
| **$\mathcal{D}_{\text{test}}^{\text{mix}}$ (`N = 1,440`, $\mathcal{P}_{12}$)** | `0.45` | `648.0` | `100.0%` | `99.99%` | **`99.51%`** | **`95.09%`** |
| **$\mathcal{D}_{\text{test}}^{\text{mix}}$ (`N = 1,440`, $\mathcal{P}_{12}$)** | `0.50` | `720.0` | `100.0%` | `100.0%` | **`99.77%`** | **`96.81%`** |
| **$\mathcal{D}_{\text{test},10}^{\text{mix}}$ (`E[N] = 1,200`, $\mathcal{P}_{10}$)** | `0.50` | `600.0` | `100.0%` | `99.97%` | **`99.19%`** | **`93.46%`** |

### 3.2.4 Paired Policy Comparison Power and Minimum Detectable Effect (MDE)

For paired binary `TSR` comparisons across $N$ matched `(scenario, seed)` episodes with total discordant proportion $q = p_{01} + p_{10}$ (empirically $q = (43 + 59)/500 = 0.204$ between V7 and V8 in `benchmark_episodes.csv`), the paired standard error under null equality is $\mathrm{SE}_0 = \sqrt{q / N}$, two-sided 95% CI half-width is $1.96\,\mathrm{SE}_0$, and the Minimum Detectable Effect (or tightest certifiable noninferiority margin $|\Delta_{\mathrm{NI}}|$ when true $\Delta = 0$) at one-sided significance $\alpha_{\mathrm{NI}} = 0.05$ (`95%` one-sided LCB) and $\alpha_{\mathrm{NI}} = 0.025$ (`97.5%` one-sided LCB) is $(z_{1-\alpha_{\mathrm{NI}}} + z_{1-\beta})\sqrt{q / N}$:

| Sample Size $N$ | Discordant Rate $q$ | Paired $\mathrm{SE}_0$ | 2-Sided 95% Half-Width | MDE (80% Power, 1-Sided $\alpha_{\mathrm{NI}}=0.05$) | MDE (90% Power, 1-Sided $\alpha_{\mathrm{NI}}=0.05$) | MDE (80% Power, 1-Sided $\alpha_{\mathrm{NI}}=0.025$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `N = 500` (Historical V8) | `0.204` | `2.02%` | `±3.96%` | `5.02%` *(underpowered for 5% NI)* | `5.91%` | `5.66%` |
| **`N = 1,200` ($\mathcal{D}_{\text{test}}^{\text{scen}}$ Core-10)** | `0.204` | **`1.30%`** | **`±2.56%`** | **`3.24%`** (`< 5.0%` NI margin) | **`3.82%`** | **`3.65%`** |
| **`N = 1,440` ($\mathcal{D}_{\text{test}}^{\text{scen}}$ Full-12)** | `0.204` | **`1.19%`** | **`±2.33%`** | **`2.96%`** (`< 5.0%` NI margin) | **`3.48%`** | **`3.33%`** |

### 3.2.5 Explicit Scope Limitations: Claims NOT Supportable at Planned Sample Size

At $N_s = 120$ episodes per scenario on $\mathcal{D}_{\text{test}}^{\text{scen}}$:
1. **Per-scenario selective risk $R_{\mathrm{sel},s} \le 0.05$ CANNOT be certified in low-coverage fault scenarios** whenever $M_s < 59$ (`C_s < 49.2%` unadjusted) or $M_s < 107$ (`C_s < 89.2%` simultaneous 12-scenario Šidák/Holm). In `FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, and `COMPOUND_HOLDOUT_EXTREME`, safe runtime assurance *should* abstain on most or all episodes ($M_s \approx 0\text{–}15$); V9 will therefore certify **per-scenario unconditional incidence $R_{\mathrm{inc},s} \le 0.05$** ($120 \ge 107$ when $K_s = 0$) and report exact selective-risk CIs (`UNDEFINED` when $M_s = 0$) without claiming per-scenario selective certification where $M_s$ is insufficient.
2. **Ultra-low risk claims ($R_{\mathrm{sel}} \le 1.0\%$ or $0.1\%$)** cannot be certified (`R_sel <= 1%` at $k=0$ requires $m \ge 299$ zero-error acceptances; `<= 0.1%` requires $m \ge 2,995$).

---

## 3.3 Predefined Baseline Suite and Strict Four-Input Sensor-Interface Parity (`[VERIFIED]`, `[APPROVED-DECISION]`)

All 8 historical controllers in `experiments/benchmark_next.py:221-237` and `src/aegis/next/baselines.py` expose the identical closed-loop step signature:
```python
update(
    reading_a: SensorReading,
    reading_b: SensorReading,
    range_reading: RangeReading,
    anchor_reading: AnchorReading | None = None,
    step: int = 0,
) -> tuple[np.ndarray, str, np.ndarray, bool]
```
returning `(force_action, decision_type, calibrated_vector, query_anchor_next)`, plus `reset() -> None`.

**Approved Decision 4 — Strict Four-Input Sensor-Interface Parity (`[APPROVED-DECISION]`):**
- `AegisV9Controller` **must keep the exact four required runtime sensor inputs** (`reading_a`, `reading_b`, `range_reading`, and `anchor_reading`, plus step index `step: int = 0`).
- **No new mandatory wheel odometry, wheel encoder, or IMU sensor** unavailable to the V1–V8 baseline systems may be introduced.
- Derived temporal consistency features are permitted **only** when computed strictly from information available through those four runtime inputs, their valid intra-episode histories (`ctrl.reset()` wipes all history between episodes), their declared nominal `sigma` fields, and the controller's own previously issued force actions $\mathbf{u}_{0:t-1}$. Accessing `world.state()` ground-truth position/velocity or introducing any hidden observation channel is strictly prohibited; optional configuration fields in `AegisV9Config` may specify policy thresholds ($\lambda^{(j)} \in \Lambda$) only and must never silently inject extra sensor observations.

| # | Policy Key | Implementation Class & Source | Core Mechanism | Comparability & Coverage Caveats (`[VERIFIED]`) |
| :-: | :--- | :--- | :--- | :--- |
| 1 | `UNSHIELDED_ALWAYS_ACT` | `UnshieldedAlwaysActController` (`baselines.py:46-82`) | Equal/inverse-variance fusion + noisy finite-diff PD pursuit; zero fault gating; never emits `"ABSTAIN"`. | `140/500` episodes time out at `step=300` (`AB=140`), giving `72.0%` coverage and `45.0%` selective risk. |
| 2 | `CHISQUARE_NIS_GATING` | `ChiSquareNISGatingController` (`baselines.py:87-148`) | Classical $\chi^2_2$ gate (`5.991`) on $\|\mathbf{z}_a - \mathbf{z}_b\|^2 / (\sigma_a^2+\sigma_b^2)$; abstains on `2` consecutive breaches. | Blind to common-mode vector faults (`CORRELATED_BIAS`, `FAULTY_REFERENCE_SENSOR`: `100%` `R_sel`); `48%` nominal false-alarm/timeout rate. |
| 3 | `EKF_CONSISTENCY_MONITOR` | `EKFConsistencyController` (`baselines.py:153-228`) | 2D state EKF (`Q=1e-4*I`) with $3\sigma$ range-innovation gate (`norm_innov_sq > 9.0`). | **Extreme low-coverage degeneracy:** `97.0%` abstention (`M = 15/500`, `C = 3.0%`); raw `0/15` (`0%`) selective-risk point estimate has `UCB95 = 18.1%` and is **misleading without coverage context**. |
| 4 | `AEGIS_V4_PASSIVE_VERIFY` | `AegisV4PassiveController` (`baselines.py:233-281`) | Instantaneous cross-modal gate `\| \|\|z_fused\|\| - r \| > 0.35` $\implies$ permanent `"ABSTAIN"`. | No recalibration or anchor capability (`C = 27.4%`, `R_sel = 5.84%`). |
| 5 | `AEGIS_V5_HUBER_CALIBRATE` | `AegisV5HuberController` (`baselines.py:286-382`) | Fixed 2-phase orthogonal probing (`32` steps) + `OnlineBiasEstimator` (`HUBER` + FIM gate); no anchor or multi-hypothesis diagnosis. | Vulnerable to reference-sensor faults and compound drift (`COMPOUND_HOLDOUT_EXTREME`: `12/15 = 80.0%` `R_sel`). |
| 6 | `AEGIS_V6_DISCRIMINATIVE` | `AegisV6DiscriminativeController` (`baselines.py:387-418` $\to$ `v6/recovery_controller.py`) | 7-hypothesis Bayesian engine + discriminative probing (`STRATEGY_F`); no anchor sensor (`query_anchor=False`). | Cannot resolve `CORRELATED_BIAS` (`0/50` accepted); high overshoot (`0.1545 m`) and `65.0%` `R_sel` in `INDEPENDENT_BIAS`. |
| 7 | `AEGIS_V7_MPC_BASELINE` | `AegisV7MPCBaselineController` (`baselines.py:423-454` $\to$ `v7/recovery_controller.py`) | Receding-horizon pseudo-MPC + `AnchorQueryScheduler` + `AnchorIntegrityGate` + Huber calibration. | Highest historical `TSR` (`53.4%`) and anchor cost (`0.144`), but `5.99%` pooled `R_sel` (`11/36 = 30.6%` in `INDEPENDENT_BIAS`). |
| 8 | `AEGIS_NEXT_MARTINGALE` | `AegisNextController` (`agent_next.py:40-305`) | Scalar Ville e-process + `KinematicVelocityController` + event-triggered anchor + Huber calibration. | Frozen V8.1 baseline (`TSR = 50.2%`, pooled `R_sel = 6/257 = 2.33%`, `INDEPENDENT_BIAS` `4/32 = 12.5%`, `COMPOUND_HOLDOUT_EXTREME` `2/3 = 66.7%`). |
| 9 | `AEGIS_V9_CALIBRATED` | Planned `AegisV9Controller` (`src/aegis/v9/`, **not yet implemented**) | Frozen LTT-selected joint policy $\hat{\pi} = \pi_{\hat{\lambda}}$ (`Lambda` size `J=6`): hybrid Channel A ($\gamma=1$ Ville) + Channel B (CUSUM drift), per-sensor $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ calibration with disjoint fit/val windows, fail-closed anchor/range gate, and 4-input parity. | Primary evaluated policy; if calibration returns $\hat{\Lambda}_{\mathrm{FST}} = \emptyset$, marked `UNCERTIFIED`. |

---

## 3.4 Approved V9 Runtime-Assurance Architecture & Compound-Fault Diagnostics (`[APPROVED-DECISION]`, `[NEW-DERIVATION]`)

All geometric and temporal relationships below are derived from the verified simulation environment (`src/aegis/v3/env/world.py`), vector sensor model (`src/aegis/v3/sensors/sensors.py:51-148`), range sensor model (`src/aegis/v3/sensors/cross_modal.py:48-84`), and anchor sensor (`src/aegis/v7/anchor_sensor.py`):
- **Coordinate Frame, Sign Convention, & Units:** Global 2D horizontal world frame $(x, y)$ in meters (`m`), fixed timestep $\Delta t = 0.02\text{ s}$, horizon $T_{\max} = 300$. True relative target vector is $\mathbf{d}_t := \mathbf{p}^* - \mathbf{p}_{\text{robot}}(t) \in \mathbb{R}^2$ (`benchmark_next.py:251`; for stationary targets `moving_target=False`, $\mathbf{d}_{t_2} - \mathbf{d}_{t_1} = -(\mathbf{p}_{\text{robot}}(t_2) - \mathbf{p}_{\text{robot}}(t_1))$).
- **Sensor Observation Equations:**
  $$\mathbf{z}_{k,t} = \mathbf{d}_t + \mathbf{b}_k + \mathbf{d}_{\mathrm{drift},k}\, t + \boldsymbol{\varepsilon}_{k,t} \quad (k \in \{a, b\},\; \boldsymbol{\varepsilon}_{k,t} \sim \mathcal{N}(\mathbf{0}, \sigma_k^2 \mathbf{I}_2)),$$
  $$r_t = \max\big(0,\, \|\mathbf{d}_t\|_2 + b_r + \nu_t\big) \quad (\nu_t \sim \mathcal{N}(0, \sigma_r^2)), \qquad \mathbf{z}_{\mathrm{anc},t} = \mathbf{d}_t + \mathbf{b}_{\mathrm{anc}} + \boldsymbol{\varepsilon}_{\mathrm{anc},t} \quad (\boldsymbol{\varepsilon}_{\mathrm{anc},t} \sim \mathcal{N}(\mathbf{0}, \sigma_{\mathrm{anc}}^2 \mathbf{I}_2)).$$

### 3.4.1 Approved Decision 1 — Hybrid Parallel Monitoring (Channel A + Channel B) & Frozen Joint Family $\Lambda$
- **Channel A (Exact $\gamma = 1.0$ Ville e-Process):** Evaluates nonnegative subchannels $c \in \mathcal{C} = \{\mathrm{ab}, (\mathrm{vr},a), (\mathrm{vr},b)\}$ with $e_{\mathrm{ab},t} = \|\mathbf{z}_{a,t} - \mathbf{z}_{b,t}\|_2$ ($\mu_{0,\mathrm{ab}} = \sqrt{\frac{\pi}{2}(\sigma_a^2 + \sigma_b^2)}$) and $e_{\mathrm{vr},k,t} = |\|\mathbf{z}_{k,t}\|_2 - r_t|$ ($\mu_{0,\mathrm{vr},k} = \sigma_k\sqrt{\frac{\pi}{2}} + \sigma_r\sqrt{\frac{2}{\pi}}$). Using upper-only concave clipping $x_{c,t} = \min((e_{c,t} - \mu_{0,c})/v_{\max,c}, x_{\max})$ ($v_{\max,c}=0.40\text{ m}, x_{\max}=3.50$), strictly $\mathcal{F}_{t-1}$-predictable $\lambda_{c,t} \in [0, \min(0.85, 0.90\,v_{\max,c}/\mu_{0,c})]$, $\gamma = 1.0$, **no reflecting lower floor**, and **no invalidating upper cap**, the equal-weight convex mixture $E_t^{\mathrm{Ville}} = \frac{1}{|\mathcal{C}|}\sum_{c \in \mathcal{C}} \exp\big(\sum_{s=1}^t \ln(1 + V_{c,s}\lambda_{c,s}x_{c,s})\big)$ satisfies $\mathbb{P}_{H_{0,\mathrm{mon}}}(\exists t \ge 1 : E_t^{\mathrm{Ville}} \ge 1/\alpha_{\mathrm{mon}}^{(j)}) \le \alpha_{\mathrm{mon}}^{(j)}$ under the nominal conditional bounded-mean null $H_{0,\mathrm{mon}}$ (`docs/v9_risk_calibration_design.md`, Proposition 2.1). **Channel A bounds only nominal Type-I monitor false alarms under $H_{0,\mathrm{mon}}$ and is never claimed to control closed-loop $R_{\mathrm{sel}}$ under faults.**
- **Channel B (Complementary Page CUSUM Drift Detector):** Evaluates $S_{c,t} = \max\big(0, S_{c,t-1} + V_{c,t}(\min(e_{c,t}/\sigma_{c,\mathrm{scale}}, 6.0) - \kappa_{c,\mathrm{drift}})\big)$ ($\kappa_{\mathrm{ab},\mathrm{drift}} = 1.80, \kappa_{\mathrm{vr},k,\mathrm{drift}} = 1.60$), alarming when $\max_{c \in \mathcal{C}} S_{c,t} \ge h_{\mathrm{cusum}}^{(j)}$ to bound detection delay on late-onset or slowly ramping faults after nominal stretches. **Channel B is never described as Ville-anytime-valid.**
- **Joint Candidate Family $\Lambda$ ($J = 6$, Identical to `docs/v9_risk_calibration_design.md`, Section 2.4.1):** Both channel thresholds and their OR-combination logic (`alarm_A OR alarm_B OR instantaneous_gate`), together with per-sensor validation, anchor/range tolerance, and terminal arrival gates, define $\lambda^{(j)} = (\alpha_{\mathrm{mon}}^{(j)}, h_{\mathrm{cusum}}^{(j)}, \tau_{\mathrm{diff}}^{(j)}, \tau_{ar}^{(j)}, \tau_{\mathrm{val}}^{(j)}, \tau_{\mathrm{stop}}^{(j)})$ across Tiers `1..6` (`(0.010, 6.0, 3.20, 3.80, 0.10, 0.36)`, `(0.020, 7.0, 3.50, 4.20, 0.11, 0.38)`, `(0.030, 8.0, 3.80, 4.60, 0.12, 0.40)`, `(0.040, 9.0, 4.10, 5.00, 0.13, 0.41)`, `(0.050, 10.0, 4.40, 5.47, 0.14, 0.42)`, `(0.075, 11.5, 4.80, 6.00, 0.15, 0.44)`), calibrated end-to-end via Fixed-Sequence LTT on $\mathcal{D}_{\text{cal}}$ while keeping **(1) monitor false alarms**, **(2) fault detection delay**, and **(3) closed-loop selective risk $R_{\mathrm{sel}}$** strictly distinct.

### 3.4.2 Approved Decision 2 — Per-Sensor Bias Calibration (`vec_a`, `vec_b`), Uncertainty State, & Disjoint Validation Data-Flow
- **Separate Per-Sensor Estimators (Primary Policy):** During `ACTIVE_PROBING`, V9 runs separate `OnlineBiasEstimator` instances `estimator_a` ($\hat{\mathbf{b}}_a$) and `estimator_b` ($\hat{\mathbf{b}}_b$) rather than pre-fusing raw vectors and fitting one shared bias (selective calibration of only a single diagnosed sensor is retained strictly as a future comparison candidate, not the primary policy).
- **Input Hygiene & Per-Sensor Status/Uncertainty Representation:** Invalid, missing, or dropout readings (`not reading_k.valid` or `not range_reading.valid`) are discarded **before** buffer insertion; any `NaN`/`Inf` in a `valid == True` reading triggers immediate fail-closed `"ABSTAIN"`. Each sensor $k \in \{a, b\}$ maintains $(\hat{\mathbf{b}}_k \in \mathbb{R}^2,\; \hat{u}_k^2 \in (0, \infty],\; \mathrm{status}_k)$ with $\mathrm{status}_k \in \{\text{\texttt{UNCALIBRATED}},\, \text{\texttt{CALIBRATED\_VALID}},\, \text{\texttt{DROPOUT\_INSUFFICIENT}},\, \text{\texttt{REJECTED\_OR\_FAULTY}}\}$:
  - Sensor $k$ achieves `CALIBRATED_VALID` iff $n_{\mathrm{fit},k} \ge n_{\mathrm{fit,min}} = 10$, FIM minimum eigenvalue $\lambda_{\min,k} \ge \lambda_{\mathrm{fim,min}} = 10^{-3}$, held-out count $n_{\mathrm{val},k} \ge n_{\mathrm{val,min}} = 6$, held-out validation $\mathrm{RMSE}_{\mathrm{val},k} \le \tau_{\mathrm{val}}^{(j)}$, and no validation drift-slope breach, setting $\hat{u}_k^2 = \sigma_k^2 + \mathrm{RMSE}_{\mathrm{val},k}^2 / \max(\lambda_{\min,k}, 10^{-6})$ (otherwise $\hat{u}_k^2 = +\infty$, fusion weight $w_k = 0$).
  - When **both** $a, b$ are `CALIBRATED_VALID` and post-calibration inter-sensor agreement holds on $\mathcal{I}_{\mathrm{val}}$ ($\mathrm{RMS}\|\tilde{\boldsymbol{\delta}}_{ab,t}\|_2 / \sqrt{\hat{u}_a^2 + \hat{u}_b^2} \le \tau_{\mathrm{diff}}^{(j)}$, where $\tilde{\boldsymbol{\delta}}_{ab,t} = (\mathbf{z}_{a,t}-\hat{\mathbf{b}}_a) - (\mathbf{z}_{b,t}-\hat{\mathbf{b}}_b)$), `CALIBRATED` mode fuses valid readings via inverse-uncertainty weights $w_k \propto \hat{u}_k^{-2}$ and seamlessly uses $\mathbf{z}_{k,t} - \hat{\mathbf{b}}_k$ on single-sensor dropout steps without fused-bias jumps (`COMPOUND_ANTIPODAL_RANGE_SHIFT`). When **exactly one** sensor $k^*$ is `CALIBRATED_VALID` (the other being `REJECTED_OR_FAULTY` due to drift or `DROPOUT_INSUFFICIENT`), V9 isolates the faulty sensor ($w_{\neg k^*} \equiv 0$) and navigates on $\mathbf{z}_{k^*,t} - \hat{\mathbf{b}}_{k^*}$. When **neither** sensor is `CALIBRATED_VALID`, V9 transitions immediately to `"ABSTAIN"`.
- **Data-Flow Elimination of Validation Leakage & Prohibition of Continuous Online Refitting:**
  - Entering `ACTIVE_PROBING` immediately resets `estimator_a`, `estimator_b`, `val_buf_a`, and `val_buf_b` and returns `"PROBE"` on the trigger step (fixing `agent_next.py:188-205`).
  - Probing ($T_{\mathrm{probe}} = 36$ steps) is partitioned at the data-routing level into: (i) **Fitting Window $\mathcal{I}_{\mathrm{fit}} = \{1,\dots,22\}$** (writes exclusively to `estimator_k`, after which $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ are computed and **locked**); (ii) **Transition Buffer $\mathcal{I}_{\mathrm{gap}} = \{23,24\}$** (heading reversal; zero buffer writes); and (iii) **Held-Out Validation Window $\mathcal{I}_{\mathrm{val}} = \{25,\dots,36\}$** (writes exclusively to `val_buf_k`; `set(I_fit) & set(I_val) == set()`, failing closed if $n_{\mathrm{val},k} < 6$).
  - During `CALIBRATED` approach, **continuous online updates to $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ are strictly prohibited** so estimates cannot track drift or absorb static range bias $b_r \ne 0$, and terminal `"STOP"` requires `range_reading.valid == True` with $r_t \le \tau_{\mathrm{stop}}^{(j)}$ (or Decision-3 verified anchor distance $\le \tau_{\mathrm{stop}}^{(j)}$), eliminating the invalid-range arrival bypass (`agent_next.py:203, 296`).

### 3.4.3 Approved Decision 3 — Fail-Closed Anchor/Range Disagreement Rule & Vector-Displacement Corroboration
- **Parameterized Discrepancy Gate (Demoting V8's `0.35 m` Heuristic):** Under healthy anchor ($\sigma_{\mathrm{anc}} = 0.04\text{ m}$) and range ($\sigma_r \in \{0.05, 0.06\}\text{ m}$), radial difference variance away from the origin is $\sigma_{ar}^2 = \sigma_{\mathrm{anc}}^2 + \sigma_r^2$ ($\sigma_{ar} \approx 0.06403\text{ m}$ at $\sigma_r = 0.05\text{ m}$). V9 tests the dimensionless discrepancy $\tilde{\Delta}_{ar,t} := |\|\mathbf{z}_{\mathrm{anc},t}\|_2 - r_t| / \sqrt{\sigma_{\mathrm{anc}}^2 + \sigma_r^2} > \tau_{ar}^{(j)}$ (treating V8's `0.35 m` $\approx 5.47\,\sigma_{ar}$ solely as Tier-5 candidate $\tau_{ar}^{(5)}$, **not** as a validated safety limit).
- **Default Fail-Closed Decision & Pre-Holdout Fixed Corroboration Rule:** Whenever $\tilde{\Delta}_{ar,t} > \tau_{ar}^{(j)}$, **neither range nor anchor is treated as an oracle, and V9 defaults to `"ABSTAIN"`**, overriding to corroborate one modality **only if** all prespecified multi-step vector-displacement criteria hold simultaneously across two anchor/range observation epochs $t_1 < t_2$ ($t_2 - t_1 \ge 10$ steps):
  1. *Derived Vector Chord & Common-Mode Drift Exclusion:* For a candidate sensor $k^* \in \{a, b\}$ with valid readings at $t_1, t_2$, $\Delta \mathbf{z}_{k^*, t_1 \to t_2} := \mathbf{z}_{k^*, t_2} - \mathbf{z}_{k^*, t_1} = (\mathbf{d}_{t_2} - \mathbf{d}_{t_1}) + \mathbf{d}_{\mathrm{drift},k^*}(t_2 - t_1) + (\boldsymbol{\varepsilon}_{k^*,t_2} - \boldsymbol{\varepsilon}_{k^*,t_1})$ cancels static bias $\mathbf{b}_{k^*}$ ($\mathrm{SD} = \sqrt{2}\sigma_{k^*}$ per axis) but **not** drift $\mathbf{d}_{\mathrm{drift},k^*}$. Corroboration requires minimum chord length $\|\Delta \mathbf{z}_{k^*, t_1 \to t_2}\|_2 \ge L_{\min} = 0.40\text{ m}$, absence of second-difference / inter-sensor drift alarms on $k^*$, and two-epoch anchor-chord agreement $\|\Delta \mathbf{z}_{\mathrm{anc}, t_1 \to t_2} - \Delta \mathbf{z}_{k^*, t_1 \to t_2}\|_2 \le 3.0\sqrt{2(\sigma_{\mathrm{anc}}^2 + \sigma_{k^*}^2)}$ (note: two measurements sharing a common-mode drifting source are **not** independent corroboration).
  2. *Directional/Curvature Range-Increment Test Against Static Anchor Bias (`CORRUPTED_ANCHOR_STRESS` Trap):* Because static anchor corruption $\mathbf{b}_{\mathrm{anc}} = (1.2, -1.0)\text{ m}$ (`anchor_sensor.py:27, 94`) **also cancels out** of $\Delta \mathbf{z}_{\mathrm{anc}, t_1 \to t_2}$, checking $\Delta \mathbf{z}_{\mathrm{anc}} \approx \Delta \mathbf{z}_{k^*}$ alone would falsely validate a corrupted anchor! For $r_{t_1}, r_{t_2} > 0$, static range bias $b_r$ cancels out of observed range change $\Delta r_{t_1 \to t_2} = r_{t_2} - r_{t_1}$, whereas the anchor position hypothesis predicts $\widehat{\Delta r}_{\mathrm{anc}} := \|\mathbf{z}_{\mathrm{anc},t_1} + \Delta \mathbf{z}_{k^*, t_1 \to t_2}\|_2 - \|\mathbf{z}_{\mathrm{anc},t_1}\|_2$ and the calibrated range-circle hypothesis predicts $\widehat{\Delta r}_{\mathrm{rng}} := \|(\mathbf{z}_{k^*,t_1} - \hat{\mathbf{b}}_{k^*}) + \Delta \mathbf{z}_{k^*, t_1 \to t_2}\|_2 - \|\mathbf{z}_{k^*,t_1} - \hat{\mathbf{b}}_{k^*}\|_2$. With $\sigma_{\Delta r} := \sqrt{2(\sigma_r^2 + \sigma_{k^*}^2 + \sigma_{\mathrm{anc}}^2)}$, V9 corroborates the anchor (identifying static range bias $b_r \ne 0$) **iff** $|\widehat{\Delta r}_{\mathrm{anc}} - \Delta r_{t_1 \to t_2}| \le 2.5\,\sigma_{\Delta r}$ **and** $|\widehat{\Delta r}_{\mathrm{rng}} - \Delta r_{t_1 \to t_2}| > 3.5\,\sigma_{\Delta r}$; corroborates range (rejecting corrupted anchor $\mathbf{b}_{\mathrm{anc}} \ne \mathbf{0}$) **iff** $|\widehat{\Delta r}_{\mathrm{anc}} - \Delta r_{t_1 \to t_2}| > 3.5\,\sigma_{\Delta r}$ while $k^*$ passes `CALIBRATED_VALID`; and **returns `"ABSTAIN"` in every other case** (single anchor query, $r_t = 0$ clamping, $\|\Delta \mathbf{z}_{k^*}\|_2 < 0.40\text{ m}$, common-mode drift, or ambiguous residuals).

### 3.4.4 Derived Temporal Consistency Diagnostics (`D1`–`D5`) Within the Four-Input Interface (`Decision 4`)

### Diagnostic D1 — Pre-Fusion Inter-Sensor Vector Disagreement ($\boldsymbol{\delta}_{ab,t}$)
- **Physical / Mathematical Relationship:** Because both `vec_a` and `vec_b` observe the identical relative vector $\mathbf{d}_t$ in the world $(x, y)$ frame (`m`), when both readings are valid (`reading_a.valid and reading_b.valid`), $\mathbf{d}_t$ cancels identically:
  $$\boldsymbol{\delta}_{ab,t} := \mathbf{z}_{a,t} - \mathbf{z}_{b,t} = (\mathbf{b}_a - \mathbf{b}_b) + (\mathbf{d}_{\mathrm{drift},a} - \mathbf{d}_{\mathrm{drift},b}) t + (\boldsymbol{\varepsilon}_{a,t} - \boldsymbol{\varepsilon}_{b,t}).$$
  Under nominal operation ($\mathbf{b}_a = \mathbf{b}_b = \mathbf{0}, \mathbf{d}_{\mathrm{drift}} = \mathbf{0}$), $q_{ab,t} := \frac{\|\boldsymbol{\delta}_{ab,t}\|_2^2}{\sigma_a^2 + \sigma_b^2} \sim \chi^2_2$ with $\mathbb{E}_{H_0}[q_{ab,t}] = 2.0$ and $\mathbb{E}_{H_0}[\|\boldsymbol{\delta}_{ab,t}\|_2] = \sqrt{\frac{\pi}{2}(\sigma_a^2 + \sigma_b^2)}$ (`0.08862 m` for $\sigma_a = \sigma_b = 0.05\text{ m}$).
- **Independent Observability:** Directly observable whenever `reading_a.valid and reading_b.valid`, completely independent of range bias $b_r$, robot motion, or anchor availability.
- **Expected Noise Sensitivity:** $\sigma_{\mathrm{diff}} = \sqrt{\sigma_a^2 + \sigma_b^2} = 0.07071\text{ m}$ (`0.08485 m` when $\sigma=0.06\text{ m}$). In `INDEPENDENT_BIAS`, $\|\mathbf{b}_a - \mathbf{b}_b\| = 1.1045\text{ m} = 15.62\sigma_{\mathrm{diff}}$ (`q_ab ≈ 244 >> 2`); in `COMPOUND_HOLDOUT_EXTREME` at step `100`, $\|\mathbf{d}_{\mathrm{drift},a} \cdot 100\| = 0.2828\text{ m} = 3.33\sigma_{\mathrm{diff}}$.
- **Potential False Alarms & Missed Detections:** *False alarms:* heavy-tailed single-step bursts in `OUTLIER_BURSTS` (`p=0.12, 4.5x` $\implies$ `ChiSquareNISGatingController` falsely abstained `48/50` times because it used raw unclipped quadratic `q_ab` without Huber/bounded e-process clipping!). *Missed detections:* pure common-mode faults where $\mathbf{b}_a \equiv \mathbf{b}_b$ and $\mathbf{d}_{\mathrm{drift},a} \equiv \mathbf{d}_{\mathrm{drift},b}$ (`CORRELATED_BIAS`, `FAULTY_REFERENCE_SENSOR`), or steps where one sensor drops out.
- **V9 Integration (`Decisions 1 & 2`):** Feed $\|\boldsymbol{\delta}_{ab,t}\|_2$ into Channel A ($\gamma = 1.0$ Ville e-process) and Channel B (CUSUM) AND calibrate $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ separately (`Section 3.4.2`). Evaluate false-alarm rate on `NOMINAL` + `OUTLIER_BURSTS` and detection latency on `INDEPENDENT_BIAS` on $\mathcal{D}_{\text{dev}}$ vs. $\mathcal{D}_{\text{test}}^{\text{scen}}$.

### Diagnostic D2 — Temporal Bias-Increment & Disjoint Split-Window Cross-Validation
- **Physical / Mathematical Relationship:** Under any *static* bias hypothesis ($\mathbf{d}_{\mathrm{drift},a} = \mathbf{d}_{\mathrm{drift},b} = \mathbf{0}$), both (i) window-averaged inter-sensor difference $\bar{\boldsymbol{\delta}}_{ab}(\mathcal{W}_2) - \bar{\boldsymbol{\delta}}_{ab}(\mathcal{W}_1)$ across disjoint time blocks $\mathcal{W}_1 < \mathcal{W}_2$, and (ii) out-of-sample per-sensor cross-modal residuals $e_{k,t}(\hat{\mathbf{b}}_k) = \|\mathbf{z}_{k,t} - \hat{\mathbf{b}}_k\|_2 - r_t$ for $t \in \mathcal{I}_{\mathrm{val}}$ (`t > max I_fit`), have zero drift mean. Under linear drift $\mathbf{d}_{\mathrm{drift}} \cdot t$, $\mathbb{E}[\bar{\boldsymbol{\delta}}_{ab}(\mathcal{W}_2) - \bar{\boldsymbol{\delta}}_{ab}(\mathcal{W}_1)] = (\mathbf{d}_{\mathrm{drift},a} - \mathbf{d}_{\mathrm{drift},b})(\bar{t}_2 - \bar{t}_1) \ne \mathbf{0}$.
- **Independent Observability:** Directly observable from valid `(reading_a, reading_b, range_reading)` histories once $\mathcal{I}_{\mathrm{fit}} = \{1..22\}$, $\mathcal{I}_{\mathrm{gap}} = \{23,24\}$, and $\mathcal{I}_{\mathrm{val}} = \{25..36\}$ are strictly partitioned (`Section 3.4.2`).
- **Expected Noise Sensitivity:** For two 15-step blocks separated by $\Delta \bar{t} = 30$ steps, $\mathrm{SD}(\|\Delta \bar{\boldsymbol{\delta}}_{ab}\|) \approx \sqrt{2/15}\,\sigma_{\mathrm{diff}} \approx 0.0258\text{ m}$, whereas `COMPOUND_HOLDOUT_EXTREME` drift `(0.002, 0.002)` produces $\|\Delta \mathbf{b}\| = 30\sqrt{2}(0.002) = 0.0849\text{ m}$ (`3.3 SD` in 30 steps, growing to `9.3 SD` over 85 steps).
- **Potential False Alarms & Missed Detections:** *False alarms:* short validation windows (`< 6` valid samples under high dropout, handled by explicit `DROPOUT_INSUFFICIENT` status). *Missed detections:* pure static bias paired with static range shift (`b_r != 0, drift = 0`) over a narrow angular arc.

### Diagnostic D3 — Spherical Range-Chord Curvature vs. Vector-Displacement Consistency (Detecting Static Range Bias $b_r \ne 0$)
- **Physical / Mathematical Relationship:** Any constant vector bias $\mathbf{b}_k$ cancels out of temporal vector differences $\Delta \mathbf{z}_{k,t_1 \to t_2} = \mathbf{z}_{k,t_2} - \mathbf{z}_{k,t_1}$, while for $r_{t_1}, r_{t_2} > 0$, any constant range bias $b_r$ cancels out of temporal range differences $\Delta r_{t_1 \to t_2} = r_{t_2} - r_{t_1} = (\|\mathbf{d}_{t_2}\|_2 - \|\mathbf{d}_{t_1}\|_2) + (\nu_{t_2} - \nu_{t_1})$, *whereas* $b_r$ **does NOT cancel** out of spherical chord curvature! Specifically, writing $\mathbf{d}_{t_2} = \mathbf{d}_{t_1} + \Delta \mathbf{d}$:
  $$\|\mathbf{d}_{t_2}\|_2 - \|\mathbf{d}_{t_1}\|_2 = \sqrt{\|\mathbf{d}_{t_1} + \Delta \mathbf{d}\|_2^2} - \|\mathbf{d}_{t_1}\|_2.$$
  When range has bias $b_r \ne 0$ (`-0.40 m` in `COMPOUND_HOLDOUT_EXTREME` or `+1.0 m` in `FAULTY_REFERENCE_SENSOR`) and Huber fits a spurious $\hat{\mathbf{b}}_k$ matching radius $R + b_r$ instead of true radius $R$, traversing a transverse chord of length $L$ yields true range change $\sqrt{R^2 + L^2} - R \approx \frac{L^2}{2R}$ vs. spurious circle prediction $\sqrt{(R + b_r)^2 + L^2} - (R + b_r) \approx \frac{L^2}{2(R + b_r)}$ (`0.123 m` mismatch near arrival at $R = 0.83\text{ m}, b_r = -0.40\text{ m}, L = 0.50\text{ m}$), directly powering the fail-closed Decision-3 corroboration gate (`Section 3.4.3`).
- **Independent Observability & Noise Sensitivity:** Computed strictly from valid `(reading_a, reading_b, range_reading, anchor_reading)` histories (`Decision 4`). Single-step finite differences $\dot{r}_t = (r_t - r_{t-1})/\Delta t$ have extreme noise (`3.54 m/s`—**never use 1-step finite-difference range rates!**); multi-step chord increments over $t_2 - t_1 \ge 10\text{–}16$ steps have $\mathrm{SD}(\Delta r) = \sqrt{2}\sigma_r \approx 0.0707\text{ m}$.
- **False Alarms & Missed Detections:** *False alarms:* evaluating curvature at large distance $R > 3.5\text{ m}$ where $\frac{L^2}{2R}$ lies within noise (prevented by failing closed to `"ABSTAIN"` whenever separation is $\le 3.5\,\sigma_{\Delta r}$ in `Section 3.4.3`). *Missed detections:* small range biases $|b_r| < 0.12\text{ m}$ without anchor queries.

### Diagnostic D4 — Post-Calibration Residual Autocorrelation & Drift-Slope Statistic
- **Physical / Mathematical Relationship:** For a correctly calibrated static bias $\hat{\mathbf{b}} = \mathbf{b}$ under $b_r = 0$ and $\mathbf{d}_{\mathrm{drift}} = \mathbf{0}$, the signed post-calibration residual $\tilde{e}_t(\hat{\mathbf{b}}) := \|\mathbf{z}_t - \hat{\mathbf{b}}\|_2 - r_t \approx \frac{\mathbf{d}_t^\top \boldsymbol{\varepsilon}_t}{\|\mathbf{d}_t\|_2} - \nu_t$ is zero-mean **temporally white** noise ($\mathrm{Cov}(\tilde{e}_t, \tilde{e}_{t-1}) = 0$) with $\mathrm{Var}(\tilde{e}_t) = \sigma_v^2 + \sigma_r^2$. Under uncompensated bias error $\Delta \mathbf{b} \ne \mathbf{0}$, linear drift $\mathbf{d}_{\mathrm{drift}} t$, or range bias $b_r \ne 0$, $\tilde{e}_t(\hat{\mathbf{b}})$ contains a deterministic trajectory trend $\mu_t = \|\mathbf{d}_t + \Delta\mathbf{b} + \mathbf{d}_{\mathrm{drift}} t\|_2 - \|\mathbf{d}_t\|_2 - b_r$, inducing positive lag-1 autocorrelation $\rho_1 > 0$ and non-zero OLS slope $\hat{\beta}_1$ of $\tilde{e}_t$ on $t$.
- **Independent Observability:** Directly observable from valid `(z_t, r_t)` pairs during `CALIBRATED` approach.
- **Noise Sensitivity:** Over $W = 20$ steps, nominal $\mathrm{SD}\big(\frac{1}{W}\sum \tilde{e}_t\big) = \sqrt{(\sigma_v^2+\sigma_r^2)/20} \approx 0.0137\text{ m}$ (fused $\sigma_v = 0.0354, \sigma_r = 0.05$). Note that in V8 (`agent_next.py:63-65, 287`), `calibrated_martingale` monitored the **folded** residual $|\tilde{e}_t|$ against `nominal_mean = 0.065 m` (`0.995` decay), losing sign coherence and ~`25%` drift sensitivity compared to monitoring signed $\tilde{e}_t^2 - (\sigma_v^2 + \sigma_r^2)$ and $\sum \tilde{e}_{t}\tilde{e}_{t-1}$!
- **False Alarms & Missed Detections:** *False alarms:* near $d_t \to 0$, $\|\mathbf{d}_t + \boldsymbol{\varepsilon}_t\|_2$ acquires positive Jensen bias $\approx \frac{\sigma_v^2}{2 d_t}$ (`~0.0028 m` at $d=0.22\text{ m}$, negligible, but up to `0.044 m` at $d=0$). *Missed detections:* constant range bias $b_r < 0$ cancelled locally by a mis-fit $\hat{\mathbf{b}}$ along a straight-line radial approach (which is why D1 + D2 + symmetric 3-way anchor/chord checks are also needed).

### Diagnostic D5 — Commanded-Force MuJoCo Rolling-Sphere Kinematics vs. Observed Vector Motion
- **Exact Physical Derivation from `world.py` (`[NEW-DERIVATION]`, `[VERIFIED]`):**
  Inspecting `src/aegis/v3/env/world.py:84-116, 158-176, 261-295`:
  1. The robot is a uniform solid 3D sphere of mass $m = 1.0\text{ kg}$ and radius $R = 0.20\text{ m}$ (`lines 14-15, 105-109`) with a 6-DoF `<freejoint/>` (`line 102`), initialized at $\mathbf{q}_{\text{pos}}(0) = (-2.0, -2.0, 0.25)\text{ m}$ (`lines 158-162`, i.e., $5\text{ cm}$ above the floor plane $z = 0$ since $R = 0.20\text{ m}$) with zero velocity (`line 171`).
  2. External horizontal force $\mathbf{F}_t = F_{\mathrm{ctrl}}\,\mathrm{clip}(\mathbf{u}_t, -1, 1)$ ($F_{\mathrm{ctrl}} = 1.0\text{ N}$, `lines 17, 238-264, 281-284`) is applied at the sphere center of mass (`xfrc_applied[robot_body_id, :2]`).
  3. **Two Physical Regimes Verified in MuJoCo 3.14.0:**
     - **Steps $0 \le t \le 5$ (Free-Fall Before Floor Contact):** While $z(t) > 0.20\text{ m}$, there is zero floor contact friction, so horizontal CoM acceleration is $\mathbf{a}_{\mathrm{free},t} = \frac{\mathbf{F}_t}{m} = 1.0\,\mathbf{u}_t\text{ m/s}^2$.
     - **Steps $t \ge 7$ (Rolling Without Slipping on Plane $z = 0$):** Under gravity $g = 9.81\text{ m/s}^2$ (normal force $N = mg = 9.81\text{ N}$, default MuJoCo sliding friction $\mu = 1.0 \implies \mu N = 9.81\text{ N} \gg \frac{2}{7}\|\mathbf{F}_t\| \le 0.404\text{ N}$), static contact friction enforces rolling without slipping ($\mathbf{v}_{\mathrm{CoM}} = \boldsymbol{\omega} \times R\hat{\mathbf{k}}$). With solid-sphere rotational inertia $I = \frac{2}{5}mR^2$, $m\dot{\mathbf{v}} = \mathbf{F}_t - \mathbf{f}_s$ and $I\dot{\boldsymbol{\omega}} = R\mathbf{f}_s \implies \mathbf{f}_s = \frac{2}{7}\mathbf{F}_t$, yielding effective translational mass $m_{\mathrm{eff}} = \frac{7}{5}m = 1.40\text{ kg}$ and horizontal acceleration:
       $$\mathbf{a}_{\mathrm{roll},t} = \frac{5}{7m} F_{\mathrm{ctrl}} \mathbf{u}_t = \frac{5}{7}\mathbf{u}_t \approx 0.714286\,\mathbf{u}_t\text{ m/s}^2!$$
  4. Therefore, for a stationary target (`moving_target=False`, `actuator_noise=0.0`, `external_force_probability=0.0`), second-order sensor differences over $L$ steps ($t \ge 7$) satisfy:
     $$(\mathbf{z}_{k,t+L} - \mathbf{z}_{k,t}) - (\mathbf{z}_{k,t} - \mathbf{z}_{k,t-L}) \approx -\sum_{\ell=1}^{L}\big(\mathbf{p}_{\text{robot}}(t+\ell)-\mathbf{p}_{\text{robot}}(t+\ell-1)\big) + \dots + (\boldsymbol{\varepsilon}_{k,t+L} - 2\boldsymbol{\varepsilon}_{k,t} + \boldsymbol{\varepsilon}_{k,t-L}),$$
     where **constant velocity AND constant linear sensor drift $\mathbf{d}_{\mathrm{drift},k}\, t$ BOTH cancel out of second differences**, whereas open-loop integration from $t=0$ accumulates velocity uncertainty if any initial bounce or external disturbance occurs!
- **Independent Observability & Interface Boundary (`[VERIFIED]`):**
  `world.state()["robot_velocity"]` is **NOT** passed to `ctrl.update(...)` (`benchmark_next.py:260-262`). Only the controller's own commanded actions $\mathbf{u}_{0:t-1}$ are known to the agent!
  - *Noise Sensitivity:* Because $(\Delta t)^2 = 4 \times 10^{-4}\text{ s}^2$, single-step displacement acceleration is $\sim 2.86 \times 10^{-4}\text{ m}$ vs. $\sqrt{6}\sigma_v \approx 0.122\text{ m}$ sensor noise (`SNR << 1` at $L=1$), becoming informative **only** over long windows $L \ge 25$ steps ($L^2 (\Delta t)^2 a \approx 0.18\text{ m}$ vs. $\sqrt{6}\sigma_v \approx 0.12\text{ m}$, `SNR ~ 1.5`) AND breaking if `moving_target=True` or external disturbances are enabled (`world.py:25-29`).
  - *Design Consequence:* Open-loop force double-integration is useful only as a coarse sanity check against sudden step jumps (such as single-sensor dropout bias jumps in `COMPOUND_ANTIPODAL_RANGE_SHIFT`, where $\mathbf{z}_{\text{fused}}$ jumps by $0.50\text{ m}$ in `1` step = `1,750x` max physical 1-step acceleration!), **not** for dead-reckoning terminal position!

---

## 3.5 Primary & Secondary Outcomes, Noninferiority, and Utility Guardrails

To prevent achieving $R_{\mathrm{sel}} \le 0.05$ through trivial near-total abstention (as `EKF_CONSISTENCY_MONITOR` did at `3.0%` coverage), V9 evaluates safety and operational utility jointly across eight predeclared metrics:

| Metric | Symbol / Estimator | Paired Statistical Comparison vs. V8 & V7 (`D_test^scen`) | Acceptance / Interpretation Criterion |
| :--- | :--- | :--- | :--- |
| **1. Selective False-Success Risk (Primary)** | $\hat{R}_{\mathrm{sel}} = K / M$ (`UNDEFINED` if $M=0$) | 1-sided 95% exact Clopper–Pearson UCB (`D_test^mix`); paired episode bootstrap CI for $\Delta R_{\mathrm{sel}}$ | **Confirmatory Pass (`H1`):** $M \ge 59$ and $U_{\mathrm{CP},1}(K, M; 0.05) \le 0.05$. |
| **2. Unconditional FS Incidence** | $\hat{R}_{\mathrm{inc}} = K / N$ | Exact 2-sided paired McNemar test + Newcombe paired CI | Must satisfy $U_{\mathrm{CP},1}(K, N; 0.05) \le 0.05$ pooled and reduced incidence on $\mathcal{S}_{\mathrm{comp}}$ (`H4`). |
| **3. True-Success Rate (`TSR`) & Noninferiority** | $\widehat{TSR} = \sum TS_i / N$ | **Prespecified NI Test:** 1-sided 95% paired LCB on $\Delta TSR = TSR(\hat{\pi}) - TSR(\pi_{\mathrm{ref}})$ across $N=1,200$ matched $\mathcal{S}_{10}$ pairs (`D_test^scen`) | **Noninferiority Margin $\Delta_{\mathrm{NI}} = -0.05$ (`-5.0%`):** Claim noninferiority iff $\mathrm{LCB}_{95\%}(\Delta TSR) > -0.05$ AND $\widehat{TSR}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$. |
| **4. Acceptance Coverage & Abstention Split** | $\hat{C} = M/N$, $\widehat{AB}_{\mathrm{exp}}$, $\widehat{TO}$ | Exact paired McNemar + 2-sided 95% CI | Minimum overall utility guardrail: $\hat{C}(\hat{\pi}; \mathcal{P}_{12}) \ge C_{\min} = 0.35$ (target $\ge 0.45$). |
| **5. Anchor Query Cost** | $\overline{AC} = \frac{1}{N}\sum \text{anchor\_cost}_i$ | Paired Wilcoxon signed-rank + paired bootstrap 95% CI | Report cost-risk Pareto frontier; target $\overline{AC}(\hat{\pi}; \mathcal{P}_{10}) \le \overline{AC}(\pi_{\mathrm{V7}}) = 0.144$. |
| **6. Decision Latency (Steps & Wall-Clock)** | Mean/median `steps` (overall & on `TS=1`) + per-step ms | Paired Wilcoxon signed-rank + paired bootstrap 95% CI | Target per-step runtime `< 2.0 ms` CPU; report horizon timeout rate $\widehat{TO}$ separately. |
| **7. Trajectory Overshoot** | $\bar{O} = \frac{1}{N}\sum \text{max\_overshoot}_i$ | Paired Wilcoxon signed-rank + paired $t$-test + paired bootstrap CI | Target $\bar{O}(\hat{\pi}) \le 0.10\text{ m}$; never report unpaired or miscalculated $p$-values. |
| **8. Scenario Worst-Case & Compound Reliability** | $\max_{s} \hat{R}_{\mathrm{inc},s}$, $\max_{s: M_s \ge 1} \hat{R}_{\mathrm{sel},s}$ | Šidák/Holm simultaneous 12-scenario CIs + Berger IUT | Explicit per-scenario breakdown across all `12` scenarios (`H5`). |

**Strict Anti-Gaming Rule:** A reduction in $R_{\mathrm{sel}}$ or $R_{\mathrm{inc}}$ accompanied by either $\hat{C}(\hat{\pi}; \mathcal{P}_{12}) < 0.35$, $\widehat{TSR}_{\mathrm{NOMINAL}}(\hat{\pi}) < 0.94$, or violation of the $-5.0\%$ paired `TSR` noninferiority bound **must NOT be reported as an overall operational improvement**; it must be reported transparently as a **conservative risk–coverage trade-off**.

---

## 3.6 Reproducibility, Data Provenance, and Execution Integrity Requirements

### 3.6.1 Locked Seed & Split Manifest Specification

All splits use Python's `numpy.random.default_rng` (PCG64) with zero overlap across partitions:
1. **Historical Archive ($\mathcal{D}_{\text{hist}}$, read-only):** `results/next/benchmark_episodes.csv` (`seeds 60000..60049` on $\mathcal{S}_{10}$). Protected by SHA-256 verification; **never overwritten**.
2. **Development ($\mathcal{D}_{\text{dev}}$):** Deterministic grid `[(s, seed) for s in S_12 for seed in range(70000, 70030)]` (`360` episodes).
3. **Calibration ($\mathcal{D}_{\text{cal}}$):** Generated once via `rng_manifest = np.random.default_rng(20260901)`, drawing `scen_idx = rng_manifest.integers(0, 12, size=960)` paired with unique episode seeds `71000 .. 71959` (`960` episodes). Written to `results/v9/manifests/cal_manifest.json` with SHA-256 digest before calibration runs.
4. **Pre-Holdout Validation ($\mathcal{D}_{\text{val}}$):** Deterministic grid `[(s, seed) for s in S_12 for seed in range(72000, 72040)]` (`480` episodes).
5. **Final Holdout — Pooled Mixture ($\mathcal{D}_{\text{test}}^{\text{mix}}$):** Generated once via `rng_manifest = np.random.default_rng(20260902)`, drawing `scen_idx = rng_manifest.integers(0, 12, size=1440)` paired with unique episode seeds `73000 .. 74439` (`1,440` episodes). Written to `results/v9/manifests/test_mix_manifest.json`.
6. **Final Holdout — Stratified Per-Scenario ($\mathcal{D}_{\text{test}}^{\text{scen}}$):** Deterministic grid `[(s, seed) for s in S_12 for seed in range(75000, 75120)]` (`1,440` episodes; `120` per scenario). Written to `results/v9/manifests/test_scen_manifest.json`.

### 3.6.2 Verified Runtime Environment & Invocation Standards (`[VERIFIED]`)

- **Verified Baseline Environment:**
  - OS / Architecture: `macOS-27.0.1-arm64-arm-64bit` (Apple Silicon)
  - Package Manager: `uv 0.12.19` (`pyproject.toml` + `uv.lock`)
  - Python: `3.12.14`
  - Core Scientific Stack: `numpy 2.5.3`, `scipy 1.18.1`, `mujoco 3.14.0`, `pytest 9.1.1`
- **Isolated Output Directory Rule:** All future V9 scripts must write exclusively under `results/v9/` (`results/v9/dev/`, `results/v9/cal/`, `results/v9/val/`, `results/v9/test_mix/`, `results/v9/test_scen/`, `results/v9/sha256_manifest.json`). Writing to `results/next/` or `results/v8_audit/` is strictly prohibited.
- **Planned CLI Entrypoints (for future V9 implementation phase only — NOT created in this task):**
  - Historical test regression check: `uv run pytest -q` (must keep all `67` historical V1–V8.1 tests passing).
  - Manifest generation & hash lock: `PYTHONPATH=src uv run python experiments/v9_generate_manifests.py`
  - Single-shot LTT calibration: `PYTHONPATH=src uv run python experiments/v9_calibrate_ltt.py --manifest results/v9/manifests/cal_manifest.json --candidates configs/v9_candidates_frozen.json --out results/v9/cal/`
  - Single-shot locked holdout evaluation: `PYTHONPATH=src uv run python experiments/v9_evaluate_holdout.py --frozen-policy results/v9/cal/selected_policy.json --out results/v9/test/`
  - Deterministic Markdown/CSV table compiler: `PYTHONPATH=src uv run python experiments/v9_compile_report_tables.py --in-dir results/v9/ --verify-hashes`

### 3.6.3 Required Test Coverage Before Running Calibration or Holdout

Before `v9_calibrate_ltt.py` or `v9_evaluate_holdout.py` may be executed in the implementation phase, automated `pytest` tests (`tests/test_v9_*.py`) must verify:
1. **Hybrid Monitor Integrity & Input Hygiene (`Decision 1`):** Exact $\gamma = 1.0$, absence of lower reflecting wealth floor and invalidating upper cap on Channel A, strict $\mathcal{F}_{t-1}$-predictability of $\lambda_{c,t}$, strict positivity $m_{c,t} \ge 0.10 > 0$, `NaN`/`Inf` fail-closed `"ABSTAIN"` handling, empirical nominal Channel A false-alarm rate $\le \alpha_{\mathrm{mon}}$ over both `300`-step and `5,000`-step horizons, and explicit separation of Channel B CUSUM threshold $h_{\mathrm{cusum}}^{(j)}$ inside $\Lambda$ without Ville claims.
2. **Per-Sensor Calibration, Disjoint Data-Flow, & Fail-Closed Gates (`Decisions 2, 3, & 4`):** Regression tests proving: (i) separate `estimator_a` / `estimator_b` fitting and single-sensor isolation without fused-bias jumps under dropout; (ii) `NOMINAL` $\to$ `ACTIVE_PROBING` returns `"PROBE"` immediately without falling through to `"STOP"`; (iii) dropped range packets (`range_reading.valid == False`) never bypass terminal arrival verification; (iv) strictly disjoint probing index sets (`set(fit_steps) & set(val_steps) == set()`, `val_passed == False` when $n_{\mathrm{val},k} < 6$, and zero online estimator mutations during `CALIBRATED` mode); (v) fail-closed `"ABSTAIN"` on anchor/range disagreement including rejection of static anchor bias `(1.2, -1.0)` in `CORRUPTED_ANCHOR_STRESS`; and (vi) exact 4-input signature parity `(reading_a, reading_b, range_reading, anchor_reading)` (`step: int = 0`).
3. **Exact Selective-Risk Statistics:** Unit tests verifying `p_sel == 1.0` when $M < m_{\min}$, exact `UNDEFINED` (`NaN` + `selective_risk_defined == False`) when $M = 0$, exact agreement with `scipy.stats.binom.cdf` and `scipy.stats.beta.ppf`, Fixed-Sequence LTT FWER $\le 0.05$ under Monte Carlo simulation with non-monotone risks, and exact seed-disjointness across all manifests.
4. **Historical Reproduction & Failed/Incomplete Run Integrity:** Exact bit-level reproduction check confirming `AegisNextController` on `NOMINAL` (`seed=60000`) and `INDEPENDENT_BIAS` (`seed=60002`) matches historical V8 behavior, plus schema enforcement requiring complete episode counts (`N == len(manifest)`) where any aborted/incomplete benchmark run marks the entire run artifact `INCOMPLETE_INVALID` and refuses summary compilation, while any per-episode controller exception logs `crashed = 1, false_success = 1` visibly in the output report.

---

## 3.7 Approved Preregistration Decisions (1–4), Residual Design Risks, and Next Milestone (`[APPROVED-DECISION]`, `[DESIGN-RISK]`)

### 3.7.1 Summary of Locked Preregistration Decisions

1. **Decision 1 (Hybrid Parallel Ville + Drift-Detection Channels):** Adopt **Channel A** (exact $\gamma = 1.0$, unfloored, uncapped nonnegative Ville e-process mixture under nominal bounded-mean null $H_{0,\mathrm{mon}}$, never claimed to control closed-loop task risk) alongside **Channel B** (complementary Page CUSUM drift detector, never described as Ville-anytime-valid), calibrating both channel thresholds ($\alpha_{\mathrm{mon}}^{(j)}, h_{\mathrm{cusum}}^{(j)}$) and their combination logic jointly inside the 6-tier candidate family $\Lambda$ via Fixed-Sequence LTT on $\mathcal{D}_{\text{cal}}$, while keeping monitor false alarms, fault detection delay, and policy selective risk $R_{\mathrm{sel}}$ strictly distinct.
2. **Decision 2 (Per-Sensor Bias Calibration & Disjoint Validation Data-Flow):** Estimate `vec_a` ($\hat{\mathbf{b}}_a$) and `vec_b` ($\hat{\mathbf{b}}_b$) separately during `ACTIVE_PROBING` (preserving explicit inter-sensor disagreement, filtering invalid/dropout samples before buffer insertion, tracking per-sensor `CALIBRATED_VALID` / `DROPOUT_INSUFFICIENT` / `REJECTED_OR_FAULTY` status and variance $\hat{u}_k^2$, and deferring selective single-sensor-only calibration as a future comparison candidate), while enforcing strictly disjoint $(\mathcal{I}_{\mathrm{fit}}, \mathcal{I}_{\mathrm{gap}}, \mathcal{I}_{\mathrm{val}})$ probing windows and prohibiting continuous online refitting during `CALIBRATED` mode.
3. **Decision 3 (Fail-Closed Anchor/Range Disagreement Rule):** Treat V8's `0.35 m` threshold as an unvalidated inherited candidate rather than a safety limit; parameterize normalized tolerance $\tau_{ar}^{(j)}$ inside $\Lambda$; default to `"ABSTAIN"` on anchor/range disagreement unless all prespecified pre-holdout drift-free vector-chord and range-increment corroboration conditions (`Section 3.4.3`) hold unambiguously without common-mode vulnerability; never treat range or anchor as an unquestionable oracle.
4. **Decision 4 (Strict Four-Input Sensor-Interface Parity):** Keep the exact runtime signature `(reading_a, reading_b, range_reading, anchor_reading)` (`step: int = 0`) with zero new wheel odometry, encoder, or IMU sensors, computing all temporal consistency diagnostics (`D1`–`D5`) solely from valid intra-episode histories of those four inputs and past controller commands $\mathbf{u}_{0:t-1}$.

### 3.7.2 Remaining Unresolved Assumptions & Operational Design Risks (`[DESIGN-RISK]`)

1. **Non-Gaussian Burst Sensitivity (`OUTLIER_BURSTS`):** Heavy-tailed $4.5\times\sigma$ bursts ($p = 0.12$) violate Channel A's nominal Gaussian mean bound $H_{0,\mathrm{mon}}$, increasing `ACTIVE_PROBING` entry rates; whether post-probing Huber per-sensor recovery preserves `TSR` noninferiority without inflating $\hat{R}_{\mathrm{sel}}$ must be verified on $\mathcal{D}_{\text{dev}}$ before locking $\Lambda$.
2. **Per-Sensor Probing Sample Size Under `40%` Dropout:** Under `SENSOR_DROPOUT` (`p_drop = 0.40`) or `COMPOUND_ANTIPODAL_RANGE_SHIFT` (`p_drop = 0.35`), a 22-step $\mathcal{I}_{\mathrm{fit}}$ window yields $\mathbb{E}[n_{\mathrm{fit},k}] \approx 13.2\text{–}14.3$ and a 12-step $\mathcal{I}_{\mathrm{val}}$ window yields $\mathbb{E}[n_{\mathrm{val},k}] \approx 7.2\text{–}7.8$, creating a non-zero probability that one sensor falls into `DROPOUT_INSUFFICIENT` ($n_{\mathrm{val},k} < 6$) and relies on the healthy companion sensor.
3. **Anchor Budget vs. Two-Epoch Corroboration:** Distinguishing static range bias ($b_r \ne 0$) from static anchor corruption ($\mathbf{b}_{\mathrm{anc}} \ne \mathbf{0}$) under Decision 3 requires at least two valid anchor queries separated by chord length $L \ge 0.40\text{ m}$ (`cost >= 0.10`); episodes where anchor queries fail to achieve $L \ge 0.40\text{ m}$ will conservatively abstain (`"ABSTAIN"`), trading coverage for safety in `COMPOUND_HOLDOUT_EXTREME`.
4. **Mixture Shift Non-Invariance & Low-Coverage Scenario Limits:** Pooled certification on $\mathcal{P}_{12}$ guarantees $R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) \le 0.05$ under uniform 12-scenario mixture sampling only—not under adversarial scenario reweighting—and per-scenario selective certification $R_{\mathrm{sel},s} \le 0.05$ remains statistically unattainable in abstention-dominated fault scenarios where $M_s < 59$ (`107` simultaneous).

### 3.7.3 Next Implementation Milestone (Authorized Only in Subsequent Task — Not Started Here)

- **Milestone V9-M1 (Modular Runtime-Assurance & Statistical Harness Implementation on `v9.0-runtime-assurance`):** Implement `src/aegis/v9/` (Channel A Ville monitor, Channel B CUSUM detector, per-sensor disjoint-window calibration engine, fail-closed anchor/range chord gate, `AegisV9Controller` with 4-input parity, and exact conditional-binomial LTT statistics), write and pass `tests/test_v9_*.py` while keeping all `67` historical V1–V8.1 tests passing, tune/verify $\Lambda$ ordering strictly on $\mathcal{D}_{\text{dev}}$ (`seeds 70000..70029`), freeze `configs/v9_candidates_frozen.json`, and stop prior to running single-shot $\mathcal{D}_{\text{cal}}$ / $\mathcal{D}_{\text{test}}$ certification unless explicitly authorized.
