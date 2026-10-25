# NEXVIA AEGIS V9-M2R1 — Pre-Calibration Consistency Audit & Discrepancy Reconciliation

**Document Identifier:** `docs/v9_m2r1_pre_cal_consistency_audit.md`  
**Protocol Version:** `v9.0-preregistered-2026-10-amendment-r1`  
**Base Commit Reference:** `88290b76920f77977467776b97eb4b23d922bc84`  
**Date:** October 2026  
**Status:** PREREGISTERED AUDIT & READINESS REPORT (Authorized prior to calibration review)

---

## 1. Executive Summary & Audit Verdict

This audit performs an independent, read-only verification of the completed NEXVIA AEGIS V9-M2R1 preparation on branch `v9.0-runtime-assurance`.

### Formal Verdict: `READY_FOR_CALIBRATION_REVIEW`
All pre-calibration technical conditions, RNG decoupling architectures, fail-closed arrival decision rules, artifact hashes, and partition guardrails are verified and consistent. No calibration episodes have been executed on manifest `76000..76959`, and all reserved validation and holdout partitions remain untouched.

---

## 2. Historical Seed-71717 Discrepancy Reconciliation

### 2.1 The Discrepancy
In the initial V9-M2R1 milestone report, a narrative discrepancy appeared regarding the scenario label and physical parameters of historical calibration episode seed `71717`:
- **Historical Calibration Record:** Documented seed `71717` under scenario `COMPOUND_HOLDOUT_EXTREME` with true distance `0.5683 m`, common-mode vector bias `(+0.5, +0.5)`, and range bias `-0.40 m`.
- **Erroneous Narrative Description:** A section of the M2R1 completion text described seed `71717` as occurring under `COMPOUND_ANTIPODAL_RANGE_SHIFT` with true distance `0.5704 m`, vector biases `(+0.55, +0.40)` / `(-0.45, -0.35)`, and range bias `-0.30 m`.

### 2.2 Forensic Artifact Trace & Root Cause
We conducted an exact audit of raw artifacts and test fixtures across the repository:
1. **Raw Calibration CSV (`results/v9/cal/cal_episodes.csv`):**
   ```csv
   episode_index,seed,scenario_index,scenario,suite,sequence_position,policy,accepted,true_success,false_success,...,final_distance,steps,...,terminal_reason
   717,71717,9,COMPOUND_HOLDOUT_EXTREME,S_10,1,V9_CAND_1_TIER1_STRICTEST,1,0,1,...,0.5683,0,...,NOMINAL_VERIFIED_ARRIVAL
   717,71717,9,COMPOUND_HOLDOUT_EXTREME,S_10,4,V9_CAND_4_TIER4_BALANCED,1,0,1,...,0.5683,0,...,NOMINAL_VERIFIED_ARRIVAL
   ```
   Row 717 confirms that seed `71717` belongs strictly to scenario index 9 (`COMPOUND_HOLDOUT_EXTREME`), yielding a step-0 false success (`steps=0, accepted=1, false_success=1`) with true terminal distance `0.5683 m`.
2. **Diagnostic Summary (`results/v9/cal/cal_scenario_breakdown_diagnostic.csv`):**
   Lines 11, 23, 35 record that the single false success in the historical calibration occurred in scenario `COMPOUND_HOLDOUT_EXTREME` ($N_{\text{FS}} = 1, N_{\text{accepted}} = 1, R_{\text{sel}} = 1.0$). Scenario `COMPOUND_ANTIPODAL_RANGE_SHIFT` had zero accepted episodes ($N_{\text{accepted}} = 0, N_{\text{FS}} = 0$).
3. **Historical Manifest (`results/v9/manifests/cal_manifest.json`):**
   Episode index 717 maps seed `71717` to `COMPOUND_HOLDOUT_EXTREME` (`suite: S_10`).
4. **Forensic Unit Test (`tests/test_v9_step_zero_fail_closed.py:44-112`):**
   The executable test `test_1_historical_seed_71717_forensic_reproduction` faithfully instantiates `COMPOUND_HOLDOUT_EXTREME` on seed `71717` with true distance `0.5683 m`, confirms the historical fail-open defect on old logic, and verifies that the corrected controller emits `VERIFY` (with anchor query) at step 0 and transitions to `ACTIVE_PROBING` (`PROBE`, `UNCORROBORATED_INITIAL_ARRIVAL_PROBE`) at step 1.
5. **Preregistered Protocol Amendment (`docs/v9_m2r1_protocol_amendment.md`):**
   Lines 18 and 43–46 explicitly cite `COMPOUND_HOLDOUT_EXTREME` and distance `0.5683 m`.

### 2.3 Conclusion of Reconciliation
The raw calibration record, manifest, committed protocol amendment, and executable regression test are 100% harmonious and correct. The discrepancy was confined entirely to the narrative text of the summary report, which inadvertently conflated the parameters of the separate adversarial scenario `COMPOUND_ANTIPODAL_RANGE_SHIFT` with the historical failure case on `COMPOUND_HOLDOUT_EXTREME`. Both cases have now been tested independently and both fail closed.

