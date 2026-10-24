# NEXVIA AEGIS V9-M2R1 Protocol Amendment: RNG Stream Decoupling & Initial-State Fail-Closed Verification

**Amendment Identifier:** `docs/v9_m2r1_protocol_amendment.md`  
**Protocol Version:** `v9.0-preregistered-2026-10-amendment-r1`  
**Design Commit Reference:** `891c13e7bbd60e36c416c9bada8407e51233e663`  
**V9-M1 Implementation Commit Reference:** `6c87f66a9ea602c96d4fe8bfc97728d0513b157f`  
**V8.1 Audited Baseline Commit Reference:** `4d891c7500cfb4c8110f276038455bc62765ef3b`  
**Date:** October 2026  
**Status:** PREREGISTERED PROTOCOL AMENDMENT (Committed prior to new development evaluation and calibration generation)  

---

## 1. Executive Summary & Rationale for Amendment

During the review of the V9-M2 calibration artifacts, two structural defects were identified that prevent the completed V9-M2 calibration from supporting the intended Learn-Then-Test (LTT) finite-sample risk certification without substantial qualification:

1. **Environment and Sensor RNG Stream Reuse:** In `run_single_episode` within `experiments/v9_evaluate_dev.py` and `experiments/v9_calibrate_ltt.py`, both `rng_env` (responsible for target position sampling during `world.reset`) and `rng_ep` (responsible for per-step sensor noise, dropout, and outlier sampling) were initialized with the identical integer seed `ep_seed`. Consequently, the first two pseudo-random draws determining target coordinates in `rng_env` were derived from the identical initial PCG64 state as the step-zero sensor noise variates in `rng_ep`. This cross-stream coupling violates strict statistical independence between environment configuration and measurement error.
2. **Step-Zero Fail-Open Arrival Defect:** In `AegisV9Controller.update` ([`src/aegis/v9/controller.py:658-743`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/controller.py#L658-L743)), if instantaneous fused vector norm satisfied $\le \tau_{\mathrm{arr}}$ (`0.22 m`) and range reading satisfied $\le \tau_{\mathrm{stop}}$ (`0.35 m`) at `step == 0`, the controller immediately executed `STOP` with reason `NOMINAL_VERIFIED_ARRIVAL` without requiring temporal observation, dynamic motion consistency, or independent auxiliary corroboration. In episode seed `71717` of `COMPOUND_HOLDOUT_EXTREME`, common-mode vector bias $(+0.5, +0.5)$ and range corruption $-0.40\text{ m}$ artificially aligned with a target at true distance $0.5683\text{ m}$, causing a false success on step zero across all six candidates.

In accordance with scientific integrity and preregistration principles:
- The historical V9-M2 calibration artifacts and seed `71717` false success remain preserved on disk as immutable historical records.
- The original calibration seeds `71000..71959` are **retired** and will not be reused for certification.
- This amendment formally specifies the corrected randomization architecture, the corrected fail-closed initial-state decision logic, and the fresh, non-overlapping manifest identifiers for development and single-shot calibration.

---

## 2. Forensic Analysis of Discovered Defects

### 2.1 Defect 1: Pseudo-Random Number Generator Coupling
In the V9-M1 simulation harness:
```python
# Historical code in v9_evaluate_dev.py:253, 275:
rng_env = np.random.default_rng(ep_seed)
world.reset(rng_env)
...
rng_ep = np.random.default_rng(ep_seed)
read_a = sensor_a.measure(true_delta, rng_ep, step=st["step"])
```
- **Mechanism:** In NumPy's PCG64 implementation, `default_rng(ep_seed)` instantiates a bit generator starting at step 0 of sequence stream `ep_seed`. Re-instantiating `default_rng(ep_seed)` for `rng_ep` resets the generator to the identical initial internal state.
- **Consequence:** In `world.reset()`, two uniform draws $u_1, u_2 \sim \mathcal{U}(-3, 3)$ set `target_pos`. In `sensor_a.measure()`, the first normal variates $\varepsilon_{a,x}, \varepsilon_{a,y} \sim \mathcal{N}(0, \sigma^2)$ are transformed from the identical underlying bit sequence. Target location and initial sensor error are therefore deterministically correlated, violating the assumption that sensor noise is conditionally independent of true state.
- **Deterministic Seed Sequence Limitation:** A simple grid of consecutive integers `71000..71959` without an explicit hierarchical seed sequence does not mathematically establish independent stochastic realizations across episodes.

### 2.2 Defect 2: Initial-State False-Acceptance (Seed 71717 Reproduction)
- **Historical Evidence:** In `results/v9/cal/cal_episodes.csv` row 717, seed `71717` recorded:
  ```csv
  717,71717,9,COMPOUND_HOLDOUT_EXTREME,S_10,1,V9_CAND_1_TIER1_STRICTEST,1,0,1,0,0,0,0,,0.5683,0,0.1465,0.0,0,0.0,0.0,NOMINAL_VERIFIED_ARRIVAL
  ```
- **Physics of the Failure:**
  - True robot position: $(-2.0, -2.0)$.
  - True target position sampled by `rng_env(71717)`: $(-2.4287, -2.3730)$.
  - True relative delta: $\mathbf{d}_0 = (-0.4287, -0.3730)\text{ m}$; true distance: $\|\mathbf{d}_0\| = 0.5683\text{ m} > 0.45\text{ m}$.
  - Scenario `COMPOUND_HOLDOUT_EXTREME` injects common-mode bias $\mathbf{b} = (+0.5, +0.5)$ and range bias $b_r = -0.40\text{ m}$.
  - Measured relative vectors: $\mathbf{z}_{a,0} \approx \mathbf{d}_0 + \mathbf{b} = (+0.0713, +0.1270)\text{ m}$ ($\|\mathbf{z}_{a,0}\| \approx 0.15\text{ m}$).
  - Measured range: $r_0 \approx 0.5683 - 0.40 + \text{noise} \approx 0.0414\text{ m}$.
  - Because `steps == 0`, Ville wealth was at initial value $1.0$ and CUSUM score was $0.0$.
  - Because both vector sensors suffered identical bias, inter-sensor disagreement $\delta_{ab} \approx 0.04\text{ m}$ did not trip instantaneous discrepancy.
  - The controller checked `nav_dist <= 0.22 m` and `r_dist <= 0.35 m`. Both conditions held instantaneously.
  - The controller committed `STOP` on step 0 without moving or querying an anchor, terminating in false success ($d = 0.5683\text{ m}$).

---

## 3. Corrected Architecture & Decision Logic

### 3.1 Randomization Model: Master SeedSequence & Independent Child Streams

To ensure mathematical independence between environment state and measurement noise, the randomization architecture is redesigned using `numpy.random.SeedSequence`:

1. **Master Entropy:** A master `SeedSequence(entropy=20261025)` governs the generation of the partition manifest.
2. **Hierarchical Spawning:** For each episode $i \in \{0, \dots, N-1\}$ in the manifest, the master sequence spawns a dedicated episode `SeedSequence`:
   ```python
   episode_ss = master_ss.spawn(N)[i]
   ```
3. **Decoupled Child Streams:** Each episode sequence spawns two distinct, non-overlapping child generators:
   ```python
   env_ss, sensor_ss = episode_ss.spawn(2)
   rng_env = np.random.default_rng(env_ss)       # Strictly for world.reset() and target generation
   rng_sensors = np.random.default_rng(sensor_ss) # Strictly for sensor noise, dropout, and outliers
   ```
4. **Joint Scenario Sampling:** Scenario indices $s_i \in \{0, \dots, 11\}$ are sampled from a dedicated manifest RNG stream spawned from the master sequence, ensuring exact uniform mixture sampling $P(S_k) = 1/12$.
5. **State Isolation:** Controller instance is completely re-instantiated or reset via `reset()` between episodes, ensuring no residual filter memory carries over.

### 3.2 Decision Rule: Initial-State Fail-Closed Verification Gate

A new decision rule is implemented in `AegisV9Controller.update` governing initial steps ($t < t_{\mathrm{temporal\_min}} = 3$ steps):

1. **Prohibition of Step-Zero Uncorroborated STOP:** Under no circumstances may `STOP` be returned at $t=0$ based solely on primary vector sensors and range reading.
2. **Sufficient Temporal Evidence Requirement:** At least $t \ge 3$ consecutive steps of dynamic motion and residual tracking are required before the nominal arrival condition (`nav_dist <= arrival_tolerance` and `r_dist <= tau_stop`) may commit `STOP`.
3. **Genuine Initial-at-Goal Handling via Independent Corroboration:**
   - If $t=0$ and apparent arrival is detected ($\|\mathbf{z}_{\mathrm{fused}}\| \le \tau_{\mathrm{arr}}$ and $r \le \tau_{\mathrm{stop}}$):
     - The controller **must not** return `STOP`.
     - The controller returns action $\mathbf{u} = \mathbf{0}$, decision `"VERIFY"`, and flags `query_anchor = True`.
   - At step $t=1$, when the independent third-modality anchor measurement $\mathbf{z}_{\mathrm{anc}}$ is received:
     - The anchor reading is evaluated by the Anchor Integrity Gate.
     - If the anchor independently corroborates that $\|\mathbf{z}_{\mathrm{anc}}\| \le \tau_{\mathrm{arr}}$ AND agrees with the range reading within $\tau_{ar}$ AND agrees with the vector reading within $\tau_{ar}$:
       - The genuine initial-at-goal state is verified. The controller may commit `STOP` with terminal reason `"CORROBORATED_INITIAL_GOAL_ARRIVAL"`.
     - If the anchor disagrees ($\|\mathbf{z}_{\mathrm{anc}}\| > \tau_{\mathrm{arr}}$ or anchor gate rejects consistency):
       - The apparent arrival was an illusion created by common-mode bias.
       - The controller immediately transitions to `"ACTIVE_PROBING"` (or fails closed to `"ABSTAIN"` if anchor/range corruption is confirmed).
4. **Fail-Closed Default:** If anchor queries are exhausted or unavailable and temporal evidence remains insufficient, the controller returns `"PROBE"` or `"ABSTAIN"`, never `"STOP"`.

---

## 4. Manifest Partition Re-allocation & Disjointness Proof

All seed and manifest identifiers are updated to guarantee complete disjointness from all historical and reserved partitions:

| Partition Role | Partition Code | Identifier Range | Count ($N$) | Sampling Law | Status in V9-M2R1 |
|---|---|---|---|---|---|
| **Historical V8 Benchmark** | $\mathcal{D}_{\mathrm{hist}}$ | `60000..60049` | 500 | Historical matched seeds | Preserved (Immutable) |
| **Historical V9 Dev** | $\mathcal{D}_{\mathrm{dev,old}}$ | `70000..70029` | 360 | Historical grid | Preserved (Immutable) |
| **Historical V9 Cal (Retired)** | $\mathcal{D}_{\mathrm{cal,old}}$ | `71000..71959` | 960 | Retired cal manifest | Preserved (Immutable) |
| **Pre-Holdout Validation** | $\mathcal{D}_{\mathrm{val}}$ | `72000..72039` | 480 | Reserved grid | **RESERVED (Untouched)** |
| **Final Holdout — Mixture** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ | `73000..74439` | 1,440 | Reserved mixture | **RESERVED (Untouched)** |
| **Final Holdout — Scenario** | $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ | `75000..75119` | 1,440 | Reserved stratified grid | **RESERVED (Untouched)** |
| **Fresh V9-M2R1 Calibration** | $\mathcal{D}_{\mathrm{cal,r1}}$ | **`76000..76959`** | **960** | **Master SeedSequence Mixture** | **FRESH MANIFEST (Prepared, Unexecuted)** |
| **Fresh V9-M2R1 Development** | $\mathcal{D}_{\mathrm{dev,r1}}$ | **`77000..77029`** | **30** | **Master SeedSequence Mixture** | **ACTIVE DEVELOPMENT (To be evaluated)** |

### Disjointness Verification:
- $\max(\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}) = 75119 < 76000 = \min(\mathcal{D}_{\mathrm{cal,r1}})$.
- $\max(\mathcal{D}_{\mathrm{cal,r1}}) = 76959 < 77000 = \min(\mathcal{D}_{\mathrm{dev,r1}})$.
- No identifier in $\mathcal{D}_{\mathrm{cal,r1}}$ or $\mathcal{D}_{\mathrm{dev,r1}}$ overlaps with any historical or reserved split.

---

## 5. Statistical Assumptions & Certification Criteria in Force

The statistical framework approved in `docs/v9_risk_calibration_design.md` and `docs/v9_experiment_protocol.md` remains strictly in force under this amendment:

1. **Target Estimand:** Selective False-Success Risk:
   $$R_{\mathrm{sel}}(\pi; \mathcal{P}_{12}) = \mathbb{P}_{P_{12}}(d_{\mathrm{final}} > 0.45\text{ m} \mid \text{Decision} = \text{STOP}).$$
2. **Target Safety Bound:** $\alpha = 0.05$ at confidence level $1 - \delta = 0.95$.
3. **Statistical Procedure:** Fixed-Sequence Learn-Then-Test (LTT) testing composite null hypotheses:
   $$H_0^{\mathrm{sel}}(\lambda^{(j)}) : \{C(\pi_\lambda; \mathcal{P}_{12}) = 0\} \cup \{C(\pi_\lambda; \mathcal{P}_{12}) > 0 \text{ and } R_{\mathrm{sel}}(\pi_\lambda; \mathcal{P}_{12}) \ge \alpha\}.$$
4. **Conditional Binomial Test Statistic:**
   $$p_{\mathrm{sel}}(\lambda) = \begin{cases}
   1.0 & \text{if } M_{\mathrm{cal}}(\lambda) < m_{\mathrm{eff}} \\
   \sum_{k=0}^{K} \binom{M}{k} \alpha^k (1-\alpha)^{M-k} & \text{if } M_{\mathrm{cal}}(\lambda) \ge m_{\mathrm{eff}}
   \end{cases}$$
   where $m_{\mathrm{eff}} = \max(m_0, \lceil C_{\min} N \rceil) = \max(59, \lceil 0.35 \times 960 \rceil) = 336$.
5. **Fixed-Sequence Stopping Rule:** Test candidate index $j = 1, \dots, 6$ strictly in order at level $\delta = 0.05$. Stop at the first $j^*$ where $p_{\mathrm{sel}} > 0.05$. Select the policy within the certified prefix $\{1, \dots, j^*-1\}$ maximizing empirical True Success Rate.

---

## 6. Pre-Execution Verification Gate

Before fresh calibration (`D_cal,r1`) or holdout evaluation may be executed:
- [x] Protocol amendment committed.
- [ ] RNG decoupled child-stream implementation passes unit tests.
- [ ] Initial-state fail-closed gate passes regression tests (including forensic test on seed `71717`).
- [ ] Focused development evaluation (`D_dev,r1`, seeds `77000..77029`) executed and candidate family verified.
- [ ] Fresh candidate configuration frozen with canonical SHA-256 digest.
- [ ] Fresh calibration manifest (`76000..76959`) generated and verified without executing calibration episodes.
- [ ] Reserved partitions (`72000..75119`) confirmed untouched.
