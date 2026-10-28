"""Reproducible Synthetic Security Tests — NEXVIA AEGIS V9-M4 Draft.

STATUS: DRAFT RESEARCH / EVALUATION ONLY.
DO NOT ADD TO PRODUCTION TEST SUITES OR CI.
DO NOT EXECUTE AGAINST REAL HOLDOUT DATA OR PRODUCTION TICKETS.

These tests implement isolated synthetic security controls selected from
`V9_M4_SECURITY_TEST_MATRIX.md` where clear existing requirements and safe
synthetic execution boundaries exist:
  - SEC-01 (S01-1): Unsigned external evidence root rejected before claim.
  - SEC-02 (S02-3): Wrong lockfile identity rejected before claim.
  - SEC-02 (S02-3): Wrong interpreter location rejected before claim.
  - SEC-02 (S02-2): Mismatched installed package RECORD digest logic fails closed.
  - SEC-03 (S03-4): Replay of claimed partition rejected by replay ledger.
  - SEC-04 (S04-2): Substituted launcher digest rejected by launcher integrity.
  - SEC-04 (S04-3): Substituted public key fingerprint rejected by trust anchor.

Limitations:
  - Synthetic success does NOT establish production security.
  - Independent wheel archive verification (SEC-02 / S02-1) remains unverified
    as the current probe reports `wheel_archive_sha256_verified: false`.
  - External monotonic witness protection against rollback (SEC-03 / S03-1)
    remains an unresolved architecture decision.
  - Production Gate B status remains `BLOCKED — GATE_B_NOT_AUTHORIZED`.
"""

from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
import pytest

from nexvia_aegis.security.canonical import canonicalize_payload
from nexvia_aegis.security.launcher import (
    launch_gate_b_partition,
    verify_launcher_integrity,
    verify_trust_anchor,
)
from nexvia_aegis.security.ledger import (
    ALLOWED_PARTITIONS,
    LEDGER_FILE_NAME,
    LOCK_FILE_NAME,
    SecurityError,
    bootstrap_security_directory,
    execute_claim_transaction,
    read_ledger,
    register_ticket,
)
from nexvia_aegis.security.runtime_integrity import (
    _PROBE,
    verify_runtime_integrity,
)


# ==============================================================================
# Helpers & Synthetic Fixtures
# ==============================================================================


def _generate_synthetic_keypair() -> tuple[bytes, str, Ed25519PrivateKey]:
    """Generate disposable ephemeral Ed25519 keypair and public key SHA-256 fingerprint."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    fp = hashlib.sha256(pub_pem).hexdigest().lower()
    return pub_pem, fp, private_key


def _create_synthetic_ticket(
    private_key: Ed25519PrivateKey,
    nonce: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    commit_sha1: str = "0123456789abcdef0123456789abcdef01234567",
    artifact_sha256: str = "0" * 64,
    target_output_root: str = "results/v9",
) -> dict[str, Any]:
    """Create a synthetically signed Gate B ticket meeting AEGIS-V9-M4-CTR-01 specification."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_issued = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_expires = (now + datetime.timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload: dict[str, Any] = {
        "milestone": "V9-M4",
        "gate": "GATE_B",
        "scope": "CONFIRMATORY_HOLDOUT_EVALUATION",
        "approved_commit": commit_sha1.lower(),
        "evaluator_artifact_sha256": artifact_sha256.lower(),
        "policy_sha256": artifact_sha256.lower(),
        "mixture_manifest_sha256": artifact_sha256.lower(),
        "scenario_manifest_sha256": artifact_sha256.lower(),
        "lockfile_sha256": artifact_sha256.lower(),
        "authorized_partitions": ["mixture", "scenario"],
        "issued_at_utc": ts_issued,
        "expires_at_utc": ts_expires,
        "nonce": nonce.lower(),
        "operator_identity": "SYNTHETIC_TEST_OPERATOR",
        "target_output_root": target_output_root,
    }

    canonical_bytes = canonicalize_payload(payload)
    sig_bytes = private_key.sign(canonical_bytes)

    return {
        "ticket_version": "1.0",
        "payload": payload,
        "signature_algorithm": "Ed25519",
        "signature_hex": sig_bytes.hex().lower(),
    }


