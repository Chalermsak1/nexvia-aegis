# V9-M4 Historical Calibration/Validation Hash Erratum — Supplemental Report

**Status:** `DRAFT — NOT APPROVED`
**Disposition:** `OWNER & RESEARCH INTEGRITY DECISION REQUIRED`
**Project Status:** `BLOCKED — GATE_B_NOT_AUTHORIZED`
**Date:** 2026-10-28 (Asia/Bangkok)

---

## 1. Executive Summary & Purpose

This supplemental report accompanies `V9_M4_HISTORICAL_HASH_ERRATUM_DRAFT.md` and `V9_M4_HISTORICAL_ARTIFACT_PROVENANCE_INVENTORY.md`. It provides independent research-integrity analysis of historical hash citations across early Phase 9 reports (Reports 09, 10, 13, 19, and 20) against current verified artifacts in Git commit `74f93fe2613221c476828d1558c03d0598c06b7e`.

**Crucial Research Integrity Invariant:**
No disputed hash citation is chosen simply to permit release progression. All original reports remain preserved exactly as recorded; this erratum establishes transparent provenance distinction without overwriting historical documentation.

---

## 2. Distinguishing Hash & Identity Categories

To eliminate ambiguity across prior audits, every digest is categorized into one of five rigorous identity categories:

1. **Raw SHA-256 of Exact File Bytes:**
   - Evaluated as `hashlib.sha256(Path(file).read_bytes()).hexdigest()`.
   - Represents the immutable byte sequence of the file as written on the filesystem.
2. **Git Blob Identity (Git Object SHA-1):**
   - Evaluated as `git hash-object <path>` or via `git ls-tree`.
   - Distinguishes Git tracking provenance from raw byte digests.
3. **Canonical-Payload Digest (JSON Serialization):**
   - For risk statistics and report JSONs: RFC 8785 canonical JSON omitting top-level `integrity_sha256` (`src/aegis/v9/risk_statistics.py:636-640`).
   - For manifests: JCS canonical serialization omitting `manifest_sha256` (`src/aegis/v9/randomization.py:162-167, 251-256`).
   - *Note:* The risk statistics and randomization canonical schemes are structurally distinct.
4. **Historical Report Citations:**
   - Numerical hex values quoted in prior text reports (e.g. Report 09, 10, 13, 19, 20).
   - Provenance status: **HISTORICAL CLAIM (UNVERIFIED SOURCE BYTES)** until independently substantiated.
5. **Verified Present-Byte Identity:**
   - SHA-256 and Git blob hashes of the artifacts present in the repository at commit `74f93fe2613221c476828d1558c03d0598c06b7e`.
   - Corroborated 100% by internal producer inventories (`cal_r2/calibration_report.json` and `val_r1/validation_report.json`).

---

## 3. Discrepancy Matrix & Provenance Analysis

| Artifact | Present Raw SHA-256 | Present Canonical SHA-256 | Historical Citation(s) & Source | Analysis & Provenance Status |
| :--- | :--- | :--- | :--- | :--- |
| `results/v9/cal_r2/calibration_report.json` | `c07b04ba1600aad2416ade36cc6e9c33501327fb4b0a03d2d5b05b6f9b6a963e` | `016990be14b2e751edfbc9d0620e1f928a7f3ba31e2b2f723d4228c1fe81da1b` | `a91b9b008d...` in Rep 09:155, 10:95, 13:72;<br>`ef3eb0a2b5...` in Rep 19:242 | Neither citation matches raw or canonical bytes. Rep 09/10/13 were committed *before* artifact commit `74f93fe`. **Status: Unsupported historical draft claim.** |
| `results/v9/cal_r2/calibration_run_config_frozen_r2.json` | `1a19f6b4c294217260540db19af877f514c852d09921cb06523baaca7ab77564` | `390af9d5c953bd09407d046def719bb9e13aec257f0b0d49e28c8d179c10635d` | `f3e582b13c...` in Rep 20:286-289 | Neither raw nor canonical matches. Source bytes unverified. **Status: Unsupported citation.** |
| `results/v9/cal_r2/cal_candidate_summary.csv` | `c37f673d0751e1848687f286c5c8199b151a24d1a199363b1a8191057725a3ae` | N/A (CSV) | `043d84a7e9...` in Rep 19:237-241 | Explicit raw SHA-256 conflict. Current file matches `v9_m3_validation_protocol.md:38` prefix. **Status: Unsupported citation.** |
| `results/v9/val_r1/validation_report.json` | `a5f4df07996c6e5c04a48b5ed86668960bafb691aa489c526e5232aea635b500` | `6aa98a3cf5e9d594a3ccae8903881ac62e0fbc80e025704beb65bab1876846d3` | `c97fffa626...` in Rep 09:156, 10:96, 13:73;<br>`a84baea0ca...` in Rep 19:243, 20:292 | Present bytes match `v9_m3_post_validation_audit.md:59-68`. Earlier citations reflect pre-freeze runs. **Status: Unsupported citation.** |
| `results/v9/manifests/cal_manifest_r2.json` | `49bf68b60f7dd76219a17383bdc829005f4dedb0fb1f1ed687ed23eb66fce9e0` | `b0161b8ea2008287744238be219f286bb346599efcd6a8d555abb6258566fa72` | `9154ec5a26...` in Rep 09:157, 10:97, 13:68, 74 | Present bytes match `v9_m2r2_protocol_amendment.md:95-97`. Disputed source bytes unverified. **Status: Unsupported citation.** |
| `results/v9/manifests/val_manifest_r1.json` | `72d9b98bda622d80db4c5aa8d9e4b1ce88f0bbc52d3bb26258917cea08959175` | `40ff489504ce628f954b735b562474474b746a2c38c65d459d1084b625909f1e` | `d6ae0837f6...` in Rep 09:158, 10:98, 13:75 | Present bytes match `v9_m3_post_validation_audit.md:59-68`. Disputed source bytes unverified. **Status: Unsupported citation.** |

---

## 4. Root Cause Analysis of Citation Discrepancies

Temporal analysis of Git commit logs (`git log --diff-filter=A`) provides the exact explanation for the discrepancies:
1. **Pre-Artifact Documentation Phase:** Reports 09, 10, and 13 were authored and checked into Git during early drafting phases before the final frozen simulation runs were executed and archived.
2. **Intermediate Draft Runs:** Historical citations reflect intermediate or preliminary simulation outputs that were superseded during validation runs (as noted in `docs/v9_m3_post_validation_audit.md:85-99`).
3. **Definitive Freeze Commit:** Commit `74f93fe2613221c476828d1558c03d0598c06b7e` is the authoritative commit that introduced the actual calibration and validation result artifacts into version control. The internal producer inventories generated at run time directly match the files in this commit.

---

## 5. Disposition & Approval Requirements

To transition this erratum from `DRAFT — NOT APPROVED` to effective status, the following formal actions must be taken:
1. **Owner Decision:** Formally record in `V9_M4_OWNER_DECISION_REGISTER.md` that historical citations in Reports 09, 10, 13, 19, and 20 represent non-controlling preliminary drafts.
2. **Research Integrity Approval:** An independent reviewer must verify that no cherry-picking occurred and confirm that commit `74f93fe` artifacts are authentic.
3. **Staging Manifest Reconciliation:** Populate the controlling Staging Manifest using exclusively the verified raw and canonical digests, explicitly bound to commit `74f93fe`.

**Sign-off Record:**
- Owner Approval: `UNAPPROVED`
- Research Integrity Reviewer: `PENDING REVIEW`
- Gate B Status: `LOCKED — GATE_B_NOT_AUTHORIZED`
