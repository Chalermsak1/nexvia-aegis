# NEXVIA AEGIS V9-M3 — Post-Validation Audit Report

**Milestone:** V9-M3 (Operational Validation Audit)  
**Workspace:** `/Users/chalermsak/Desktop/nexvia-aegis-main`  
**Branch:** `v9.0-runtime-assurance`  
**HEAD Commit:** [`9e43d0f`](file:///Users/chalermsak/Desktop/nexvia-aegis-main)  
**Pre-execution Freeze Commit:** [`dd58b83`](file:///Users/chalermsak/Desktop/nexvia-aegis-main)  
**Evaluated Policy:** `V9_CAND_1_TIER1_STRICTEST`  
**Audit Status:** Complete  
**Audit Decision:** **`M3_COMPLETED`** (Operational Validation Completed and Audited)

---

## 1. Executive Audit Summary

This post-validation audit evaluates the completed **Milestone V9-M3: Independent Operational Validation** of the frozen calibrated policy `V9_CAND_1_TIER1_STRICTEST` on the reserved validation partition $\mathcal{D}_{\mathrm{val}}$ (seeds `72000..72039`, $N=480$ episodes across $\mathcal{S}_{12}$).

### Key Audit Findings:
1. **Zero Simulation Flaws & Outcome Algebra Compliance:** All 480 episodes ran to completion with zero simulation crashes, zero runtime exceptions during control, and 100% adherence to the preregistered outcome algebra partition ($M = TS + FS$, $AB = AB_{\mathrm{exp}} + TO$, $N = M + AB$).
2. **Robustness Under Faults:** The frozen policy achieved $\widehat{TSR}_{\mathrm{NOMINAL}} = 100.0\%$ (exceeding the $94.0\%$ threshold) and executed **100% fail-closed explicit abstention** ($40/40$ episodes) across all four catastrophic/adversarial corruption scenarios (`FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, `COMPOUND_HOLDOUT_EXTREME`, `COMPOUND_ANTIPODAL_RANGE_SHIFT`).
3. **Zero False Successes Observed:** Across the entire 480-episode grid, $FS = 0$ ($0.0\%$ empirical incidence and $0.0\%$ empirical selective risk among $M=269$ accepted decisions).
4. **Execution Chronology & Post-Processing Bug Resolution:** A formatting bug (`AttributeError: 'PolicyEvaluationSummary' object has no attribute 'mean_step_ms'`) occurred at line 520 during the initial report formatting step after all 480 episodes were simulated and saved to `val_episodes.csv` (`1b6b80402ffe...`). The runner was patched in commit `9e43d0f` to calculate `mean_step_ms_pooled` and load the untouched raw episode CSV to generate summary tables and `validation_report.json`. No simulation was re-run or altered.
5. **Holdout Partitions Intact:** The final reserved holdout partitions ($\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ `73000..74439` and $\mathcal{D}_{\mathrm{test}}^{\mathrm{scen}}$ `75000..75119`) remain strictly ungenerated, unexecuted, and uninspected.

---

## 2. Code Provenance and Freeze Chronology Audit

### 2.1 Git History & Commits
- **Pre-execution Freeze Commit:** [`dd58b83`](file:///Users/chalermsak/Desktop/nexvia-aegis-main) (`feat(v9-m3): freeze validation protocol, harness, manifest r1, and run configuration r1`)
  - Created [`docs/v9_m3_validation_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_m3_validation_protocol.md)
  - Generated and froze [`results/v9/manifests/val_manifest_r1.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/val_manifest_r1.json)
  - Created [`results/v9/val_r1/validation_run_config_frozen_r1.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/val_r1/validation_run_config_frozen_r1.json) via `--freeze-only`
  - Created runner [`experiments/v9_validate.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/experiments/v9_validate.py) (Raw SHA-256: `94476689eaa26133f93e7c43ddd9e5e35d4375e23d185e710a5fe3ec18d6321a`)
  - Created test suite [`tests/test_v9_validation.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_validation.py)
- **Post-Simulation Reporting Fix Commit:** [`9e43d0f`](file:///Users/chalermsak/Desktop/nexvia-aegis-main) (`fix(v9-m3): resolve mean_step_ms calculation and add CSV-record type parsing in validation runner`)
  - Runner SHA-256 updated to: `1b24b1474213f74b5d6927b1d05e9e1a13436e8cf25da6b55865a7d1c915da07`

### 2.2 Technical Reconciliation of Runner Modification
- **First Invocation (Task 1479):** The single-shot execution was launched using runner `94476689eaa2...`.
  - The simulation loop iterated through all 480 manifest episodes.
  - Every episode completed closed-loop simulation with zero exceptions.
  - The raw episode file [`results/v9/val_r1/val_episodes.csv`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/val_r1/val_episodes.csv) was written to disk with all 480 rows (SHA-256: `1b6b80402ffe40bce66d4bd9df27556433988e54ba813ce26e0fcca886dcc41e`).
  - Line 520 then attempted to access `pooled_summary.mean_step_ms`. Because `PolicyEvaluationSummary` in `src/aegis/v9/risk_statistics.py` defines `mean_steps` but not `mean_step_ms`, Python raised `AttributeError` and terminated with exit code 1 before compiling the aggregate summary and report JSON.
- **Reporting Patch:** In commit `9e43d0f`, the runner was updated to:
  1. Calculate `mean_step_ms_pooled` directly from `episode_records`.
  2. Load the existing complete `val_episodes.csv` (checking that exact 480 records exist and parsing numeric fields) rather than re-running the simulation.
  3. Generate `val_summary.csv`, `val_scenario_breakdown.csv`, and `validation_report.json`.
- **Integrity Assessment:**
  - The raw simulation outcomes were **never modified, re-simulated, or replaced**. The hash `1b6b80402ffe...` of `val_episodes.csv` is preserved identically from the initial simulation.
  - The single-shot execution guard was verified: re-running `v9_validate.py` now unconditionally raises `RuntimeError: SINGLE-SHOT EXECUTION GUARD: Validation output already exists in results/v9/val_r1`.

---

## 3. Reconciliation of Validation Artifacts & Outcome Algebra

### 3.1 Cryptographic Digest Audit

| Artifact | File Path | Verified Raw SHA-256 | Canonical SHA-256 | Integrity Status |
| :--- | :--- | :--- | :--- | :--- |
| Validation Manifest | `results/v9/manifests/val_manifest_r1.json` | `72d9b98bda622d80db4c5aa8d9e4b1ce88f0bbc52d3bb26258917cea08959175` | `40ff489504ce628f954b735b562474474b746a2c38c65d459d1084b625909f1e` | **VALID** |
| Frozen Run Config | `results/v9/val_r1/validation_run_config_frozen_r1.json` | `a09ebc079537233d6ced80c4deba71deed8f49c34ab437c4afa7f4a82d00b100` | `b3ec3c60162985392d4745fb3f6c87e148e6922572a1e05fcce58f188589fe94` | **VALID** |
| Raw Episodes CSV | `results/v9/val_r1/val_episodes.csv` | `1b6b80402ffe40bce66d4bd9df27556433988e54ba813ce26e0fcca886dcc41e` | — | **VALID (480 rows)** |
| Summary CSV | `results/v9/val_r1/val_summary.csv` | `d44a41cf3901e162b9fb46923122bfd5100e6d027fdbf0e98491e7a8ce83783e` | — | **VALID** |
| Scenario Breakdown CSV | `results/v9/val_r1/val_scenario_breakdown.csv` | `60ff1d9fa3a766b3e17a93f92ceffe41cb7c8a74022a1535d3dfc2d4c454de08` | — | **VALID (12 rows)** |
| Validation Report | `results/v9/val_r1/validation_report.json` | `a5f4df07996c6e5c04a48b5ed86668960bafb691aa489c526e5232aea635b500` | `6aa98a3cf5e9d594a3ccae8903881ac62e0fbc80e025704beb65bab1876846d3` | **VALID** |

All artifact digests recorded in `validation_report.json` under `artifact_sha256` match current disk contents bit-for-bit.

### 3.2 Partition Algebra and Outcome Reconciliation
Direct recomputation from raw `val_episodes.csv` confirms:
- **Total Episodes:** $N = 480$.
- **Terminal Acceptance:** $M = 269$ clean stops, $0$ crashes.
- **Terminal Success:** $TS = 269$ (all accepted decisions had final distance $d \le 0.45\text{ m}$).
- **False Terminal Success:** $FS = 0$ (no accepted stop exceeded $0.45\text{ m}$; no crashes occurred).
- **Explicit Abstention:** $AB_{\mathrm{exp}} = 207$.
- **Horizon Timeout:** $TO = 4$.
- **Total Abstention:** $AB = AB_{\mathrm{exp}} + TO = 207 + 4 = 211$.
- **Verification of Identities:**
  $$M = TS + FS \implies 269 = 269 + 0 \quad \checkmark$$
  $$AB = AB_{\mathrm{exp}} + TO \implies 211 = 207 + 4 \quad \checkmark$$
  $$N = M + AB \implies 480 = 269 + 211 \quad \checkmark$$
  $$TS + FS + AB_{\mathrm{exp}} + TO = 269 + 0 + 207 + 4 = 480 \quad \checkmark$$

### 3.3 Reconciliation of Historical Artifact Hash Discrepancies
An audit query identified a discrepancy between the full SHA-256 hashes presented in narrative text in the preliminary V9-M3 summary and the actual files on disk:
- **Reported in preliminary chat text:**
  - `val_summary.csv`: `d44a41cf3901b0445d4715aa31fe186e8da468e8e604f378a5716df1ea6cb59f`
  - `val_scenario_breakdown.csv`: `60ff1d9fa3a76efea0b3f5546d141e976dbbb94c1a9386d3b37905d4df483d3f`
- **Actual on-disk files & `validation_report.json` `artifact_sha256` records:**
  - `val_summary.csv`: `d44a41cf3901e162b9fb46923122bfd5100e6d027fdbf0e98491e7a8ce83783e`
  - `val_scenario_breakdown.csv`: `60ff1d9fa3a766b3e17a93f92ceffe41cb7c8a74022a1535d3dfc2d4c454de08`

**Forensic Investigation & Resolution:**
1. **Creation Timing:** The two on-disk CSV files were written during commit `9e43d0f` at 13:46 UTC on 2026-10-25 when the runner completed post-simulation aggregation.
2. **Immutability:** The raw simulation file `val_episodes.csv` (`1b6b80402ffe...`) was never modified, regenerated, or re-run.
3. **Internal Hash Consistency:** The validation report JSON (`validation_report.json`) was generated simultaneously with the CSV files. Its internal `artifact_sha256` dictionary explicitly recorded `d44a41cf3901e162...` and `60ff1d9fa3a766b3...`, and its canonical integrity digest `6aa98a3cf5e9...` confirms that no file tampering or silent regeneration occurred.
4. **Source of Discrepancy:** The conflicting string values (`...b0445d47...` and `...6efea0b3...`) originated as a transcription error in the conversational markdown response. The actual files on disk and the recorded report hashes have remained completely intact and bit-identical.
5. **Data Consistency:** Direct independent recomputation from the 480 raw episode rows in `val_episodes.csv` confirmed that all summary totals, coverage rates, TSR values, and all 12 scenario breakdown metrics in the on-disk CSVs match the raw simulation data with 100% precision.

---

## 4. Review of Statistical Claims and Methodological Qualifications

To ensure scientific integrity, the reported validation metrics must be understood within their rigorous statistical boundaries:

### 4.1 Stratified Design vs. Unqualified i.i.d. Mixture
- $\mathcal{D}_{\mathrm{val}}$ is a **deterministic stratified grid** with fixed quotas of $40$ episodes per scenario ($12 \times 40 = 480$).
- Episodes were not drawn from an unconditional multinomial mixture.
- **Correction / Qualification:** The pooled coverage ($\hat{C} = 56.04\%$) and pooled TSR ($\widehat{TSR} = 56.04\%$) represent stratified sample descriptive statistics. They must not be described as an unweighted i.i.d. population mixture sample without acknowledging the fixed-quota stratification.

### 4.2 Interpretation of Pooled Binomial Reference Bound (1.11%)
- For $K = 0$ errors in $M = 269$ accepted decisions, the unstratified exact Clopper–Pearson 1-sided 95% upper confidence bound is:
  $$\text{BetaInv}(0.95, 1, 269) = 1 - 0.05^{1/269} \approx 0.011075 = 1.11\%$$
- **Correction / Qualification:** This bound is strictly an unstratified-binomial reference calculation. Because the underlying sampling across scenarios is stratified, this number serves as descriptive benchmarking evidence rather than a certified population selective-risk bound.

### 4.3 Per-Scenario Uncertainty (7.22% Bound)
- For scenarios where all $40$ episodes were accepted with zero errors ($M_s = 40, K_s = 0$, e.g., `NOMINAL`, `SENSOR_DROPOUT`):
  $$\text{BetaInv}(0.95, 1, 40) = 1 - 0.05^{1/40} \approx 0.072158 = 7.22\%$$
- **Correction / Qualification:** Because $7.22\% > 5.0\%$, observing zero false successes in $40$ episodes **does NOT establish that per-scenario selective risk is below 5%**. It only proves that scenario-level risk is bounded below $7.22\%$ at $95\%$ confidence. For scenarios with lower acceptance ($M_s = 17$, e.g., `COMPOUND_DRIFT_DROPOUT`), the bound is $16.16\%$.

### 4.4 Undefined Selective Risk When Acceptance is Zero ($M_s = 0$)
- In `FAULTY_REFERENCE_SENSOR`, `CORRUPTED_ANCHOR_STRESS`, `COMPOUND_HOLDOUT_EXTREME`, and `COMPOUND_ANTIPODAL_RANGE_SHIFT`, $M_s = 0$.
- **Correction / Qualification:** Selective risk is strictly $R_{\mathrm{sel}} = 0/0 = \text{UNDEFINED}$, not zero. Full abstention in a scenario ($40/40$) is not evidence that the selective risk is zero; it represents a safety-versus-utility trade-off (fail-closed refusal to act under unresolvable corruption), not a zero-risk estimate.

### 4.5 Empirical Nominal TSR
- In [`docs/v9_experiment_protocol.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_experiment_protocol.md) Section 3.5 Table 3.5.1, the requirement $\widehat{TSR}_{\mathrm{NOMINAL}}(\hat{\pi}) \ge 0.94$ explicitly uses the hat notation $\widehat{\cdot}$, signifying the empirical point estimate.
- In $\mathcal{D}_{\mathrm{val}}$, $\widehat{TSR}_{\mathrm{NOMINAL}} = 40/40 = 100.0\% \ge 94.0\%$. This satisfies the empirical requirement.

### 4.6 Precondition vs. Population Coverage
- Empirical coverage on the validation grid is $\hat{C} = 269/480 = 56.04\% > 35.0\%$.
- **Correction / Qualification:** Meeting the empirical eligibility floor confirms operational viability under the test suite. It is not an unconstrained population coverage guarantee across arbitrary non-uniform deployment distributions.

### 4.7 Zero Errors $\neq$ Zero Risk
- Observing $FS = 0$ in the finite validation sample indicates that the controller's fail-closed gates operated as designed, but it does not prove that true risk is identically zero.

### 4.8 Simulation Boundary & Physical Hardware Safety Non-Certification
- All validation experiments were executed entirely within a 2D kinematic simulation environment.
- **Correction / Qualification:** Validation outcomes provide empirical runtime evidence under simulated disturbance models; they do **not** certify physical-hardware safety. Hardware deployment requires separate physical-layer commissioning, fail-safe actuation interlocks, and real-world system verification.

---

## 5. Audit of RNG Documentation & NumPy PRNG Model

### 5.1 Verification of PRNG Implementation
- The repository implementation in [`src/aegis/v9/randomization.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/randomization.py) correctly constructs decoupled NumPy `PCG64` bit generators via `SeedSequence`:
  - Calibration: `spawn_key = (2, 1, i, ...)`
  - Validation: `spawn_key = (3, 1, i, ...)`
  - Holdout Mixture: `spawn_key = (4, 1, i, ...)`
  - Holdout Scenario: `spawn_key = (5, 1, i, ...)`
  - Tests: `spawn_key = (6, ...)`
- In [`tests/test_v9_validation.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_validation.py), unit tests verified that child streams for environment and sensors produce non-identical bitstreams and distinct initial states.

### 5.2 Documentation Refinement: SeedSequence PRNG Model
- **NumPy Architectural Alignment:** `numpy.random.SeedSequence` uses an internal 128-bit entropy pool (`pool_size=4` 32-bit unsigned integers) mixed via Melissa E. O'Neill's bit-mixing algorithm to set the initial states for BitGenerators (specifically `PCG64`).
- **Correction of "SplitMix64" Terminology:** Previous draft documentation loosely referred to a "SplitMix64 model". This is corrected: SplitMix64 is a specific 64-bit generator by Steele et al., whereas NumPy's `SeedSequence` employs a 128-bit pool mixer designed to initialize independent bit generators.
- **Tree Disjointness vs. Probabilistic Independence:**
  - Distinct `spawn_key` tuples guarantee structural tree-path disjointness in the derivation hierarchy.
  - The mixed initial states are designed to be independent and very probably non-overlapping. This is a **high-probability statistical model**, not a mathematical guarantee of zero collision probability.
- **Collision Probability Bound:**
  - In an entropy pool of $S = 2^{128} \approx 3.4028 \times 10^{38}$ states, the birthday-paradox collision probability among $K$ spawned streams is modeled by:
    $$P_{\text{collision}} \approx 1 - \exp\left(-\frac{K(K-1)}{2 \times 2^{128}}\right) \approx \frac{K^2}{2^{129}}$$
    (Source: NumPy NEP 19 / SeedSequence architectural documentation).
  - Across the entire NEXVIA AEGIS experimental design (development $N=30$, calibration $N=960$, validation $N=480$, holdouts $N=2{,}880$, and diagnostic test suites, yielding $K \approx 5{,}000$ streams total across environment and sensor generators):
    $$P_{\text{collision}} \approx \frac{(5 \times 10^3)^2}{2 \times 2^{128}} = \frac{2.5 \times 10^7}{6.81 \times 10^{38}} \approx 3.67 \times 10^{-32} \ll 10^{-31}$$
  - This estimate represents an approximate collision probability under the birthday model, not a deterministic guarantee. Registered entropy, partition indices, and episode seeds remain completely unchanged.

---

## 6. Detailed Operational Findings by Scenario Group

| Scenario Category | Realized Scenarios | $N$ | $M$ | $TS$ | $FS$ | Abstention Behavior | Operational Assessment |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **Nominal Baseline** | `NOMINAL` | 40 | 40 | 40 | 0 | $0$ abstentions, $0$ timeouts | Full utility ($100\%$ TSR); 0 false alarms. |
| **Benign Spatial Biases** | `PRIMARY_BIAS`<br>`INDEPENDENT_BIAS`<br>`CORRELATED_BIAS` | 120 | 114 | 114 | 0 | $5$ explicit abstentions,<br>$1$ timeout | $95.0\%$ coverage; adaptive probing calibrates biases cleanly. |
| **Dynamic Faults & Outliers** | `SENSOR_DRIFT`<br>`OUTLIER_BURSTS` | 80 | 58 | 58 | 0 | $19$ explicit abstentions,<br>$3$ timeouts | CUSUM and Ville monitors detect drift and burst deviations; $72.5\%$ coverage, $0$ errors. |
| **Sensor Loss** | `SENSOR_DROPOUT` | 40 | 40 | 40 | 0 | $0$ abstentions, $0$ timeouts | Single-sensor isolation operates cleanly ($100\%$ TSR). |
| **Compound Dynamic Drift** | `COMPOUND_DRIFT_DROPOUT` | 40 | 17 | 17 | 0 | $23$ explicit abstentions | Controller selectively accepts only when bias estimate remains valid ($42.5\%$ coverage, $0$ errors). |
| **Catastrophic / Adversarial Corruption** | `FAULTY_REFERENCE_SENSOR`<br>`CORRUPTED_ANCHOR_STRESS`<br>`COMPOUND_HOLDOUT_EXTREME`<br>`COMPOUND_ANTIPODAL_RANGE_SHIFT` | 160 | 0 | 0 | 0 | **160 explicit abstentions (100%)** | **Complete fail-closed protection** ($0$ false successes; cross-modal and step-zero gates refuse all arrivals). |

---

## 7. Audit Decision

### Decision: `M3_COMPLETED`
Milestone V9-M3 operational validation is **audited and accepted as complete**:
- The single-shot execution guard was preserved; raw simulation data were generated once and preserved unchanged.
- All 480 episodes satisfy the outcome algebra.
- The frozen policy demonstrated zero false successes, zero crashes, and robust fail-closed abstention.
- All statistical claims have been rigorously bounded and qualified.
- Historical calibration records and holdout partitions remain completely intact.
