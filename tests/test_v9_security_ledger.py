"""Tests for Persistent Anti-Replay Ledger and Bootstrap Utility.

Verifies one-time bootstrap, lock file inode stability, atomic crash-durable updates,
ticket registration, sequential partition lifecycle, mutual exclusion, under-lock expiry,
and stranded claim terminal lockout per Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nexvia_aegis.security.canonical import canonicalize_payload
from nexvia_aegis.security.ledger import (
    LOCK_FILE_NAME,
    LEDGER_FILE_NAME,
    PersistentLedgerLock,
    SecurityError,
    bootstrap_security_directory,
    execute_claim_transaction,
    execute_outcome_transaction,
    read_ledger,
    reconcile_stranded_claim,
    register_ticket,
    resolve_security_dir,
)


@pytest.fixture
def dummy_ed25519_keypair():
    """Generates an ephemeral, dynamic Ed25519 keypair for unit testing."""
    privkey = Ed25519PrivateKey.generate()
    pubkey = privkey.public_key()
    return privkey, pubkey


from datetime import datetime, timedelta, timezone

@pytest.fixture
def sample_ticket_factory(dummy_ed25519_keypair):
    """Factory creating valid signed ticket envelopes with custom nonces/timestamps."""
    privkey, pubkey = dummy_ed25519_keypair

    def _create(
        nonce: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        issued_at: str | None = None,
        expires_at: str | None = None,
        milestone: str = "V9-M4",
    ):
        now = datetime.now(timezone.utc)
        if issued_at is None:
            issued_at = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if expires_at is None:
            expires_at = (now + timedelta(minutes=55)).strftime("%Y-%m-%dT%H:%M:%SZ")

        payload = {
            "milestone": milestone,
            "gate": "GATE_B",
            "scope": "CONFIRMATORY_HOLDOUT_EVALUATION",
            "approved_commit": "c511a0bcae93ed969ffb50504017ca2be88fde95",
            "evaluator_artifact_sha256": "4b83f090b82f8d2eb929a75ff72d9a48970891d4e08f8702c89280d463b7852c",
            "policy_sha256": "5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2",
            "mixture_manifest_sha256": "70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db",
            "scenario_manifest_sha256": "55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d",
            "lockfile_sha256": "345628a865b28e9c5422fd4bc52fd6e23864bd58feaa4b418e8389192c0e7d56",
            "authorized_partitions": ["mixture", "scenario"],
            "issued_at_utc": issued_at,
            "expires_at_utc": expires_at,
            "nonce": nonce,
            "operator_identity": "test_operator@chalermsak",
            "target_output_root": "results/v9",
        }
        canonical_bytes = canonicalize_payload(payload)
        sig_bytes = privkey.sign(canonical_bytes)
        return {
            "ticket_version": "1.0",
            "payload": payload,
            "signature_algorithm": "Ed25519",
            "signature_hex": sig_bytes.hex().lower(),
        }, pubkey

    return _create


# ==============================================================================
# 1. Bootstrap Utility Tests
# ==============================================================================

class TestBootstrapUtility:
    def test_first_time_bootstrap_success(self, tmp_path):
        sec_dir = tmp_path / "test_sec"
        lock_path, ledger_path = bootstrap_security_directory(sec_dir)

        assert lock_path.exists()
        assert ledger_path.exists()
        assert (lock_path.stat().st_mode & 0o777) == 0o600
        assert (ledger_path.stat().st_mode & 0o777) == 0o600

        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.0"
        assert data["active_tickets"] == {}
        assert data["historical_nonces"] == []

    def test_bootstrap_rejection_when_already_initialized(self, tmp_path):
        sec_dir = tmp_path / "test_sec"
        bootstrap_security_directory(sec_dir)

        with pytest.raises(SecurityError, match="SECURITY_DIR_ALREADY_INITIALIZED"):
            bootstrap_security_directory(sec_dir)

    def test_bootstrap_rejection_when_only_lock_exists(self, tmp_path):
        sec_dir = tmp_path / "test_sec"
        sec_dir.mkdir(parents=True)
        (sec_dir / LOCK_FILE_NAME).touch()

        with pytest.raises(SecurityError, match="SECURITY_DIR_ALREADY_INITIALIZED"):
            bootstrap_security_directory(sec_dir)

    def test_bootstrap_rejection_when_only_ledger_exists(self, tmp_path):
        sec_dir = tmp_path / "test_sec"
        sec_dir.mkdir(parents=True)
        (sec_dir / LEDGER_FILE_NAME).touch()

        with pytest.raises(SecurityError, match="SECURITY_DIR_ALREADY_INITIALIZED"):
            bootstrap_security_directory(sec_dir)

    def test_bootstrap_symlink_security_dir_rejected(self, tmp_path):
        real_dir = tmp_path / "real_sec"
        real_dir.mkdir()
        symlink_dir = tmp_path / "symlink_sec"
        symlink_dir.symlink_to(real_dir)

        with pytest.raises(SecurityError, match="SYMLINK_SECURITY_DIR_REJECTED"):
            bootstrap_security_directory(symlink_dir)

    def test_bootstrap_cli_script(self, tmp_path):
        sec_dir = tmp_path / "cli_sec"
        script = Path("scripts/tools/setup_gate_b_ledger.py")

        # First run succeeds
        res1 = subprocess.run(
            [sys.executable, str(script), "--security-dir", str(sec_dir)],
            capture_output=True,
            text=True,
        )
        assert res1.returncode == 0
        assert "INITIALIZATION_SUCCESSFUL" in res1.stdout

        # Second run fails closed
        res2 = subprocess.run(
            [sys.executable, str(script), "--security-dir", str(sec_dir)],
            capture_output=True,
            text=True,
        )
        assert res2.returncode == 1
        assert "SECURITY_DIR_ALREADY_INITIALIZED" in res2.stderr


# ==============================================================================
# 2. Lock & Inode Stability Tests
# ==============================================================================

class TestLockAndLedgerIntegrity:
    def test_missing_lock_file_fails_closed(self, tmp_path):
        sec_dir = tmp_path / "sec"
        sec_dir.mkdir()
        # No lock file created
        with pytest.raises(SecurityError, match="CORRUPTED_OR_MISSING_LEDGER"):
            with PersistentLedgerLock(sec_dir):
                pass

    def test_symlinked_lock_file_rejected(self, tmp_path):
        sec_dir = tmp_path / "sec"
        sec_dir.mkdir()
        real_file = tmp_path / "real_lock"
        real_file.touch()
        (sec_dir / LOCK_FILE_NAME).symlink_to(real_file)

        with pytest.raises(SecurityError, match="SYMLINK_LOCK_REJECTED"):
            with PersistentLedgerLock(sec_dir):
                pass

    def test_missing_ledger_file_fails_closed(self, tmp_path):
        sec_dir = tmp_path / "sec"
        sec_dir.mkdir()
        (sec_dir / LOCK_FILE_NAME).touch()
        os.chmod(sec_dir / LOCK_FILE_NAME, 0o600)

        with pytest.raises(SecurityError, match="CORRUPTED_OR_MISSING_LEDGER"):
            read_ledger(sec_dir)

    def test_corrupted_json_ledger_fails_closed(self, tmp_path):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)
        (sec_dir / LEDGER_FILE_NAME).write_text("{corrupt json!!", encoding="utf-8")

        with pytest.raises(SecurityError, match="CORRUPTED_OR_MISSING_LEDGER"):
            read_ledger(sec_dir)

    def test_lock_inode_stability_during_updates(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        lock_path = sec_dir / LOCK_FILE_NAME
        initial_inode = lock_path.stat().st_ino

        ticket, pubkey = sample_ticket_factory()
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # Inode of stable lock must remain identical
        assert lock_path.stat().st_ino == initial_inode


# ==============================================================================
# 3. Ticket Registration Lifecycle Tests
# ==============================================================================

class TestTicketRegistration:
    def test_successful_ticket_registration(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="a" * 64)
        nonce = register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        assert nonce == "a" * 64

        ledger = read_ledger(sec_dir)
        assert "a" * 64 in ledger["historical_nonces"]
        assert "a" * 64 in ledger["active_tickets"]

        entry = ledger["active_tickets"]["a" * 64]
        assert entry["ticket_state"] == "ISSUED"
        assert entry["active_partition"] is None
        assert entry["partitions"]["mixture"]["status"] == "UNCLAIMED"
        assert entry["partitions"]["scenario"]["status"] == "UNCLAIMED"

    def test_duplicate_ticket_registration_rejected(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="b" * 64)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        with pytest.raises(SecurityError, match="NONCE_ALREADY_USED"):
            register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

    def test_nonce_reuse_with_different_payload_rejected(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        reused_nonce = "c" * 64
        ticket1, pubkey1 = sample_ticket_factory(nonce=reused_nonce)
        register_ticket(ticket1, security_dir=sec_dir, public_key_obj=pubkey1)

        # Attempt to register second ticket with same nonce
        ticket2, pubkey2 = sample_ticket_factory(nonce=reused_nonce)
        with pytest.raises(SecurityError, match="NONCE_ALREADY_USED"):
            register_ticket(ticket2, security_dir=sec_dir, public_key_obj=pubkey2)

    def test_expired_ticket_registration_rejected(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        # Ticket expired in 2020
        ticket, pubkey = sample_ticket_factory(
            nonce="d" * 64,
            issued_at="2020-01-01T00:00:00Z",
            expires_at="2020-01-01T01:00:00Z",
        )
        with pytest.raises(SecurityError, match="TICKET_EXPIRED"):
            register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

    def test_cryptographically_invalid_ticket_rejected_before_ledger(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="e" * 64)
        ticket["signature_hex"] = "0" * 128  # Invalid signature

        with pytest.raises(SecurityError, match="INVALID_TICKET_SIGNATURE"):
            register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # Verify nonce was NOT added to ledger
        ledger = read_ledger(sec_dir)
        assert "e" * 64 not in ledger["historical_nonces"]


# ==============================================================================
# 4. Partition Claim Transaction & Concurrency Tests
# ==============================================================================

class TestClaimTransaction:
    def test_successful_claim_mixture(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="f" * 64)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        res = execute_claim_transaction(sec_dir, nonce="f" * 64, partition="mixture")
        assert res["ticket_state"] == "ACTIVE_PARTIAL"
        assert res["active_partition"] == "mixture"
        assert res["partitions"]["mixture"]["status"] == "CLAIMED"
        assert res["partitions"]["mixture"]["claimed_at_utc"] is not None

        # Verify on-disk ledger matches
        ledger = read_ledger(sec_dir)
        disk_entry = ledger["active_tickets"]["f" * 64]
        assert disk_entry["partitions"]["mixture"]["status"] == "CLAIMED"
        assert disk_entry["active_partition"] == "mixture"

    def test_duplicate_claim_same_partition_rejected(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="1" * 64)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce="1" * 64, partition="mixture")

        # Second claim attempt on same partition must fail
        with pytest.raises(SecurityError, match="ACTIVE_PARTITION_IN_PROGRESS"):
            execute_claim_transaction(sec_dir, nonce="1" * 64, partition="mixture")

    def test_concurrent_claim_other_partition_rejected_while_active(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="2" * 64)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # Claim mixture
        execute_claim_transaction(sec_dir, nonce="2" * 64, partition="mixture")

        # Attempt to claim scenario while mixture is actively executing must fail
        with pytest.raises(SecurityError, match="ACTIVE_PARTITION_IN_PROGRESS"):
            execute_claim_transaction(sec_dir, nonce="2" * 64, partition="scenario")

    def test_unregistered_ticket_claim_rejected(self, tmp_path):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        with pytest.raises(SecurityError, match="TICKET_NOT_REGISTERED"):
            execute_claim_transaction(sec_dir, nonce="9" * 64, partition="mixture")

    def test_under_lock_expired_ticket_rejected(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        # Register ticket with very short window that expires immediately
        ticket, pubkey = sample_ticket_factory(
            nonce="3" * 64,
            issued_at="2026-01-01T00:00:00Z",
            expires_at="2026-01-01T00:01:00Z",  # Expired in past
        )
        # Directly inject to test under-lock claim rejection
        with PersistentLedgerLock(sec_dir):
            ledger = read_ledger(sec_dir)
            ticket_entry = {
                "ticket_version": "1.0",
                "registered_at_utc": "2026-01-01T00:00:00Z",
                "issued_at_utc": "2026-01-01T00:00:00Z",
                "expires_at_utc": "2026-01-01T00:01:00Z",
                "ticket_state": "ISSUED",
                "active_partition": None,
                "partitions": {
                    "mixture": {"status": "UNCLAIMED", "claimed_at_utc": None},
                    "scenario": {"status": "UNCLAIMED", "claimed_at_utc": None},
                },
            }
            ledger["active_tickets"]["3" * 64] = ticket_entry
            from nexvia_aegis.security.ledger import _persist_ledger_crash_durable
            _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

        with pytest.raises(SecurityError, match="TICKET_EXPIRED_AT_CLAIM_BOUNDARY"):
            execute_claim_transaction(sec_dir, nonce="3" * 64, partition="mixture")


# ==============================================================================
# 5. Outcome Transactions and Full Two-Partition Lifecycle
# ==============================================================================

class TestOutcomeAndLifecycle:
    def test_two_partition_happy_path_to_closed(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "4" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # 1. Claim Mixture
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # 2. Complete Mixture with Exit Code 0
        t1 = execute_outcome_transaction(
            sec_dir,
            nonce=nonce,
            partition="mixture",
            exit_code=0,
            report_sha256="a" * 64,
            worker_pid=12345,
        )
        assert t1["partitions"]["mixture"]["status"] == "CONSUMED"
        assert t1["partitions"]["mixture"]["report_sha256"] == "a" * 64
        assert t1["ticket_state"] == "ACTIVE_PARTIAL"
        assert t1["active_partition"] is None

        # 3. Claim Scenario
        execute_claim_transaction(sec_dir, nonce=nonce, partition="scenario")

        # 4. Complete Scenario with Exit Code 0
        t2 = execute_outcome_transaction(
            sec_dir,
            nonce=nonce,
            partition="scenario",
            exit_code=0,
            report_sha256="b" * 64,
            worker_pid=12346,
        )
        assert t2["partitions"]["scenario"]["status"] == "CONSUMED"
        assert t2["ticket_state"] == "CLOSED"
        assert t2["active_partition"] is None

        # Attempting to claim again under CLOSED ticket fails
        with pytest.raises(SecurityError, match="TICKET_ALREADY_CLOSED"):
            execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

    def test_partition_failure_transitions_to_failed_terminal(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "5" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # Claim Mixture
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # Mixture fails with non-zero exit code (e.g. 1)
        res = execute_outcome_transaction(
            sec_dir, nonce=nonce, partition="mixture", exit_code=1
        )
        assert res["partitions"]["mixture"]["status"] == "FAILED"
        assert res["ticket_state"] == "FAILED_TERMINAL"
        assert res["active_partition"] is None

        # Any subsequent claim attempt on this ticket fails closed
        with pytest.raises(SecurityError, match="TICKET_FAILED_TERMINAL"):
            execute_claim_transaction(sec_dir, nonce=nonce, partition="scenario")

    def test_stranded_claim_reconciliation(self, tmp_path, sample_ticket_factory):
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "6" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # Claim Mixture
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # Simulate dead launcher PID (e.g. PID 99999999 which does not exist)
        with PersistentLedgerLock(sec_dir):
            ledger = read_ledger(sec_dir)
            ledger["active_tickets"][nonce]["partitions"]["mixture"]["launcher_pid"] = 99999999
            from nexvia_aegis.security.ledger import _persist_ledger_crash_durable
            _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

        # Reconcile detects dead process and transitions to terminal failure
        reconciled = reconcile_stranded_claim(sec_dir, nonce=nonce, owner_confirmation=True)
        assert reconciled is True

        ledger = read_ledger(sec_dir)
        entry = ledger["active_tickets"][nonce]
        assert entry["partitions"]["mixture"]["status"] == "FAILED"
        assert entry["ticket_state"] == "FAILED_TERMINAL"
        assert entry["active_partition"] is None

        # Stranded claim must remain permanently spent; retry is rejected
        with pytest.raises(SecurityError, match="TICKET_FAILED_TERMINAL"):
            execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

    def test_crash_after_durable_claim_before_worker_startup_remains_spent(self, tmp_path, sample_ticket_factory):
        """If supervisor process crashes after durable claim but before worker starts, claim is permanently spent."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "7" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        # Claim committed to durable disk
        res = execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")
        assert res["partitions"]["mixture"]["status"] == "CLAIMED"

        # Simulate fresh process opening ledger after crash without any cleanup code running
        # Status on disk is already CLAIMED, so another claim on mixture must be rejected
        with pytest.raises(SecurityError, match="ACTIVE_PARTITION_IN_PROGRESS"):
            execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

    def test_worker_spawn_failure_transitions_to_failed_terminal(self, tmp_path, sample_ticket_factory):
        """If worker process cannot be spawned, outcome transaction records failure and enters FAILED_TERMINAL."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "8" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # Worker spawn failure (e.g. exit code 127 for FileNotFoundError or exec failure)
        res = execute_outcome_transaction(sec_dir, nonce=nonce, partition="mixture", exit_code=127)
        assert res["partitions"]["mixture"]["status"] == "FAILED"
        assert res["ticket_state"] == "FAILED_TERMINAL"
        assert res["active_partition"] is None

        # Scenario is permanently blocked
        with pytest.raises(SecurityError, match="TICKET_FAILED_TERMINAL"):
            execute_claim_transaction(sec_dir, nonce=nonce, partition="scenario")

    def test_scenario_blocked_when_mixture_fails(self, tmp_path, sample_ticket_factory):
        """Under registered sequential workflow, Scenario cannot be claimed if Mixture failed."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "9" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")
        execute_outcome_transaction(sec_dir, nonce=nonce, partition="mixture", exit_code=1)

        with pytest.raises(SecurityError, match="TICKET_FAILED_TERMINAL"):
            execute_claim_transaction(sec_dir, nonce=nonce, partition="scenario")

    def test_atomic_replacement_failure_fails_closed(self, tmp_path, sample_ticket_factory, monkeypatch):
        """If os.replace fails during ledger update, transaction fails closed and temp file is cleaned up."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="0" * 64)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        def mock_replace(src, dst):
            raise OSError("Simulated disk error during atomic replace")

        monkeypatch.setattr(os, "replace", mock_replace)

        with pytest.raises(SecurityError, match="LEDGER_PERSISTENCE_FAILED"):
            execute_claim_transaction(sec_dir, nonce="0" * 64, partition="mixture")

        # Original ledger remains valid and unmodified
        ledger = read_ledger(sec_dir)
        assert ledger["active_tickets"]["0" * 64]["partitions"]["mixture"]["status"] == "UNCLAIMED"

    def test_directory_sync_failure_fails_closed(self, tmp_path, sample_ticket_factory, monkeypatch):
        """If directory synchronization fails after replace, transaction raises DIRECTORY_SYNC_FAILED fail-closed."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        ticket, pubkey = sample_ticket_factory(nonce="d" * 64)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        from nexvia_aegis.security import ledger as ledger_module

        def mock_sync_parent(dir_path, strict=True):
            raise SecurityError("DIRECTORY_SYNC_FAILED: Simulated directory sync failure")

        monkeypatch.setattr(ledger_module, "_sync_parent_dir", mock_sync_parent)

        with pytest.raises(SecurityError, match="DIRECTORY_SYNC_FAILED"):
            execute_claim_transaction(sec_dir, nonce="d" * 64, partition="mixture")

    def test_stranded_claim_rejects_implicit_recovery_without_owner_confirmation(self, tmp_path, sample_ticket_factory):
        """reconcile_stranded_claim must abort fail-closed if owner_confirmation is False."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "e" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        with pytest.raises(SecurityError, match="OWNER_CONFIRMATION_REQUIRED"):
            reconcile_stranded_claim(sec_dir, nonce=nonce, owner_confirmation=False)

    def test_stranded_claim_active_process_fails_closed(self, tmp_path, sample_ticket_factory):
        """If launcher or worker process is still active, reconciliation must abort fail-closed."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "f" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # Record current active test process PID as worker_pid
        with PersistentLedgerLock(sec_dir):
            ledger = read_ledger(sec_dir)
            ledger["active_tickets"][nonce]["partitions"]["mixture"]["worker_pid"] = os.getpid()
            from nexvia_aegis.security.ledger import _persist_ledger_crash_durable
            _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

        with pytest.raises(SecurityError, match="ACTIVE_PROCESS_DETECTED"):
            reconcile_stranded_claim(sec_dir, nonce=nonce, owner_confirmation=True)

    def test_outcome_success_requires_valid_report_digest(self, tmp_path, sample_ticket_factory):
        """Exit code 0 requires a valid 64-character hex report_sha256; missing digest fails closed."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "1" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # Missing report_sha256 (None) must fail closed to FAILED_TERMINAL
        with pytest.raises(SecurityError, match="INVALID_OUTCOME_EVIDENCE"):
            execute_outcome_transaction(sec_dir, nonce=nonce, partition="mixture", exit_code=0, report_sha256=None)

        ledger = read_ledger(sec_dir)
        entry = ledger["active_tickets"][nonce]
        assert entry["partitions"]["mixture"]["status"] == "FAILED"
        assert entry["ticket_state"] == "FAILED_TERMINAL"

    def test_outcome_success_validates_report_file_digest_and_binding(self, tmp_path, sample_ticket_factory):
        """Validates report file digest match and exact ticket/partition binding."""
        import hashlib
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "2" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        report_file = tmp_path / "mixture_report.json"
        report_data = {
            "schema_version": "nexvia-aegis-v9-holdout-mixture-report/1.0",
            "status": "COMPLETE_VALID",
            "simulation_mode": "PRODUCTION_PHYSICS",
            "partition": "mixture",
            "ticket_nonce": nonce,
            "episodes_count": 1440,
        }
        report_bytes = json.dumps(report_data).encode("utf-8")
        report_file.write_bytes(report_bytes)
        report_digest = hashlib.sha256(report_bytes).hexdigest()

        # Success with matching report file and digest
        res = execute_outcome_transaction(
            sec_dir,
            nonce=nonce,
            partition="mixture",
            exit_code=0,
            report_sha256=report_digest,
            output_report_path=report_file,
        )
        assert res["partitions"]["mixture"]["status"] == "CONSUMED"

    def test_outcome_fails_on_report_digest_mismatch(self, tmp_path, sample_ticket_factory):
        """Mismatched report SHA-256 fails closed to FAILED_TERMINAL."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "3" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        report_file = tmp_path / "mixture_report.json"
        report_file.write_text('{"partition": "mixture"}', encoding="utf-8")

        with pytest.raises(SecurityError, match="REPORT_DIGEST_MISMATCH"):
            execute_outcome_transaction(
                sec_dir,
                nonce=nonce,
                partition="mixture",
                exit_code=0,
                report_sha256="0" * 64,  # Incorrect hash
                output_report_path=report_file,
            )

        ledger = read_ledger(sec_dir)
        entry = ledger["active_tickets"][nonce]
        assert entry["partitions"]["mixture"]["status"] == "FAILED"
        assert entry["ticket_state"] == "FAILED_TERMINAL"

    def test_outcome_fails_on_report_binding_mismatch(self, tmp_path, sample_ticket_factory):
        """Report claiming wrong partition fails closed."""
        import hashlib
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "4" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        # Report says partition is 'scenario' instead of 'mixture'
        report_file = tmp_path / "bad_report.json"
        content = json.dumps({"partition": "scenario", "ticket_nonce": nonce}).encode("utf-8")
        report_file.write_bytes(content)
        report_sha = hashlib.sha256(content).hexdigest()

        with pytest.raises(SecurityError, match="REPORT_PARTITION_MISMATCH"):
            execute_outcome_transaction(
                sec_dir,
                nonce=nonce,
                partition="mixture",
                exit_code=0,
                report_sha256=report_sha,
                output_report_path=report_file,
            )

    def test_outcome_fails_on_symlink_report(self, tmp_path, sample_ticket_factory):
        """Symlinked report file is rejected fail-closed."""
        import hashlib
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "5" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)
        execute_claim_transaction(sec_dir, nonce=nonce, partition="mixture")

        real_report = tmp_path / "real_rep.json"
        content = json.dumps({"partition": "mixture", "ticket_nonce": nonce}).encode("utf-8")
        real_report.write_bytes(content)
        report_sha = hashlib.sha256(content).hexdigest()

        symlink_rep = tmp_path / "symlink_rep.json"
        symlink_rep.symlink_to(real_report)

        with pytest.raises(SecurityError, match="SYMLINK_REPORT_REJECTED"):
            execute_outcome_transaction(
                sec_dir,
                nonce=nonce,
                partition="mixture",
                exit_code=0,
                report_sha256=report_sha,
                output_report_path=symlink_rep,
            )

    def test_real_multiprocess_claim_contention_same_partition(self, tmp_path, sample_ticket_factory):
        """Spawns two real independent OS processes simultaneously contending for the same partition."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "6" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        worker_script = """
