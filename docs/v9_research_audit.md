# NEXVIA AEGIS V9.0 — Forensic Research Audit (Step 1 of 3)

**Repository Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`
**Active Git Branch:** `v9.0-runtime-assurance`
**Protected V8.1 Baseline Commit:** `4d891c7500cfb4c8110f276038455bc62765ef3b` (`v8.1-audited`)
**Historical Test Suite Status:** `67 passed` (`57` V1–V8 tests + `10` V8.1 audit tests)
**Design Governance Status:** **Preregistration Decisions 1–4 Approved & Locked Prior to Implementation**
**Scope:** Design-phase forensic verification of source code, raw episode records (`results/next/benchmark_episodes.csv`, `4,000` rows), historical research summaries (`docs/research_summary_next.md`), and V8.1 audit artifacts (`docs/v8_audit/*.md`, `results/v8_audit/metrics_recalculated.csv`). No V1–V8.1 source files, historical results, or V8.1 audit documents are modified by this task.

---

## 0. Evidentiary Classification Taxonomy

To prevent conflating historical claims, prior audit assertions, new mathematical proofs, approved design choices, and remaining risks, every finding in this document is tagged with an explicit evidentiary label:

- **`[VERIFIED]`** — Independently verified against executable source code, raw episode-level CSV rows, or exact numerical calculation.
- **`[AUDIT-DISCREPANCY]`** — Asserted in V8 documentation (`docs/research_summary_next.md`) or V8.1 audit reports (`docs/v8_audit/*.md`), independently tested, and found to be numerically incorrect, bibliographically inaccurate, or statistically misapplied.
- **`[NEW-DERIVATION]`** — Mathematical proof or empirical root-cause mechanism newly derived during this V9 forensic audit.
- **`[APPROVED-DECISION]`** — Research architecture or statistical governance decision formally approved for V9 preregistration (not yet implemented in runtime code).
- **`[DESIGN-RISK]`** — Residual modeling assumption or operational risk that must be verified empirically during V9 development/calibration without post-hoc holdout tuning.

---

## 1. Executive Summary of Audited Discrepancies (A–F)

| ID | Audited Topic | Primary Source Locations | Core Forensic Finding | Evidentiary Status |
| :--- | :--- | :--- | :--- | :--- |
| **A** | Infinite-horizon vs. finite-horizon e-process validity | `src/aegis/next/martingale_monitor.py:28-104`, `src/aegis/next/agent_next.py:60-65`, `docs/v8_audit/martingale_validity_report.md:96-103,168` | Reflecting floor `max(1e-4, ...)` is convex and violates the supermartingale inequality once wealth reaches `1e-4` ($\ge 1,838$ nominal steps), invalidating infinite-horizon Ville bounds (`P=1` eventual alarm). However, within the `300`-step benchmark horizon (`0.995^300 = 0.2223 >> 1e-4`), the stopped process never reaches the floor and finite-horizon nominal Type-I alarm control ($\le 0.05$) holds. Neither finite- nor infinite-horizon Ville bounds control closed-loop false-success risk under $H_1$. | `[AUDIT-DISCREPANCY]` + `[NEW-DERIVATION]` |
| **B** | `INDEPENDENT_BIAS` false successes, `COMPOUND_HOLDOUT_EXTREME` failure, & validation leakage | `src/aegis/next/agent_next.py:134-299`, `src/aegis/calibration.py:49,92-94,304-325`, `src/aegis/v7/anchor_scheduler.py:92-100` | Four coupled code-level defects explain all `6` V8 false successes: (1) blind equal-weight pre-fusion hides $\|\mathbf{z}_a - \mathbf{z}_b\| \approx 1.105\text{ m}$ ($15.6\sigma$) behind $\|\mathbf{b}_{\text{fused}}\| = 0.4528\text{ m}$; (2) a missing `return` in `NOMINAL` (`lines 188-205`) lets the agent trigger `ACTIVE_PROBING` and still execute `"STOP"` on the same step; (3) `13/16` (`81.25%`) of `_validation_vectors` lie directly inside the `25`-sample Huber fit window and share the same range sensor; (4) `AnchorIntegrityGate` rejects healthy anchors when range is biased (`-0.40 m`) and the biased range sensor spoofs the `0.45 m` arrival gate. | `[VERIFIED]` + `[NEW-DERIVATION]` |
| **C** | Baseline per-scenario summary discrepancies | `docs/research_summary_next.md:83-120`, `results/next/benchmark_episodes.csv`, `src/aegis/next/baselines.py:46-454` | Pooled Table 3.1 matches episode counts, but per-scenario Table 3.2 contains `29` erroneous `TS` cells out of `70` shown, omits `EKF_CONSISTENCY_MONITOR` completely, and reports `0.0%` Covered Risk on `0/50` accepted episodes in `FAULTY_REFERENCE_SENSOR`. | `[VERIFIED]` + `[AUDIT-DISCREPANCY]` |
| **D** | Paired vs. unpaired statistical-test discrepancies | `docs/v8_audit/baseline_fairness_audit.md:107-125`, `results/next/benchmark_episodes.csv` | All `500` episodes (`10` scenarios $\times$ seeds `60000..60049`) are strictly paired across policies. Prior audit reported paired $t$-test $p = 0.084$ for max overshoot (actual paired $t = 0.4977, p = 0.6189$; Wilcoxon $p = 0.9146$) and used unpaired Fisher's exact test ($p = 0.0327$) on paired false-success incidence (actual paired exact McNemar $p = 0.0034$ on `1` vs. `12` discordant pairs; paired episode bootstrap for $\Delta R_{\text{sel}} = -3.65\%$ yields 95% CI `[-6.23%, -1.33%]`, $p_{\text{boot}} = 0.00088$). V7 vs. V8 `TS` (`267` vs. `251`, `43` vs. `59` discordant) gives exact McNemar $p = 0.1371$ and paired 95% CI `[-7.15%, +0.75%]`. | `[AUDIT-DISCREPANCY]` + `[VERIFIED]` |
| **E** | Confidence interval discrepancies & zero-denominator semantics | `experiments/benchmark_next.py:45-54,332-345`, `docs/v8_audit/benchmark_reconciliation.md`, `results/v8_audit/metrics_recalculated.csv` | V8 pooled selective risk (`6/257 = 2.3346%`) has two-sided 95% Wilson `[1.074%, 4.999%]`, two-sided 95% Clopper–Pearson `[0.862%, 5.012%]` ($>5\%$), and one-sided 95% Clopper–Pearson UCB `4.556%` (valid only for a prespecified frozen policy, which V8 was not). `19` `(scenario, policy)` cells have `0` accepted episodes (`undefined` selective risk, previously logged as `0.0`). Zero-error nominal scenarios (`0/50`) have one-sided 95% UCB `5.816% > 5%`. Minor prose rounding discrepancies in `benchmark_reconciliation.md` are also corrected. | `[VERIFIED]` + `[AUDIT-DISCREPANCY]` |
| **F** | LTT bibliography & selective-risk vs. CRC theory | `docs/v8_audit/related_work_update.md:52`, `docs/v8_audit/v9_research_recommendations.md` | `related_work_update.md:52` cited a non-existent `JRSSB 2024` LTT paper with inaccurate author list and DOI (`10.1093/jrsssb/qkae002`). Primary LTT reference is Angelopoulos, Bates, Candès, Jordan, & Lei (*Annals of Applied Statistics*, 19(2):1641–1662, 2025, `10.1214/24-AOAS1998`), distinct from *Conformal Risk Control* (Angelopoulos et al., *ICLR* 2024) and *Non-Exchangeable Conformal Risk Control* (Farinhas et al., *ICLR* 2024). Standard CRC controls marginal expected monotone loss, **not** conditional selective risk with random acceptance denominators. | `[AUDIT-DISCREPANCY]` + `[VERIFIED]` |

---

## 2. Detailed Forensic Investigation

### A. Infinite-Horizon vs. Finite-Horizon e-Process Validity

- **Source Files & Line Numbers:**
  - `src/aegis/next/martingale_monitor.py:27-35` (`MartingaleConfig`), `lines 54-104` (`AnytimeValidSequentialMonitor.update`).
  - `src/aegis/next/agent_next.py:60-65` (instantiation overriding `nominal_mean=0.065`, `scale_vmax=0.40`, `alpha=0.05`).
  - `src/aegis/v3/env/world.py:23` (`max_steps: int = 300`).
  - `src/aegis/v3/sensors/cross_modal.py:67-78` (`RangeSensor.measure` clamping at `0.0`).
  - `docs/v8_audit/martingale_validity_report.md:96-103, 168` (prior audit supermartingale claim).

- **Mathematical & Empirical Issue (`[AUDIT-DISCREPANCY]`, `[NEW-DERIVATION]`):**
  In `martingale_monitor.py:65-95`, at step $t \ge 1$, given scalar cross-modal residual $e_t = |\|\mathbf{z}_{v,t}\| - r_t|$, the wealth $E_t$ (`self.wealth`, initialized at $E_0 = 1.0$) is updated via:
  $$x_t = \mathrm{clip}\!\left(\frac{e_t - \mu_0}{v_{\max}},\, -0.90,\, 3.50\right), \qquad m_t = 1 + \lambda_t x_t, \qquad E_t = \max\!\Big(10^{-4},\, \min\!\big(10^7,\, \gamma E_{t-1} m_t\big)\Big),$$
  with $\mu_0 = 0.065\text{ m}$ (`agent_next.py:61`; class default is `0.0564` at `martingale_monitor.py:30`), $v_{\max} = 0.40\text{ m}$, $\lambda_{\max} = 0.85$, $\gamma = 0.995$ (`decay_factor`), and alarm threshold $1/\alpha = 20.0$.

  The V8.1 report (`docs/v8_audit/martingale_validity_report.md:101, 168`) asserted that clipping and decay satisfy $E_t \le E_{t-1} \gamma (1 + \lambda_t x_t)$ and therefore preserve Ville's supermartingale bound over an unbounded horizon $t \ge 1$. That inequality is **mathematically false** because $y \mapsto \max(10^{-4}, y)$ is convex and satisfies $\max(10^{-4}, y) \ge y$, reversing the direction of the inequality at the lower boundary.

- **Term-by-Term Verification (`[VERIFIED]`, `[NEW-DERIVATION]`):**
  1. **Nonnegative Multiplier Requirement (`martingale_monitor.py:71, 86, 92`):** Since $x_t \ge -0.90$ and $\lambda_t \in [0, 0.85]$, every finite input satisfies $m_t = 1 + \lambda_t x_t \ge 1 - 0.85 \times 0.90 = 0.235 > 0$. Moreover, because $e_t = |\|\mathbf{z}_{v,t}\| - r_t| \ge 0$ for valid finite readings, $x_t \ge (0 - 0.065)/0.40 = -0.1625$, so $m_t \ge 1 - 0.85 \times 0.1625 = 0.861875 > 0$. *Edge-case defect:* `e_t = float(cross_modal_residual)` (`line 65`) does not guard against `NaN` (`np.clip(np.nan, -0.90, 3.50)` returns `nan` in NumPy, permanently poisoning `self.wealth` and returning `is_alarm = False`).
  2. **Predictability of Betting Parameter $\lambda_t$ (`martingale_monitor.py:66, 73-90`):** Although `self.history.append(e_t)` occurs on `line 66` prior to computing $\lambda_t$, `burn_in_steps = 1` forces $\lambda_1 = 0.0$ (`lines 73-75`), and for $t \ge 2$, `self.history[-15:-1]` (`line 78`) slices indices up to $t-1$ while strictly excluding `self.history[-1]` ($e_t$). Hence $\lambda_t$ is strictly $\mathcal{F}_{t-1}$-measurable.
  3. **Conditional Expectation under $H_0$ (`agent_next.py:61`, `cross_modal.py:75`):** Under $H_0$ ($\mathbf{b}_a = \mathbf{b}_b = \mathbf{0}$, $b_r = 0$, $\sigma_a = \sigma_b = \sigma_r = 0.05\text{ m}$), equal-weight fusion yields $\sigma_{v,\text{fused}} = 0.05/\sqrt{2} \approx 0.03536\text{ m}$ (or $\sigma_v = 0.05\text{ m}$ under single-sensor dropout). Away from the origin ($d = \|\mathbf{d}_t\| \gg \sigma_v$), $\|\mathbf{d}_t + \boldsymbol{\varepsilon}_t\| - (d + \nu_t)$ has variance $\sigma_v^2 + \sigma_r^2 \le 0.05^2 + 0.05^2 = 0.005\text{ m}^2$, giving folded-normal mean $\sqrt{2/\pi}\sqrt{0.005} \approx 0.05642\text{ m}$ (and $\approx 0.04886\text{ m}$ when both vector sensors are valid). Even at $d = 0$, where $\|\boldsymbol{\varepsilon}_t\|$ is Rayleigh($\sigma_v$) with mean $\sigma_v\sqrt{\pi/2} \le 0.06267\text{ m}$ and $r_t = \max(0, \nu_t)$ is half-normal(`0.05`) with mean $0.05/\sqrt{2\pi} \approx 0.01995\text{ m}$, numerical integration confirms $\sup_{d \ge 0} \mathbb{E}_{H_0}[e_t \mid d] \approx 0.05642\text{ m} < \mu_0 = 0.065\text{ m}$. Because $e_t \ge 0 \implies (e_t - 0.065)/0.40 \ge -0.1625 > -0.90$, the lower clip at `-0.90` never activates for non-negative residuals, while the upper clip at `3.50` only decreases expectation. Thus $\mathbb{E}_{H_0}[x_t \mid \mathcal{F}_{t-1}] < 0$ holds across all target distances $d \ge 0$.
  4. **Upper Wealth Cap at `1e7` (`martingale_monitor.py:94`):** Since $y \mapsto \min(10^7, y)$ is concave ($\min(10^7, y) \le y$) and $10^7 \gg 1/\alpha = 20.0$, the upper cap preserves the supermartingale inequality and never alters the stopping event $\{E_t \ge 20.0\}$.
  5. **Decay Factor $\gamma = 0.995$ (`martingale_monitor.py:34, 93`):** Without a lower floor, multiplying a nonnegative supermartingale increment by $\gamma \in (0, 1)$ preserves $\mathbb{E}[\gamma E_{t-1} m_t \mid \mathcal{F}_{t-1}] \le \gamma E_{t-1} \le E_{t-1}$. However, decay has two severe operational downsides: (i) on an infinite horizon, it drives nominal wealth monotonically down to the reflecting floor `1e-4`; and (ii) under gradual or delayed faults, it exponentially attenuates accumulated evidence ($0.995^{200} \approx 0.3670$).
  6. **Reflecting Floor at `1e-4` & Infinite-Horizon Invalidity (`martingale_monitor.py:94`):** Under $\lambda_t = 0$, $E_t = \max(10^{-4}, 0.995^t)$ reaches $10^{-4}$ at $t = \lceil \ln(10^{-4})/\ln(0.995) \rceil = 1,838$ steps. Once $E_{t-1} = 10^{-4}$, on any step where a positive 14-sample fluctuation produces $\lambda_t > 0$ and $\mathbb{P}_{H_0}(\gamma(1 + \lambda_t x_t) > 1 \mid \mathcal{F}_{t-1}) > 0$ (which occurs with positive probability because $x_t$ ranges up to $+3.50$), we have:
     $$\mathbb{E}_{H_0}\!\left[\max\!\big(10^{-4},\, 10^{-4}\gamma(1+\lambda_t x_t)\big) \,\middle|\, \mathcal{F}_{t-1}, E_{t-1}=10^{-4}\right] > 10^{-4} = E_{t-1}.$$
     Furthermore, on the compact state space (or recurrent Markov chain of $(E_t, e_{t-13:t})$ on $[10^{-4}, 20]$), reflection at $10^{-4}$ makes $\{E_t \ge 20\}$ accessible in finitely many upper-tail innovations from every state, so by standard Borel–Cantelli block arguments $\mathbb{P}_{H_0}(\exists t \ge 1 : E_t \ge 20) = 1$ as $t \to \infty$.
  7. **Why Finite-Horizon (`T = 300`) Validity Holds in the V8 Benchmark (`[NEW-DERIVATION]`):** Let $\tilde{E}_t = \prod_{k=1}^t \gamma m_k$ denote the unfloored process ($\tilde{E}_0 = 1$), which is a genuine nonnegative $H_0$-supermartingale satisfying Ville's inequality $\mathbb{P}_{H_0}(\exists t \ge 1 : \tilde{E}_t \ge 20) \le 0.05$. Within $T = 300$ steps (`WorldConfig.max_steps = 300`), can $\tilde{E}_t$ ever drop below $10^{-4}$? For $e_k \ge 0$, $m_k \ge 0.861875$ when $\lambda_k > 0$ and $m_k = 1$ when $\lambda_k = 0$. Since $0.995^{300} = 0.22229$, reaching $10^{-4}$ within $300$ steps requires $(0.861875)^B < 10^{-4} / 0.22229 = 4.4986 \times 10^{-4}$, i.e., at least $B \ge \lceil \ln(4.4986\times 10^{-4})/\ln(0.861875) \rceil = 52$ steps with $\lambda_k = 0.85$ and $e_k = 0$! Yet `martingale_monitor.py:83-89` sets $\lambda_k > 0$ **only** when the preceding 14-step mean satisfies $\bar{x}_{k-14:k-1} > 0$, whereas negative multipliers ($m_k < 1$) immediately pull $\bar{x}$ negative and shut off betting ($\lambda = 0$). Even in the worst mathematically realizable adversarial non-negative sequence $e_{1:300} \ge 0$, constrained optimization verifies $\min_{e_{1:300} \ge 0} \min_{1 \le t \le 300} \tilde{E}_t > 10^{-2} \gg 10^{-4}$. Consequently, $E_t \equiv \tilde{E}_t$ identically on $1 \le t \le 300$ up to $\tau = \inf\{t : E_t \ge 20\}$, so **finite-horizon ($T \le 300$) Type-I nominal alarm control $\mathbb{P}_{H_0}(\exists t \le 300 : E_t \ge 20) \le 0.05$ is valid**.

- **Safety & Statistical Consequence:**
  1. Claiming "infinite-horizon anytime-valid Type-I control" for `martingale_monitor.py` as currently coded is invalid (`[AUDIT-DISCREPANCY]`).
  2. More fundamentally, **even an exact infinite-horizon Ville e-process only bounds $\mathbb{P}_{H_0}(\text{false alarm}) \le \alpha$ under nominal sensors**. It provides **zero upper bound** on Type-II missed-detection probability $\mathbb{P}_{H_1}(\forall t \le \tau_{\text{stop}} : E_t < 1/\alpha)$ under faulty sensors, and therefore **never guarantees closed-loop selective false-success risk $R_{\text{sel}}(\pi) \le \alpha$**.

- **Independent Reproduction Status:** `[VERIFIED]` and `[NEW-DERIVATION]` (both the infinite-horizon counterexample and the exact `300`-step non-hitting proof verified analytically and numerically).

- **Approved V9 Design Decision (`[APPROVED-DECISION]` — Decision 1: Hybrid Parallel Ville + Drift-Detection Channels):**
  1. **Channel A (Exact Ville e-Process):** Use a nonnegative test-supermartingale with $\gamma = 1.0$, **no reflecting lower wealth floor**, and **no invalidating upper wealth cap**, evolved in log-wealth space $\ell_{c,t} = \sum_{s=1}^t \ln(1 + V_{c,s} \lambda_{c,s} x_{c,s})$ (`V_{c,s} = 1` on valid finite readings, `V_{c,s} = 0` on dropout, failing closed to `"ABSTAIN"` on `NaN`/`Inf`) across subchannels $c \in \mathcal{C} = \{\mathrm{ab}, (\mathrm{vr},a), (\mathrm{vr},b)\}$ combined via equal-weight convex mixture $E_t^{\mathrm{Ville}} = \frac{1}{|\mathcal{C}|}\sum_{c \in \mathcal{C}} \exp(\ell_{c,t})$. For non-negative residuals $e_{c,t} \ge 0$, upper-only concave clipping $x_{c,t} = \min((e_{c,t} - \mu_{0,c})/v_{\max,c}, x_{\max})$ with strictly $\mathcal{F}_{t-1}$-predictable $\lambda_{c,t} \in [0, \min(\lambda_{\max}, 0.90\,v_{\max,c}/\mu_{0,c})]$ guarantees $1 + V_{c,t} \lambda_{c,t} x_{c,t} \ge 0.10 > 0$ and $\mathbb{E}_{H_{0,\mathrm{mon}}}[E_t^{\mathrm{Ville}} \mid \mathcal{F}_{t-1}] \le E_{t-1}^{\mathrm{Ville}}$ for **all $t \ge 1$** under the explicit conditional bounded-mean null $H_{0,\mathrm{mon}} : \mathbb{E}[e_{c,t} \mid \mathcal{F}_{t-1}, V_{c,t}=1] \le \mu_{0,c}$ (with exact closed-form Gaussian bounds $\mu_{0,\mathrm{ab}} = \sqrt{\frac{\pi}{2}(\sigma_a^2 + \sigma_b^2)}$ and $\mu_{0,\mathrm{vr},k} = \sigma_k\sqrt{\frac{\pi}{2}} + \sigma_r\sqrt{\frac{2}{\pi}}$ proved in `docs/v9_risk_calibration_design.md`, Section 2.1.4).
  2. **Channel B (Complementary CUSUM / Shiryaev–Roberts-Type Drift Detector):** Run a separate Page CUSUM change-point channel $S_{c,t} = \max(0, S_{c,t-1} + V_{c,t}(z_{c,t} - \kappa_{c,\mathrm{drift}}))$ targeting persistent or slowly ramping faults after nominal stretches. **Never describe Channel B as Ville-anytime-valid** (its lower reflection at `0` violates the supermartingale property over unbounded horizons); treat both Channel A ($\alpha_{\mathrm{mon}}^{(j)}$) and Channel B ($h_{\mathrm{cusum}}^{(j)}$) thresholds and their combination logic as components of the 6-parameter joint candidate policy $\pi_{\lambda^{(j)}}$ ($\lambda^{(j)} \in \Lambda$) calibrated end-to-end via episode-level selective-risk LTT on $\mathcal{D}_{\text{cal}}$.
  3. **Mandatory Three-Way Conceptual Separation:** Across all V9 claims, strictly distinguish: (i) *nominal monitor false-alarm control* under $H_{0,\mathrm{mon}}$; (ii) *fault detection power and detection delay* under $H_1$; and (iii) *closed-loop policy selective false-success risk* $R_{\mathrm{sel}}(\pi; \mathcal{M})$. None of these three properties automatically establishes any of the others.

- **Remaining Design Risk (`[DESIGN-RISK]`):** Heavy-tailed nominal noise (`OUTLIER_BURSTS`, $p=0.12, 4.5\times\sigma$) violates the Gaussian nominal null $H_{0,\mathrm{mon}}$, potentially increasing false alarms into `ACTIVE_PROBING` on Channel A or Channel B unless $x_{\max}$ / $z_{\max}$ clipping and $\lambda^{(j)}$ tiers are properly ordered on $\mathcal{D}_{\text{dev}}$ before locking $\mathcal{D}_{\text{cal}}$.

---

### B. `INDEPENDENT_BIAS` False Successes, Compound-Fault Failure, and Validation Leakage

- **Source Files & Line Numbers:**
  - `src/aegis/next/agent_next.py:134-138` (pre-fusion), `165-170` (scalar residual), `172-181` (anchor check), `186-208` (`NOMINAL` mode & fall-through bug), `212-276` (`ACTIVE_PROBING` & validation leakage), `281-300` (`CALIBRATED` mode).
  - `src/aegis/calibration.py:49, 92-94` (`window_size = 25`), `304-325` (`validate_candidate_bias`).
  - `src/aegis/v7/anchor_scheduler.py:92-100` (`AnchorIntegrityGate.validate_anchor`).
  - `results/next/benchmark_episodes.csv` (all `6` rows where `policy == "AEGIS_NEXT_MARTINGALE"` and `false_success == 1`).

- **Empirical Verification of All 6 V8 False-Success Rows (`[VERIFIED]`):**
  Direct inspection of `results/next/benchmark_episodes.csv` confirms that `AEGIS_NEXT_MARTINGALE` incurred exactly `6` false successes across `500` episodes (`257` accepted decisions), concentrated exclusively in two scenarios:

  | Scenario | Seed | `final_distance` (m) | `steps` | `distance_traveled` (m) | `anchor_queries` | `anchor_cost` | `max_overshoot` (m) |
  | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
  | `INDEPENDENT_BIAS` | `60002` | `0.4613` | `173` | `2.6562` | `0` | `0.0` | `0.0040` |
  | `INDEPENDENT_BIAS` | `60008` | `0.4711` | `181` | `2.7689` | `0` | `0.0` | `0.0086` |
  | `INDEPENDENT_BIAS` | `60010` | `0.4591` | `173` | `2.6503` | `0` | `0.0` | `0.0110` |
  | `INDEPENDENT_BIAS` | `60012` | `0.4539` | `201` | `3.3071` | `0` | `0.0` | `0.0` |
  | `COMPOUND_HOLDOUT_EXTREME` | `60016` | `0.8342` | `176` | `3.8295` | `3` | `0.15` | `0.0` |
  | `COMPOUND_HOLDOUT_EXTREME` | `60044` | `0.8232` | `83` | `1.2016` | `0` | `0.0` | `0.0` |

- **Four Verified Code-Level Failure Mechanisms (`[VERIFIED]`, `[NEW-DERIVATION]`):**

  1. **Mechanism B1 — Blind Equal-Variance Pre-Fusion Conceals Inter-Sensor Vector Disagreement (`agent_next.py:134-138, 166`):**
     In `INDEPENDENT_BIAS` (`experiments/benchmark_next.py:90-96`), `vec_a` has static bias $\mathbf{b}_a = (+0.60, +0.40)\text{ m}$ and `vec_b` has $\mathbf{b}_b = (-0.50, +0.50)\text{ m}$ with equal $\sigma_a = \sigma_b = 0.05\text{ m}$. Lines `135-137` average them before monitoring:
     $$\mathbf{b}_{\text{fused}} = \frac{1}{2}\mathbf{b}_a + \frac{1}{2}\mathbf{b}_b = (+0.05, +0.45)\text{ m}, \qquad \|\mathbf{b}_{\text{fused}}\| = \sqrt{0.05^2 + 0.45^2} \approx 0.45277\text{ m}.$$
     Notice two fatal geometric facts:
     - First, $\|\mathbf{b}_{\text{fused}}\| = 0.4528\text{ m}$ lies **just outside** the safety radius $d_{\text{safe}} = 0.45\text{ m}$ (`benchmark_next.py:291-292`). When the robot drives $\mathbf{z}_{\text{fused}} \approx \mathbf{d}_t + \mathbf{b}_{\text{fused}} \to \mathbf{0}$, its true terminal displacement converges to $\mathbf{d}_t \approx -\mathbf{b}_{\text{fused}}$ with $\|\mathbf{d}_t\| \approx 0.453\text{–}0.471\text{ m}$, producing the exact four false-success distances (`0.4539–0.4711 m`) observed above!
     - Second, the inter-sensor difference $\boldsymbol{\delta}_{ab,t} = \mathbf{z}_{a,t} - \mathbf{z}_{b,t}$ has mean $\mathbf{b}_a - \mathbf{b}_b = (+1.10, -0.10)\text{ m}$ and norm $\|\mathbf{b}_a - \mathbf{b}_b\| = \sqrt{1.22} \approx 1.1045\text{ m}$—an overwhelming **$15.62\sigma_{\text{diff}}$** anomaly relative to nominal $\sigma_{\text{diff}} = \sqrt{0.05^2 + 0.05^2} \approx 0.07071\text{ m}$! Yet the martingale monitor (`agent_next.py:166-167`) receives **only** the scalar cross-modal residual $e_t = |\|\mathbf{z}_{\text{fused},t}\| - r_t|$. Whenever $\mathbf{d}_t$ approaches along the locus $\|\mathbf{d}_t + \mathbf{b}_{\text{fused}}\| \approx \|\mathbf{d}_t\|$ (i.e., $2\mathbf{d}_t^\top \mathbf{b}_{\text{fused}} + \|\mathbf{b}_{\text{fused}}\|^2 \approx 0$), $e_t$ stays near zero throughout most of the trajectory. For example, deterministic replay of `seed=60002` confirms that `martingale_wealth` reaches only `16.39 < 20.0` by `step=172`, never triggering `ACTIVE_PROBING` prior to arrival!

  2. **Mechanism B2 — `NOMINAL` $\to$ `ACTIVE_PROBING` Fall-Through Bug and Unguarded Range-Dropout Terminal Gate (`agent_next.py:188-205, 296`):**
     Look at `agent_next.py:188-205`:
     ```python
     if self.state.mode == "NOMINAL":
         if is_alarm or cross_res > 0.35:
             self.state.mode = "ACTIVE_PROBING"
             ...
         if range_reading.valid:
             self.estimator.add_observation(raw_vector, range_reading.distance, True)
         action, arrived = self.motion_controller.plan_approach_action(raw_vector, self._velocity)
         if arrived:
             if range_reading.valid and range_reading.distance > 0.45:
                 return np.zeros(2), "VERIFY", raw_vector, False
             return np.zeros(2), "STOP", raw_vector, False
     ```
     Because `lines 188-193` lack a `return` (or `else` branch), on the exact step where `is_alarm` or `cross_res > 0.35` fires near the target, `self.state.mode` transitions to `"ACTIVE_PROBING"` and **immediately falls through** to `lines 200-205`, evaluates `arrived` on the **uncalibrated** `raw_vector`, and commits terminal `"STOP"` whenever a single noisy range draw dips $\le 0.45\text{ m}$! Replay of `INDEPENDENT_BIAS` `seed=60002` at `step=172` (`true_dist = 0.4613 m`) shows `cross_res = 0.3507 > 0.35` triggering `"ACTIVE_PROBING"`, falling straight through with `||raw_vector|| = 0.0914 <= 0.22` (`arrived = True`) and `range_reading.distance = 0.4421 <= 0.45`, and returning `"STOP"` on the exact step a fault was flagged!
     Additionally, on both `line 203` and `line 296` (`if range_reading.valid and range_reading.distance > 0.45:`), if `range_reading.valid` is `False` (a dropped range packet at arrival), the condition short-circuits to `False` and commits `"STOP"` with **zero terminal cross-modal verification**.

  3. **Mechanism B3 — In-Sample Validation Leakage (`agent_next.py:214-218, 260-264`, `calibration.py:49, 92-94, 304-325`):**
     During `ACTIVE_PROBING` (`probing_steps = 32`), `agent_next.py:215` calls `self.estimator.add_observation(raw_vector, range_reading.distance, True)` on **every** probing step $k \in \{1, \dots, 32\}$ (after `line 197` already added one sample on the transition step $k = 0$), while `lines 216-218` append `(raw_vector, range_reading.distance)` to `_validation_vectors` / `_validation_ranges` on every **even** step $k \in \{2, 4, \dots, 32\}$ (`16` points). Because `OnlineBiasEstimator` uses a rolling FIFO buffer of `window_size = 25` (`calibration.py:49, 92-94`), at $k = 32$ the Huber M-estimator fits $\hat{\mathbf{b}}$ on steps $\{8, 9, \dots, 32\}$. Consequently:
     - **`13` out of `16` (`81.25%`) validation observations** ($k \in \{8, 10, 12, \dots, 32\}$) are **identical training points** inside the Huber optimization objective!
     - The remaining `3` observations ($k \in \{2, 4, 6\}$) come from the same continuous trajectory within `0.12 s` of fit-window onset and measure against the **exact same range sensor** $r_t$.
     - Furthermore (`agent_next.py:260-261`), `val_passed` defaults to `True` if `_validation_vectors` is empty.
     *(Note: The identical `probing_step_count % 2 == 0` in-sample leakage also exists in `src/aegis/v7/recovery_controller.py:262-265`.)*

  4. **Mechanism B4 — Inverted Anchor Rejection & Terminal Range-Gate Spoofing in `COMPOUND_HOLDOUT_EXTREME` (`anchor_scheduler.py:92-100`, `agent_next.py:244, 296`):**
     In `COMPOUND_HOLDOUT_EXTREME` (`benchmark_next.py:150-159`), `vec_a` has $\mathbf{b}_a = (0.5, 0.5)$ plus linear drift $(0.002, 0.002)t$, `vec_b` has $\mathbf{b}_b = (0.5, 0.5)$, `range_sensor_bias = -0.40 m`, and the anchor is **healthy** (`anchor_corrupted = False`).
     - In `seed=60016`, `AEGIS_NEXT_MARTINGALE` issued `3` anchor queries (at probing steps `4, 12, 20`). When the healthy anchor returned $\|\mathbf{z}_{\text{anc}}\| \approx 2.42\text{ m}$ and the biased range sensor reported $r_t \approx 2.02\text{ m}$, `AnchorIntegrityGate.validate_anchor` (`anchor_scheduler.py:96-100`) saw $|2.42 - 2.02| = 0.40 > 0.35$ and **blamed and rejected the healthy anchor**, assuming the range sensor was ground truth! Next, `MultiHypothesisDiagnosisEngine` failed to classify $H_3$ (`H3_REFERENCE_FAULT`), Huber fit $\hat{\mathbf{b}} = (0.830, -0.127)\text{ m}$ to match the `-0.40 m` biased range circle (passing the leaked validation gate with `RMSE = 0.068 <= 0.15`), and in `CALIBRATED` mode at `true_dist = 0.8342 m`, the `-0.40 m` biased range sensor reported `0.4323 <= 0.45 m`, spoofing the terminal range gate (`agent_next.py:296`) while ignoring that $\|\mathbf{z}_a - \mathbf{z}_b\|$ had drifted to `0.559 m`!
     - In `seed=60044`, the target initialized nearby (`true_dist_0 = 1.25 m`); at `step=83` (`true_dist = 0.8232 m`), `NOMINAL` fell straight through on arrival because `range_reading.distance = 0.8232 - 0.40 + \nu = 0.418 <= 0.45 m`!

- **Approved V9 Design Decisions (`[APPROVED-DECISION]` — Decisions 2 & 3) and Data-Flow Requirements (`[NEW-DERIVATION]`):**
  1. **Per-Sensor Bias Estimation (`Decision 2`):** Adopt separate `OnlineBiasEstimator` instances for `vec_a` ($\hat{\mathbf{b}}_a$) and `vec_b` ($\hat{\mathbf{b}}_b$) as the primary V9 design rather than pre-fusing raw vectors into a single shared bias estimate. Preserve explicit raw ($\boldsymbol{\delta}_{ab,t} = \mathbf{z}_{a,t} - \mathbf{z}_{b,t}$) and bias-corrected ($\tilde{\boldsymbol{\delta}}_{ab,t}$) inter-sensor disagreement; discard invalid, missing, or dropout readings before buffer insertion; track per-sensor qualification status (`UNCALIBRATED`, `CALIBRATED_VALID`, `REJECTED_OR_FAULTY`, `DROPOUT_INSUFFICIENT`) and combined variance $\hat{u}_k^2 = \sigma_k^2 + \mathrm{RMSE}_{\mathrm{fit},k}^2 / \max(\lambda_{\min,k}, 10^{-6})$; and retain selective single-sensor-only calibration strictly as a future comparison candidate rather than the primary V9 policy.
  2. **Strict Data-Flow Elimination of Validation Leakage (`Decision 2`):** Clear all `NOMINAL` buffers on `ACTIVE_PROBING` entry (returning `"PROBE"` immediately without falling through to `"STOP"`), partition probing into disjoint temporal/geometric blocks $\mathcal{I}_{\mathrm{fit}} = \{1,\dots,T_{\mathrm{fit}}\}$, transition gap $\mathcal{I}_{\mathrm{gap}}$, and future validation block $\mathcal{I}_{\mathrm{val}}$ (`set(I_fit) & set(I_val) == set()`), freeze $(\hat{\mathbf{b}}_a, \hat{\mathbf{b}}_b)$ after $\mathcal{I}_{\mathrm{fit}}$, and forbid continuous online refitting during `CALIBRATED` approach (which would destroy out-of-sample independence by tracking drift/range bias). Recognize that within-episode disjoint blocks remain trajectory-coupled, so statistical risk certification relies solely on episode-level LTT on $\mathcal{D}_{\text{cal}}$ and holdout testing on $\mathcal{D}_{\text{test}}^{\text{mix}}$.
  3. **Fail-Closed Anchor/Range Disagreement Rule (`Decision 3`):** Treat V8's `0.35 m` tolerance as an unvalidated inherited candidate rather than a certified safety limit, replacing it with a parameterized normalized discrepancy gate $\tilde{\Delta}_{ar,t} = |\|\mathbf{z}_{\mathrm{anc},t}\|_2 - r_t| / \sqrt{\sigma_{\mathrm{anc}}^2 + \sigma_r^2} > \tau_{ar}^{(j)}$ inside $\Lambda$. Whenever anchor and range disagree beyond $\tau_{ar}^{(j)}$, **default to `"ABSTAIN"`** unless independent, drift-verified multi-step vector-displacement chord evidence ($\Delta \mathbf{z}_{k, t_1 \to t_2}$) unambiguously corroborates one modality under fixed pre-holdout rules; never treat either range or anchor as an unquestionable oracle, and abstain whenever evidence is ambiguous or vulnerable to common-mode failure.

- **Remaining Design Risk (`[DESIGN-RISK]`):** Under high single-sensor dropout (`p_drop = 0.35–0.40`), a fixed `22`-step fit block $\mathcal{I}_{\mathrm{fit}}$ yields fewer valid observations ($\mathbb{E}[n_{\mathrm{fit}}] \approx 13.2$); FIM conditioning ($\lambda_{\min}$) and rejection rates on $\mathcal{I}_{\mathrm{val}}$ must be verified on $\mathcal{D}_{\text{dev}}$ before freezing $\Lambda$.

---

### C. Baseline Summary Discrepancies

- **Source Files & Line Numbers:**
  - `docs/research_summary_next.md:83-96` (Table 3.1 Pooled) and `lines 104-119` (Table 3.2 Per-Scenario).
  - `results/next/benchmark_episodes.csv` (`4,000` episode records) and `results/next/benchmark_summary.csv` (`80` scenario-policy rows).
  - `src/aegis/next/baselines.py:46-382` (mechanical origin of nominal baseline timeouts/abstentions).

- **Calculation Method (`[VERIFIED]`):**
  All reproducible metrics below were computed directly in Python by grouping the `4,000` rows of `results/next/benchmark_episodes.csv` by `(scenario, policy)` (`50` episodes per cell; `500` episodes per policy pooled across all `10` scenarios), summing integer indicators `TS = sum(true_success)`, `FS = sum(false_success)`, `AB = sum(abstain)`, decomposing `AB = AB_early (steps < 300) + AB_timeout (steps == 300)`, and computing `M = TS + FS`, `Coverage = M / N`, and `R_sel = FS / M` if `M > 0` else `UNDEFINED`.

- **Audit of Pooled Table 3.1 (`docs/research_summary_next.md:85-95`, `[VERIFIED]`):**
  All integer `TS`, `FS`, and `AB` counts in Table 3.1 match `results/next/benchmark_episodes.csv`, with three minor numerical/reporting defects:
  1. `AEGIS_V7_MPC_BASELINE` mean `max_overshoot` is `0.068748 m` (`0.0687 m` to 4 decimals), transcribed as `0.0688 m`.
  2. `EKF_CONSISTENCY_MONITOR` (`0/15` false successes) 95% Wilson upper bound was truncated to `0.20` (exact two-sided 95% Wilson `[0.0000, 0.2039]`; two-sided 95% Clopper–Pearson `[0.0000, 0.2180]`).
  3. `AEGIS_NEXT_MARTINGALE` (`6/257`) 95% CI upper bound was written `[0.011, 0.050]`, masking that exact two-sided 95% Wilson is `[0.01074, 0.04999]` while exact two-sided 95% Clopper–Pearson is `[0.00862, 0.05012] > 0.05`.

- **Audit of Per-Scenario Table 3.2 (`docs/research_summary_next.md:106-117`, `[AUDIT-DISCREPANCY]`):**
  Table 3.2 exhibits **three major discrepancies** against `results/next/benchmark_episodes.csv`:
  1. `EKF_CONSISTENCY_MONITOR` was omitted entirely from Table 3.2 without explanation.
  2. In `FAULTY_REFERENCE_SENSOR`, `AEGIS-Next Covered Risk` was reported as **`0.0%`** despite `AEGIS_NEXT_MARTINGALE` having `TS = 0, FS = 0, AB = 50` (`M = 0` accepted episodes $\implies$ selective risk is **`UNDEFINED`**, not `0.0%`).
  3. **`29` out of `70` reported scenario-policy `TS` cells in Table 3.2 disagree with the actual raw CSV data:**

  | Scenario | Policy Column in Table 3.2 | Reported in `research_summary_next.md` | Actual in `benchmark_episodes.csv` (`TS/50`) | Discrepancy ($\text{Reported} - \text{Actual}$) |
  | :--- | :--- | :---: | :---: | :---: |
  | `NOMINAL` | `Unshielded` | `50/50` | **`39/50`** (`0 FS, 11 TO`) | `+11` |
  | `NOMINAL` | `Chi2 NIS` | `49/50` | **`22/50`** (`0 FS, 24 early AB, 4 TO`) | `+27` |
  | `NOMINAL` | `V4` | `50/50` | **`39/50`** (`0 FS, 11 TO`) | `+11` |
  | `NOMINAL` | `V5` | `50/50` | **`39/50`** (`0 FS, 11 TO`) | `+11` |
  | `PRIMARY_BIAS` | `Unshielded` | `0/50` | **`18/50`** (`22 FS, 10 TO`) | `-18` |
  | `PRIMARY_BIAS` | `V4` | `0/50` | **`3/50`** (`4 FS, 43 AB`) | `-3` |
  | `PRIMARY_BIAS` | `V5` | `25/50` | **`8/50`** (`5 FS, 37 AB`) | `+17` |
  | `PRIMARY_BIAS` | `V6` | `17/50` | **`13/50`** (`1 FS, 36 AB`) | `+4` |
  | `INDEPENDENT_BIAS` | `Unshielded` | `0/50` | **`29/50`** (`8 FS, 13 TO`) | `-29` |
  | `INDEPENDENT_BIAS` | `V4` | `0/50` | **`5/50`** (`4 FS, 41 AB`) | `-5` |
  | `INDEPENDENT_BIAS` | `V5` | `22/50` | **`11/50`** (`5 FS, 34 AB`) | `+11` |
  | `INDEPENDENT_BIAS` | `V6` | `23/50` | **`7/50`** (`13 FS, 30 AB`) | `+16` |
  | `CORRELATED_BIAS` | `V5` | `0/50` | **`8/50`** (`3 FS, 39 AB`) | `-8` |
  | `SENSOR_DRIFT` | `Unshielded` | `48/50` | **`37/50`** (`0 FS, 13 TO`) | `+11` |
  | `SENSOR_DRIFT` | `Chi2 NIS` | `0/50` | **`1/50`** (`0 FS, 49 AB`) | `-1` |
  | `SENSOR_DRIFT` | `V4` | `0/50` | **`15/50`** (`0 FS, 35 AB`) | `-15` |
  | `SENSOR_DRIFT` | `V5` | `35/50` | **`36/50`** (`1 FS, 13 AB`) | `-1` |
  | `SENSOR_DRIFT` | `V6` | `40/50` | **`46/50`** (`0 FS, 4 TO`) | `-6` |
  | `OUTLIER_BURSTS` | `Unshielded` | `50/50` | **`37/50`** (`0 FS, 13 TO`) | `+13` |
  | `OUTLIER_BURSTS` | `Chi2 NIS` | `0/50` | **`2/50`** (`0 FS, 48 AB`) | `-2` |
  | `OUTLIER_BURSTS` | `V4` | `50/50` | **`29/50`** (`0 FS, 21 AB`) | `+21` |
  | `OUTLIER_BURSTS` | `V5` | `50/50` | **`31/50`** (`0 FS, 19 AB`) | `+19` |
  | `OUTLIER_BURSTS` | `V6` | `46/50` | **`49/50`** (`1 FS, 0 AB`) | `-3` |
  | `SENSOR_DROPOUT` | `Unshielded` | `50/50` | **`38/50`** (`0 FS, 12 TO`) | `+12` |
  | `SENSOR_DROPOUT` | `Chi2 NIS` | `0/50` | **`24/50`** (`0 FS, 26 AB`) | `-24` |
  | `SENSOR_DROPOUT` | `V4` | `29/50` | **`38/50`** (`0 FS, 12 TO`) | `-9` |
  | `SENSOR_DROPOUT` | `V5` | `0/50` | **`38/50`** (`0 FS, 12 TO`) | `-38` |
  | `SENSOR_DROPOUT` | `V6` | `42/50` | **`50/50`** (`0 FS, 0 AB`) | `-8` |
  | `CORRUPTED_ANCHOR_STRESS` | `V5` | `0/50` | **`8/50`** (`3 FS, 39 AB`) | `-8` |

  *(Count check: all `29` discordant `TS` cells out of `70` reported in Table 3.2 reflect manual transcription from stale/pre-run notes rather than programmatic aggregation from `benchmark_episodes.csv`.)*

- **Complete Reproducible $10 \times 8$ Per-Scenario Reference Matrix (`TS / FS / AB`, where `M = TS + FS`, `N = 50`, `[VERIFIED]`):**

  | Scenario (`N=50` each) | `UNSHIELDED` | `CHISQ_NIS` | `EKF_CONSIST` | `AEGIS_V4` | `AEGIS_V5` | `AEGIS_V6` | `AEGIS_V7` | `AEGIS_NEXT (V8)` |
  | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
  | `NOMINAL` | `39/0/11` | `22/0/28` | `11/0/39` | `39/0/11` | `39/0/11` | `50/0/0` | `49/0/1` | `50/0/0` |
  | `PRIMARY_BIAS` | `18/22/10` | `0/0/50` | `0/0/50` | `3/4/43` | `8/5/37` | `13/1/36` | `30/3/17` | `17/0/33` |
  | `INDEPENDENT_BIAS` | `29/8/13` | `0/0/50` | `0/0/50` | `5/4/41` | `11/5/34` | `7/13/30` | `25/11/14` | `28/4/18` |
  | `CORRELATED_BIAS` | `0/34/16` | `0/18/32` | `0/0/50` | `0/0/50` | `8/3/39` | `0/0/50` | `36/0/14` | `37/0/13` |
  | `SENSOR_DRIFT` | `37/0/13` | `1/0/49` | `1/0/49` | `15/0/35` | `36/1/13` | `46/0/4` | `41/0/9` | `19/0/31` |
  | `OUTLIER_BURSTS` | `37/0/13` | `2/0/48` | `1/0/49` | `29/0/21` | `31/0/19` | `49/1/0` | `41/0/9` | `48/0/2` |
  | `SENSOR_DROPOUT` | `38/0/12` | `24/0/26` | `2/0/48` | `38/0/12` | `38/0/12` | `50/0/0` | `43/0/7` | `50/0/0` |
  | `FAULTY_REFERENCE_SENSOR` | `0/34/16` | `0/18/32` | `0/0/50` | `0/0/50` | `0/0/50` | `0/0/50` | `0/0/50` | `0/0/50` |
  | `CORRUPTED_ANCHOR_STRESS` | `0/34/16` | `0/18/32` | `0/0/50` | `0/0/50` | `8/3/39` | `0/0/50` | `0/0/50` | `1/0/49` |
  | `COMPOUND_HOLDOUT_EXTREME` | `0/30/20` | `0/2/48` | `0/0/50` | `0/0/50` | `3/12/35` | `3/14/33` | `2/3/45` | `1/2/47` |
  | **Pooled (`N=500`)** | **`198/162/140`** | **`49/56/395`** | **`15/0/485`** | **`129/8/363`** | **`182/29/289`** | **`218/29/253`** | **`267/17/216`** | **`251/6/243`** |

- **Mechanical Root Cause of Baseline `NOMINAL` Behavior (`[NEW-DERIVATION]`):**
  Inspecting `src/aegis/next/baselines.py` explains why several baselines miss `50/50` in `NOMINAL`:
  - `UnshieldedAlwaysActController` (`lines 72-80`), `AegisV4PassiveController` (`lines 260-279`), and `AegisV5HuberController` (`lines 320-337`) differentiate unfiltered noisy fused vectors (`-(raw_vec - _prev_vector) / 0.02`, standard deviation $\approx 2.50\text{ m/s}$) and apply a damped force command `u_dir * 0.50 - 0.20 * _velocity`, causing distant targets in $[-3, 3]^2$ (initial distance up to $7.07\text{ m}$ from $(-2, -2)$) to time out at `step = 300` in `11/50` nominal seeds.
  - `ChiSquareNISGatingController` (`lines 129-137`) tests per-step $\mathrm{NIS}_t > 5.991$ ($\alpha_{\text{step}} = 0.05$) and permanently abstains on `2` consecutive breaches (`24` early abstentions + `4` timeouts in `NOMINAL`).
  - `EKFConsistencyController` (`lines 165, 190, 200-219`) propagates finite-difference noisy velocity while setting process covariance to `Q = 1e-4 * I_2`, collapsing state covariance `P` so `3-sigma` range-innovation gating (`norm_innov_sq > 9.0`) triggers `37` false nominal abstentions.

- **Approved V9 Design Decision (`[APPROVED-DECISION]`):** Prohibit manual Markdown table transcription. Every summary table in V9 must be emitted directly by a deterministic reporting script reading episode-level CSV artifacts and verified via SHA-256 checksums in automated tests.

---

### D. Statistical-Test Discrepancies

- **Source Files & Line Numbers:**
  - `docs/v8_audit/baseline_fairness_audit.md:107-125` (V8.1 statistical comparison table and commentary).
  - `docs/research_summary_next.md:98` (original V8 claim of McNemar $p = 0.32$).
  - `experiments/benchmark_next.py:198-205, 241` (matched-seed experimental design).
  - `results/next/benchmark_episodes.csv`.

- **Matched-Seed Experimental Structure (`[VERIFIED]`):**
  In `experiments/benchmark_next.py:198-205, 241`, for each of the `10` scenarios and each `ep_idx in range(50)` (`ep_seed = 60000 + ep_idx`), **every policy is evaluated on the exact same initial target position `world.reset(np.random.default_rng(ep_seed))` and identical sensor RNG seed `np.random.default_rng(ep_seed)`**. Thus the `500` episodes form **`500` matched pairs** $(s, \text{seed})$ across any two policies $(\pi_A, \pi_B)$ (note that closed-loop trajectories diverge once actions differ, so sensor draws remain matched at step $t=0$ and coupled via common random numbers thereafter). Statistical tests on episode-level binary or continuous outcomes across `500` episodes **must respect this paired design**.

- **Independent Reproduction & Audit of All Three Comparisons (`[AUDIT-DISCREPANCY]`, `[VERIFIED]`):**

  1. **Maximum Overshoot (`AEGIS_V7_MPC_BASELINE` vs. `AEGIS_NEXT_MARTINGALE`):**
     - Empirical means across `N = 500` matched episodes: $\bar{O}_{\text{V7}} = 0.068748\text{ m}$, $\bar{O}_{\text{V8}} = 0.075104\text{ m}$ ($\hat{\Delta}_O = +0.006355\text{ m}$).
     - `docs/v8_audit/baseline_fairness_audit.md:116` reported a paired $t$-test of **`p = 0.084`** ("marginally worse").
     - **Exact reproduction (`scipy.stats.ttest_rel` on the `500` matched pairs):** $t = 0.497703$ ($\mathrm{df} = 499$), two-sided **`p = 0.618913`**! (Unpaired Welch $t$-test gives $t = 0.329672, p = 0.741718$; paired non-parametric Wilcoxon signed-rank test on non-zero differences gives $W = 1331.0, p = 0.914628$.) Neither paired nor unpaired tests yield `0.084`; `0.084` in `baseline_fairness_audit.md` is an unverified numerical fabrication/error (`[AUDIT-DISCREPANCY]`). Because overshoot is heavily zero-inflated and right-skewed, V9 will predeclare paired Wilcoxon signed-rank + paired bootstrap CI alongside paired $t$-tests.

  2. **True-Success Rate (`AEGIS_V7_MPC_BASELINE` vs. `AEGIS_NEXT_MARTINGALE`):**
     - Counts (`N = 500`): V7 `267/500` (`53.40%`), V8 `251/500` (`50.20%`), $\hat{\Delta}_{\text{TS}} = \text{V8} - \text{V7} = -3.20\%$.
     - Exact $2 \times 2$ paired contingency table on `(TS_V7, TS_V8)`:
       - Both fail (`0, 0`): $n_{00} = 190$
       - V7 fails, V8 succeeds (`0, 1`): $n_{01} = 43$
       - V7 succeeds, V8 fails (`1, 0`): $n_{10} = 59$
       - Both succeed (`1, 1`): $n_{11} = 208$
     - Exact two-sided McNemar test ($\mathrm{Binomial}(n_{01}+n_{10}=102, 0.5)$ at $\min(43, 59)=43$): **`p = 0.137099`** (confirming V8.1's correction of V8's erroneous `p = 0.32`).
     - Paired Wald standard error $\mathrm{SE}_{\text{paired}} = \frac{1}{N}\sqrt{n_{01} + n_{10} - \frac{(n_{01}-n_{10})^2}{N}} = 0.020148$ (sample SD of $d_i \in \{-1,0,1\}$ with `ddof=1` gives `0.020168`), yielding two-sided 95% CI **`[-7.15%, +0.75%]`** (one-sided 95% lower confidence bound **`-6.51%`**). Thus at a `-5.0%` noninferiority margin, V8 **cannot** claim noninferiority in `TS` to V7 on `N = 500`.

  3. **False-Success Comparison — Unconditional Incidence vs. Selective Risk (`[AUDIT-DISCREPANCY]`, `[NEW-DERIVATION]`):**
     - `docs/v8_audit/baseline_fairness_audit.md:113` applied **unpaired Fisher's exact test** (`p = 0.03266`) to `17/500` vs. `6/500`, violating the matched-seed design AND conflating unconditional incidence with selective risk:
       - **Comparison 1: Unconditional False-Success Incidence $R_{\text{inc}}(\pi_8) - R_{\text{inc}}(\pi_7)$ (`N = 500` matched pairs).**
         Paired contingency table on `(FS_V7, FS_V8)`: $n_{00} = 482$, $n_{01} = 1$ (V8 false success where V7 did not: `INDEPENDENT_BIAS` `seed=60012`), $n_{10} = 12$ (V7 false success where V8 did not), $n_{11} = 5$ (both false success). The design-appropriate **exact two-sided McNemar test** on $(n_{01}, n_{10}) = (1, 12)$ yields **`p = 0.003418`** ($\hat{\Delta}_{\text{inc}} = -2.20\%$).
       - **Comparison 2: Conditional Selective Risk $R_{\text{sel}}(\pi_8) - R_{\text{sel}}(\pi_7)$ (`6/257 = 2.335%` vs. `17/284 = 5.986%`).**
         Because acceptance indicators $A_i(\pi_7)$ and $A_i(\pi_8)$ differ across episodes (`284` vs. `257` accepted), **neither McNemar's test nor unpaired Fisher's exact test (`p = 0.05271 > 0.05`) is valid**: unpaired Fisher ignores positive within-seed correlation across the `5` shared false successes, while McNemar requires a common denominator of `500` units. The design-consistent estimator is a **paired episode-level bootstrap** resampling matched `(scenario, seed)` units $i \in \{1, \dots, 500\}$ with replacement ($B = 50,000$, stratified by scenario or pooled according to the estimand) and computing $\hat{R}_{\text{sel}}^*(\pi_8) - \hat{R}_{\text{sel}}^*(\pi_7) = \frac{\sum FS_i^*(\pi_8)}{\sum A_i^*(\pi_8)} - \frac{\sum FS_i^*(\pi_7)}{\sum A_i^*(\pi_7)}$:
         - Point difference: $\hat{\Delta}_{R_{\text{sel}}} = -0.036513$ (`-3.65%`).
         - Paired bootstrap 95% percentile CI: **`[-6.23%, -1.33%]`** (two-sided paired bootstrap $p = 0.00088$).

- **Approved V9 Design Decision (`[APPROVED-DECISION]`):** Predeclare the exact statistical test matched to both the **experimental unit** (paired `(scenario, seed)` episode) and the **estimand**: exact McNemar + Newcombe/Tango paired CI for binary full-sample rates (`TS`, `Coverage`, `R_inc`), paired episode-level stratified bootstrap for ratio estimands with policy-dependent denominators ($\Delta R_{\text{sel}}$), and paired Wilcoxon signed-rank + paired bootstrap CI for skewed continuous metrics (`max_overshoot`, `anchor_cost`, `steps`).

---

### E. Confidence Interval Discrepancies and Zero-Denominator Semantics

- **Source Files & Line Numbers:**
  - `experiments/benchmark_next.py:45-54` (`wilson_score_interval` returning `(0.0, 0.0)` for `trials == 0`), `lines 332-345` (`cov_risk = 0.0` when `(ts_count + fs_count) == 0`).
  - `experiments/audit_v8_metrics.py` & `results/v8_audit/metrics_recalculated.csv`.
  - `docs/v8_audit/benchmark_reconciliation.md:50-108`.

- **Interval Methods & Exact Definitions (`[VERIFIED]`):**
  For $k \in \{0, \dots, n\}$ failures in $n \ge 1$ independent Bernoulli($p$) trials:
  1. **Two-sided $1-\alpha_{\text{ci}}$ Wilson Score Interval** ($z = \Phi^{-1}(1 - \alpha_{\text{ci}}/2) = 1.95996398$ for $95\%$):
     $$\frac{\hat{p} + \frac{z^2}{2n} \pm z\sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}, \qquad \hat{p} = \frac{k}{n}.$$
     *Limitation:* Asymptotic normal approximation; can slightly undercover near $p \to 0$ (e.g., at $k=6, n=257$, Wilson upper is `0.049989 < 0.05` whereas exact Clopper–Pearson upper is `0.050120 > 0.05`).
  2. **Two-sided $1-\alpha_{\text{ci}}$ Exact Clopper–Pearson Interval:**
     $$L_{\text{CP},2}(k, n; \alpha_{\text{ci}}) = \mathrm{Beta}^{-1}\!\left(\frac{\alpha_{\text{ci}}}{2};\, k,\, n - k + 1\right)\ \text{(or } 0 \text{ if } k=0\text{)}, \qquad U_{\text{CP},2}(k, n; \alpha_{\text{ci}}) = \mathrm{Beta}^{-1}\!\left(1 - \frac{\alpha_{\text{ci}}}{2};\, k + 1,\, n - k\right)\ \text{(or } 1 \text{ if } k=n\text{)}.$$
  3. **One-sided $1-\delta$ Exact Clopper–Pearson Upper Confidence Bound (UCB)** (for directional safety certification $p \le \alpha$ at confidence $1-\delta$, e.g. $\delta = 0.05$):
     $$U_{\text{CP},1}(k, n; \delta) = \begin{cases} \text{UNDEFINED}, & n = 0, \\ 1.0, & k = n \ge 1, \\ \mathrm{Beta}^{-1}(1 - \delta;\, k + 1,\, n - k), & 0 \le k < n, \end{cases}$$
     which satisfies $U_{\text{CP},1}(k, n; \delta) \le \alpha \iff \sum_{j=0}^k \binom{n}{j} \alpha^j (1-\alpha)^{n-j} \le \delta$. For $k = 0$, $U_{\text{CP},1}(0, n; \delta) = 1 - \delta^{1/n}$.

- **Six Mandatory Distinctions & Exact Recalculated Values (`[VERIFIED]`, `[AUDIT-DISCREPANCY]`):**

  | Estimand / Edge Case | Concrete Example from `benchmark_episodes.csv` | Integer Ratio $k / n$ | Point Est. | 2-Sided 95% Wilson | 2-Sided 95% Clopper–Pearson | 1-Sided 95% CP UCB ($\delta=0.05$) | Audit Note |
  | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
  | **1. Pooled selective risk** | `AEGIS_NEXT` pooled (`10` scenarios) | `6 / 257` | `2.335%` | `[1.074%, 4.999%]` | `[0.862%, 5.012%]` | `4.556%` | Valid CI *only* if policy was frozen before seeing seeds `60000..60049` (not true in V8). |
  | **1b. Pooled selective risk (V5)** | `AEGIS_V5` pooled (`10` scenarios) | `29 / 211` | `13.744%` | `[9.743%, 19.042%]` | `[9.402%, 19.139%]` | `18.264%` | `benchmark_reconciliation.md:54` prose wrote `[0.0969, 0.1912]` vs. exact `[0.0974, 0.1904]`. |
  | **2. Per-scenario selective risk** | `AEGIS_NEXT` in `INDEPENDENT_BIAS` | `4 / 32` | `12.500%` | `[4.968%, 28.067%]` | `[3.513%, 28.990%]` | `26.364%` | `benchmark_reconciliation.md` prose wrote `0.279` vs. exact `0.2807` Wilson upper. |
  | **2b. Per-scenario selective risk** | `AEGIS_NEXT` in `COMPOUND_HOLDOUT_EXTREME` | `2 / 3` | `66.667%` | `[20.766%, 93.851%]` | `[9.430%, 99.160%]` | `98.305%` | Extreme small-denominator compound-fault failure. |
  | **3. Unconditional FS incidence** | `AEGIS_NEXT` pooled (`10` scenarios) | `6 / 500` | `1.200%` | `[0.551%, 2.593%]` | `[0.442%, 2.594%]` | `2.355%` | Dilutes errors across `243` abstentions (`R_inc = C * R_sel`). |
  | **3b. Unconditional FS incidence** | `AEGIS_NEXT` in `COMPOUND_HOLDOUT_EXTREME` | `2 / 50` | `4.000%` | `[1.104%, 13.460%]` | `[0.488%, 13.714%]` | `12.060%` | `R_inc = 4.0% <= 5%` point estimate hides `R_sel = 66.7%`! |
  | **4. Zero observed errors (moderate $m$)** | `AEGIS_NEXT` in `NOMINAL` | `0 / 50` | `0.000%` | `[0.000%, 7.135%]` | `[0.000%, 7.112%]` | `5.816%` | Even `0/50` errors cannot certify `<= 5.0%` at 95% confidence (`m >= 59` required)! |
  | **4b. Zero observed errors (low $m$)** | `EKF_CONSIST` pooled / `AEGIS_NEXT` in `CORRUPTED_ANCHOR` | `0 / 15` / `0 / 1` | `0.000%` | `[0.0%, 20.39%]` / `[0.0%, 79.35%]` | `[0.0%, 21.80%]` / `[0.0%, 97.50%]` | `18.104%` / `95.000%` | Zero empirical errors at tiny coverage provides virtually no safety assurance. |
  | **5. Zero accepted decisions ($m=0$)** | `AEGIS_NEXT` in `FAULTY_REFERENCE_SENSOR` (+`18` other cells) | `0 / 0` | **`UNDEFINED`** | **`UNDEFINED`** | **`UNDEFINED`** | **`UNDEFINED`** | `benchmark_next.py:48,342` logged `0.0` (`[AUDIT-DISCREPANCY]`). Note `R_inc = 0/50` (`UCB95 = 5.816%`) IS defined, whereas `R_sel` is NOT. |

  > **Critical Non-Universality Caveat on `m = 59` (`[VERIFIED]`):** Observing $m \ge 59$ accepted decisions is **NOT** a universal 5% risk-certification guarantee. It is merely the minimum denominator needed *when $k = 0$ errors are observed, for a single prespecified hypothesis at unadjusted one-sided $\delta = 0.05$, under exact i.i.d. episode sampling*. Any positive error count ($k = 1 \implies m \ge 93$; $k = 2 \implies m \ge 124$; $k = 6 \implies m \ge 234$), unordered candidate selection (Holm step-1 across $J = 6 \implies m \ge 94$ at $k = 0$), simultaneous multi-scenario certification ($S = 12$ Šidák/Holm $\implies m_s \ge 107$ per scenario at $k_s = 0$), or post-hoc threshold tuning strictly increases the required sample size or invalidates the bound altogether.

---

### F. LTT Reference, Conformal Risk Control Distinctions, and Selective-Risk Nuance

- **Source Files & Line Numbers:**
  - `docs/v8_audit/related_work_update.md:52` (erroneous LTT citation).
  - `docs/v8_audit/v9_research_recommendations.md` (conflation of LTT and CRC for selective risk).

- **Bibliographic Audit Finding (`[AUDIT-DISCREPANCY]`, `[VERIFIED]`):**
  Line `52` of `docs/v8_audit/related_work_update.md` cited:
  > *Angelopoulos, A. N., Bates, S., Candès, E. J., Jordan, M. I., & Malik, J. (2024). Learn Then Test: Calibrating Predictive Algorithms to Achieve Risk Control. Journal of the Royal Statistical Society Series B, 86(2), 345-372. https://doi.org/10.1093/jrsssb/qkae002*

  Independent verification confirms that **this journal venue, volume/pages, co-author (`Jitendra Malik` belongs to RCPS 2021, whereas LTT's fifth author is `Lihua Lei`), year, and DOI are inaccurate/non-existent**. Because `docs/v8_audit/` is frozen historical evidence, the authoritative bibliographic record and theorem comparison are established here for V9:

- **Verified Primary Bibliography & Exact Theorem Assumptions (`[VERIFIED]`):**

  1. **Learn Then Test (LTT — Primary Framework for Finite Policy-Family Calibration):**
     - **Citation:** Anastasios N. Angelopoulos, Stephen Bates, Emmanuel J. Candès, Michael I. Jordan, and Lihua Lei (2025). *Learn then Test: Calibrating Predictive Algorithms to Achieve Risk Control*. **The Annals of Applied Statistics**, Vol. 19, No. 2, pp. 1641–1662, June 2025. DOI: `https://doi.org/10.1214/24-AOAS1998` (preprint: `https://arxiv.org/abs/2110.01052`).
     - **Supported Claim & Assumptions:** Given a finite predeclared hyperparameter grid $\Lambda = \{\lambda^{(1)}, \dots, \lambda^{(J)}\}$ and an i.i.d. calibration dataset $\mathcal{D}_{\text{cal}}$ independent of policy design, if each null hypothesis $H_{0,j} : R(\lambda^{(j)}) > \alpha$ is tested using a finite-sample super-uniform p-value ($\mathbb{P}_{H_{0,j}}(p_j \le u) \le u$ for all $u \in [0,1]$) and a familywise error rate (FWER)-controlling procedure at level $\delta$ (such as Fixed-Sequence Testing or Holm's step-down procedure, valid under arbitrary p-value dependence), then every returned configuration $\hat{\lambda} \in \hat{\Lambda}$ satisfies $\mathbb{P}_{\mathcal{D}_{\text{cal}}}\big(\sup_{\lambda \in \hat{\Lambda}} R(\lambda) \le \alpha\big) \ge 1 - \delta$ (with the convention $\sup \emptyset = -\infty$, i.e., abstaining from certifying any policy if $\hat{\Lambda} = \emptyset$). Critically, **LTT does NOT require monotone losses**, provided a valid super-uniform p-value is constructed for the exact target risk $R(\lambda)$.

  2. **Conformal Risk Control (CRC — Marginal Monotone Loss Control, NOT Conditional Selective Risk):**
     - **Citation:** Anastasios N. Angelopoulos, Stephen Bates, Adam Fisch, Lihua Lei, and Tal Schuster (2024). *Conformal Risk Control*. **Proceedings of the Twelfth International Conference on Learning Representations (ICLR 2024)**. Stable URL: `https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html` (preprint: `https://arxiv.org/abs/2208.02814`).
     - **Supported Claim & Why It Does NOT Directly Certify V9 Selective Risk:** Under exchangeability of $\{(X_i, Y_i)\}_{i=1}^{n+1}$ and a bounded loss $L_i(\lambda) \in (-\infty, B]$ that is **pointwise non-increasing (monotone) in $\lambda$** on every sample, CRC selects $\hat{\lambda}$ to guarantee **marginal expectation control** $\mathbb{E}[L_{n+1}(\hat{\lambda})] \le \alpha$ over the joint draw of calibration and test data. It fails two V9 requirements: (i) it provides an expectation bound rather than a $(1-\delta)$ high-probability calibration certificate $\mathbb{P}_{\text{cal}}(R(\hat{\lambda}) \le \alpha) \ge 1 - \delta$; and (ii) selective risk $R_{\text{sel}}(\lambda) = \frac{\mathbb{E}[FS(\lambda)]}{\mathbb{E}[A(\lambda)]}$ is a **ratio of expectations** (a conditional expectation given $A(\lambda)=1$, not an unconditional samplewise loss) and **need not be monotone in conservatism $\lambda$** if tightening a gate rejects easy true-success episodes faster than borderline compound-fault episodes!

  3. **Non-Exchangeable Conformal Risk Control (Distribution-Shift Extension of CRC):**
     - **Citation:** António Farinhas, Chrysoula Zerva, Dennis Ulmer, and André F. T. Martins (2024). *Non-Exchangeable Conformal Risk Control*. **Proceedings of the Twelfth International Conference on Learning Representations (ICLR 2024)**. Stable URL: `https://proceedings.iclr.cc/paper_files/paper/2024/hash/de04896f011beff76c91e094f72727f4-Abstract-Conference.html` (preprint: `https://arxiv.org/abs/2310.01262`).
     - **Supported Claim & Assumptions:** Extends CRC to non-exchangeable sequences using fixed weights $w_i \in [0, 1]$, yielding $\mathbb{E}[L_{n+1}(\hat{\lambda})] \le \alpha + B \sum_{i=1}^n \tilde{w}_i \,\mathrm{d}_{\mathrm{TV}}(Z_{n+1}, Z_i)$ for monotone bounded losses. Because $\mathrm{d}_{\mathrm{TV}}$ is unobservable without knowing the shift magnitude and the estimand remains marginal unconditional loss rather than conditional selective risk, it cannot be invoked to claim a $5\%$ selective-risk bound without explicit shift-bound assumptions.

  4. **Risk-Controlling Prediction Sets (RCPS):**
     - **Citation:** Stephen Bates, Anastasios N. Angelopoulos, Lihua Lei, Jitendra Malik, and Michael I. Jordan (2021). *Distribution-Free, Risk-Controlling Prediction Sets*. **Journal of the ACM**, Vol. 68, No. 6, Article 43, pp. 1–34. DOI: `https://doi.org/10.1145/3478535`.
     - **Supported Claim & Assumptions:** Establishes $(1-\delta)$ high-probability upper confidence bounds for **monotone** nested risks via one-sided concentration/exact binomial inversion.

  5. **Selective Classification Conditional Binomial Risk Bound:**
     - **Citation:** Yonatan Geifman and Ran El-Yaniv (2017). *Selective Classification for Deep Neural Networks*. **Advances in Neural Information Processing Systems (NeurIPS)**, Vol. 30, pp. 4878–4887. Stable URL: `https://proceedings.neurips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract-Conference.html` (preprint: `https://arxiv.org/abs/1705.08500`).
     - **Supported Claim & Assumptions:** Shows that conditional on the realized accepted count $M = m \ge 1$ of an i.i.d. sample under a fixed selective classifier, the number of selective errors follows $\mathrm{Binomial}(m, R_{\text{sel}})$, enabling exact one-sided binomial upper confidence bounds conditional on $M = m > 0$ (which, as proved formally in `docs/v9_risk_calibration_design.md`, combines with LTT once zero-coverage policies $C(\lambda)=0$ are included in the null hypothesis via a minimum-acceptance guard $M \ge m_{\min} \ge 1$).

  6. **Multiple Testing with Correlated e-Values (Optional Diagnostic Reference):**
     - **Citation:** Ruodu Wang and Aaditya Ramdas (2022). *False discovery rate control with e-values*. **Journal of the Royal Statistical Society: Series B (Statistical Methodology)**, Vol. 84, No. 3, pp. 822–852. DOI: `https://doi.org/10.1111/rssb.12489`.
     - **Supported Claim & Relevance:** Establishes the e-BH procedure controlling **FDR** (not FWER) under arbitrary dependence among e-values. Note: Policy certification requires **FWER** control (so the single chosen policy $\hat{\lambda}$ is safe with probability $\ge 1-\delta$), for which Fixed-Sequence Testing and Holm's procedure on exact binomial p-values are directly valid under arbitrary matched-seed dependence without needing FDR approximations.

---

## 3. Summary of Approved V9 Architectural & Statistical Decisions (`[APPROVED-DECISION]`)

1. **Decision 1 — Parallel Hybrid Monitoring (`Discrepancy A`):** Pair **Channel A** (exact $\gamma = 1.0$, unfloored, uncapped Ville e-process with concave upper clipping testing explicit nominal bounded-mean null $H_{0,\mathrm{mon}}$) with **Channel B** (complementary CUSUM/Shiryaev–Roberts-type drift detector for slow/late-onset faults, explicitly *not* described as Ville-anytime-valid). Include both channel thresholds and combination logic inside the frozen candidate family $\Lambda$, and strictly separate (i) nominal monitor false-alarm control, (ii) fault detection delay/power, and (iii) closed-loop policy selective false-success risk $R_{\mathrm{sel}}$.
2. **Decision 2 — Per-Sensor Bias Calibration & Data-Flow Validation Isolation (`Discrepancy B`):** Estimate `vec_a` ($\hat{\mathbf{b}}_a$) and `vec_b` ($\hat{\mathbf{b}}_b$) separately during `ACTIVE_PROBING` rather than fitting one shared fused bias; preserve explicit inter-sensor disagreement; reject invalid/dropout samples before buffer insertion; enforce disjoint fitting ($\mathcal{I}_{\mathrm{fit}}$), transition gap ($\mathcal{I}_{\mathrm{gap}}$), and validation ($\mathcal{I}_{\mathrm{val}}$) windows with no continuous online refitting during `CALIBRATED` mode; and fix the `NOMINAL` $\to$ `ACTIVE_PROBING` fall-through bug (`agent_next.py:188-205`) and invalid-range arrival bypass (`lines 203, 296`).
3. **Decision 3 — Fail-Closed Anchor/Range Disagreement Gate (`Discrepancy B`):** Treat V8's `0.35 m` anchor-range threshold as an unvalidated inherited candidate rather than a safety limit; parameterize normalized anchor-range tolerance $\tau_{ar}^{(j)}$ inside $\Lambda$; default to `"ABSTAIN"` whenever anchor and range disagree unless fixed, pre-holdout, drift-verified multi-step vector-displacement chord evidence ($\Delta \mathbf{z}_{k, t_1 \to t_2}$) independently corroborates one modality without common-mode vulnerability; never treat range or anchor as an infallible oracle.
4. **Decision 4 — Strict Four-Input Sensor-Interface Parity & Statistical Governance (`Discrepancies C, D, E, F`):** Preserve the exact runtime interface `(reading_a, reading_b, range_reading, anchor_reading)` with zero new mandatory wheel/encoder/IMU sensors; derive all temporal consistency features solely from valid histories of those four inputs and past controller commands; represent $M = 0$ selective risk strictly as `UNDEFINED`; pair all hypothesis tests on `(scenario, seed)`; and certify selective risk via exact conditional-binomial LTT on $\mathcal{D}_{\text{cal}}$ (`seeds 71000..71959`) followed by locked single-policy evaluation on $\mathcal{D}_{\text{test}}$ (`seeds 73000..74439`, `75000..75119`).
