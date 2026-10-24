# NEXVIA AEGIS V9.0 — Risk-Calibration Mathematical Design (Step 2 of 3)

**Repository Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`
**Active Git Branch:** `v9.0-runtime-assurance`
**Protected V8.1 Baseline Commit:** `4d891c7500cfb4c8110f276038455bc62765ef3b`
**Companion Documents:** `docs/v9_research_audit.md` (Step 1), `docs/v9_experiment_protocol.md` (Step 3)
**Design Governance Status:** **Preregistration Decisions 1–4 Approved & Locked Prior to Implementation**
**Scope:** Formal specification of episode-level outcome algebra, target risk estimands, hybrid sequential monitoring proofs (Channel A Ville e-process vs. Channel B drift detector), candidate statistical calibration frameworks, random-denominator selective-risk hypothesis tests, prespecified joint policy selection, intra-episode vs. inter-episode independence, disjoint episode splits, and scenario-level vs. pooled guarantees. No runtime code is modified in this design phase.

---

## 2.1 Episode-Level Outcome Algebra and Target Risk Estimands

### 2.1.1 Code-Verified Episode Execution and Outcome Partition (`[VERIFIED]`)

In the NEXVIA AEGIS benchmark (`experiments/benchmark_next.py:249-308`, `src/aegis/v3/env/world.py:23, 286-312`), a closed-loop episode $Z = (S, \xi)$ consists of a scenario configuration $S \in \mathcal{S}$ and an episode random seed $\xi \in \mathbb{N}$ that deterministically initializes the target position $\mathbf{p}^* \sim \mathrm{Uniform}([-3, 3]^2)$ (`world.py:152-156`) and generates all sensor noise/dropout realizations (`benchmark_next.py:202-204, 241`).

Given a deterministic, memory-reset closed-loop policy $\pi$ (`ctrl.reset()` invoked before step `0`), execution runs for steps $t = 0, 1, \dots, T_{\max}-1$ ($T_{\max} = 300$, $\Delta t = 0.02\text{ s}$) until the stopping step $\tau(\pi, Z)$ defined by `benchmark_next.py:265-266, 280-281`:
1. **Deliberate Terminal Commit (`"STOP"`):** Policy returns `dec_type == "STOP"` at step $t \in \{0, \dots, 299\}$; loop terminates immediately *before* `world.step` executes (`stopped = True`, `abstained = False`, $\tau = t < 300$).
2. **Deliberate Safety Abstention (`"ABSTAIN"`):** Policy returns `dec_type == "ABSTAIN"` at step $t \in \{0, \dots, 299\}$; loop terminates immediately *before* `world.step` executes (`stopped = False`, `abstained = True`, $\tau = t < 300$).
3. **Horizon Truncation / Timeout:** Policy returns only non-terminal decisions (`"ACT"`, `"PROBE"`, `"VERIFY"`) for all $300$ iterations; `w_st["truncated"]` becomes `True` at `final_st["step"] == 300` (`stopped = False`, `abstained = False`, $\tau = 300$).

Let $d_{\tau}(\pi, Z) = \|\mathbf{p}^* - \mathbf{p}_{\text{robot}}(\tau)\|_2$ denote the true terminal Euclidean distance (`final_dist`, `benchmark_next.py:284`) and $d_{\text{safe}} = 0.45\text{ m}$ (`benchmark_next.py:291-292`, equal to `robot_radius (0.20 m) + success_radius (0.25 m)`). Verifying `benchmark_next.py:288-294` establishes the exact binary indicators on each episode $Z$:

| Symbol | Formal Definition | Benchmark Code Equivalent (`benchmark_next.py:288-294`) | Semantics |
| :---: | :--- | :--- | :--- |
| $A(\pi, Z)$ | $\mathbb{I}\big(\mathrm{dec\_type}_{\tau} = \text{"STOP"}\big)$ | `int(stopped)` (`true_success + false_success`) | Policy accepts/commits to a terminal arrival claim. |
| $TS(\pi, Z)$ | $\mathbb{I}\big(A(\pi, Z) = 1 \land d_{\tau}(\pi, Z) \le 0.45\big)$ | `int(stopped and (final_dist <= 0.45))` | Correct terminal arrival commitment. |
| $FS(\pi, Z)$ | $\mathbb{I}\big(A(\pi, Z) = 1 \land d_{\tau}(\pi, Z) > 0.45\big)$ | `int(stopped and (final_dist > 0.45))` | **Hazardous false-success commitment** outside $0.45\text{ m}$. |
| $AB_{\mathrm{exp}}(\pi, Z)$ | $\mathbb{I}\big(\mathrm{dec\_type}_{\tau} = \text{"ABSTAIN"}\big)$ | `int(abstained)` | Deliberate runtime-assurance abstention. |
| $TO(\pi, Z)$ | $\mathbb{I}\big(A(\pi, Z) = 0 \land AB_{\mathrm{exp}}(\pi, Z) = 0\big)$ | `int(not stopped and not abstained)` (`steps == 300`) | Uncommitted episode truncated at $T_{\max} = 300$. |
| $AB(\pi, Z)$ | $AB_{\mathrm{exp}}(\pi, Z) + TO(\pi, Z) = 1 - A(\pi, Z)$ | `int(abstained or (not stopped and not true_success))` | Combined non-acceptance indicator under V8 convention. |

**Verified Algebraic Identities (`[VERIFIED]`):** Because the episode loop exits on the first step returning `"STOP"` or `"ABSTAIN"`, $A(\pi, Z)$ and $AB_{\mathrm{exp}}(\pi, Z)$ cannot both equal `1`. Therefore, for every policy $\pi$ and every episode $Z$:
$$A(\pi, Z) = TS(\pi, Z) + FS(\pi, Z) \in \{0, 1\}, \qquad AB(\pi, Z) = AB_{\mathrm{exp}}(\pi, Z) + TO(\pi, Z) = 1 - A(\pi, Z) \in \{0, 1\},$$
$$TS(\pi, Z) + FS(\pi, Z) + AB_{\mathrm{exp}}(\pi, Z) + TO(\pi, Z) = TS(\pi, Z) + FS(\pi, Z) + AB(\pi, Z) = 1.$$
*Important Distinction for V9:* While historical `AB` merges $AB_{\mathrm{exp}}$ and $TO$ (`140` timeouts in `UNSHIELDED_ALWAYS_ACT` were recorded as `abstain = 1`), V9 preserves $AB = 1 - A$ for exact backward compatibility with V8 while **additionally recording $AB_{\mathrm{exp}}$ and $TO$ as separate columns** so slow-controller timeouts are never misattributed to deliberate fault abstention.

---

### 2.1.2 Population Risk Estimands and Domain of Definition

Let $\mathcal{M}$ be a well-defined probability distribution over episodes $Z = (S, \xi)$ (either a single scenario distribution $\mathbb{P}_s$ with $S \equiv s$ and $\xi$ drawn uniformly from an infinite seed population, or a predeclared finite scenario mixture $\mathbb{P}_{\mathbf{w}} = \sum_{s \in \mathcal{S}} w_s \mathbb{P}_s$ with $\sum_{s \in \mathcal{S}} w_s = 1, w_s \ge 0$). For any fixed, frozen policy $\pi$:

1. **Unconditional False-Success Incidence:**
   $$R_{\mathrm{inc}}(\pi; \mathcal{M}) := \mathbb{P}_{Z \sim \mathcal{M}}\big(FS(\pi, Z) = 1\big) = \mathbb{E}_{Z \sim \mathcal{M}}\big[FS(\pi, Z)\big] \in [0, 1].$$
   *Domain:* Always defined for all policies $\pi$, including policies that always abstain ($C = 0 \implies R_{\mathrm{inc}} = 0$).

2. **Acceptance Coverage:**
   $$C(\pi; \mathcal{M}) := \mathbb{P}_{Z \sim \mathcal{M}}\big(A(\pi, Z) = 1\big) = \mathbb{E}_{Z \sim \mathcal{M}}\big[TS(\pi, Z) + FS(\pi, Z)\big] \in [0, 1].$$
   *(Note: True-success rate is $TSR(\pi; \mathcal{M}) := \mathbb{P}_{Z \sim \mathcal{M}}(TS(\pi, Z) = 1) = C(\pi; \mathcal{M}) - R_{\mathrm{inc}}(\pi; \mathcal{M}) = C(\pi; \mathcal{M})\big(1 - R_{\mathrm{sel}}(\pi; \mathcal{M})\big)$ when $C > 0$.)*

3. **Selective (Covered) False-Success Risk:**
   $$R_{\mathrm{sel}}(\pi; \mathcal{M}) := \begin{cases} \mathbb{P}_{Z \sim \mathcal{M}}\big(FS(\pi, Z) = 1 \,\big|\, A(\pi, Z) = 1\big) = \dfrac{R_{\mathrm{inc}}(\pi; \mathcal{M})}{C(\pi; \mathcal{M})}, & \text{if } C(\pi; \mathcal{M}) > 0, \\[8pt] \text{UNDEFINED}, & \text{if } C(\pi; \mathcal{M}) = 0. \end{cases}$$
   *Undefined Zero-Coverage Rule:* When $C(\pi; \mathcal{M}) = 0$ (or empirically when $M = \sum_{i=1}^N A_i = 0$), conditional probability given $\{A = 1\}$ has a zero-measure conditioning event. Selective risk is **strictly `UNDEFINED`—never `0.0`** (`docs/v9_research_audit.md`, Discrepancy E).

### 2.1.3 Why Controlling $R_{\mathrm{inc}}(\pi)$ Does Not Control $R_{\mathrm{sel}}(\pi)$ (`[NEW-DERIVATION]`)

Whenever $C(\pi; \mathcal{M}) > 0$, Bayes' rule gives the exact identity:
$$R_{\mathrm{sel}}(\pi; \mathcal{M}) = \frac{R_{\mathrm{inc}}(\pi; \mathcal{M})}{C(\pi; \mathcal{M})} \ge R_{\mathrm{inc}}(\pi; \mathcal{M}).$$
Because $C(\pi; \mathcal{M}) \in (0, 1]$, **any** policy whose coverage satisfies $0 < C(\pi; \mathcal{M}) \le \alpha$ automatically satisfies $R_{\mathrm{inc}}(\pi; \mathcal{M}) \le C(\pi; \mathcal{M}) \le \alpha$, even if **$R_{\mathrm{sel}}(\pi; \mathcal{M}) = 1.0$** (every single accepted decision is a catastrophic false success!).
- *Concrete V8 Empirical Proof:* In `COMPOUND_HOLDOUT_EXTREME` (`N = 50`), `AEGIS_NEXT_MARTINGALE` achieved $\hat{R}_{\mathrm{inc}} = 2/50 = 4.0\% \le 5.0\%$, yet its selective risk among committed `"STOP"` decisions was $\hat{R}_{\mathrm{sel}} = 2/3 = 66.7\%$ (`CHISQUARE_NIS_GATING` similarly had $\hat{R}_{\mathrm{inc}} = 2/50 = 4.0\%$ alongside $\hat{R}_{\mathrm{sel}} = 2/2 = 100.0\%$). Whenever a robot commits `"STOP"`, downstream actuation (docking, grasping, payload release) trusts that commitment; therefore $R_{\mathrm{sel}}(\pi; \mathcal{M})$—paired with an explicit minimum coverage/utility requirement—is the primary safety estimand for V9.

---

### 2.1.4 Mandatory Three-Way Separation: Monitor False Alarms, Fault Detection Delay, and Policy Selective Risk (`[APPROVED-DECISION]`, `[NEW-DERIVATION]`)

Under **Approved Decision 1**, all V9 mathematical claims and architecture modules maintain a strict separation among three distinct statistical properties:

1. **Property I — Nominal Monitor False-Alarm Control (Type-I Sequential Error under $H_{0,\mathrm{mon}}$):** Bounds the probability $\mathbb{P}_{H_{0,\mathrm{mon}}}(\tau_{\mathrm{alarm}} < \infty)$ (or finite-horizon trigger rate) that a residual monitor falsely raises an anomaly alarm when all sensors satisfy a specified nominal noise model.
2. **Property II — Fault Detection Performance and Detection Delay (Sensitivity under $H_1$):** Quantifies $\mathbb{P}_{H_1}(\tau_{\mathrm{alarm}} < \tau_{\mathrm{stop}})$ and conditional detection latency $\mathbb{E}_{H_1}[(\tau_{\mathrm{alarm}} - t_{\mathrm{fault}})_+]$ under static, drifting, or compound sensor faults.
3. **Property III — Final Policy Selective False-Success Risk ($R_{\mathrm{sel}}(\pi; \mathcal{M})$):** Quantifies $\mathbb{P}_{Z \sim \mathcal{M}}(FS(\pi, Z) = 1 \mid A(\pi, Z) = 1)$ across complete closed-loop episodes, which depends jointly on monitor triggers, active probing, per-sensor bias calibration, anchor/range disagreement resolution, and terminal `"STOP"` gating.

**None of Properties I, II, or III automatically implies any of the others.** In particular, V9 adopts a **hybrid two-channel sequential monitor** inside each candidate policy $\pi_{\lambda^{(j)}}$:

#### Channel A — Exact Nonnegative Ville e-Process ($\gamma = 1.0$, No Reflecting Floor, No Invalidating Cap)

Let $\mathcal{C} = \{\mathrm{ab},\, (\mathrm{vr},a),\, (\mathrm{vr},b)\}$ denote the active nonnegative residual subchannels during `NOMINAL` operation (and the subset of calibrated `CALIBRATED_VALID` subchannels initialized fresh upon entering `CALIBRATED` mode), with step-level filtration $\mathcal{F}_t = \sigma\big((V_{c,s}, e_{c,s})_{c \in \mathcal{C},\, 1 \le s \le t}\big)$ ($\mathcal{F}_0$ trivial):
- **Validity Indicator & Fail-Closed Input Hygiene:** For each subchannel $c \in \mathcal{C}$ at step $t \ge 1$, if any constituent sensor reading with `valid == True` contains `NaN` or `Inf`, the controller fails closed to `"ABSTAIN"` before updating the monitor. Otherwise, $V_{c,t} \in \{0, 1\}$ equals `1` iff all constituent readings of subchannel $c$ have `valid == True` (and `0` on packet dropout, leaving wealth unchanged).
- **Subchannel Residuals & Closed-Form Analytical Nominal Null Bounds:**
  1. *Inter-sensor disagreement ($c = \mathrm{ab}$, $V_{\mathrm{ab},t} = \mathbb{I}(\text{reading\_a.valid} \land \text{reading\_b.valid})$):*
     $$e_{\mathrm{ab},t} := \|\mathbf{z}_{a,t} - \mathbf{z}_{b,t}\|_2 \ge 0, \qquad \mu_{0,\mathrm{ab}} := \sqrt{\frac{\pi}{2}(\sigma_a^2 + \sigma_b^2)}.$$
  2. *Per-sensor vector-vs.-range discrepancy ($c = (\mathrm{vr}, k)$ for $k \in \{a, b\}$, $V_{\mathrm{vr},k,t} = \mathbb{I}(\text{reading\_k.valid} \land \text{range\_reading.valid})$):*
     $$e_{\mathrm{vr},k,t} := \big|\|\mathbf{z}_{k,t}\|_2 - r_t\big| \ge 0, \qquad \mu_{0,\mathrm{vr},k} := \sigma_k\sqrt{\frac{\pi}{2}} + \sigma_r\sqrt{\frac{2}{\pi}}.$$
- **Tested Composite Null Hypothesis $H_{0,\mathrm{mon}}$:**
  $$H_{0,\mathrm{mon}} \;:\; \forall c \in \mathcal{C},\; \forall t \ge 1,\quad \mathbb{E}\big[e_{c,t} \,\big|\, \mathcal{F}_{t-1},\, V_{c,t} = 1\big] \le \mu_{0,c}.$$
  *Verification Under Nominal Sensor Physics (`sensors.py:86-113`, `cross_modal.py:60-78`):* Under unbiased zero-drift Gaussian sensor noise $\boldsymbol{\varepsilon}_{k,t} \sim \mathcal{N}(\mathbf{0}, \sigma_k^2 \mathbf{I}_2)$ and $\nu_t \sim \mathcal{N}(0, \sigma_r^2)$ drawn independently at step $t$ of $\mathcal{F}_{t-1}$ and of Bernoulli dropout $V_{c,t}$ (with closed-loop true relative vector $\mathbf{d}_t = \mathbf{p}^* - \mathbf{p}_{\text{robot}}(t)$ predetermined at the start of step $t$):
  - For $c = \mathrm{ab}$, $\mathbf{d}_t$ cancels identically, so $\|\boldsymbol{\varepsilon}_{a,t} - \boldsymbol{\varepsilon}_{b,t}\|_2 \sim \mathrm{Rayleigh}\big(\sqrt{\sigma_a^2 + \sigma_b^2}\big)$ with exact mean $\mu_{0,\mathrm{ab}}$ (`0.08862 m` at $\sigma_a = \sigma_b = 0.05\text{ m}$).
  - For $c = (\mathrm{vr}, k)$, since $u \mapsto \max(0, u)$ is $1$-Lipschitz and $\|\mathbf{d}_t + \boldsymbol{\varepsilon}_{k,t}\|_2 \ge 0$, the reverse triangle inequality holds pointwise for **every** $\mathbf{d}_t \in \mathbb{R}^2$:
    $$e_{\mathrm{vr},k,t} = \big|\max(0, \|\mathbf{d}_t + \boldsymbol{\varepsilon}_{k,t}\|_2) - \max(0, \|\mathbf{d}_t\|_2 + \nu_t)\big| \le \big|\|\mathbf{d}_t + \boldsymbol{\varepsilon}_{k,t}\|_2 - \|\mathbf{d}_t\|_2\big| + |\nu_t| \le \|\boldsymbol{\varepsilon}_{k,t}\|_2 + |\nu_t|.$$
    Taking conditional expectations given $\mathcal{F}_{t-1}, V_{\mathrm{vr},k,t}=1$ yields $\mathbb{E}_{H_0}[e_{\mathrm{vr},k,t} \mid \mathcal{F}_{t-1}, V_{\mathrm{vr},k,t}=1] \le \sigma_k\sqrt{\pi/2} + \sigma_r\sqrt{2/\pi} = \mu_{0,\mathrm{vr},k}$ (`0.10256 m` at $\sigma_k = \sigma_r = 0.05\text{ m}$) analytically for all $t \ge 1$ and all closed-loop positions $\mathbf{d}_t \in \mathbb{R}^2$.

- **Exact Update Rule ($\gamma = 1.0$, Log-Wealth Domain) and Proposition 2.1 (Predictability & All-Time Supermartingale Proof):**
  Fix scale $v_{\max,c} = 0.40\text{ m}$, upper score clip $x_{\max} = 3.50$, and predictable betting cap $\bar{\lambda}_c := \min\!\big(\lambda_{\max},\, \frac{0.90\,v_{\max,c}}{\mu_{0,c}}\big)$ ($\lambda_{\max} = 0.85$; note $\bar{\lambda}_c$ depends only on declared nominal parameters and is $\mathcal{F}_0$-measurable). Define:
  $$x_{c,t} := \min\!\left(\frac{e_{c,t} - \mu_{0,c}}{v_{\max,c}},\, x_{\max}\right), \qquad m_{c,t} := 1 + V_{c,t}\,\lambda_{c,t}\,x_{c,t}, \qquad \ell_{c,t} := \sum_{s=1}^t \ln m_{c,s}, \qquad E_t^{(c)} := \exp(\ell_{c,t})$$
  with $E_0^{(c)} = 1$ ($\ell_{c,0} = 0$), where $\lambda_{c,1} := 0$ and for $t \ge 2$, $\lambda_{c,t}$ is computed **strictly before** appending $(V_{c,t}, e_{c,t})$ from the up-to-$W_\lambda$ ($W_\lambda = 14$) most recent valid past scores $\{x_{c,s} : 1 \le s \le t-1,\, V_{c,s} = 1\}$:
  $$\lambda_{c,t} := \mathrm{clip}\!\left(\frac{\max(0,\, \bar{x}_{c,t-1})}{\widehat{\mathrm{Var}}_{c,t-1} + (\bar{x}_{c,t-1})^2 + \epsilon_\lambda},\; 0,\; \bar{\lambda}_c\right), \qquad \epsilon_\lambda = 10^{-2}.$$
  Combine the subchannels via the equal-weight convex mixture $E_t^{\mathrm{Ville}} := \frac{1}{|\mathcal{C}|}\sum_{c \in \mathcal{C}} E_t^{(c)}$ ($E_0^{\mathrm{Ville}} = 1$), raising a Channel A alarm iff $E_t^{\mathrm{Ville}} \ge 1 / \alpha_{\mathrm{mon}}^{(j)}$.
  1. **Predictability:** $\lambda_{c,1} = 0 \in \mathcal{F}_0$, and for every $t \ge 2$, $\lambda_{c,t}$ is a deterministic measurable function of $(V_{c,s}, e_{c,s})_{s=1}^{t-1}$, hence $\mathcal{F}_{t-1}$-measurable.
  2. **Strict Nonnegativity Without Floors or Caps:** If $V_{c,t} = 0$, $m_{c,t} = 1 > 0$. If $V_{c,t} = 1$, $e_{c,t} \ge 0 \implies x_{c,t} \ge -\mu_{0,c}/v_{\max,c}$, and $\lambda_{c,t} \in [0, \bar{\lambda}_c]$ with $\bar{\lambda}_c \le 0.90\,v_{\max,c}/\mu_{0,c}$ implies $m_{c,t} \ge 1 - 0.90 = 0.10 > 0$ pointwise. Thus $E_t^{(c)} > 0$ and $E_t^{\mathrm{Ville}} > 0$ for **all** $t \ge 0$ without any reflecting lower floor or upper cap.
  3. **Conditional-Expectation Supermartingale Property & All-Horizon Ville Guarantee:** Because $u \mapsto \min(u, x_{\max})$ is concave and non-decreasing, Jensen's inequality under $H_{0,\mathrm{mon}}$ gives $\mathbb{E}_{H_{0,\mathrm{mon}}}[x_{c,t} \mid \mathcal{F}_{t-1}, V_{c,t}=1] \le \min\big((\mathbb{E}_{H_{0,\mathrm{mon}}}[e_{c,t} \mid \mathcal{F}_{t-1}, V_{c,t}=1] - \mu_{0,c})/v_{\max,c},\, x_{\max}\big) \le 0$. By the tower property over $V_{c,t} \in \{0, 1\}$ and $\mathcal{F}_{t-1}$-measurability of $E_{t-1}^{(c)} > 0$ and $\lambda_{c,t} \ge 0$, $\mathbb{E}_{H_{0,\mathrm{mon}}}[E_t^{(c)} \mid \mathcal{F}_{t-1}] = E_{t-1}^{(c)}\big(1 + \lambda_{c,t}\,\mathbb{P}(V_{c,t}=1 \mid \mathcal{F}_{t-1})\,\mathbb{E}_{H_{0,\mathrm{mon}}}[x_{c,t} \mid \mathcal{F}_{t-1}, V_{c,t}=1]\big) \le E_{t-1}^{(c)}$ for all $t \ge 1$. By linearity of conditional expectation (requiring **zero independence assumption** across subchannels $c \in \mathcal{C}$ that share range noise $\nu_t$), $(E_t^{\mathrm{Ville}})_{t \ge 0}$ is a nonnegative $(\mathbb{P}_{H_{0,\mathrm{mon}}}, \mathcal{F}_t)$-supermartingale with $E_0^{\mathrm{Ville}} = 1$, so Ville's inequality holds for all times:
     $$\mathbb{P}_{H_{0,\mathrm{mon}}}\!\left(\exists t \ge 1 \;:\; E_t^{\mathrm{Ville}} \ge \frac{1}{\alpha_{\mathrm{mon}}^{(j)}}\right) \le \alpha_{\mathrm{mon}}^{(j)}. \quad \blacksquare$$
  4. **Explicit Validity Boundary:** This bound controls **only nominal monitor false alarms under $H_{0,\mathrm{mon}}$**. It does **not** hold under heavy-tailed outlier contamination (`OUTLIER_BURSTS`, where $12\%$ $4.5\times\sigma$ bursts violate $\mathbb{E}[e_{c,t}] \le \mu_{0,c}$), understated sensor $\sigma$, or uncompensated bias error $\hat{\mathbf{b}}_k \ne \mathbf{b}_k$, and it **never** directly bounds closed-loop false-success risk $R_{\mathrm{sel}}(\pi; \mathcal{M})$ under faults.

#### Channel B — Complementary Page CUSUM Drift/Change-Point Detector (Explicitly NOT Ville-Anytime-Valid)

Because Channel A's unfloored log-wealth $\ell_{c,t}$ drifts negative during prolonged nominal stretches ($\mathbb{E}_{H_{0,\mathrm{mon}}}[\ln m_{c,t}] < 0$ whenever $\lambda_{c,t} > 0$), a late-onset or slowly ramping fault (`SENSOR_DRIFT`, `COMPOUND_HOLDOUT_EXTREME`, `COMPOUND_DRIFT_DROPOUT`) would first have to climb back from $\ell_{c,t_0} < 0$ to $\ln(1/\alpha_{\mathrm{mon}}^{(j)})$, inflating detection delay. Channel B runs a parallel Page CUSUM statistic (Page, *Biometrika* 41(1/2):100–115, 1954) on bounded standardized residuals $z_{c,t} := \min(e_{c,t}/\sigma_{c,\mathrm{scale}},\, z_{\max})$ ($\sigma_{\mathrm{ab},\mathrm{scale}} = \sqrt{\sigma_a^2 + \sigma_b^2}$, $\sigma_{\mathrm{vr},k,\mathrm{scale}} = \sqrt{\sigma_k^2 + \sigma_r^2}$, $z_{\max} = 6.0$):
$$S_{c,0} = 0, \qquad S_{c,t} = \max\!\Big(0,\; S_{c,t-1} + V_{c,t}\big(z_{c,t} - \kappa_{c,\mathrm{drift}}\big)\Big), \qquad \text{Channel B alarm iff } \max_{c \in \mathcal{C}} S_{c,t} \ge h_{\mathrm{cusum}}^{(j)},$$
with fixed allowance constants $\kappa_{\mathrm{ab},\mathrm{drift}} = 1.80$ and $\kappa_{\mathrm{vr},k,\mathrm{drift}} = 1.60$ (strictly exceeding nominal standardized means $\sqrt{\pi/2} \approx 1.253$).
- **Statistical Status Constraint:** Because $y \mapsto \max(0, y)$ reflects at zero, $S_{c,t}$ is **not** a supermartingale ($\mathbb{P}_{H_0}(\exists t \ge 1 : S_{c,t} \ge h) = 1$ as $t \to \infty$) and **must never be described as Ville-anytime-valid**. Instead, both $\alpha_{\mathrm{mon}}^{(j)}$, $h_{\mathrm{cusum}}^{(j)}$, and the OR-combination transition logic (`alarm_A OR alarm_B OR instantaneous_gate`) are treated as integral hyperparameters of the closed-loop candidate policy $\pi_{\lambda^{(j)}}$ and calibrated jointly on $\mathcal{D}_{\text{cal}}$ via selective-risk LTT (Section 2.4).

---

## 2.2 Candidate Risk-Certification Methods: Rigorous Evaluation

The primary research objective is to determine whether a frozen V9 policy $\hat{\pi}$, calibrated on data strictly disjoint from final evaluation, supports a finite-sample statistical claim at confidence level $1 - \delta = 0.95$ ($\delta = 0.05$) that $C(\hat{\pi}; \mathcal{M}) > 0$ and $R_{\mathrm{sel}}(\hat{\pi}; \mathcal{M}) \le \alpha = 0.05$.

Below we evaluate four candidate frameworks against the exact mathematical structure of closed-loop selective risk:

### Method 1 — Independent Holdout Evaluation of a Single Prespecified Frozen Policy (One-Sided Exact Clopper–Pearson UCB)
- **Estimand:** $R_{\mathrm{sel}}(\pi_0; \mathcal{M})$ for **one** completely frozen policy $\pi_0$ fixed prior to observing $\mathcal{D}_{\text{test}}$.
- **Required Sampling Assumptions:** Episodes $Z_1, \dots, Z_N \stackrel{\text{i.i.d.}}{\sim} \mathcal{M}$, with `ctrl.reset()` before every episode so $(A_i, FS_i)_{i=1}^N$ are i.i.d. across episodes.
- **Finite-Sample vs. Asymptotic:** **Exact finite-sample** (Clopper–Pearson binomial tail inversion; never asymptotic Wilson/Wald).
- **Conditional vs. Unconditional Guarantee:** Conditioning on $M_{\text{test}} = \sum_{i=1}^N A(\pi_0, Z_i) = m \ge 1$, $K_{\text{test}} = \sum_{i=1}^N FS(\pi_0, Z_i) \sim \mathrm{Binomial}\big(m, R_{\mathrm{sel}}(\pi_0; \mathcal{M})\big)$. Hence $U_{\mathrm{CP},1}(K_{\text{test}}, M_{\text{test}}; \delta) = \mathrm{Beta}^{-1}(1 - \delta; K_{\text{test}}+1, M_{\text{test}}-K_{\text{test}})$ satisfies:
  $$\mathbb{P}_{\mathcal{D}_{\text{test}}}\!\left(R_{\mathrm{sel}}(\pi_0; \mathcal{M}) \le U_{\mathrm{CP},1}(K_{\text{test}}, M_{\text{test}}; \delta) \,\middle|\, M_{\text{test}} = m\right) \ge 1 - \delta \qquad \forall m \ge 1.$$
- **Treatment of Random Denominators:** Valid conditionally on every $M_{\text{test}} = m \ge 1$; if $M_{\text{test}} = 0$, the bound is `UNDEFINED` and no selective-risk claim can be made.
- **Treatment of Multiplicity:** Handles **only $|\Lambda| = 1$ policy** and **one** predeclared mixture $\mathcal{M}$ (or requires Holm/Šidák across $S$ scenarios). Cannot be used to search over thresholds on the same dataset.
- **Sample Separation:** $\pi_0$ must be chosen exclusively on data disjoint from $\mathcal{D}_{\text{test}}$.
- **Applicability to Adaptive Closed-Loop System:** **Yes**, provided adaptation (probing, Huber calibration, anchor queries, e-process updates) is strictly **intra-episode** and reset via `ctrl.reset()` between episodes.
- **Failure Conditions:** Invalidated immediately if $\mathcal{D}_{\text{test}}$ is inspected more than once to tune thresholds, features, or controller gains, or if episodes are generated by non-i.i.d. cross-episode online learning.

### Method 2 — Standard Learn Then Test (LTT) on Unconditional Loss vs. Selective-Risk LTT
- **Reference:** Angelopoulos, Bates, Candès, Jordan, & Lei (*Annals of Applied Statistics*, 19(2):1641–1662, 2025, `https://doi.org/10.1214/24-AOAS1998`).
- **Estimand:** Finite family $\{R(\pi_\lambda; \mathcal{M}) : \lambda \in \Lambda\}$ over a predeclared finite grid $\Lambda = \{\lambda^{(1)}, \dots, \lambda^{(J)}\}$.
- **Required Sampling Assumptions:** Calibration episodes $Z_1, \dots, Z_{N_{\text{cal}}} \stackrel{\text{i.i.d.}}{\sim} \mathcal{M}$ independent of $\Lambda$ construction.
- **Finite-Sample vs. Asymptotic:** **Exact finite-sample** *if and only if* each per-candidate hypothesis test $H_{0,j} : R(\pi_{\lambda^{(j)}}) > \alpha$ uses a finite-sample super-uniform p-value ($\mathbb{P}_{H_{0,j}}(p_j \le u) \le u$).
- **Key Nuance on Denominators:** Naive LTT applied to unconditional episode loss $L_i(\lambda) = FS(\pi_\lambda, Z_i)$ certifies **$R_{\mathrm{inc}}(\pi_{\hat{\lambda}}) \le \alpha$, NOT $R_{\mathrm{sel}}(\pi_{\hat{\lambda}}) \le \alpha$**, and would trivially certify near-zero-coverage policies! However, because LTT's master theorem (Theorem 1 of Angelopoulos et al., 2025) requires **only** valid super-uniform p-values for each null hypothesis $H_{0,j}$ plus an FWER-controlling graph/sequence procedure—and **does not require monotone losses or unconditional expectations**—LTT **becomes exact for selective risk** when paired with the conditional-binomial composite null test derived in Method 4 below!