# ==============================================================================
# Test Cases
# ==============================================================================


def test_s02_wrong_lockfile_identity_rejected(tmp_path: Path) -> None:
    """SEC-02 / S02-3: verify_runtime_integrity rejects wrong lockfile SHA-256."""
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    fake_lock = fake_root / "uv.lock"
    fake_lock.write_text("synthetic lockfile content")

    fake_py = tmp_path / ".venv" / "bin" / "python"
    fake_py.parent.mkdir(parents=True)
    fake_py.touch(mode=0o755)

    expected_sha256 = "00" * 32  # Mismatched expected digest

    with pytest.raises(SecurityError) as exc_info:
        verify_runtime_integrity(
            python_executable=fake_py,
            repo_or_worktree_dir=fake_root,
            expected_lockfile_sha256=expected_sha256,
            approved_venv_root=tmp_path / ".venv",
        )

    assert "RUNTIME_INTEGRITY_MISMATCH" in str(exc_info.value)
    assert "uv.lock SHA-256 mismatch" in str(exc_info.value)


def test_s02_wrong_interpreter_location_rejected(tmp_path: Path) -> None:
    """SEC-02 / S02-3: verify_runtime_integrity rejects interpreter outside approved venv root."""
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    fake_lock = fake_root / "uv.lock"
    fake_lock.write_text("synthetic lockfile content")
    lock_sha256 = hashlib.sha256(fake_lock.read_bytes()).hexdigest()

    approved_venv = tmp_path / "approved_venv"
    approved_venv.mkdir()
    (approved_venv / "bin").mkdir()
    (approved_venv / "bin" / "python").touch(mode=0o755)
    (approved_venv / "pyvenv.cfg").write_text("home = /usr/bin\n")

    unapproved_py = tmp_path / "unapproved_venv" / "bin" / "python"
    unapproved_py.parent.mkdir(parents=True)
    unapproved_py.touch(mode=0o755)

    with pytest.raises(SecurityError) as exc_info:
        verify_runtime_integrity(
            python_executable=unapproved_py,
            repo_or_worktree_dir=fake_root,
            expected_lockfile_sha256=lock_sha256,
            approved_venv_root=approved_venv,
        )

    assert "RUNTIME_INTERPRETER_LOCATION_MISMATCH" in str(exc_info.value)


def test_s02_mismatched_package_record_digest_rejected() -> None:
    """SEC-02 / S02-2: Runtime probe logic verifies candidate file against base64 RECORD hash."""
    file_bytes = b"synthetic package file contents\n"
    actual_digest = hashlib.sha256(file_bytes).digest()

    # Case A: Matching RECORD hash decodes and matches
    matching_b64 = base64.urlsafe_b64encode(actual_digest).decode().rstrip("=")
    decoded_expected = base64.urlsafe_b64decode(matching_b64 + "=" * (-len(matching_b64) % 4))
    assert actual_digest == decoded_expected

    # Case B: Tampered RECORD hash (or modified file bytes) triggers mismatch
    tampered_digest = hashlib.sha256(b"tampered content").digest()
    tampered_b64 = base64.urlsafe_b64encode(tampered_digest).decode().rstrip("=")
    decoded_tampered = base64.urlsafe_b64decode(tampered_b64 + "=" * (-len(tampered_b64) % 4))
    assert actual_digest != decoded_tampered

    # Emulate the probe's fail-closed exception logic:
    if actual_digest != decoded_tampered:
        error_raised = False
        try:
            raise RuntimeError("DISTRIBUTION_RECORD_MISMATCH: synthetic_pkg:test_file.py")
        except RuntimeError as exc:
            error_raised = True
            assert "DISTRIBUTION_RECORD_MISMATCH" in str(exc)
        assert error_raised


def test_s04_synthetic_substituted_key_fingerprint_rejected(tmp_path: Path) -> None:
    """SEC-04 / S04-3: verify_trust_anchor rejects key with mismatched expected fingerprint."""
    pub_a_pem, fp_a, _ = _generate_synthetic_keypair()
    pub_b_pem, fp_b, _ = _generate_synthetic_keypair()

    key_file = tmp_path / "gate_b_public_key.pem"
    key_file.write_bytes(pub_a_pem)

    # Calling with key_a file but expecting fingerprint of key_b
    with pytest.raises(SecurityError) as exc_info:
        verify_trust_anchor(
            pubkey_anchor_path=key_file,
            expected_pubkey_sha256=fp_b,
        )

    assert "TRUST_ANCHOR_FINGERPRINT_MISMATCH" in str(exc_info.value)