---

## 3. Verification of RNG Independence & Stochastic Modeling

### 3.1 Code-Level Stream Separation
In `src/aegis/v9/randomization.py`, random number generation is structured as a rooted directed tree using `numpy.random.SeedSequence`:
```
                  Master Entropy (20261025)
                          |
             +------------+------------+
             |                         |
       Branch 0 (Scenarios)      Branch 1 (Episodes)
             |                         |
       PCG64(spawn_key=(0,))     Episode i (spawn_key=(1, i))
                                       |
                         +-------------+-------------+
                         |                           |
                   Environment                  Sensors
              PCG64(spawn_key=(1, i, 0))   PCG64(spawn_key=(1, i, 1))
```
1. **Dedicated Scenario Stream:** `branch_scen_ss` (spawn key `(0,)`) samples scenario indices uniformly across $\{0, \dots, 11\}$ without consuming episode variates.
2. **Dedicated Episode Streams:** For each episode $i \in \{0, \dots, N-1\}$, `branch_eps_ss.spawn(N)` generates a separate child `SeedSequence` (spawn key `(1, i)`).
3. **Decoupled Environment and Sensor Streams:** `env_ss` (`(1, i, 0)`) and `sens_ss` (`(1, i, 1)`) are spawned independently. Target placement and physical kinematics never draw from the sensor PRNG; noise, dropout, and outliers never draw from the environment PRNG.
4. **No Scalar Seed Reuse:** No code path instantiates both generators with the same scalar integer.
5. **Stateless O(1) Reconstruction:** Manifest items record `master_entropy`, `env_spawn_key`, and `sensor_spawn_key`. Any episode can be reproduced in isolation via `instantiate_episode_rngs_from_manifest_item`.

### 3.2 Distinction: Stream Separation vs. Empirical Correlation Tests
- **Code-Level Distinction:** Hashing in `SeedSequence` guarantees distinct 128-bit initialization states for the underlying PCG64 generators. This architectural separation is the mathematical foundation for assuming independent episode draws.
- **Empirical Diagnostic Role:** Observing a sample correlation $|r| < 0.10$ across $N = 500$ realizations is a necessary sanity check, but sample correlation is not a mathematical proof of statistical independence.
- **Stochastic Model & Limitations:**
  - The i.i.d. assumption in Fixed-Sequence LTT calibration applies to the *modeled simulation law* $\mathcal{P}_{12}$.
  - PRNG streams are deterministic sequences approximating pseudo-randomness; they do not possess physical indeterminacy.
  - Guarantees on $\mathcal{P}_{12}$ do not transfer to physical hardware without domain adaptation, physical sensor calibration, and out-of-distribution runtime monitoring.

### 3.3 Scenario Mixture Verification
In `results/v9/manifests/cal_manifest_r1.json` ($N = 960$):
- Target mixture: Uniform $p_k = 1/12 \approx 0.08333$ for all 12 scenarios.
- Realized counts: Range $[67, 90]$, mean $80.0$.
- Chi-square goodness-of-fit test: $\chi^2 = 9.475 < 19.675$ ($df = 11, p = 0.578$). The realized mixture is consistent with multinomial draws from $\mathcal{P}_{12}$.

---

## 4. Re-Audit of Fail-Closed Initial-Arrival Gate