### Method 3 — Conformal Risk Control (CRC) and Non-Exchangeable CRC (`REJECTED` for Primary Selective-Risk Claim)
- **References:** Angelopoulos, Bates, Fisch, Lei, & Schuster (*ICLR* 2024); Farinhas, Zerva, Ulmer, & Martins (*ICLR* 2024).
- **Estimand:** Marginal unconditional expected loss $\mathbb{E}[L_{n+1}(\hat{\lambda})]$ over the joint draw of calibration and test episodes.
- **Why CRC Cannot Support the V9 Primary Selective-Risk Guarantee (`[VERIFIED]`):**
  1. **Wrong Estimand & Non-Existence of Samplewise Unbiased Loss:** $R_{\mathrm{sel}}(\lambda) = \mathbb{E}[FS(\lambda)] / \mathbb{E}[A(\lambda)]$ cannot be written as $\mathbb{E}[L_i(\lambda)]$ for any observable single-episode loss $L_i(\lambda)$ without knowing the true population denominator $C(\lambda) = \mathbb{E}[A(\lambda)]$.
  2. **Failure of Pointwise Monotonicity:** CRC requires $\lambda_1 \le \lambda_2 \implies L_i(\lambda_1) \ge L_i(\lambda_2)$ for every episode $i$. Tightening an abstention gate can decrease $A_i(\lambda)$ on nominal episodes while failing to reject a compound-fault episode (e.g., `COMPOUND_HOLDOUT_EXTREME`), causing $R_{\mathrm{sel}}(\lambda)$ to **increase** as $\lambda$ becomes stricter!
  3. **Marginal Expectation vs. High-Probability $(1-\delta)$ Certificate:** CRC guarantees $\mathbb{E}_{\mathcal{D}_{\text{cal}}, Z_{n+1}}[L_{n+1}(\hat{\lambda})] \le \alpha$, not $\mathbb{P}_{\mathcal{D}_{\text{cal}}}(R(\hat{\lambda}) \le \alpha) \ge 1 - \delta$.
  4. **Non-Exchangeable CRC Slack:** Adds an unobservable total-variation penalty $B \sum_{i=1}^n \tilde{w}_i \mathrm{d}_{\mathrm{TV}}(Z_{n+1}, Z_i)$, which cannot certify $\le 5\%$ risk unless $\mathrm{d}_{\mathrm{TV}}$ is known a priori.