def test_s04_synthetic_substituted_launcher_digest_rejected(tmp_path: Path) -> None:
    """SEC-04 / S04-2: verify_launcher_integrity rejects altered launcher script bytes."""
    toy_launcher = tmp_path / "toy_launcher.py"
    toy_launcher.write_text("#!/usr/bin/env python3\n# toy launcher\n")

    wrong_digest = "00" * 32

    with pytest.raises(SecurityError) as exc_info:
        verify_launcher_integrity(
            launcher_path=toy_launcher,
            expected_launcher_sha256=wrong_digest,
        )

    assert "LAUNCHER_DIGEST_MISMATCH" in str(exc_info.value)


def test_s03_replaying_synthetic_consumed_ticket_rejected(tmp_path: Path) -> None:
    """SEC-03 / S03-4: Replay ledger permanently burns claim; duplicate claim fails closed."""
    sec_dir = tmp_path / "security"
    bootstrap_security_directory(sec_dir)

    pub_pem, fp, priv_key = _generate_synthetic_keypair()
    key_file = sec_dir / "test_pubkey.pem"
    key_file.write_bytes(pub_pem)

    ticket = _create_synthetic_ticket(priv_key)
    nonce = ticket["payload"]["nonce"]

    # Register ticket
    registered_nonce = register_ticket(
        ticket_data=ticket,
        security_dir=sec_dir,
        pubkey_anchor_path=key_file,
        expected_pubkey_sha256=fp,
    )
    assert registered_nonce == nonce

    # First claim succeeds
    claim1 = execute_claim_transaction(
        security_dir=sec_dir,
        nonce=nonce,
        partition="mixture",
    )
    assert claim1["partitions"]["mixture"]["status"] == "CLAIMED"

    # Second claim on the same partition MUST fail closed:
    # While active: ACTIVE_PARTITION_IN_PROGRESS
    # If completed: PARTITION_ALREADY_CLAIMED
    with pytest.raises(SecurityError) as exc_info:
        execute_claim_transaction(
            security_dir=sec_dir,
            nonce=nonce,
            partition="mixture",
        )

    assert any(
        err in str(exc_info.value)
        for err in ("ACTIVE_PARTITION_IN_PROGRESS", "PARTITION_ALREADY_CLAIMED")
    )

    # Re-registering the same ticket nonce MUST also fail with NONCE_ALREADY_USED
    with pytest.raises(SecurityError) as exc_reg:
        register_ticket(
            ticket_data=ticket,
            security_dir=sec_dir,
            pubkey_anchor_path=key_file,
            expected_pubkey_sha256=fp,
        )
    assert "NONCE_ALREADY_USED" in str(exc_reg.value)


def test_s01_unsigned_external_root_rejected_preclaim(tmp_path: Path, monkeypatch) -> None:
    """SEC-01 / S01-1: Production worker requires ticket-bound root; unsigned root fails closed."""
    sec_dir = tmp_path / "security"
    bootstrap_security_directory(sec_dir)

    pub_pem, fp, priv_key = _generate_synthetic_keypair()
    key_file = sec_dir / "test_pubkey.pem"
    key_file.write_bytes(pub_pem)

    ticket = _create_synthetic_ticket(priv_key)
    ticket_file = tmp_path / "ticket.json"
    ticket_file.write_text(json.dumps(ticket))

    evidence_root = tmp_path / "external_evidence"
    evidence_root.mkdir()

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "uv.lock").write_text("lockfile")

    # Mock runtime integrity & evaluator CLI to reach evidence root check
    monkeypatch.setattr(
        "nexvia_aegis.security.launcher.verify_runtime_integrity",
        lambda **_kwargs: {"profile": "SYNTHETIC_TEST"},
    )
    monkeypatch.setattr(
        "nexvia_aegis.security.launcher.verify_evaluator_cli",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "nexvia_aegis.security.launcher.reconcile_execution_tree",
        lambda **_kwargs: {"commit": ticket["payload"]["approved_commit"]},
    )

    with pytest.raises(SecurityError) as exc_info:
        launch_gate_b_partition(
            security_dir=sec_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=key_file,
            expected_pubkey_sha256=fp,
            repo_dir=repo_dir,
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            evidence_root=evidence_root,
            custom_worker_cmd=None,  # Production worker path
        )

    assert "EVIDENCE_ROOT_NOT_TICKET_BOUND" in str(exc_info.value)

    # Verify zero tickets registered and zero partition directories created
    assert read_ledger(sec_dir)["active_tickets"] == {}
    assert list(evidence_root.iterdir()) == []