import sys
from pathlib import Path
from nexvia_aegis.security.ledger import execute_claim_transaction, SecurityError

sec_dir = Path(sys.argv[1])
nonce = sys.argv[2]
partition = sys.argv[3]

try:
    execute_claim_transaction(sec_dir, nonce, partition)
    sys.exit(0)
except SecurityError:
    # Contention rejected fail-closed as expected
    sys.exit(42)
except Exception:
    sys.exit(99)
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{str(Path.cwd())}:{str(Path.cwd() / 'src')}"

        cmd1 = [sys.executable, "-c", worker_script, str(sec_dir), nonce, "mixture"]
        cmd2 = [sys.executable, "-c", worker_script, str(sec_dir), nonce, "mixture"]

        p1 = subprocess.Popen(cmd1, env=env)
        p2 = subprocess.Popen(cmd2, env=env)

        p1.wait(timeout=10)
        p2.wait(timeout=10)

        rcs = sorted([p1.returncode, p2.returncode])
        # Exactly one must succeed (0), and one must fail closed with SecurityError (42)
        assert rcs == [0, 42], f"Expected exactly [0, 42], got {rcs}"

        # Verify on-disk ledger integrity
        ledger = read_ledger(sec_dir)
        entry = ledger["active_tickets"][nonce]
        assert entry["partitions"]["mixture"]["status"] == "CLAIMED"
        assert entry["active_partition"] == "mixture"

    def test_real_multiprocess_claim_contention_different_partitions(self, tmp_path, sample_ticket_factory):
        """Spawns two real independent OS processes contending for different partitions under mutual exclusion."""
        sec_dir = tmp_path / "sec"
        bootstrap_security_directory(sec_dir)

        nonce = "7" * 64
        ticket, pubkey = sample_ticket_factory(nonce=nonce)
        register_ticket(ticket, security_dir=sec_dir, public_key_obj=pubkey)

        worker_script = """
import sys
from pathlib import Path
from nexvia_aegis.security.ledger import execute_claim_transaction, SecurityError

sec_dir = Path(sys.argv[1])
nonce = sys.argv[2]
partition = sys.argv[3]

try:
    execute_claim_transaction(sec_dir, nonce, partition)
    sys.exit(0)
except SecurityError:
    sys.exit(42)
except Exception:
    sys.exit(99)
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{str(Path.cwd())}:{str(Path.cwd() / 'src')}"

        cmd1 = [sys.executable, "-c", worker_script, str(sec_dir), nonce, "mixture"]
        cmd2 = [sys.executable, "-c", worker_script, str(sec_dir), nonce, "scenario"]

        p1 = subprocess.Popen(cmd1, env=env)
        p2 = subprocess.Popen(cmd2, env=env)

        p1.wait(timeout=10)
        p2.wait(timeout=10)

        rcs = sorted([p1.returncode, p2.returncode])
        assert rcs == [0, 42], f"Expected exactly [0, 42], got {rcs}"

        ledger = read_ledger(sec_dir)
        entry = ledger["active_tickets"][nonce]
        claimed_part = entry["active_partition"]
        assert claimed_part in ("mixture", "scenario")
        assert entry["partitions"][claimed_part]["status"] == "CLAIMED"
        other_part = "scenario" if claimed_part == "mixture" else "mixture"
        assert entry["partitions"][other_part]["status"] == "UNCLAIMED"
