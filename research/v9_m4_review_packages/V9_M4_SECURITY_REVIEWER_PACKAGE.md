# V9-M4 Security Reviewer Package

**Review Status:** `READY FOR QUALIFIED SECURITY REVIEW — PENDING DECISIONS`
**Gate B Disposition:** `BLOCKED — GATE_B_NOT_AUTHORIZED`
**Date:** 2026-10-28 (Asia/Bangkok)

---

## 1. Reviewer Overview & Scope

This package compiles the necessary security contracts, technical gap analyses, and testing matrices for the independent security reviewer evaluating the execution integrity and release assurance of NEXVIA AEGIS V9-M4.

**Required Reference Documents:**
1. `docs/reports/v9_m4_release_remediation/V9_M4_SECURITY_TEST_MATRIX.md` (preserved in commit `822c1b2e7e89b5850d2ddbb616c89acf00e0573e`)
2. `docs/reports/v9_m4_release_remediation/V9_M4_PACKAGE_RUNTIME_PROVENANCE_INVENTORY.md` (preserved in commit `822c1b2e7e89b5850d2ddbb616c89acf00e0573e`)
3. `docs/reports/v9_m4_release_remediation/V9_M4_RUNTIME_TRUST_GAP_REPORT.md` (preserved in commit `822c1b2e7e89b5850d2ddbb616c89acf00e0573e`)
4. [`docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md)
5. Security contract: [`docs/architecture/v9_m4_signed_gate_b_ticket_implementation_contract.md`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/docs/architecture/v9_m4_signed_gate_b_ticket_implementation_contract.md)
6. Security implementation:
   - [`src/nexvia_aegis/security/launcher.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/nexvia_aegis/security/launcher.py)
   - [`src/nexvia_aegis/security/ledger.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/nexvia_aegis/security/ledger.py)
   - [`src/nexvia_aegis/security/verifier.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/nexvia_aegis/security/verifier.py)
   - [`src/nexvia_aegis/security/runtime_integrity.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/nexvia_aegis/security/runtime_integrity.py)

---

## 2. Five Critical Security Decisions Requiring Independent Review

### SEC-01: Signed Durable Evidence-Root Binding (Priority: P0)
- **Current State:** Ticket v1 signs literal `"results/v9"`. The production launcher deliberately fails closed with `EVIDENCE_ROOT_NOT_TICKET_BOUND` when an external, operator-supplied evidence directory is provided.
- **Review Decision:**
  - Option A: Signed path + volume/filesystem identifier in Ticket v2 schema.
  - Option B: Signed content-addressable storage identifier.
- **Reviewer Action:** Review proposed Ticket v2 schema changes and confirm that no production claim can be executed against an unsigned or mutable directory.

### SEC-02: Independent Package & Runtime Provenance (Priority: P0)
- **Current State:**
  - The runtime probe (`src/nexvia_aegis/security/runtime_integrity.py`) validates local consistency (lockfile hash, virtual environment path, dependency versions, installed RECORD file hashes, and import origins).
  - The probe explicitly returns `wheel_archive_sha256_verified: false` (`:232`).
  - No independent wheelhouse or signed build/install attestation exists in the repository.
- **Review Decision:**
  - Option A: Owner-controlled offline wheelhouse with explicit platform tags and raw SHA-256 digests.
  - Option B: Separately authenticated signed build/install attestation.
- **Reviewer Action:** Evaluate whether local RECORD consistency is acceptable for interim testing, or require an authenticated wheelhouse before any release candidate designation.

### SEC-03: Replay Ledger Rollback & Monotonic Witness (Priority: P0)
- **Current State:**
  - `GateBLedger` provides strict POSIX flock, atomic replacement (`rename`), directory sync, and monotonic nonces.
  - However, within the same UID, an adversary with filesystem write access can restore an earlier, valid version of `ledger.json` (local rollback).
- **Review Decision:**
  - Option A: External append-only monotonic witness service.
  - Option B: Write-once storage media / HSM transaction witness.
  - Option C: Formal risk acceptance of same-UID local rollback residual risk.
- **Reviewer Action:** Review threat boundary definitions in contract (`:90-98, 534-541`) and specify required witness architecture.

### SEC-04: Candidate-Bound Tool & Public Key Authentication (Priority: P1)
- **Current State:**
  - Launcher validates Git HEAD and cleanliness, but relies on expected values supplied by the caller.
  - Trust anchor public key fingerprint is checked, but if both key and expected fingerprint are supplied by an untrusted caller, circular trust occurs.
- **Review Decision:**
  - Independent pinning of complete toolset (launcher, signer, verifier, canonicalizer, ledger, runtime probe).
  - Out-of-band trust anchor public key distribution outside the git repository.
- **Reviewer Action:** Review and approve the complete tool and public key pin inventory.

### SEC-05: Signer Identity, Key Custody, and Revocation (Priority: P1)
- **Current State:** Signer supports unencrypted and passphrase-protected Ed25519 PEM keys. No formal revocation list or key rotation protocol is implemented.
- **Review Decision:**
  - Select key custody model (Model A: out-of-band HSM/air-gapped; Model B: passphrase-protected local; Model C: unencrypted local with UID controls).
  - Define formal revocation authority and incident handling checklist.
- **Reviewer Action:** Audit the signing ceremony procedure and approve key lifecycle protocols.

---

## 3. Synthetic Security Test Evidence

A dedicated, isolated synthetic security test suite has been prepared under:
[`research/v9_m4_synthetic_test_drafts/test_synthetic_security_controls.py`](file:///Users/chalermsak/Desktop/nexvia-aegis-main/research/v9_m4_synthetic_test_drafts/test_synthetic_security_controls.py)

**Executed Synthetic Tests (9/9 Passed):**
1. `test_s02_wrong_lockfile_identity_rejected`: Rejection of mismatched `uv.lock` SHA-256 (`RUNTIME_INTEGRITY_MISMATCH`).
2. `test_s02_wrong_interpreter_location_rejected`: Rejection of interpreter outside approved venv (`RUNTIME_INTERPRETER_LOCATION_MISMATCH`).
3. `test_s02_mismatched_package_record_digest_rejected`: Fail-closed detection of tampered package file against RECORD hash.
4. `test_s04_synthetic_substituted_key_fingerprint_rejected`: Rejection of mismatched public key fingerprint (`TRUST_ANCHOR_FINGERPRINT_MISMATCH`).
5. `test_s04_synthetic_substituted_launcher_digest_rejected`: Rejection of altered launcher script bytes (`LAUNCHER_DIGEST_MISMATCH`).
6. `test_s03_replaying_synthetic_consumed_ticket_rejected`: Rejection of replay of active partition (`ACTIVE_PARTITION_IN_PROGRESS`) and duplicate nonce reuse (`NONCE_ALREADY_USED`).
7. `test_s01_unsigned_external_root_rejected_preclaim`: Enforcement that production worker with external root fails closed before ticket registration or claim (`EVIDENCE_ROOT_NOT_TICKET_BOUND`).
8. `test_s02_wheel_archive_verification_fail_closed`: Enforcement that unverified wheel archive fails closed before production execution (`UNVERIFIED_WHEEL_ARCHIVE`).
9. `test_s03_external_monotonic_witness_detects_ledger_rollback`: Detection of local replay ledger rollback via external monotonic witness hash verification (`LEDGER_ROLLBACK_DETECTED`).

*Verification note:* These tests run outside default `pytest` discovery (`testpaths = ["tests"]`). They execute strictly with ephemeral in-memory fixtures and temporary directories. No production tickets, signing keys, or Holdout data are accessed.

---

## 4. Current Reviewer Status

- Independent Security Reviewer Assigned: `PENDING APPOINTMENT`
- Formal Security Review Approval: `NONE RECORDED`
- Recommendation: Maintain `BLOCKED — GATE_B_NOT_AUTHORIZED` until SEC-01 through SEC-05 are formally approved.
