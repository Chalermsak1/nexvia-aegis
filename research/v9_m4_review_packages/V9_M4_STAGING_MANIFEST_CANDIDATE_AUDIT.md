# V9-M4 Staging Manifest Candidate Audit Specification

**Audit Revision:** 1.0 (Post-Remediation Candidate Baseline)  
**Date:** 2026-10-28 (Asia/Bangkok)  
**Milestone:** NEXVIA AEGIS V9-M4 — Autonomous Safety & Research Integrity Verification Subsystem  
**Governance Status:** `BLOCKED — GATE_B_NOT_AUTHORIZED`  
**Authority:** Research Engineering Candidate Audit Specification (Pending Owner Final Freeze & Gate B Authorization)  

---

## 1. Candidate Scope & Provenance

| Field | Authenticated Value | Verification Status |
| :--- | :--- | :--- |
| **Active Branch / Base HEAD** | `main` @ `a37d1d9bc93cf5ed60c702a2c753b74f925b6bf2` | Git tracked |
| **Historical Release Baseline** | `bc440151545aad6795902b285972faac7534c92e` | Historical reference only |
| **Calibration/Validation Freeze** | `74f93fe2613221c476828d1558c03d0598c06b7e` | Internal producer inventory corroborated |
| **Test Suite Baseline** | **307 / 307 Passed** (0 failures, 29.39s) | Verified via `uv run pytest` |
| **Synthetic Security Test Baseline** | **9 / 9 Passed** (0 failures, 0.11s) | Verified via `uv run pytest research/v9_m4_synthetic_test_drafts/` |
| **Evaluation Mode** | Synthetic Regression / Preflight Only | **Holdout Reserved Data Inaccessible** |

---

## 2. Candidate-Bound Artifact Inventory (Post-Remediation Verified Digests)

Every release-critical component has been audited for both exact raw byte SHA-256 and canonical payload SHA-256 where defined:

| Artifact Path | Raw File SHA-256 | Canonical Payload SHA-256 | Verification / Role |
| :--- | :--- | :--- | :--- |
| `experiments/v9_evaluate_holdout.py` | `fc459dbe9afc2f683804edde114e070d6413056a4ff9de4be27a52f7d2609a21` | N/A (Python source) | Remediated H1–H5 evaluator, strict expected_n check, scoped claims |
| `src/nexvia_aegis/security/launcher.py` | `cd35d855cf98f6b263ac3e4debcd46ad4586ca8bf98ec118ebf3e491511847cc` | N/A (Python source) | Gate B Partition Launcher, fail-closed pre-claim guards |
| `src/nexvia_aegis/security/runtime_integrity.py` | `0ecb8e480c7be3bfbf9e6861029d1909bb9a79e3f29ea216ce2b1c65a1a11a7c` | N/A (Python source) | Environment & RECORD integrity probe |
| `src/nexvia_aegis/security/ledger.py` | `56bfb3dc03285df555e411ce060de27eb6bdafbf8a72d562c7f1b7c44603f22a` | N/A (Python source) | Persistent Anti-Replay Ledger |
| `src/nexvia_aegis/security/verifier.py` | `491430bcda2aa31b75fa2ce0f098583fe8994ec41d8b1d0dd9b9a04af41986a1` | N/A (Python source) | Gate B Ticket Verifier |
| `src/nexvia_aegis/security/canonical.py` | `b7636b32b7376751f4dedbb93a53bb946878425742c0adc7dbf1fc60d09b1827` | N/A (Python source) | RFC 8785 Canonical JSON Serialization |
| `scripts/tools/sign_gate_b_ticket.py` | `1610a72c85a9c2447f6c37bf5d330732240592c77cb9083a8735c28a7b63f95e` | N/A (Python source) | Owner ticket signing utility |
| `scripts/tools/run_gate_b_launcher.py` | `3fccb784e3f564af938bde7cbc870ac2534fdc96941f4328adacca21d1f5db3c` | N/A (Python source) | Launcher entrypoint script |
| `uv.lock` | `f90654ab95d7b7c543179fc64fe666a912e10f5c9b2e3d72bb9223f2a7e3c2aa` | N/A (Lockfile) | Frozen dependency tree |
| `results/v9/cal_r2/selected_policy.json` | `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` | `1e3706ee5d3ef46c745a3e803fa5c2a713903096e146bedef01e725fd5dccba4` | Frozen candidate policy (`V9_CAND_1_TIER1_STRICTEST`) |
| `tests/test_v9_holdout_preflight.py` | `2cfda4b42ff9900a0b542b6a25429cfc77118baba9fb37a1a580f150c1d9947d` | N/A (Python test) | 71 confirmatory preflight regression tests |
| `research/v9_m4_synthetic_test_drafts/test_synthetic_security_controls.py` | `132849bd60a6f2644cdbac1d755132dbe508366067ae31cb5c4e12aa199e5833` | N/A (Python test) | 9 isolated synthetic security control tests |

---

## 3. Statistical Protocol & Decision Register Mapping

All seven scientific blocker decisions (SCI-01 through SCI-07) have been implemented and verified via automated regression tests:
- **SCI-01 ($H_1$ Option A):** Verified by `test_65` (boundary tests at $M=59$, $M=503$, $M=504$).
- **SCI-02 ($H_2$ Gate):** Verified by `test_65` (fails closed with `BLOCKED_BY_H1_GATE` when $H_1$ fails).
- **SCI-03 ($H_3$ Primary Baseline):** Verified by `test_66` (mandatory V8.1 primary baseline; V7 auxiliary).
- **SCI-04 ($H_4$ Compound Fault):** Verified by `test_68` (4 compound scenarios, matched McNemar + bootstrap CI).
- **SCI-05 ($H_5$ Worst-Case Safety):** Verified by `test_69` (Berger IUT incidence + explicit $M_s=0$ undefined selective risk reporting).
- **SCI-06 (Evidence Verification):** Verified by `test_67` (strict `expected_n` verification against registered partition).
- **SCI-07 (Claim Multiplicity):** Verified by `test_70` (mixture classification scoped to `MIXTURE_CERTIFIED_OPERATIONAL_IMPROVEMENT`; aggregate system claims withheld until full evaluation).

---

## 4. Preserved Boundary & Gate B Governance

1. **Gate B Locked:** Under no circumstances should live Holdout data (`results/v9/manifests/test_*.json`), production private keys, or reserved simulation seeds be loaded or accessed.
2. **Preflight Boundary:** All test executions documented in this audit operated strictly using synthetic fixtures and ephemeral temporary directories.
3. **Release Approval Sequence:**
   - Formal Owner approval of `V9_M4_OWNER_DECISION_REGISTER.md`.
   - Security Reviewer sign-off on SEC-01 through SEC-05.
   - Independent Statistician sign-off on SCI-01 through SCI-07.
   - Detached verification worktree execution at the designated candidate commit.
