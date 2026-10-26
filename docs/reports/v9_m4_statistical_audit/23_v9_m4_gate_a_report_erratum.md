# NEXVIA AEGIS V9-M4 — Gate A Report Erratum

**Document Identifier:** `AEGIS-V9-M4-ERR-23`  
**Phase:** Phase 23 — Post-Gate-A Verification & Manifest Integrity Erratum  
**Date:** October 26, 2026  
**Auditor / Recorder:** Autonomous Verification Subsystem (Google DeepMind Antigravity)  
**Git Branch:** `v9.0-runtime-assurance`  
**Base Commit:** [`7201f8cfff951af9b6de7177b4b1606fda31d7c3`](https://github.com/Chalermsak1/nexvia-aegis/commit/7201f8cfff951af9b6de7177b4b1606fda31d7c3) (`7201f8c`)  
**Target Milestone:** Milestone V9-M4 (Confirmatory Holdout Evaluation)  
**Governance State:** Gate B remains strictly **`NOT AUTHORIZED`** (locked).

---

## 1. Erratum Summary & Scope

| Erratum Field | Record / Status | Detailed Finding |
| :--- | :---: | :--- |
| **Target Document** | Gate A Completion Report (§6.2) | Gate A Remediation and Manifest Integrity Freeze Report |
| **Erroneous Notation** | `[5, scen_idx, ep_idx, {0, 1}]` | Narrative transcription error in reporting summary text |
| **Authoritative Notation** | Episode: `[5, 1, i]`<br>Env: `[5, 1, i, 0]`<br>Sensor: `[5, 1, i, 1]` | Where $i = \text{episode\_index} \in \{0, \dots, 1439\}$ |
| **Manifest Census** | $1{,}440 / 1{,}440$ episodes (100.0%) | 0 episodes deviate from the authoritative $[5, 1, i]$ hierarchy |
| **Manifest Integrity** | **MATCH / VALIDATED** | Raw SHA-256: `55e04c45...` & Integrity: `9c9ab7e0...` |
| **Production Evaluator** | **NOT EXECUTED** | Zero simulation environments instantiated; Gate B locked |

---

### Critical Governance Invariant

> [!CAUTION]
> ### DOCUMENTATION ERRATUM ONLY — GATE B REMAINS LOCKED
> 1. **Purely Documentation Clarification:** This erratum documents and corrects a narrative transcription error in the Gate A completion report. It does **not** alter repository code, frozen policy, statistical decision thresholds, or manifest files.
> 2. **No Manifest Regeneration:** The committed production manifests [`results/v9/manifests/test_scen_manifest_r1.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/test_scen_manifest_r1.json) and [`results/v9/manifests/test_mix_manifest_r1.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/test_mix_manifest_r1.json) are byte-for-byte intact and validated. No manifest has been regenerated or modified.
> 3. **Gate B Remains Locked:** Gate B production holdout evaluation remains strictly **`NOT AUTHORIZED`**. No evaluation token (`V9_M4_AUTH_TOKEN`) has been supplied, accessed, or invoked. Zero real holdout episodes have been simulated or evaluated.

---

### บทสรุปสำหรับผู้บริหาร (Executive Summary in Thai)

1. **การแก้ไขข้อความในรายงาน Gate A:** ในรายงานสรุปการดำเนินงาน Gate A (หัวข้อ 6.2) มีการพิมพ์สัญลักษณ์ลำดับชั้น PRNG Spawn-Key ของชุด Scenario Holdout ผิดพลาดจากการสรุปความเชิงบรรยายเป็น `[5, scen_idx, ep_idx, {0, 1}]`
2. **การตรวจสอบข้อเท็จจริงระดับรหัสและไฟล์จริง:** การตรวจสอบรหัสต้นฉบับใน [`src/aegis/v9/randomization.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/randomization.py) และข้อมูลทุกตอน (1,440 ตอน) ในไฟล์ [`results/v9/manifests/test_scen_manifest_r1.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/test_scen_manifest_r1.json) ยืนยันว่าค่า Spawn-Key ที่แท้จริงคือ:
   - Episode: `[5, 1, i]`
   - Environment: `[5, 1, i, 0]`
   - Sensor: `[5, 1, i, 1]`
   ตรงตามพิธีสารหลัก [`docs/v9_m3_post_validation_audit.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_m3_post_validation_audit.md) §5.1 และ [`docs/v9_m2r2_protocol_amendment.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_m2r2_protocol_amendment.md) อย่างสมบูรณ์ 100%
3. **ความสมบูรณ์ของ Artifact:** ไฟล์ Manifest ที่ถูก Commit ไว้มีค่า Hash ตรงกับที่บันทึกไว้ทุกประการ ไม่มีการสร้างไฟล์ใหม่ ไม่มีการแก้ไขโค้ด และไม่มีการเปลี่ยนสถานะการกำกับดูแล
4. **สถานะ Gate B:** ยืนยันว่า Gate B ยังคง **`NOT AUTHORIZED`** อย่างเคร่งครัด ไม่มีการรันการประเมินผลจริง ไม่มีการจำลองตอนทดสอบ และไม่มีการใช้โทเค็นลับ

---

## 2. Technical Detail of the Discrepancy

### 2.1 The Reporting Transcription Error
In Section 6.2 of the conversational Gate A Remediation and Manifest Integrity Freeze Report, the scenario partition derivation was informally described as:
$$\text{PRNG Spawn-Key hierarchy: Verified } [5, \text{scen\_idx}, \text{ep\_idx}, \{0, 1\}] \text{ for all episodes.}$$

This notation arose because the stratified manifest generator contains nested loops over scenario definitions ($S_{12}$) and seeds per scenario ($120$):
```python
for sc_idx, scen in enumerate(scenarios):
    for s_offset in range(seeds_per_scenario):
        ...
```
The drafter inadvertently substituted the conceptual outer-loop variable `scen_idx` for the fixed branch index `1` in the derivation tree.

### 2.2 The Authoritative Implementation & Derivation Architecture
The actual generator implementation in [`src/aegis/v9/randomization.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/randomization.py#L190-L220) defines the tree strictly as:

```python
part_ss = np.random.SeedSequence(self.master_entropy, spawn_key=(partition_index,)) # (5,)
branch_scen_ss, branch_eps_ss = part_ss.spawn(2)                                   # (5, 0) and (5, 1)
ep_sequences = branch_eps_ss.spawn(total_episodes)                                 # (5, 1, ep_idx)

ep_idx = 0
for sc_idx, scen in enumerate(scenarios):
    for s_offset in range(seeds_per_scenario):
        ep_ss = ep_sequences[ep_idx]
        env_ss, sens_ss = ep_ss.spawn(2)
        ...
        ep_item = {
            "episode_index": ep_idx,
            "seed": seed_start + s_offset,
            "manifest_id": seed_start + s_offset,
            "scenario_index": sc_idx,
            "scenario": scen.name,
            "partition_index": partition_index,
            "spawn_key": list(ep_ss.spawn_key),              # [5, 1, ep_idx]
            "env_spawn_key": list(env_ss.spawn_key),        # [5, 1, ep_idx, 0]
            "sensor_spawn_key": list(sens_ss.spawn_key),    # [5, 1, ep_idx, 1]
        }
        episodes.append(ep_item)
        ep_idx += 1
```

Under NumPy's `SeedSequence` model:
- `branch_eps_ss` is created by spawning 2 children from `part_ss`; child 1 receives `spawn_key = (5, 1)`.
- `branch_eps_ss.spawn(1440)` spawns 1,440 episode seed sequences directly from child 1; each episode $i \in \{0, \dots, 1439\}$ receives `spawn_key = (5, 1, i)`.
- `ep_ss.spawn(2)` produces the decoupled environment stream `(5, 1, i, 0)` and sensor stream `(5, 1, i, 1)`.

---

## 3. Full Census of Committed Manifest Artifact

The committed file [`results/v9/manifests/test_scen_manifest_r1.json`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/results/v9/manifests/test_scen_manifest_r1.json) was audited across all 1,440 episodes without modification or regeneration:

| Episode Range | Scenario Index | Scenario Name | Episode Index Range | Seed Range | Episode `spawn_key` | `env_spawn_key` | `sensor_spawn_key` |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 0 – 119 | 0 | `NOMINAL` | 0 – 119 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 120 – 239 | 1 | `PRIMARY_BIAS` | 120 – 239 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 240 – 359 | 2 | `INDEPENDENT_BIAS` | 240 – 359 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 360 – 479 | 3 | `CORRELATED_BIAS` | 360 – 479 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 480 – 599 | 4 | `SENSOR_DRIFT` | 480 – 599 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 600 – 719 | 5 | `OUTLIER_BURSTS` | 600 – 719 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 720 – 839 | 6 | `SENSOR_DROPOUT` | 720 – 839 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 840 – 959 | 7 | `FAULTY_REFERENCE_SENSOR` | 840 – 959 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 960 – 1079 | 8 | `CORRUPTED_ANCHOR_STRESS` | 960 – 1079 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 1080 – 1199 | 9 | `COMPOUND_HOLDOUT_EXTREME` | 1080 – 1199 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 1200 – 1319 | 10 | `COMPOUND_DRIFT_DROPOUT` | 1200 – 1319 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |
| 1320 – 1439 | 11 | `COMPOUND_ANTIPODAL_RANGE_SHIFT` | 1320 – 1439 | 75000 – 75119 | `[5, 1, i]` | `[5, 1, i, 0]` | `[5, 1, i, 1]` |

### Audit Census Verification Findings:
1. **Total episodes:** Exactly 1,440.
2. **Scenario balance:** Exactly 120 episodes per scenario across all 12 scenarios.
3. **Key format:**
   - Episodes with `spawn_key != [5, 1, ep_idx]`: **0** (0.00%)
   - Episodes with `env_spawn_key != [5, 1, ep_idx, 0]`: **0** (0.00%)
   - Episodes with `sensor_spawn_key != [5, 1, ep_idx, 1]`: **0** (0.00%)
4. **Cryptographic hashes:**
   - Raw SHA-256: `55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d`
   - Canonical integrity SHA-256: `9c9ab7e0fb798570aa4968cd823c71f367cf17c69fca5951853d49cd6c567679`

---

## 4. Citation of Preregistered Protocol References

The verified $[5, 1, i]$ hierarchy conforms strictly to the preregistered protocol and historical audits:

1. **[`docs/v9_m3_post_validation_audit.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_m3_post_validation_audit.md#L147-L151) (§5.1):**
   ```markdown
   - Calibration: spawn_key = (2, 1, i, ...)
   - Validation: spawn_key = (3, 1, i, ...)
   - Holdout Mixture: spawn_key = (4, 1, i, ...)
   - Holdout Scenario: spawn_key = (5, 1, i, ...)
   - Tests: spawn_key = (6, ...)
   ```
2. **[`docs/v9_m2r2_protocol_amendment.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/v9_m2r2_protocol_amendment.md#L88-L91) (§3):**
   ```markdown
   - Per-Episode Spawn Keys:
     - spawn_key: [2, 1, i]
     - env_spawn_key: [2, 1, i, 0]
     - sensor_spawn_key: [2, 1, i, 1]
   ```
3. **[`tests/test_v9_holdout_preflight.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_v9_holdout_preflight.py#L2405-L2407) (`test_63`):**
   ```python
   assert ep["spawn_key"] == [4, 1, ep["episode_index"]]
   assert ep["env_spawn_key"] == [4, 1, ep["episode_index"], 0]
   assert ep["sensor_spawn_key"] == [4, 1, ep["episode_index"], 1]
   ```

---

## 5. Formal Erratum Declaration

Be it recorded in the project archive:
> The narrative string `[5, scen_idx, ep_idx, {0, 1}]` appearing in Section 6.2 of the conversational Gate A Remediation and Manifest Integrity Freeze Report was an informal editorial transcription error.  
> The authoritative, preregistered, implemented, and verified PRNG spawn-key hierarchy for the Scenario Holdout partition is:
> - Episode: `spawn_key = [5, 1, i]`
> - Environment: `env_spawn_key = [5, 1, i, 0]`
> - Sensor: `sensor_spawn_key = [5, 1, i, 1]`  
> for each episode index $i \in \{0, \dots, 1439\}$.
> All historical reports, frozen manifests, certified policies, and regression tests remain 100% valid and unaltered.

---

## 6. Governance Status Confirmation

| Governance Invariant | Status |
| :--- | :---: |
| **Gate A Remediation & Freeze** | **`PASSED`** (Commit `7201f8c`) |
| **Gate A Erratum** | **`RECORDED`** (Document `AEGIS-V9-M4-ERR-23`) |
| **Gate B Execution Status** | **`NOT AUTHORIZED` (LOCKED)** |
| Production Evaluator Execution | None (0 runs) |
| Holdout Simulation / Episode Loading | None (0 episodes) |
| Output Directories (`results/v9/test_mix/`, `test_scen/`) | Non-existent |
| Production Secret Token (`V9_M4_AUTH_TOKEN`) | Unused / Unsupplied |
| Certified Policy Hash Integrity | Canonical SHA-256: `90dc5c0068bb...` (Intact) |