### 4.1 Verification Criteria
We re-audited `AegisV9Controller.update` ([`src/aegis/v9/controller.py:660-835`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/controller.py#L660-L835)) and verified:

1. **Step-Zero Fail-Closed Gate:** When `nav_dist <= arrival_tolerance_m` occurs without temporal approach (`_nominal_approach_steps < 3`):
   - The controller checks for 3-way corroboration: anchor distance $\le 0.22\text{ m}$, vector-anchor agreement $\le \tau_{\text{diff}}$, and anchor-range agreement $\le \tau_{\text{ar}}$.
   - If anchor has not been queried, the controller emits `decision="VERIFY"` with `query_anchor=True`, never `STOP`.
   - If anchor refutes arrival or is unavailable, the controller transitions to `ACTIVE_PROBING` (`decision="PROBE"`, `terminal_reason="UNCORROBORATED_INITIAL_ARRIVAL_PROBE"`), never `STOP`.
2. **Missing / Invalid Observation Handling:**
   - Invalid or dropped range readings trigger `VERIFY` and fail closed to `ABSTAIN` (`INVALID_OR_DROPPED_RANGE_AT_ARRIVAL`) if persistent.
   - NaN or infinite vector readings immediately trigger `ABSTAIN` with malformed input tags.
3. **Temporal Approach Guard:**
   - Approach counter `_nominal_approach_steps` increments strictly when the robot actively pursues the goal from outside the arrival zone (`nav_dist > arrival_tolerance_m`).
   - Merely replaying repeated identical stationary observations or static bias cannot increment the pursuit counter.
4. **Adversarial Antipodal Sweep:**
   A sweep across 100 seeds on `COMPOUND_ANTIPODAL_RANGE_SHIFT` across all 6 candidate policies confirmed 0 step-zero false acceptances ($0 / 600$).

---

## 5. Artifact & Integrity Verification

| Artifact | Path | Raw File SHA-256 | Canonical Payload SHA-256 | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Candidate Config r1** | `configs/v9_candidates_frozen_r1.json` | `346f95929f244b4e93f14d784e7dd1d9b5ce0168404745925eac80a5cd11bf18` | `732862c33d5a2e987bd2065e83b92bec5ad4ffb16a9c3b56a7b15ec6cb9b4d72` | Verified |
| **Dev Episodes r1** | `results/v9/dev/dev_episodes_r1.csv` | `64d9590e41607d4e0de7fbaaa06fca874a24787b6031ba79c79a15bd6b1ad8ee` | — (2,880 rows) | Verified |
| **Dev Policy Summary r1**| `results/v9/dev/dev_policy_summary_r1.csv` | `2df266cdf9cb78f6a3b53b20199c61be0c847723183272edfae9bb2e7fef9895` | — (8 policies) | Verified |
| **Dev Scenario Summary r1**| `results/v9/dev/dev_scenario_summary_r1.csv`| `8bb02966be3a4775a2e1da0fd269726f3d20d52572fda6f72129225992086a09` | — (96 rows) | Verified |
| **Dev Ordering Report r1** | `results/v9/dev/dev_ordering_report_r1.json` | `12ce998eb94a92759aac96ebec9d5538094e7c1b8c8b4efe180ec54b63f9efca` | — | Verified |
| **Calibration Manifest r1**| `results/v9/manifests/cal_manifest_r1.json` | `3b76312c7bd1e07c3d6bb8ec34027362d859642d0387db8c576ed510cda43a5d` | `f2598191c97c6597984a9eeb59b3dc661934084f09dfaa5a5395387b2fc8f5e9` | Verified |
| **Calibration Run Config r1**| `results/v9/cal/calibration_run_config_frozen_r1.json` | `e5ba847252a7d58cf40c11ecedcf7c283685447b1053d5444188f094832ebc81` | `d0a535718e1f8fa28a867c48f22d3ff7b6464263ac1eb48e8fac6182bd19ec7d` | Verified |

### Partition Disjointness Check:
- Historical dev: `70000..70029` ($N=30$)
- Historical calibration: `71000..71959` ($N=960$)
- Reserved validation partition: `72000..72039` ($N=40$, untouched)
- Reserved mixture holdout partition: `73000..74439` ($N=1440$, untouched)
- Reserved scenario holdout partition: `75000..75119` ($N=120$, untouched)
- Fresh calibration manifest: `76000..76959` ($N=960$, unexecuted)
- Fresh dev manifest: `77000..77029` ($N=30$, evaluated)

Pairwise intersection of all 7 identifier sets is verified empty ($\emptyset$).

---

## 6. Active Execution Guards Verification

The calibration script `experiments/v9_calibrate_ltt.py` contains two independent security gates:
1. **Single-Shot Output Directory Guard:** Refuses execution if any prior artifact (`cal_episodes.csv`, `calibration_report.json`, etc.) exists in the output directory.
2. **Phase 6 Execution Guard:** Explicitly blocks execution on manifest `cal_manifest_r1.json`:
   ```python
   if "r1" in man_path.name:
       raise RuntimeError(
           "EXECUTION GUARD: Single-shot calibration for V9-M2R1 (D_cal,r1 76000..76959) is deferred "
           "pending independent protocol review. Calibration episodes must NOT be generated or executed in Milestone V9-M2R1 Phase 6."
       )
   ```
3. **Freeze-Only Operational Verification:** Running with `--freeze-only` verifies manifest and config integrity without instantiating or executing simulation episodes.

---

## 7. Scientific Claims Boundaries

1. **No Calibration Claim:** V9-M2R1 has **not** been calibrated or certified. Only candidate definitions, manifest, and run configs are frozen.
2. **No Empirical Claim Substitution:** Unit test passage does not substitute for a single-shot calibration trial on $D_{\text{cal},r1}$.
3. **Coverage Filter vs. Guarantee:** The minimum accepted count $M_{\text{cal}} \ge 336$ is an empirical calibration guardrail; it does not provide an analytical lower bound on population coverage.
4. **Mixture Risk vs. Scenario Risk:** Selective-risk certification bounds pooled error over $\mathcal{P}_{12}$; it does not guarantee equal risk bounds for individual stress scenarios.
5. **Simulation vs. Real-World Safety:** Claims apply exclusively to the formal simulation environment defined by $\mathcal{P}_{12}$.