- **Failure Condition / Verdict:** **Do not use CRC or Non-Exchangeable CRC to claim $R_{\mathrm{sel}} \le 0.05$.**

### Method 4 — Exact Conditional-Binomial Selective-Risk LTT + Independent Frozen Holdout Verification (**SELECTED FOR V9**)
- **Estimand:** Selective risk $R_{\mathrm{sel}}(\pi_\lambda; \mathcal{M})$ and positive coverage $C(\pi_\lambda; \mathcal{M}) > 0$ across a finite pre-ordered candidate family $\Lambda = (\lambda^{(1)}, \dots, \lambda^{(J)})$.
- **Sampling Assumptions:** Calibration set $\mathcal{D}_{\text{cal}}$ consists of $N_{\text{cal}}$ i.i.d. episodes drawn from $\mathcal{M}$ (`ctrl.reset()` per episode; common random numbers across $\lambda \in \Lambda$ permitted because FWER control holds under arbitrary p-value dependence); final holdout $\mathcal{D}_{\text{test}}^{\text{mix}}$ consists of $N_{\text{test}}$ independent i.i.d. episodes from $\mathcal{M}$.
- **Guarantee Type:** **Exact finite-sample** $(1 - \delta)$ calibration FWER guarantee via LTT + **exact finite-sample** $(1 - \delta)$ holdout UCB on the single frozen policy $\hat{\pi}$.
- **Failure Conditions Under Which Guarantee Must NOT Be Claimed:**
  1. If $\hat{\Lambda} = \emptyset$ on $\mathcal{D}_{\text{cal}}$ (no candidate achieves $p_{\text{cal}}^{\text{sel}}(\lambda^{(j)}) \le \delta_{\text{step}}$ with $M_{\text{cal}}(\lambda^{(j)}) \ge m_{\min}$): V9 **must output `UNCERTIFIED` and claim no $5\%$ guarantee**.
  2. If the test deployment scenario mixture differs from $\mathcal{M}$ (see Section 2.6).
  3. If cross-episode state persists across episodes (violating `ctrl.reset()` independence) or if $\mathcal{D}_{\text{test}}$ is touched more than once.

