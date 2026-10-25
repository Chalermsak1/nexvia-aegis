# NEXVIA AEGIS V9-M3 — Independent Operational Validation Protocol

**Milestone:** V9-M3 (Operational Validation of Frozen Calibrated Policy)  
**Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`  
**Branch:** `v9.0-runtime-assurance`  
**Protocol Version:** `v9.0-preregistered-2026-10-amendment-r2-val`  
**Source Commit:** `150629aba9059fe627ca395d49489f139fb017db`  
**Selected Policy Artifact:** `results/v9/cal_r2/selected_policy.json`  
**Selected Candidate:** `V9_CAND_1_TIER1_STRICTEST`  
**Validation Partition:** $\mathcal{D}_{\mathrm{val}}$ (`seeds 72000..72039`, $N=480$ episodes)  
**Validation Manifest:** `results/v9/manifests/val_manifest_r1.json`  
**Output Directory:** `results/v9/val_r1/`

---

## 1. Executive Summary & Objective

Following the authorized single-shot calibration execution in **Milestone V9-M2R2**, which certified the V9 candidate family under Fixed-Sequence Learn-Then-Test ($p_{\mathrm{sel}} = 9.72 \times 10^{-12} \le 0.05$, $M_{\mathrm{cal}} = 561 \ge 336$) and selected **`V9_CAND_1_TIER1_STRICTEST`**, this protocol establishes the requirements, sampling design, outcome algebra, and execution guardrails for **Milestone V9-M3: Independent Operational Validation**.

### 1.1 Non-Negotiable Operational Boundaries
1. **Validation is NOT Calibration:** The selected policy $\hat{\pi} =$ `V9_CAND_1_TIER1_STRICTEST` is strictly **frozen**. No candidate selection, parameter re-tuning, threshold adjustments, offline bias re-fitting, or feature alterations are permitted on $\mathcal{D}_{\mathrm{val}}$.
2. **Single Policy Execution:** Only `V9_CAND_1_TIER1_STRICTEST` is evaluated. The runner will refuse execution if configured for any other candidate or multi-candidate search.
3. **Partition Isolation & Single-Shot Execution:** Validation outcomes are written exclusively to `results/v9/val_r1/`. The single-shot guard blocks re-execution if outputs already exist.
4. **Holdout Partition Protection:** The reserved holdout partitions ($\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ `73000..74439` and $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ `75000..75119`) remain strictly ungenerated, unexecuted, and uninspected.

---

## 2. Calibration Provenance Audit Findings

Prior to opening the reserved validation partition $\mathcal{D}_{\mathrm{val}}$, an exhaustive read-only audit of the completed V9-M2R2 calibration was conducted:

| Artifact | Recorded SHA-256 | Verified Disk SHA-256 | Status |
| :--- | :--- | :--- | :--- |
| `configs/v9_candidates_frozen_r1.json` | `346f95929f244b4e...` | `346f95929f244b4e...` | **EXACT MATCH** |
| `results/v9/manifests/cal_manifest_r2.json` | `49bf68b60f7dd762...` | `49bf68b60f7dd762...` | **EXACT MATCH** |
| `results/v9/cal_r2/calibration_run_config_frozen_r2.json` | `1a19f6b4c2942172...` | `1a19f6b4c2942172...` | **EXACT MATCH** |
| `results/v9/cal_r2/cal_episodes.csv` | `f3e153fbc0f919ce...` | `f3e153fbc0f919ce...` | **EXACT MATCH** |
| `results/v9/cal_r2/cal_candidate_summary.csv` | `c37f673d0751e184...` | `c37f673d0751e184...` | **EXACT MATCH** |
| `results/v9/cal_r2/cal_scenario_breakdown_diagnostic.csv` | `264c68620e2b7be1...` | `264c68620e2b7be1...` | **EXACT MATCH** |
| `results/v9/cal_r2/selected_policy.json` | `5a89d6061b379f1b...` | `5a89d6061b379f1b...` | **EXACT MATCH** |
| `results/v9/cal_r2/calibration_report.json` (Canonical) | `016990be14b2e751...` | `016990be14b2e751...` | **EXACT MATCH** |

**Audit Conclusion:** The calibration runner modifications in `experiments/v9_calibrate_ltt.py` were strictly confined to execution authorization, output directory isolation, and decoupled PRNG wiring via `instantiate_episode_rngs_from_manifest_item`. Algorithmic simulation, sensor models, candidate parameters, outcome definitions, and statistical calculations were verified bit-for-bit unchanged. Provenance is fully established.

---

## 3. Validation Sampling Design ($\mathcal{D}_{\mathrm{val}}$)

### 3.1 Design Specification
In adherence to `docs/v9_experiment_protocol.md` Section 3.6.1 item 4 and `docs/v9_risk_calibration_design.md` Table 4.1:
- **Partition:** $\mathcal{D}_{\mathrm{val}}$
- **Seed Block:** `72000 .. 72039` ($40$ seeds)
- **Scenario Suite:** $\mathcal{S}_{12} = \mathcal{S}_{10} \cup \mathcal{S}_{\mathrm{ext}}$ ($12$ scenarios)
- **Allocation Rule:** Deterministic stratified grid:
  $$\mathcal{D}_{\mathrm{val}} = \{(s, \text{seed}) \mid s \in \mathcal{S}_{12}, \; \text{seed} \in [72000, 72040)\}$$
- **Total Episodes:** $12 \text{ scenarios} \times 40 \text{ seeds/scenario} = 480 \text{ episodes}$.

### 3.2 Partition-Branched RNG Derivation (Amendment R2)
Under the partition-branching architecture defined in `docs/v9_m2r2_protocol_amendment.md`:
- **Root Partition Index:** $p = \text{PARTITION\_BRANCH\_VALIDATION} = 3$
- **Master Entropy:** $20261025$
- **Partition SeedSequence:**
  $$\text{ss}_{\text{val}} = \text{SeedSequence}(20261025, \text{spawn\_key}=(3,))$$
- **Branch Derivation:**
  $$\text{branch\_scen\_ss}, \text{branch\_eps\_ss} = \text{ss}_{\text{val}}.\text{spawn}(2)$$
- **Episode Stream Derivation:**
  $$\text{ep\_ss}_i = \text{branch\_eps\_ss}.\text{spawn}(480)[i] \implies \text{spawn\_key} = (3, 1, i)$$
- **Decoupled Physical / Sensor Streams:**
  $$\text{env\_ss}_i = \text{ep\_ss}_i.\text{spawn}(2)[0] \implies \text{env\_spawn\_key} = (3, 1, i, 0)$$
  $$\text{sens\_ss}_i = \text{ep\_ss}_i.\text{spawn}(2)[1] \implies \text{sensor\_spawn\_key} = (3, 1, i, 1)$$

Because the root key is prefixed with $p = 3$, validation streams use distinct hierarchical spawn paths $(3, 1, i, \cdot)$ under NumPy's `SeedSequence`. Under NumPy's PCG64/SplitMix64 model, distinct spawn keys produce pseudo-random streams designed to be independent and non-overlapping with negligible collision probability ($\approx K^2 / 2^{129} < 10^{-30}$), ensuring stream separation across development ($p=1$), calibration ($p=2$), holdouts ($p=4, 5$), and test fixtures ($p=6$).

---

## 4. Outcome Definitions and Estimands

### 4.1 Episode Terminal Outcomes
For each episode $i \in \{0, \dots, 479\}$:
- **Terminal Acceptance:** $A_i = 1$ if the robot executes clean terminal `"STOP"` and does not crash; $A_i = 0$ otherwise.
- **True Success ($TS$):** $TS_i = 1$ iff $A_i = 1$ and final true Euclidean distance $d_i \le 0.45\text{ m}$.
- **False Success ($FS$):** $FS_i = 1$ iff ($A_i = 1$ and $d_i > 0.45\text{ m}$) OR $\text{crashed}_i = 1$ (fail-unsafe accounting).
- **Explicit Abstention ($AB_{\mathrm{exp}}$):** $AB_i = 1$ iff controller returns `"ABSTAIN"` and did not execute `"STOP"`.
- **Horizon Timeout ($TO$):** $TO_i = 1$ iff controller never returned `"STOP"` or `"ABSTAIN"` within $T_{\max} = 300$ steps.
- **Fail-Unsafe Crash ($CRASH$):** If an uncaught exception occurs during simulation, $A_i = 0$, $TS_i = 0$, $FS_i = 1$, $\text{crashed}_i = 1$.

### 4.2 Estimands & Statistical Interpretation
Because $\mathcal{D}_{\mathrm{val}}$ employs a stratified design with equal fixed quotas ($n_s = 40$ per scenario), pooled metrics represent stratified sample proportions:
1. **Empirical Coverage:** $\hat{C} = \frac{M}{N} = \frac{\sum_{i=1}^{480} A_i}{480}$.
2. **Empirical True-Success Rate:** $\widehat{TSR} = \frac{\sum_{i=1}^{480} TS_i}{480}$.
3. **Empirical Unconditional False-Success Incidence:** $\hat{R}_{\mathrm{inc}} = \frac{\sum_{i=1}^{480} FS_i}{480}$.
4. **Empirical Selective False-Success Risk:**
   $$\hat{R}_{\mathrm{sel}} = \begin{cases} \frac{\sum_{i=1}^{480} FS_i}{M}, & \text{if } M > 0 \\ \text{UNDEFINED}, & \text{if } M = 0 \end{cases}$$

**Statistical Caution:**
Pooled exact Clopper–Pearson intervals assume unstratified binomial mixture sampling. For $\mathcal{D}_{\mathrm{val}}$, pooled intervals are reported descriptively as stratified estimates. Per-scenario binomial confidence bounds (conditional on scenario $s$) are calculated with exact Clopper–Pearson bounds. Validation results are confirmatory operational evidence, not a replacement for independent holdout evaluation.

---

## 5. Artifact Directory & File Inventory

The validation outputs will be recorded in `results/v9/val_r1/`:
- `val_episodes.csv`: Raw episode-level records across all 480 episodes.
- `val_summary.csv`: Pooled summary metrics for `V9_CAND_1_TIER1_STRICTEST`.
- `val_scenario_breakdown.csv`: Per-scenario metrics across all 12 scenarios.
- `validation_run_config_frozen_r1.json`: Frozen run configuration with SHA-256 hashes.
- `validation_report.json`: Comprehensive validation report with cryptographic digests.
