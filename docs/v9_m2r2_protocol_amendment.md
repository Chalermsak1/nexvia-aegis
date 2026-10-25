# NEXVIA AEGIS V9-M2R2 — Protocol Amendment: Partition-Branched SeedSequence Derivation and Calibration Stream Isolation

**Amendment Identifier:** `docs/v9_m2r2_protocol_amendment.md`  
**Protocol Version:** `v9.0-preregistered-2026-10-amendment-r2`  
**Base Commit Reference:** `3ebddcc1fceb20530777dc1c25aa43e49735d465`  
**Date:** October 2026  
**Status:** PREREGISTERED PROTOCOL AMENDMENT (Committed prior to calibration authorization)

---

## 1. Context & Motivation

During the pre-calibration consistency audit of Milestone V9-M2R1, a critical architectural defect was identified in the implementation of `V9HierarchicalManifestGenerator` ([`src/aegis/v9/randomization.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/randomization.py)):

### 1.1 The Cross-Manifest Stream Reuse Defect in R1
In `cal_manifest_r1.json`, episode streams were derived from `master_ss = np.random.SeedSequence(20261025)` via an unpartitioned root call:
```python
# Unpartitioned derivation in r1:
branch_scen_ss, branch_eps_ss = master_ss.spawn(2)
ep_sequences = branch_eps_ss.spawn(count)
env_ss, sens_ss = ep_sequences[idx].spawn(2)
```
Because the partition name was not incorporated into the `SeedSequence` spawn path:
1. Every manifest generated with `master_entropy=20261025` spawned identical scenario indices (`scen_rng = default_rng((0,))`) and identical episode streams (`spawn_key=(1, idx)`).
2. For episodes $0 \dots 499$, `cal_manifest_r1.json` generated **byte-identical random bitstreams** for environment target positions and sensor noise as the test suite fixture `test_independence` in [`tests/test_v9_randomization.py:54-81`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_randomization.py#L54-L81).
3. The test fixture physically simulated and inspected target positions and sensor noise across those 500 episodes during unit testing.
4. Using `cal_manifest_r1.json` for formal single-shot calibration would therefore evaluate 500 episodes whose pseudo-random bitstreams had already been executed in test fixtures, violating pre-registration separation.

### 1.2 Status of Historical Artifacts
- `cal_manifest_r1.json` has **never been executed for calibration**.
- `cal_manifest_r1.json` and its run config `calibration_run_config_frozen_r1.json` are retained byte-identically on disk as historical evidence.
- `cal_manifest_r1.json` is formally retired and must **never** be used for certification.

---

## 2. Partition-Branched Stream Derivation (`Amendment R2`)

### 2.1 Mathematical Formulation
To guarantee that no calibration, development, validation, holdout, or test stream can ever share or overlap PRNG bitstreams, we formulate an explicit partition-branch hierarchy under NumPy's PCG-64 and `SeedSequence` hashing:

$$\text{ss}_{\text{partition}} = \text{SeedSequence}(\text{master\_entropy}, \text{spawn\_key}=(p,))$$

Where the root partition index $p \in \{0, \dots, 7\}$ is preregistered as follows:
- **$p = 0$:** `RESERVED_GOVERNANCE`
- **$p = 1$:** `D_dev` (Development partition)
- **$p = 2$:** `D_cal` (Calibration partition, `cal_manifest_r2.json`)
- **$p = 3$:** `D_val` (Reserved validation partition, `72000..72039`)
- **$p = 4$:** `D_test_mix` (Reserved mixture holdout partition, `73000..74439`)
- **$p = 5$:** `D_test_scen` (Reserved scenario holdout partition, `75000..75119`)
- **$p = 6$:** `DIAGNOSTIC_TESTS` (Unit tests & test fixtures)
- **$p = 7$:** `SPARE`

### 2.2 Stream Hierarchy for Episode $i$ in Partition $p$
1. **Scenario Stream:**
   $$\text{branch\_scen\_ss} = \text{ss}_{\text{partition}}.\text{spawn}(2)[0] \implies \text{spawn\_key} = (p, 0)$$
2. **Episode Stream Pool:**
   $$\text{ep\_ss}_i = \text{ss}_{\text{partition}}.\text{spawn}(2)[1].\text{spawn}(N)[i] \implies \text{spawn\_key} = (p, 1, i)$$
3. **Decoupled Child Streams:**
   $$\text{env\_ss}_i = \text{ep\_ss}_i.\text{spawn}(2)[0] \implies \text{env\_spawn\_key} = (p, 1, i, 0)$$
   $$\text{sens\_ss}_i = \text{ep\_ss}_i.\text{spawn}(2)[1] \implies \text{sensor\_spawn\_key} = (p, 1, i, 1)$$

### 2.3 Deterministic Spawn Path Disjointness and PRNG Independence Model
To ensure scientific rigor, we formally distinguish between three distinct levels of independence:
1. **Structural Spawn Key Disjointness (Deterministic Hierarchy):**
   NumPy's `SeedSequence` records the exact derivation path as a tuple in `spawn_key`. Because the root partition index $p$ is prepended to all child keys:
   $$\forall p \neq p', \quad (p, 1, i, k) \neq (p', 1, j, k') \quad \forall i, j, k, k'$$
   This ensures that no two partitions share the same spawn path or derivation inputs.
2. **Initial State Collision Probability (NumPy PRNG Model):**
   NumPy's `SeedSequence` mixes the combination of entropy and `spawn_key` into a 128-bit internal pool (`pool_size=4` 32-bit words) using Melissa E. O'Neill's bit-mixing algorithm. Under NumPy's documented design, distinct spawn keys map to independent initial states with an extremely low collision probability bounded by birthday collision rates across $K$ spawned streams ($P_{\text{collision}} \approx K^2 / 2^{129} \approx 3.67 \times 10^{-32} \ll 10^{-31}$ for $K \approx 5{,}000$ streams). This establishes high-probability independence rather than a deterministic zero-collision guarantee.
3. **Simulation Modeling Assumption (i.i.d. Physical Law):**
   The assertion that simulated episode trajectories and outcomes follow the intended independent and identically distributed (i.i.d.) simulation law $\mathcal{P} = \frac{1}{12}\sum_{s=1}^{12}\mathcal{P}_s$ is a *statistical modeling assumption* about the simulation environment, reset mechanics, and PRNG quality. It is distinct from, and cannot be proven by, deterministic spawn-path uniqueness or empirical sample zero-correlation checks alone. Empirical correlation checks are descriptive consistency verifications, not proofs of distributional independence.

### 2.4 Development Partition Provenance Justification
The development partition $\mathcal{D}_{\text{dev,r1}}$ (seeds `77000..77029`, $12 \times 30 = 360$ episodes per policy) was evaluated using per-episode scalar seeds via `create_decoupled_rng_pair(77000 + i)` (`SeedSequence(77000 + i).spawn(2)`).
- **Justification as Separate Preregistered Derivation:** $\mathcal{D}_{\text{dev,r1}}$ was established as a fixed-quota exploratory and ordering-verification grid prior to the hierarchical manifest generation. Its root entropy draws from integer range `77000..77029`, which is entirely separate from the hierarchical `master_entropy = 20261025` used for `D_cal,r2`.
- **Relationship to `PARTITION_BRANCH_DEV = 1`:** The constant `PARTITION_BRANCH_DEV = 1` is preregistered in `V9HierarchicalManifestGenerator` for future hierarchical development grids. To preserve experimental integrity and adhere to the protocol rule prohibiting retrospective data regeneration, the existing completed $\mathcal{D}_{\text{dev,r1}}$ evaluation is retained and justified as an explicitly separate derivation.
- **Separation from $\mathcal{D}_{\text{cal,r2}}$:** Because $\mathcal{D}_{\text{dev,r1}}$ uses scalar entropy `77000..77029` with spawn keys `(0,)` and `(1,)`, and $\mathcal{D}_{\text{cal,r2}}$ uses master entropy `20261025` with branch `(2, 1, i, 0)` and `(2, 1, i, 1)`, there is zero stream reuse or state collision between the two datasets.

---

## 3. Fresh Calibration Manifest R2 Specification

The fresh calibration manifest [`results/v9/manifests/cal_manifest_r2.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/cal_manifest_r2.json) is generated under $p = 2$:
- **Master Entropy:** `20261025`
- **Partition Index:** `2` (`PARTITION_BRANCH_CALIBRATION`)
- **Partition Name:** `calibration_r2` (`D_cal,r2`)
- **Manifest ID Range:** `76000 .. 76959` ($N = 960$)
- **Per-Episode Spawn Keys:**
  - `spawn_key`: `[2, 1, i]`
  - `env_spawn_key`: `[2, 1, i, 0]`
  - `sensor_spawn_key`: `[2, 1, i, 1]`
- **Realized Scenario Counts ($N=960$):**
  `{'NOMINAL': 74, 'PRIMARY_BIAS': 85, 'INDEPENDENT_BIAS': 114, 'CORRELATED_BIAS': 85, 'SENSOR_DRIFT': 71, 'OUTLIER_BURSTS': 89, 'SENSOR_DROPOUT': 56, 'FAULTY_REFERENCE_SENSOR': 81, 'CORRUPTED_ANCHOR_STRESS': 66, 'COMPOUND_HOLDOUT_EXTREME': 89, 'COMPOUND_DRIFT_DROPOUT': 86, 'COMPOUND_ANTIPODAL_RANGE_SHIFT': 64}`
- **Artifact Digests:**
  - `cal_manifest_r2.json` Raw SHA-256: `49bf68b60f7dd76219a17383bdc829005f4dedb0fb1f1ed687ed23eb66fce9e0`
  - `cal_manifest_r2.json` Canonical SHA-256: `b0161b8ea2008287744238be219f286bb346599efcd6a8d555abb6258566fa72`
  - `episodes_sha256`: `2851bd9e90c793f4db5e70fe2691e6de31140aece71f3be97810f1accc1237e7`

### 3.1 Fresh Calibration Run Configuration R2
Frozen in [`results/v9/cal/calibration_run_config_frozen_r2.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/cal/calibration_run_config_frozen_r2.json):
- Raw SHA-256: `1a19f6b4c294217260540db19af877f514c852d09921cb06523baaca7ab77564`
- Canonical Payload SHA-256: `390af9d5c953bd09407d046def719bb9e13aec257f0b0d49e28c8d179c10635d`

---

## 4. Preservation of Historical and Prior Artifacts

1. **`cal_manifest_r1.json` & `calibration_run_config_frozen_r1.json`:**
   Preserved byte-identically on disk as historical evidence.
2. **`D_dev` Data (`results/v9/dev/dev_episodes_r1.csv`):**
   Preserved and valid. Evaluated under independent seeds `77000..77029` (`SeedSequence(77000 + i)`), showing zero stream overlap with `r2`.
3. **Historical V9-M2 Artifacts:**
   All original calibration records (`cal_episodes.csv`, `calibration_report.json`, etc.) remain intact.
4. **Reserved Partitions:**
   `D_val` (`72000..72039`), `D_test_mix` (`73000..74439`), and `D_test_scen` (`75000..75119`) remain strictly reserved and unexecuted.