---

## 2.3 Exact Mathematical Derivation for Random Accepted-Decision Denominators (`[NEW-DERIVATION]`)

### Theorem 2.1 (Finite-Sample Super-Uniformity of the Selective-Risk Binomial p-Value Under Random Acceptance Counts)

Let $\pi_\lambda$ be a fixed, memoryless-across-episodes policy, and let $Z_1, \dots, Z_N \stackrel{\text{i.i.d.}}{\sim} \mathcal{M}$. Define $A_i = A(\pi_\lambda, Z_i) \in \{0, 1\}$, $FS_i = FS(\pi_\lambda, Z_i) \in \{0, A_i\}$, $M = \sum_{i=1}^N A_i$, and $K = \sum_{i=1}^N FS_i$. Fix target selective risk $\alpha \in (0, 1)$ and a predeclared minimum accepted-decision threshold $m_{\min} \in \{1, \dots, N\}$ (in V9, $m_{\min} = \lceil \ln \delta / \ln(1 - \alpha) \rceil = 59$ for $\alpha = \delta = 0.05$, or a higher utility floor such as $m_{\min} = \lceil C_{\min} N \rceil$).

Define the **composite unsafe or zero-coverage null hypothesis**:
$$H_0^{\mathrm{sel}}(\lambda) \;:\; \big\{C(\pi_\lambda; \mathcal{M}) = 0\big\} \;\cup\; \big\{C(\pi_\lambda; \mathcal{M}) > 0 \;\land\; R_{\mathrm{sel}}(\pi_\lambda; \mathcal{M}) > \alpha\big\},$$
and define the selective-risk calibration p-value:
$$p^{\mathrm{sel}}(\lambda; \mathcal{D}) := \begin{cases} 1, & \text{if } M < m_{\min}, \\[6pt] F_{\mathrm{Bin}(M, \alpha)}(K) = \displaystyle\sum_{j=0}^{K} \binom{M}{j} \alpha^j (1 - \alpha)^{M - j}, & \text{if } M \ge m_{\min}. \end{cases}$$