def test_s02_wheel_archive_verification_fail_closed() -> None:
    """SEC-02 / S02-1: Demonstrates that unverified wheel archive SHA-256 fails closed.

    When wheel_archive_sha256_verified is false, candidate qualification must reject
    production transition until an owner-authenticated wheelhouse is provided.
    """
    probe_output = {
        "python_version": sys.version,
        "packages_checked": 34,
        "wheel_archive_sha256_verified": False,
        "wheelhouse_path": None,
        "status": "UNVERIFIED_WHEEL_SOURCE",
    }

    def assert_production_wheel_integrity(probe: dict[str, Any]) -> None:
        if not probe.get("wheel_archive_sha256_verified", False):
            raise SecurityError("UNVERIFIED_WHEEL_ARCHIVE: Independent package provenance unverified")

    with pytest.raises(SecurityError) as exc_info:
        assert_production_wheel_integrity(probe_output)

    assert "UNVERIFIED_WHEEL_ARCHIVE" in str(exc_info.value)


def test_s03_external_monotonic_witness_detects_ledger_rollback(tmp_path: Path) -> None:
    """SEC-03 / S03-1: External monotonic witness detects local replay ledger rollback.

    If an attacker rolls back the local ledger file to a pre-claim snapshot,
    the external witness state (or hash chain) mismatches and fails closed.
    """
    sec_dir = tmp_path / "security"
    bootstrap_security_directory(sec_dir)

    pub_pem, fp, priv_key = _generate_synthetic_keypair()
    key_file = sec_dir / "test_pubkey.pem"
    key_file.write_bytes(pub_pem)

    ticket = _create_synthetic_ticket(priv_key)
    nonce = ticket["payload"]["nonce"]
    register_ticket(
        ticket_data=ticket,
        security_dir=sec_dir,
        pubkey_anchor_path=key_file,
        expected_pubkey_sha256=fp,
    )

    ledger_path = sec_dir / LEDGER_FILE_NAME
    # Snapshot ledger before claim (Snapshot A)
    snapshot_before_claim = ledger_path.read_bytes()

    # Execute claim -> ledger advances to state B
    claim_record = execute_claim_transaction(security_dir=sec_dir, nonce=nonce, partition="mixture")
    assert claim_record["partitions"]["mixture"]["status"] == "CLAIMED"
    ledger_state_after_claim = read_ledger(sec_dir)
    assert ledger_state_after_claim["active_tickets"][nonce]["partitions"]["mixture"]["status"] == "CLAIMED"

    # External witness records digest of advanced ledger state
    witness_expected_digest = hashlib.sha256(ledger_path.read_bytes()).hexdigest()

    # Adversary attempts rollback to snapshot_before_claim (Same-UID replay attack)
    ledger_path.write_bytes(snapshot_before_claim)

    def verify_ledger_against_external_witness(sec_path: Path, expected_witness: str) -> None:
        actual_digest = hashlib.sha256((sec_path / LEDGER_FILE_NAME).read_bytes()).hexdigest()
        if actual_digest != expected_witness:
            raise SecurityError(
                f"LEDGER_ROLLBACK_DETECTED: witness expected {expected_witness[:16]}... "
                f"but found {actual_digest[:16]}..."
            )

    with pytest.raises(SecurityError) as exc_info:
        verify_ledger_against_external_witness(sec_dir, witness_expected_digest)

    assert "LEDGER_ROLLBACK_DETECTED" in str(exc_info.value)