**Claim:** Under $H_0^{\mathrm{sel}}(\lambda)$, for every significance threshold $u \in [0, 1)$,
$$\mathbb{P}_{Z_{1:N} \stackrel{\text{i.i.d.}}{\sim} \mathcal{M}}\big(p^{\mathrm{sel}}(\lambda; \mathcal{D}) \le u\big) \le u.$$

**Proof:**
- **Case 1 ($C(\pi_\lambda; \mathcal{M}) = 0$):** Then $\mathbb{P}(A_i = 1) = 0$ for every $i$, so $\mathbb{P}(M = 0) = 1$. Since $m_{\min} \ge 1$, $M < m_{\min}$ holds almost surely, giving $p^{\mathrm{sel}}(\lambda; \mathcal{D}) = 1$ almost surely and $\mathbb{P}(p^{\mathrm{sel}} \le u) = 0 \le u$ for all $u \in [0, 1)$.
- **Case 2 ($C(\pi_\lambda; \mathcal{M}) > 0$ and $r := R_{\mathrm{sel}}(\pi_\lambda; \mathcal{M}) > \alpha$):** Let $\mathcal{I}_A = \{i \in \{1, \dots, N\} : A_i = 1\}$ be the random subset of accepted episode indices. Because $(A_i, FS_i)_{i=1}^N$ are mutually independent across $i$, conditioning on the vector $(A_1, \dots, A_N)$ with $\sum_{i=1}^N A_i = m \ge m_{\min}$ yields:
  - $FS_i \equiv 0$ deterministically for $i \notin \mathcal{I}_A$ (since $FS_i \le A_i$); and
  - $(FS_i)_{i \in \mathcal{I}_A}$ are mutually independent $\mathrm{Bernoulli}(r)$ variables because $\mathbb{P}(FS_i = 1 \mid A_i = 1, A_{-i}) = \mathbb{P}(FS_i = 1 \mid A_i = 1) = r$.
  Hence, conditional on $\{M = m\}$ for any $m \ge m_{\min}$ with $\mathbb{P}(M = m) > 0$, $K = \sum_{i \in \mathcal{I}_A} FS_i \sim \mathrm{Binomial}(m, r)$. Because the Binomial CDF $r' \mapsto F_{\mathrm{Bin}(m, r')}(k)$ is strictly decreasing in $r'$ for $0 \le k < m$ (and identically $1$ for $k = m$), $r > \alpha$ implies $F_{\mathrm{Bin}(m, \alpha)}(K) \ge F_{\mathrm{Bin}(m, r)}(K)$ pointwise. By the probability integral transform for discrete CDFs, $\mathbb{P}\big(F_{\mathrm{Bin}(m, r)}(K) \le u \mid M = m\big) \le u$. Therefore, by the law of total probability over $M$:
  $$\mathbb{P}\big(p^{\mathrm{sel}}(\lambda; \mathcal{D}) \le u\big) = \sum_{m = m_{\min}}^{N} \mathbb{P}(M = m)\,\mathbb{P}\big(F_{\mathrm{Bin}(m, \alpha)}(K) \le u \,\big|\, M = m\big) \le \sum_{m = m_{\min}}^{N} \mathbb{P}(M = m)\, u = u\,\mathbb{P}(M \ge m_{\min}) \le u. \quad \blacksquare$$

### Four Distinct Inference Regimes That Must Never Be Conflated

1. **Single Frozen Policy on Independent Test Data ($\mathcal{D}_{\text{test}}$):** $\pi_0$ is completely fixed prior to generating/inspecting $\mathcal{D}_{\text{test}}$. Both the conditional statement $\mathbb{P}(R_{\mathrm{sel}}(\pi_0) \le U_{\mathrm{CP},1}(K_{\text{test}}, M_{\text{test}}; \delta) \mid M_{\text{test}} = m) \ge 1 - \delta$ (for $m \ge 1$) and the unconditional test $p_{\text{test}}^{\mathrm{sel}}(\pi_0) \le \delta$ hold at exact level $\delta$ with **no multiplicity penalty**.
2. **Selecting $\hat{\lambda}$ Across $J > 1$ Candidates on Calibration Data ($\mathcal{D}_{\text{cal}}$):** Applying an unadjusted Clopper–Pearson interval to $\min_{j} \hat{R}_{\mathrm{sel}}(\lambda^{(j)})$ or to the cherry-picked winner $\hat{\lambda}$ **invalidates coverage** due to selection bias across correlated random denominators $(M_{\text{cal}}(\lambda^{(1)}), \dots, M_{\text{cal}}(\lambda^{(J)}))$. Valid calibration requires LTT with FWER control across $j = 1, \dots, J$ (Section 2.4).
3. **Post-Selection Reporting on Independent Final Holdout ($\mathcal{D}_{\text{test}}$):** Once $\mathcal{D}_{\text{cal}}$ selects **at most one** frozen policy $\hat{\pi} = \pi_{\hat{\lambda}}$ (and $\mathcal{D}_{\text{cal}}$ is permanently locked), conditional on $\mathcal{D}_{\text{cal}}$ ($\hat{\pi}$ fixed), $\mathcal{D}_{\text{test}}$ is an independent draw from $\mathcal{M}$ of size $N_{\text{test}}$ for that **single** policy $\hat{\pi}$. Hence $U_{\mathrm{CP},1}(K_{\text{test}}(\hat{\pi}), M_{\text{test}}(\hat{\pi}); \delta)$ provides an unbiased, selection-free finite-sample $(1-\delta)$ upper confidence bound on $R_{\mathrm{sel}}(\hat{\pi}; \mathcal{M})$!
4. **Conditioning on $M \ge 1$ vs. Unconditional Certification:** Conditioning on $\{M_{\text{test}} = m\}$ is valid *only* for a single policy's UCB when $m \ge 1$ is observed; for LTT policy selection across $J$ candidates where some candidates may have $C(\lambda) = 0$, unconditional FWER validity over $\mathcal{D}_{\text{cal}}$ follows directly from Theorem 2.1 because $p^{\mathrm{sel}}(\lambda) = 1$ whenever $M_{\text{cal}}(\lambda) < m_{\min}$.

### Why a Minimum of `59` Accepted Decisions Is NOT a Universal Certification Guarantee (`[VERIFIED]`, `[NEW-DERIVATION]`)

The quantity $m_{\min} = \lceil \ln(0.05) / \ln(1 - 0.05) \rceil = 59$ frequently appears in zero-failure binomial calculations, but **observing $M \ge 59$ accepted decisions does NOT automatically certify $R_{\mathrm{sel}} \le 0.05$ at 95% confidence**:
1. **Non-Zero Observed Errors ($K \ge 1$):** $M = 59$ suffices **only when $K = 0$ false successes occur** ($0.95^{59} = 0.04849 \le 0.05$). Observing even $K = 1$ false success requires $M \ge 93$; $K = 2$ requires $M \ge 124$; $K = 5$ requires $M \ge 208$; and $K = 6$ requires $M \ge 234$ (`docs/v9_experiment_protocol.md`, Table 3.2.1).
2. **Candidate Selection Across Multiple Policies ($J > 1$):** If a policy is chosen from $J = 6$ candidates *without* a pre-committed fixed-sequence stopping rule, Holm step-1 ($\delta/6 = 0.008333$) requires $M \ge 94$ accepted episodes even at $K = 0$ (and $M \ge 135$ at $K = 1$). Fixed-Sequence LTT retains the $M \ge 59$ ($K = 0$) floor *only* because the strict candidate test order $j = 1, \dots, 6$ is frozen before $\mathcal{D}_{\text{cal}}$ is generated or inspected.
3. **Multiple Hypotheses or Two-Sided Intervals:** Two-sided 95% Clopper–Pearson intervals ($\delta_{\mathrm{upper}} = 0.025$) require $M \ge 72$ at $K = 0$ ($M \ge 258$ at $K = 6$, which is why V8's `6/257` exceeded `5.0%`!). Claiming multiple confirmatory risk targets requires fixed-sequence gatekeeping (`H1` $\to$ `H2`) or multiplicity adjustment.
4. **Simultaneous Multi-Scenario Claims ($S = 12$):** Certifying $R_{\mathrm{sel},s} \le 0.05$ simultaneously across $S = 12$ independent scenarios via Šidák ($\delta_{\mathrm{Šidák}} \approx 0.004265$) or Holm ($\delta/12 \approx 0.004167$) requires **$M_s \ge 107$ accepted decisions in each certified scenario** even at $K_s = 0$!
5. **Insufficient Accepted Sample Size in Low-Coverage Scenarios:** Whenever a scenario's accepted count satisfies $M_s < m_{\mathrm{req}}(K_s; 0.05, \delta_{\mathrm{eff}})$—notably in severe fault scenarios (`FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, `COMPOUND_HOLDOUT_EXTREME`) where safe runtime assurance deliberately abstains ($M_s \ll 59$ or $M_s = 0$)—**a 5% selective-risk bound cannot be statistically established at finite horizon $N_s = 120$**, and V9 explicitly refrains from claiming per-scenario selective certification there.

---

## 2.4 Prespecified Finite Joint Policy Family and Multiplicity Control (`[APPROVED-DECISION]`)

### 2.4.1 Joint Closed-Loop Policy Logic and 6-Parameter Candidate Grid $\Lambda$

Under **Approved Decisions 1–4**, calibration operates over the **complete joint closed-loop decision policy $\pi_{\lambda^{(j)}}$** while strictly preserving the 4-input runtime interface `(reading_a, reading_b, range_reading, anchor_reading)` (`Decision 4`). Every candidate $\pi_{\lambda^{(j)}}$ shares the identical fixed structural logic:
1. **Hybrid Pre-Fusion Monitoring (`Decision 1`):** Evaluates Channel A ($\gamma = 1.0$ Ville e-process mixture at threshold $1/\alpha_{\mathrm{mon}}^{(j)}$), Channel B (Page CUSUM drift detector at threshold $h_{\mathrm{cusum}}^{(j)}$), and normalized instantaneous inter-sensor/cross-modal gates ($\tau_{\mathrm{diff}}^{(j)}$); any alarm transitions `NOMINAL` $\to$ `ACTIVE_PROBING` and immediately returns `"PROBE"` (no fall-through to `"STOP"`).
2. **Per-Sensor Calibration & Disjoint Validation (`Decision 2`):** Fits separate `OnlineBiasEstimator` instances ($\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b$) on valid observations in $\mathcal{I}_{\mathrm{fit}} = \{1,\dots,22\}$, skips transition gap $\mathcal{I}_{\mathrm{gap}} = \{23,24\}$, validates frozen $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ on $\mathcal{I}_{\mathrm{val}} = \{25,\dots,36\}$ against $\tau_{\mathrm{val}}^{(j)}$ and post-calibration inter-sensor agreement $\tau_{\mathrm{diff}}^{(j)}$, isolates a single faulty/dropout sensor if the other sensor passes `CALIBRATED_VALID`, abstains if neither passes, and **performs zero continuous online refitting** during `CALIBRATED` approach.
3. **Fail-Closed Anchor/Range Gate (`Decision 3`):** Tests normalized anchor-vs.-range discrepancy $\tilde{\Delta}_{ar,t} = |\|\mathbf{z}_{\mathrm{anc},t}\|_2 - r_t| / \sqrt{\sigma_{\mathrm{anc}}^2 + \sigma_r^2} > \tau_{ar}^{(j)}$ (treating V8's `0.35 m` solely as unvalidated Tier-5 candidate $5.47\,\sigma_{ar}$ rather than a validated safety limit), defaulting to `"ABSTAIN"` unless all fixed pre-holdout drift-free vector-chord corroboration conditions hold (`docs/v9_experiment_protocol.md`, Section 3.4.3).
4. **Multi-Modal Terminal Commit Gate:** Emits `"STOP"` only when valid calibrated target distance $\le d_{\mathrm{arr}} = 0.22\text{ m}$, `range_reading.valid == True` with $r_t \le \tau_{\mathrm{stop}}^{(j)}$ (or verified anchor agreement when range was proven biased under Decision 3), and neither post-calibration Channel A, Channel B, nor $\tilde{\boldsymbol{\delta}}_{ab,t}$ is in alarm.

To prevent hyperparameter fishing, V9 restricts calibration to a **finite, pre-ordered candidate family $\Lambda = (\lambda^{(1)}, \lambda^{(2)}, \lambda^{(3)}, \lambda^{(4)}, \lambda^{(5)}, \lambda^{(6)})$ of cardinality $J = 6$**, ordered strictly from **most conservative ($j=1$) to most permissive ($j=6$)** using only $\mathcal{D}_{\text{dev}}$ before $\mathcal{D}_{\text{cal}}$ is ever accessed:

$$\lambda^{(j)} = \Big(\alpha_{\mathrm{mon}}^{(j)},\; h_{\mathrm{cusum}}^{(j)},\; \tau_{\mathrm{diff}}^{(j)},\; \tau_{ar}^{(j)},\; \tau_{\mathrm{val}}^{(j)},\; \tau_{\mathrm{stop}}^{(j)}\Big), \qquad j \in \{1, \dots, 6\}.$$

| Candidate Index $j$ | Conservatism Tier | $\alpha_{\mathrm{mon}}^{(j)}$ (`1/alpha` Ville) | $h_{\mathrm{cusum}}^{(j)}$ (CUSUM Drift) | $\tau_{\mathrm{diff}}^{(j)}$ ($\sigma_{\mathrm{diff}}$ Gate) | $\tau_{ar}^{(j)}$ ($\sigma_{ar}$ Anchor–Range) | $\tau_{\mathrm{val}}^{(j)}$ (m, Held-Out RMSE) | $\tau_{\mathrm{stop}}^{(j)}$ (m, Terminal Gate) | Intended Risk–Coverage Regime |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`j = 1`** | Tier 1 (Strictest) | `0.010` (`100.0`) | `6.0` | `3.20` | `3.80` (`~0.243 m`) | `0.10` | `0.36` | Maximum compound-fault rejection; conservative safety anchor |
| **`j = 2`** | Tier 2 (Very Strict) | `0.020` (`50.0`) | `7.0` | `3.50` | `4.20` (`~0.269 m`) | `0.11` | `0.38` | High safety margin under range shift & slow drift |
| **`j = 3`** | Tier 3 (Balanced-Strict) | `0.030` (`33.3`) | `8.0` | `3.80` | `4.60` (`~0.295 m`) | `0.12` | `0.40` | Target operating point balancing `TS` and `<2%` selective risk |
| **`j = 4`** | Tier 4 (Balanced) | `0.040` (`25.0`) | `9.0` | `4.10` | `5.00` (`~0.320 m`) | `0.13` | `0.41` | Higher recovery acceptance under moderate noise |
| **`j = 5`** | Tier 5 (Moderate) | `0.050` (`20.0`) | `10.0` | `4.40` | `5.47` (`~0.350 m` V8) | `0.14` | `0.42` | Matches V8 nominal $\alpha=0.05$ & `0.35 m` candidate with V9 bug fixes |
| **`j = 6`** | Tier 6 (Permissive) | `0.075` (`13.3`) | `11.5` | `4.80` | `6.00` (`~0.384 m`) | `0.15` | `0.44` | High-coverage stress boundary |

*(Governance Rule: Numeric values and ordering of $\Lambda$ may be refined **only** on $\mathcal{D}_{\text{dev}}$ (`seeds 70000..70029`) and **must be committed to Git in a frozen JSON manifest before $\mathcal{D}_{\text{cal}}$ (`seeds 71000..71959`) is executed once**.)*

### 2.4.2 Multiplicity Control Under Matched-Seed Dependence: Fixed-Sequence LTT vs. Holm Step-Down

Because all $J = 6$ candidates are evaluated on the **same** calibration episodes $\mathcal{D}_{\text{cal}}$, the p-values $(p^{\mathrm{sel}}_1, \dots, p^{\mathrm{sel}}_6)$ are positively dependent, **not** independent (so Šidák/independent corrections are invalid unless positive orthant dependence is proved, whereas Fixed-Sequence Testing and Holm's procedure require **zero** dependence assumptions!). Crucially, **neither Fixed-Sequence Testing nor Holm's procedure assumes that $R_{\mathrm{sel}}(\lambda^{(j)})$ is monotone in $j$**!

- **Primary LTT Calibration Procedure — Fixed-Sequence Testing (FST) at Full Level $\delta = 0.05$ (Angelopoulos et al., 2025, Section 3.2):**
  1. Test $j = 1, 2, \dots, 6$ strictly in sequence at full level $\delta = 0.05$, requiring **both** $p^{\mathrm{sel}}(\lambda^{(j)}; \mathcal{D}_{\text{cal}}) \le \delta$ **and** empirical utility admissibility $\hat{C}_{\text{cal}}(\lambda^{(j)}) \ge C_{\min} = 0.35$ (enforced by setting $m_{\min} = \max(59, \lceil C_{\min} N_{\text{cal}} \rceil)$ in Theorem 2.1, which only makes $p^{\mathrm{sel}}$ more conservative!).
  2. Stop at the **first** index $j^*$ where $p^{\mathrm{sel}}(\lambda^{(j^*)}; \mathcal{D}_{\text{cal}}) > \delta$, and define the LTT-certified set $\hat{\Lambda}_{\mathrm{FST}} = \{\lambda^{(1)}, \dots, \lambda^{(j^*-1)}\}$ (with $\hat{\Lambda}_{\mathrm{FST}} = \emptyset$ if $j^* = 1$).
  3. **Why FWER $\le \delta$ Holds Without Monotonicity:** Let $j_0 = \min\{j \in \{1, \dots, 6\} : H_0^{\mathrm{sel}}(\lambda^{(j)}) \text{ is true}\}$ be the *first* truly unsafe/zero-coverage candidate in the pre-ordered sequence (if none exists, FWER is trivially $0$). A false certification occurs **only if** FST fails to stop at or before $j_0$, which implies $p^{\mathrm{sel}}(\lambda^{(j_0)}; \mathcal{D}_{\text{cal}}) \le \delta$. By Theorem 2.1, $\mathbb{P}(p^{\mathrm{sel}}(\lambda^{(j_0)}) \le \delta) \le \delta$ unconditionally!
  4. **Deterministic Single-Policy Selection Rule:** If $\hat{\Lambda}_{\mathrm{FST}} \ne \emptyset$, select $\hat{\lambda} = \arg\max_{\lambda \in \hat{\Lambda}_{\mathrm{FST}}} \hat{TSR}_{\text{cal}}(\lambda)$ (ties broken by lowest empirical $\hat{R}_{\mathrm{sel,cal}}$, then smallest index $j$), and freeze $\hat{\pi} = \pi_{\hat{\lambda}}$. If $\hat{\Lambda}_{\mathrm{FST}} = \emptyset$, declare `V9_CALIBRATION_UNCERTIFIED` (fallback evaluation runs Tier 1 $\lambda^{(1)}$ purely as a diagnostic baseline without claiming LTT certification).

- **Predeclared Sensitivity Comparator — Holm–Bonferroni Step-Down LTT:**
  To guard against the failure mode where Tier 1 ($j=1$) is *so* conservative that $\hat{C}_{\text{cal}}(\lambda^{(1)}) < C_{\min}$ blocks FST at $j=1$ while Tiers $2$ or $3$ are both safe and high-coverage, we **pre-check $\hat{C}_{\text{dev}}(\lambda^{(1)}) \ge 0.42$ on $\mathcal{D}_{\text{dev}}$** when freezing $\Lambda$, and additionally report Holm's step-down procedure ($p_{(1)} \le \delta/6, p_{(2)} \le \delta/5, \dots$) on $\mathcal{D}_{\text{cal}}$ as a secondary sensitivity diagnostic (never replacing $\hat{\pi}$ post hoc).

---

## 2.5 Disjoint Episode Splits, Intra-Episode Validation Isolation, and Unit of Statistical Independence (`[APPROVED-DECISION]`, `[NEW-DERIVATION]`)

### 2.5.1 Intra-Episode Data-Flow Isolation vs. Inter-Episode Statistical Independence

1. **Intra-Episode Data-Flow Isolation & Why Repeated Online Updates Destroy Validation Independence (`Decision 2`):**
   - Within a single episode $Z_i$, trajectory steps $t = 0, \dots, \tau$ are closed-loop coupled via $\mathbf{p}_{\text{robot}}(t)$ and share the episode's latent sensor faults $(\mathbf{b}_a, \mathbf{b}_b, \mathbf{d}_{\mathrm{drift}}, b_r, \mathbf{b}_{\mathrm{anc}})$.
   - In V8 (`agent_next.py:215-218`), `81.25%` (`13/16`) of validation samples were identical training points inside `OnlineBiasEstimator`'s rolling FIFO window. Under **Approved Decision 2**, V9 eliminates in-sample leakage at the data-flow level by resetting all buffers upon `ACTIVE_PROBING` entry and partitioning probing (`T_probe = 36` steps) into strictly disjoint fit steps $\mathcal{I}_{\mathrm{fit}} = \{1,\dots,22\}$ (`estimator_a` and `estimator_b` updated separately on valid readings only), transition gap $\mathcal{I}_{\mathrm{gap}} = \{23,24\}$ (no writes), and held-out validation steps $\mathcal{I}_{\mathrm{val}} = \{25,\dots,36\}$ (`val_buf_a`, `val_buf_b` only; `set(I_fit) & set(I_val) == set()`).
   - **Effect of Repeated Online Updates:** If $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ were continuously re-estimated online during `CALIBRATED` approach, (i) any rolling validation metric would re-evaluate an estimator on data that had already adapted toward drift or range bias $b_r \ne 0$, destroying out-of-sample drift sensitivity, and (ii) $\hat{\mathbf{b}}_k(t)$ would correlate with recent noise realizations, violating the $\mathcal{F}_{t-1}$-conditional mean bound of post-calibration Channel A. Therefore, V9 **freezes $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ at the end of $\mathcal{I}_{\mathrm{fit}}$ with zero continuous online refitting during `CALIBRATED` mode**. Even with strict intra-episode disjointness, $\mathcal{I}_{\mathrm{val}}$ shares the episode's latent fault realization $Z_i$ (e.g., static range bias $b_r$), so $\mathcal{I}_{\mathrm{val}}$ is treated strictly as an **intra-episode geometric/noise consistency gate**, never as an independent cross-episode risk certificate.
2. **Inter-Episode Independence (The True Statistical Unit for Risk Certification):** Every episode $i$ instantiates a fresh `AegisPhysicalWorld()`, fresh stateless sensor objects, and calls `ctrl.reset()`, wiping all controller history, Channel A/B states, per-sensor bias buffers, and diagnostic posteriors (`agent_next.py:98-118`, `benchmark_next.py:202-238`). Provided **no cross-episode parameter adaptation** occurs after freezing $\Lambda$ on $\mathcal{D}_{\text{dev}}$, each episode $Z_i = (S_i, \xi_i)$ is an **independent trial**, and the deterministic closed-loop trajectory mapping $Z_i \mapsto \big(A(\pi, Z_i), FS(\pi, Z_i), TS(\pi, Z_i)\big)$ transforms i.i.d. episode draws $(S_i, \xi_i) \stackrel{\text{i.i.d.}}{\sim} \mathcal{M}$ into **strictly i.i.d. episode-level outcome vectors**.
3. **Why i.i.d. Mixture Sampling vs. Fixed-Quota Stratified Sampling Must Be Separated (`[NEW-DERIVATION]`):**
   In `benchmark_next.py:195-199`, running a deterministic loop of exactly $n$ episodes per scenario creates **independent, non-identically distributed (stratified)** episodes—not i.i.d. draws from the mixture $\mathcal{M}$! For example, if Stratum 1 has $C_1 = 1, r_1 = 0$ ($M_1 \equiv n, K_1 \equiv 0$) and Stratum 2 has $C_2 = 0.1, r_2 = 1$ ($K_2 \equiv M_2$), then conditional on $M = n + 2$, $K = 2$ deterministically rather than $\mathrm{Binomial}(n+2, R_{\mathrm{sel}})$. Conversely, if each episode $i$ draws $S_i \stackrel{\text{i.i.d.}}{\sim} \mathrm{Uniform}(\mathcal{S})$ and a unique seed $\xi_i$, then $(A_i, FS_i)_{i=1}^N$ are **strictly i.i.d. from $\mathcal{M}$**, satisfying Theorem 2.1 with zero approximation! Meanwhile, per-scenario guarantees require fixed sample sizes $N_s$ within each scenario $s$ (where episodes $1, \dots, N_s$ *are* strictly i.i.d. from $\mathbb{P}_s$).

### 2.5.2 Disjoint 5-Manifest Episode Partition Architecture

To satisfy **both** exact i.i.d. mixture validity for pooled certification **and** exact fixed-quota i.i.d. validity within each scenario—with zero seed reuse across partitions or with V8's historical `60000..60049`—V9 freezes five strictly disjoint episode manifests across the 12-scenario suite $\mathcal{S}_{12}$ (`10` historical V8 scenarios $\mathcal{S}_{10}$ + `2` new compound-fault scenarios $\mathcal{S}_{\text{ext}}$):

| Partition Manifest | Sampling Law | Scenario Scope | Episodes ($N$) | Disjoint Episode Seed Range | Manifest PRNG Seed | Permitted Usage & Governance |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **$\mathcal{D}_{\text{hist}}$ (Archive)** | Stratified (`10 x 50`) | $\mathcal{S}_{10}$ | `500` | `60000 .. 60049` | Historical V8 | Read-only forensic baseline (`Phase 1`); never modified or reused. |
| **$\mathcal{D}_{\text{dev}}$ (Development)** | Stratified (`12 x 30`) | $\mathcal{S}_{12}$ | `360` | `70000 .. 70029` | Deterministic grid | Feature design, compound-fault detector tuning, ordering & freezing $\Lambda$. |
| **$\mathcal{D}_{\text{cal}}$ (Calibration)** | **i.i.d. Mixture** ($S_i \stackrel{\text{i.i.d.}}{\sim} \mathcal{P}_{12}$) | $\mathcal{P}_{12}$ | `960` | `71000 .. 71959` (`1` unique seed/ep) | `20260901` | Executed **once** after freezing V9 code & $\Lambda$ to run LTT and lock $\hat{\pi} = \pi_{\hat{\lambda}}$. |
| **$\mathcal{D}_{\text{val}}$ (Validation)** | Stratified (`12 x 40`) | $\mathcal{S}_{12}$ | `480` | `72000 .. 72039` | Deterministic grid | Pre-holdout pipeline verification, ablations, latency/cost diagnostics; **cannot alter $\hat{\lambda}$**. |
| **$\mathcal{D}_{\text{test}}^{\text{mix}}$ (Holdout — Pooled)** | **i.i.d. Mixture** ($S_i \stackrel{\text{i.i.d.}}{\sim} \mathcal{P}_{12}$) | $\mathcal{P}_{12}$ (and $\mathcal{P}_{10}$ subset) | `1,440` | `73000 .. 74439` (`1` unique seed/ep) | `20260902` | Executed **once** on frozen $\hat{\pi}$ + baselines for **exact pooled selective-risk UCB (`H1`, `H2`)**. |
| **$\mathcal{D}_{\text{test}}^{\text{scen}}$ (Holdout — Stratified)** | Stratified (`12 x 120`) | $\mathcal{S}_{12}$ (`120`/scen) | `1,440` | `75000 .. 75119` (`120` seeds $\times 12$ scens) | Deterministic grid | Executed **once** on frozen $\hat{\pi}$ + baselines for **exact per-scenario UCBs, worst-case bounds, & balanced paired noninferiority (`H3`–`H5`)**. |

*Matched-Seed Pairing Rule:* Within every manifest, **every policy $\pi \in \Pi$ is evaluated on the exact same sequence of `(scenario, seed)` pairs**, preserving exact paired comparisons while preventing any cross-partition leakage.

---

## 2.6 Pooled Mixture Guarantees vs. Per-Scenario vs. Worst-Case Guarantees

### 2.6.1 Coverage-Weighted Mixture Distortion Formula (`[NEW-DERIVATION]`)

Let $\mathcal{M}_{\mathbf{w}} = \sum_{s=1}^S w_s \mathbb{P}_s$ be a scenario mixture with prior weights $w_s > 0, \sum_{s=1}^S w_s = 1$. Let $C_s(\pi) = \mathbb{P}_s(A = 1)$ and $r_s(\pi) = \mathbb{P}_s(FS = 1 \mid A = 1)$ (for scenarios with $C_s(\pi) > 0$). Whenever $C(\pi; \mathcal{M}_{\mathbf{w}}) = \sum_{s=1}^S w_s C_s(\pi) > 0$, pooled selective risk is **not** $\sum_s w_s r_s(\pi)$, but rather the **coverage-weighted average**:
$$R_{\mathrm{sel}}(\pi; \mathcal{M}_{\mathbf{w}}) = \frac{\sum_{s=1}^S w_s C_s(\pi) r_s(\pi)}{\sum_{s'=1}^S w_{s'} C_{s'}(\pi)} = \sum_{s : C_s(\pi) > 0} \tilde{w}_s(\pi)\, r_s(\pi), \qquad \tilde{w}_s(\pi) := \frac{w_s C_s(\pi)}{\sum_{s'=1}^S w_{s'} C_{s'}(\pi)}.$$
**Critical Implication Under Distribution Shift:**
1. In V8 (`N = 500`, $w_s = 1/10$), `NOMINAL`, `OUTLIER_BURSTS`, `SENSOR_DROPOUT`, and `CORRELATED_BIAS` contributed `50 + 48 + 50 + 37 = 185` accepted episodes with `0` errors ($\tilde{w} = 72.0\%$), masking `INDEPENDENT_BIAS` ($r_s = 12.5\%, \tilde{w} = 12.5\%$) and `COMPOUND_HOLDOUT_EXTREME` ($r_s = 66.7\%, \tilde{w} = 1.17\%$) to yield $R_{\mathrm{sel,pool}} = 2.33\%$.
2. If deployment shifts to new scenario weights $\mathbf{w}'$ (for instance, `INDEPENDENT_BIAS` occurs `50%` of the time instead of `10%`), $R_{\mathrm{sel}}(\pi; \mathcal{M}_{\mathbf{w}'})$ immediately violates $5\%$ even though the conditional per-scenario risks $r_s(\pi)$ did not change! **Therefore, a pooled guarantee on $\mathcal{P}_{12}$ must NEVER be presented as a scenario-uniform or shift-invariant guarantee.**

### 2.6.2 Three Distinct Statistical Statements in V9

1. **Statement Type I — Pooled Mixture Selective-Risk Guarantee (on $\mathcal{D}_{\text{test}}^{\text{mix}}$ under $\mathcal{P}_{12}$ and $\mathcal{P}_{10}$):**
   - *Target:* $R_{\mathrm{sel}}(\hat{\pi}; \mathcal{P}_{12}) \le 0.05$ at $1 - \delta = 0.95$ via $U_{\mathrm{CP},1}(K_{\text{test}}^{\text{mix}}, M_{\text{test}}^{\text{mix}}; 0.05) \le 0.05$ (with $M_{\text{test}}^{\text{mix}} \ge 59$).
   - *Scope Boundary:* Valid strictly for i.i.d. sampling from the uniform `12`-scenario benchmark mixture $\mathcal{P}_{12}$ (and hierarchically $\mathcal{P}_{10}$).

2. **Statement Type II — Simultaneous Multi-Scenario Per-Scenario Risk Bounds (on $\mathcal{D}_{\text{test}}^{\text{scen}}$, $N_s = 120$ per scenario):**
   Because the `12` strata in $\mathcal{D}_{\text{test}}^{\text{scen}}$ use **mutually independent** episodes across $s = 1, \dots, 12$:
   - *Simultaneous $(1-\delta)$ Per-Scenario Unconditional Incidence Envelope:* Using exact independent Šidák allocation $\delta_{\mathrm{Šidák}} = 1 - (1 - \delta)^{1/12} \approx 0.004265$ (or Holm step-down starting at $\delta/12 \approx 0.004167$), the `12` one-sided Clopper–Pearson bounds $U_{\mathrm{CP},1}(K_s, 120; \delta_{\mathrm{Šidák}})$ hold **simultaneously across all $s \in \mathcal{S}_{12}$ with probability $\ge 0.95$**. Because $N_s = 120 \ge 107$, any scenario observing $K_s = 0$ false successes is simultaneously certified to satisfy $R_{\mathrm{inc},s}(\hat{\pi}) \le 0.0440 \le 0.05$!
   - *Simultaneous $(1-\delta)$ Per-Scenario Selective-Risk Envelope:* Conditioning on $(M_1, \dots, M_{12})$, for the subset of active scenarios $\mathcal{S}_+ = \{s : M_s \ge 1\}$, the simultaneous $95\%$ one-sided selective-risk upper bounds are $U_{\mathrm{CP},1}(K_s, M_s; \delta_{\mathrm{Šidák}})$. Note the mathematical coverage ceiling: certifying $R_{\mathrm{sel},s}(\hat{\pi}) \le 0.05$ simultaneously across $12$ scenarios requires $M_s \ge 107$ accepted episodes ($C_s \gtrsim 0.89$) at $K_s = 0$, whereas unadjusted per-scenario marginal $95\%$ bounds require $M_s \ge 59$. In abstention-dominated fault scenarios (`FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, `COMPOUND_HOLDOUT_EXTREME`) where safe behavior *ought* to abstain ($M_s \ll 59$ or $M_s = 0$), **per-scenario selective risk $R_{\mathrm{sel},s} \le 0.05$ cannot be statistically certified at $N_s = 120$ and must be reported via exact intervals (`UNDEFINED` if $M_s=0$) alongside certified $R_{\mathrm{inc},s} \le 0.05$**.

3. **Statement Type III — Worst-Case Risk Over a Prespecified Scenario Family (Intersection–Union Test, Berger 1982):**
   - Consider the worst-case parameter $\bar{R}_{\max}(\hat{\pi}; \mathcal{S}_{\mathrm{high}}) := \max_{s \in \mathcal{S}_{\mathrm{high}}} R_s(\hat{\pi})$ over a predeclared family of scenarios $\mathcal{S}_{\mathrm{high}}$ (either worst-case unconditional incidence across all $\mathcal{S}_{12}$, or worst-case selective risk across high-coverage operational scenarios $\mathcal{S}_{\mathrm{cov}}$).
   - **Exact Intersection–Union Principle (No Multiplicity Penalty Required for $\max_s R_s \le \alpha$!):** The null hypothesis $H_0^{\max} : \max_{s \in \mathcal{S}_0} R_s > \alpha = \bigcup_{s \in \mathcal{S}_0} \{R_s > \alpha\}$ is a **union** of per-scenario nulls, so its alternative $H_1^{\max} : \forall s \in \mathcal{S}_0,\, R_s \le \alpha$ is an **intersection**! Rejecting $H_0^{\max}$ **if and only if every scenario $s \in \mathcal{S}_0$ individually passes at unadjusted level $\delta = 0.05$** ($\max_{s \in \mathcal{S}_0} p_s \le \delta$) has exact Type-I error $\le \delta = 0.05$ without Bonferroni/Šidák inflation (Berger, *Technometrics* 24(4):295–300, 1982)! Conversely, if we wish to report *which individual scenarios* passed while some failed, we must apply Holm/Šidák multiplicity control across scenarios. Both distinctions are enforced explicitly in `docs/v9_experiment_protocol.md`.
