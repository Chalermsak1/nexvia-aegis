"""Persistent Anti-Replay Ledger and Concurrency Management.

Implements the persistent stable-lock file, atomic crash-durable ledger updates,
authoritative under-lock claim transactions, sequential partition lifecycle,
and non-retryable terminal failure transitions per Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nexvia_aegis.security.canonical import canonicalize_payload, parse_strict_json
from nexvia_aegis.security.verifier import (
    RE_HEX_64,
    SecurityError,
    parse_iso8601_utc,
    validate_semantic_payload,
    verify_ticket_envelope,
)

LOCK_FILE_NAME = "gate_b_replay_ledger.lock"
LEDGER_FILE_NAME = "gate_b_replay_ledger.json"

ALLOWED_PARTITIONS = ("mixture", "scenario")
ALLOWED_PARTITION_STATUSES = ("UNCLAIMED", "CLAIMED", "CONSUMED", "FAILED")
ALLOWED_TICKET_STATES = ("ISSUED", "ACTIVE_PARTIAL", "CLOSED", "FAILED_TERMINAL")

# Darwin-specific constant for F_FULLFSYNC to flush drive hardware caches
_DARWIN_F_FULLFSYNC = 51


def _sync_fd_durable(fd: int) -> None:
    """Synchronizes file descriptor to physical media.

    On macOS (Darwin), attempts fcntl F_FULLFSYNC to instruct drive firmware to flush
    on-board write caches. Falls back to os.fsync() on other platforms or if unsupported.

    Note on Workstation Limitations:
    Even with F_FULLFSYNC, no software routine can guarantee survival against hardware
    firmware bugs, storage controller crashes, or physical power disruption during cell writes.
    Software crash-durability is achieved by writing to a temporary file, flushing, and
    atomically replacing the target file via os.replace(), ensuring either the old or the new
    intact ledger remains on disk.
    """
    if sys.platform == "darwin":
        try:
            fcntl.fcntl(fd, _DARWIN_F_FULLFSYNC)
            return
        except (OSError, ValueError):
            pass
    os.fsync(fd)


def _current_utc_iso() -> str:
    """Returns current UTC timestamp in strict ISO 8601 format ending in 'Z'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_security_dir(security_dir: Path | str | None = None) -> Path:
    """Resolves and validates the security directory path.

    Args:
        security_dir: Optional custom path; defaults to ~/.nexvia_security.

    Returns:
        Absolute, resolved Path object.

    Raises:
        SecurityError: If path contains unexpected symlinks or is invalid.
    """
    if security_dir is None:
        p = Path("~/.nexvia_security").expanduser()
    else:
        p = Path(security_dir).expanduser()

    # Reject if target path itself is a symlink
    if p.is_symlink():
        raise SecurityError(
            f"SYMLINK_SECURITY_DIR_REJECTED: Security directory '{p}' must not be a symbolic link."
        )

    return p.resolve()


def bootstrap_security_directory(security_dir: Path | str | None = None) -> tuple[Path, Path]:
    """Strict, one-time initialization of the security directory, lock file, and ledger.

    Preconditions:
      - Security directory must satisfy ownership requirements.
      - Neither gate_b_replay_ledger.lock nor gate_b_replay_ledger.json may exist.
      - If either exists, aborts fail-closed with SECURITY_DIR_ALREADY_INITIALIZED.

    Creates:
      - Directory with permissions 0700.
      - Persistent lock file with permissions 0600 (O_CREAT | O_EXCL).
      - Initial empty ledger with permissions 0600 (O_CREAT | O_EXCL).

    Returns:
        Tuple of (lock_file_path, ledger_file_path).

    Raises:
        SecurityError: If directory is already initialized or initialization fails.
    """
    sec_dir = resolve_security_dir(security_dir)
    sec_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(sec_dir, 0o700)

    lock_path = sec_dir / LOCK_FILE_NAME
    ledger_path = sec_dir / LEDGER_FILE_NAME

    # Anti-reinitialization check: refuse if either file exists
    if lock_path.exists() or ledger_path.exists():
        raise SecurityError(
            f"SECURITY_DIR_ALREADY_INITIALIZED: Security directory '{sec_dir}' already contains "
            f"established lock file or ledger. Reinitialization is strictly prohibited."
        )

    # Exclusive creation of stable lock file
    open_flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        lock_fd = os.open(str(lock_path), open_flags, 0o600)
    except OSError as e:
        raise SecurityError(
            f"LOCK_FILE_CREATION_FAILED: Could not exclusively create lock file '{lock_path}': {e}"
        ) from e

    try:
        _sync_fd_durable(lock_fd)
    finally:
        os.close(lock_fd)
    os.chmod(lock_path, 0o600)

    # Exclusive creation of initial ledger file
    initial_ledger = {
        "schema_version": "1.0",
        "initialized_at_utc": _current_utc_iso(),
        "operator_uid": os.getuid(),
        "active_tickets": {},
        "historical_nonces": [],
    }

    raw_json = json.dumps(initial_ledger, indent=2).encode("utf-8")
    try:
        ledger_fd = os.open(str(ledger_path), open_flags, 0o600)
    except OSError as e:
        # Cleanup lock file on failure
        try:
            lock_path.unlink()
        except OSError:
            pass
        raise SecurityError(
            f"LEDGER_FILE_CREATION_FAILED: Could not exclusively create ledger '{ledger_path}': {e}"
        ) from e

    try:
        os.write(ledger_fd, raw_json)
        _sync_fd_durable(ledger_fd)
    finally:
        os.close(ledger_fd)
    os.chmod(ledger_path, 0o600)

    # Sync containing directory
    _sync_parent_dir(sec_dir)

    return lock_path, ledger_path


def _sync_parent_dir(dir_path: Path, strict: bool = True) -> None:
    """Synchronizes containing directory metadata to storage where supported.

    Args:
        dir_path: Path to directory to synchronize.
        strict: If True, raises SecurityError on unhandled OS errors.
    """
    try:
        dir_fd = os.open(str(dir_path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            _sync_fd_durable(dir_fd)
        finally:
            os.close(dir_fd)
    except (NotImplementedError, AttributeError):
        pass
    except OSError as e:
        if strict:
            raise SecurityError(
                f"DIRECTORY_SYNC_FAILED: Failed to synchronize containing directory '{dir_path}': {e}"
            ) from e


def validate_ledger_structure(ledger: dict[str, Any]) -> None:
    """Validates schema integrity of an in-memory ledger dictionary."""
    if not isinstance(ledger, dict):
        raise SecurityError("MALFORMED_LEDGER: Top-level ledger must be a dictionary.")

    required_keys = {"schema_version", "initialized_at_utc", "operator_uid", "active_tickets", "historical_nonces"}
    if not required_keys.issubset(ledger.keys()):
        missing = required_keys - set(ledger.keys())
        raise SecurityError(f"CORRUPTED_OR_MISSING_LEDGER: Missing required ledger keys {missing}.")

    if ledger["schema_version"] != "1.0":
        raise SecurityError(
            f"UNSUPPORTED_LEDGER_VERSION: Expected '1.0', got '{ledger['schema_version']}'."
        )

    if not isinstance(ledger["active_tickets"], dict):
        raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: 'active_tickets' must be a dictionary.")

    if not isinstance(ledger["historical_nonces"], list):
        raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: 'historical_nonces' must be a list.")
    history = ledger["historical_nonces"]
    if any(not isinstance(nonce, str) or not RE_HEX_64.fullmatch(nonce) for nonce in history):
        raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: Historical nonce format is invalid.")
    if len(history) != len(set(history)):
        raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: Duplicate historical nonce.")
    for nonce, entry in ledger["active_tickets"].items():
        if nonce not in history or not isinstance(entry, dict):
            raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: Active ticket is absent from nonce history.")
        parts = entry.get("partitions")
        if not isinstance(parts, dict) or set(parts) != set(ALLOWED_PARTITIONS):
            raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: Ticket partition map is invalid.")
        active = entry.get("active_partition")
        claimed = [name for name, part in parts.items() if isinstance(part, dict) and part.get("status") == "CLAIMED"]
        if any(not isinstance(part, dict) or part.get("status") not in {"UNCLAIMED", "CLAIMED", "CONSUMED", "FAILED"}
               for part in parts.values()):
            raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: Partition status is invalid.")
        if len(claimed) > 1 or (active is None and claimed) or (active is not None and (active not in parts or claimed != [active])):
            raise SecurityError("CORRUPTED_OR_MISSING_LEDGER: Active partition and claimed status disagree.")


def _persist_ledger_crash_durable(ledger_path: Path, ledger: dict[str, Any]) -> None:
    """Atomically and crash-durably writes ledger dictionary to disk.

    Sequence:
      1. Write deterministically formatted JSON to a temporary file in same directory.
      2. Flush user-space buffers.
      3. Synchronize file descriptor to non-volatile storage (F_FULLFSYNC / fsync).
      4. Set permissions to 0600.
      5. Atomically replace target ledger file via os.replace().
      6. Synchronize directory metadata strictly.
    """
    tmp_path = ledger_path.with_name(f"{ledger_path.name}.{os.getpid()}.tmp")
    data_bytes = json.dumps(ledger, indent=2).encode("utf-8")

    open_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(tmp_path), open_flags, 0o600)
    except OSError as e:
        raise SecurityError(
            f"LEDGER_PERSISTENCE_FAILED: Could not open temporary ledger file '{tmp_path}': {e}"
        ) from e

    try:
        written = 0
        while written < len(data_bytes):
            count = os.write(fd, data_bytes[written:])
            if count <= 0:
                raise OSError("Short ledger write")
            written += count
        _sync_fd_durable(fd)
    except Exception as e:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise SecurityError(
            f"LEDGER_PERSISTENCE_FAILED: Failed to write or sync temporary ledger '{tmp_path}': {e}"
        ) from e
    finally:
        os.close(fd)

    os.chmod(tmp_path, 0o600)

    try:
        os.replace(tmp_path, ledger_path)
    except OSError as e:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise SecurityError(
            f"LEDGER_PERSISTENCE_FAILED: Atomic replacement of ledger failed: {e}"
        ) from e

    _sync_parent_dir(ledger_path.parent, strict=True)


class PersistentLedgerLock:
    """Context manager for acquiring exclusive flock on the stable lock file."""

    def __init__(self, security_dir: Path) -> None:
        self.security_dir = security_dir
        self.lock_path = security_dir / LOCK_FILE_NAME
        self.lock_fd: int | None = None
        self.initial_inode: int | None = None

    def __enter__(self) -> "PersistentLedgerLock":
        if not self.lock_path.exists():
            raise SecurityError(
                f"CORRUPTED_OR_MISSING_LEDGER: Lock file '{self.lock_path}' does not exist. "
                "Run setup_gate_b_ledger.py first."
            )
        if self.lock_path.is_symlink():
            raise SecurityError(
                f"SYMLINK_LOCK_REJECTED: Lock file '{self.lock_path}' must not be a symbolic link."
            )

        # Open without O_CREAT: must fail closed if missing
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            self.lock_fd = os.open(str(self.lock_path), flags)
        except OSError as e:
            raise SecurityError(
                f"LOCK_ACQUISITION_FAILED: Could not open lock file '{self.lock_path}': {e}"
            ) from e

        # Acquire exclusive non-blocking or blocking lock
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
        except OSError as e:
            os.close(self.lock_fd)
            self.lock_fd = None
            raise SecurityError(
                f"LOCK_ACQUISITION_FAILED: Exclusive flock failed on '{self.lock_path}': {e}"
            ) from e

        # Verify inode stability, ownership, and mode
        st = os.fstat(self.lock_fd)
        if st.st_uid != os.getuid():
            self._close()
            raise SecurityError("UNSAFE_LOCK_OWNERSHIP: Lock file must be owned by the current user.")
        if (st.st_mode & 0o777) != 0o600:
            self._close()
            raise SecurityError("UNSAFE_LOCK_PERMISSIONS: Lock file permissions must be exactly 0600.")

        self.initial_inode = st.st_ino
        try:
            if os.stat(self.lock_path, follow_symlinks=False).st_ino != st.st_ino:
                self._close()
                raise SecurityError("LOCK_INODE_CHANGED: Lock pathname changed during acquisition.")
        except FileNotFoundError as exc:
            self._close()
            raise SecurityError("LOCK_INODE_CHANGED: Lock pathname disappeared during acquisition.") from exc
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._close()

    def _close(self) -> None:
        if self.lock_fd is not None:
            inode_changed = False
            try:
                # Re-verify that the lock file inode was not swapped or unlinked
                st_now = os.stat(self.lock_path, follow_symlinks=False)
                if st_now.st_ino != self.initial_inode:
                    inode_changed = True
            except OSError:
                inode_changed = True
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self.lock_fd)
            except OSError:
                pass
            self.lock_fd = None
            if inode_changed:
                raise SecurityError("LOCK_INODE_CHANGED: Stable lock pathname changed while held.")


def read_ledger(security_dir: Path) -> dict[str, Any]:
    """Reads and parses the persistent data ledger fail-closed."""
    ledger_path = security_dir / LEDGER_FILE_NAME
    if not ledger_path.exists():
        raise SecurityError(
            f"CORRUPTED_OR_MISSING_LEDGER: Ledger file '{ledger_path}' does not exist. "
            "Never silently recreate an empty ledger after activity."
        )
    if ledger_path.is_symlink():
        raise SecurityError(
            f"SYMLINK_LEDGER_REJECTED: Ledger file '{ledger_path}' must not be a symbolic link."
        )

    try:
        raw_bytes = ledger_path.read_bytes()
        ledger = parse_strict_json(raw_bytes)
    except Exception as e:
        raise SecurityError(
            f"CORRUPTED_OR_MISSING_LEDGER: Failed to read or parse ledger '{ledger_path}': {e}"
        ) from e

    validate_ledger_structure(ledger)
    return ledger


def register_ticket(
    ticket_data: dict[str, Any] | str | bytes,
    security_dir: Path | str | None = None,
    pubkey_anchor_path: Path | None = None,
    expected_pubkey_sha256: str | None = None,
    public_key_obj: Ed25519PublicKey | None = None,
) -> str:
    """Verifies and atomically registers a new Gate B authorization ticket into the ledger.

    Sequence:
      1. Pre-lock cryptographic and semantic verification of ticket.
      2. Lock acquisition on stable lock file.
      3. Anti-replay checks (nonce in historical_nonces or active_tickets).
      4. Under-lock expiry check (current_time <= expires_at_utc).
      5. Creation of ticket entry with ticket_state='ISSUED', active_partition=None,
         and both partitions initialized to 'UNCLAIMED'.
      6. Permanent burning of nonce by appending to historical_nonces.
      7. Crash-durable persistence of updated ledger.

    Returns:
        The validated ticket nonce.

    Raises:
        SecurityError: If verification fails, ticket is duplicate, nonce is reused, or expired.
    """
    sec_dir = resolve_security_dir(security_dir)

    # 1. Pre-Lock Verification (Outside Lock)
    if isinstance(ticket_data, Path):
        raw_json = ticket_data.read_bytes()
    elif isinstance(ticket_data, (dict, list)):
        raw_json = json.dumps(ticket_data)
    else:
        raw_json = ticket_data

    verified_envelope = verify_ticket_envelope(
        raw_json,
        pubkey_anchor_path=pubkey_anchor_path,
        expected_pubkey_sha256=expected_pubkey_sha256,
        public_key_obj=public_key_obj,
    )
    payload = verified_envelope["payload"]
    validate_semantic_payload(payload)

    nonce = payload["nonce"]

    # 2. Under-Lock Registration
    with PersistentLedgerLock(sec_dir):
        ledger = read_ledger(sec_dir)

        # Anti-Replay: check if nonce already used
        if nonce in ledger["historical_nonces"]:
            raise SecurityError(
                f"NONCE_ALREADY_USED: Ticket nonce '{nonce}' has already been used or registered."
            )
        if nonce in ledger["active_tickets"]:
            raise SecurityError(
                f"TICKET_ALREADY_REGISTERED: Ticket nonce '{nonce}' is already active in ledger."
            )

        # Under-lock definitive expiry check
        t_reg_iso = _current_utc_iso()
        dt_reg = parse_iso8601_utc(t_reg_iso)
        dt_expires = parse_iso8601_utc(payload["expires_at_utc"])
        dt_issued = parse_iso8601_utc(payload["issued_at_utc"])

        if dt_reg > dt_expires:
            raise SecurityError(
                f"TICKET_EXPIRED_AT_REGISTRATION: Current time ({t_reg_iso}) exceeds ticket expiry ({payload['expires_at_utc']})."
            )
        if dt_reg < dt_issued:
            raise SecurityError(
                f"TICKET_NOT_YET_VALID: Current time ({t_reg_iso}) precedes ticket issuance ({payload['issued_at_utc']})."
            )

        # Initialize Ticket Entry
        ticket_entry = {
            "ticket_version": verified_envelope["ticket_version"],
            "registered_at_utc": t_reg_iso,
            "issued_at_utc": payload["issued_at_utc"],
            "expires_at_utc": payload["expires_at_utc"],
            "approved_commit": payload["approved_commit"],
            "evaluator_artifact_sha256": payload["evaluator_artifact_sha256"],
            "policy_sha256": payload["policy_sha256"],
            "mixture_manifest_sha256": payload["mixture_manifest_sha256"],
            "scenario_manifest_sha256": payload["scenario_manifest_sha256"],
            "lockfile_sha256": payload["lockfile_sha256"],
            "operator_identity": payload["operator_identity"],
            "ticket_state": "ISSUED",
            "active_partition": None,
            "partitions": {
                "mixture": {
                    "status": "UNCLAIMED",
                    "claimed_at_utc": None,
                    "completed_at_utc": None,
                    "launcher_pid": None,
                    "worker_pid": None,
                    "exit_code": None,
                    "report_sha256": None,
                },
                "scenario": {
                    "status": "UNCLAIMED",
                    "claimed_at_utc": None,
                    "completed_at_utc": None,
                    "launcher_pid": None,
                    "worker_pid": None,
                    "exit_code": None,
                    "report_sha256": None,
                },
            },
        }

        # Burn nonce permanently
        ledger["historical_nonces"].append(nonce)
        ledger["active_tickets"][nonce] = ticket_entry

        # Crash-durable persistence
        _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

    return nonce


def execute_claim_transaction(
    security_dir: Path | str | None,
    nonce: str,
    partition: str,
) -> dict[str, Any]:
    """Under-lock claim transaction committing a partition execution right.

    Enforces:
      - Ticket registration and lifecycle checks (cannot claim if CLOSED or FAILED_TERMINAL).
      - Partition validity and strictly UNCLAIMED status check.
      - Sequential partition mutual exclusion (active_partition must be None).
      - Sequential workflow invariant (scenario cannot be claimed if mixture is failed or stranded).
      - Authoritative under-lock expiry verification.
      - Crash-durable recording of status='CLAIMED', claimed_at_utc, launcher_pid, active_partition.

    A committed Claim is permanently spent. If execution fails to start or process terminates,
    the claim cannot be retried under this ticket.

    Returns:
        Deep copy of the updated ticket entry.

    Raises:
        SecurityError: If partition is unavailable, ticket is expired, or another partition is active.
    """
    if partition not in ALLOWED_PARTITIONS:
        raise SecurityError(
            f"INVALID_PARTITION: Requested partition '{partition}' must be one of {ALLOWED_PARTITIONS}."
        )

    sec_dir = resolve_security_dir(security_dir)

    with PersistentLedgerLock(sec_dir):
        ledger = read_ledger(sec_dir)

        if nonce not in ledger["active_tickets"]:
            raise SecurityError(
                f"TICKET_NOT_REGISTERED: Nonce '{nonce}' not found in active ledger tickets."
            )

        ticket_entry = ledger["active_tickets"][nonce]
        t_state = ticket_entry["ticket_state"]

        if t_state == "CLOSED":
            raise SecurityError(
                f"TICKET_ALREADY_CLOSED: All partitions under ticket '{nonce}' have been consumed."
            )
        if t_state == "FAILED_TERMINAL":
            raise SecurityError(
                f"TICKET_FAILED_TERMINAL: Ticket '{nonce}' is in terminal failure state. No further claims permitted."
            )

        # Sequential Partition Exclusion: only one partition active at a time
        if ticket_entry["active_partition"] is not None:
            raise SecurityError(
                f"ACTIVE_PARTITION_IN_PROGRESS: Partition '{ticket_entry['active_partition']}' "
                f"is currently active under ticket '{nonce}'. Concurrent execution is prohibited."
            )

        p_entry = ticket_entry["partitions"][partition]
        if p_entry["status"] != "UNCLAIMED":
            raise SecurityError(
                f"PARTITION_ALREADY_CLAIMED: Partition '{partition}' status is '{p_entry['status']}', expected 'UNCLAIMED'."
            )

        # Sequential Workflow Enforcement:
        # Scenario partition requires Mixture to be either already CONSUMED or UNCLAIMED (if executed in reverse)
        # But if mixture is FAILED or stranded CLAIMED, scenario cannot be claimed.
        other_partition = "scenario" if partition == "mixture" else "mixture"
        other_status = ticket_entry["partitions"][other_partition]["status"]
        if other_status == "FAILED":
            raise SecurityError(
                f"PARTITION_BLOCKED_BY_PREVIOUS_FAILURE: Cannot claim '{partition}' because '{other_partition}' failed."
            )
        if other_status == "CLAIMED":
            raise SecurityError(
                f"PARTITION_BLOCKED_BY_ACTIVE_CLAIM: Cannot claim '{partition}' because '{other_partition}' is actively claimed."
            )

        # Authoritative Under-Lock Expiry Check
        t_claim_iso = _current_utc_iso()
        dt_claim = parse_iso8601_utc(t_claim_iso)
        dt_expires = parse_iso8601_utc(ticket_entry["expires_at_utc"])
        dt_issued = parse_iso8601_utc(ticket_entry["issued_at_utc"])

        if dt_claim > dt_expires:
            raise SecurityError(
                f"TICKET_EXPIRED_AT_CLAIM_BOUNDARY: Current time ({t_claim_iso}) exceeds expiry ({ticket_entry['expires_at_utc']})."
            )
        if dt_claim < dt_issued:
            raise SecurityError(
                f"TICKET_NOT_YET_VALID_AT_CLAIM_BOUNDARY: Current time ({t_claim_iso}) precedes issuance ({ticket_entry['issued_at_utc']})."
            )

        # Ephemeral single-use launch claim secret
        claim_secret = secrets.token_hex(32)
        claim_secret_hash = hashlib.sha256(claim_secret.encode("utf-8")).hexdigest().lower()

        # Mutate State
        p_entry["status"] = "CLAIMED"
        p_entry["claimed_at_utc"] = t_claim_iso
        p_entry["launcher_pid"] = os.getpid()
        p_entry["claim_secret_hash"] = claim_secret_hash

        ticket_entry["active_partition"] = partition
        ticket_entry["ticket_state"] = "ACTIVE_PARTIAL"

        # Commit crash-durably before returning
        _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

        ret_entry = copy.deepcopy(ticket_entry)
        ret_entry["claim_secret"] = claim_secret
        return ret_entry


def execute_outcome_transaction(
    security_dir: Path | str | None,
    nonce: str,
    partition: str,
    exit_code: int,
    report_sha256: str | None = None,
    worker_pid: int | None = None,
    output_report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Under-lock outcome transaction recording the terminal result of a partition execution.

    Transitions:
      - If exit_code == 0:
        Validates output report evidence (report_sha256 format, file digest, JSON binding,
        and strictly requires status == 'COMPLETE_VALID' and simulation_mode == 'PRODUCTION_PHYSICS').
        Only if ALL evidence passes: partition status -> 'CONSUMED'.
        If both partitions are CONSUMED: ticket_state -> 'CLOSED'.
        Else: ticket_state -> 'ACTIVE_PARTIAL'.
        If any evidence check fails: partition status -> 'FAILED', ticket_state -> 'FAILED_TERMINAL'.
      - If exit_code != 0:
        partition status -> 'FAILED', ticket_state -> 'FAILED_TERMINAL'.
      - Clears active_partition to None.

    Returns:
        Deep copy of the updated ticket entry.

    Raises:
        SecurityError: If partition was not in CLAIMED state, or if outcome evidence is invalid.
    """
    sec_dir = resolve_security_dir(security_dir)

    with PersistentLedgerLock(sec_dir):
        ledger = read_ledger(sec_dir)

        if nonce not in ledger["active_tickets"]:
            raise SecurityError(
                f"TICKET_NOT_REGISTERED: Nonce '{nonce}' not found in active ledger tickets."
            )

        ticket_entry = ledger["active_tickets"][nonce]
        p_entry = ticket_entry["partitions"][partition]

        if p_entry["status"] != "CLAIMED":
            raise SecurityError(
                f"ILLEGAL_OUTCOME_TRANSITION: Cannot record outcome for partition '{partition}' in status '{p_entry['status']}' (expected 'CLAIMED')."
            )

        # Clear active partition
        ticket_entry["active_partition"] = None

        t_complete_iso = _current_utc_iso()
        p_entry["completed_at_utc"] = t_complete_iso
        p_entry["exit_code"] = exit_code
        p_entry["worker_pid"] = worker_pid

        if exit_code == 0:
            evidence_valid = True
            evidence_error_msg = ""

            if report_sha256 is None or not isinstance(report_sha256, str) or not RE_HEX_64.match(report_sha256):
                evidence_valid = False
                evidence_error_msg = f"INVALID_REPORT_DIGEST: Exit code 0 requires valid 64-char hex report_sha256, got '{report_sha256}'."

            if evidence_valid and output_report_path is not None:
                rep_path = Path(output_report_path)
                if not rep_path.exists():
                    evidence_valid = False
                    evidence_error_msg = f"REPORT_FILE_NOT_FOUND: Output report does not exist at '{rep_path}'."
                elif rep_path.is_symlink():
                    evidence_valid = False
                    evidence_error_msg = f"SYMLINK_REPORT_REJECTED: Output report at '{rep_path}' must not be a symlink."
                else:
                    raw_report = rep_path.read_bytes()
                    computed_sha256 = hashlib.sha256(raw_report).hexdigest().lower()
                    if computed_sha256 != report_sha256.lower():
                        evidence_valid = False
                        evidence_error_msg = f"REPORT_DIGEST_MISMATCH: Computed report SHA-256 {computed_sha256} != expected {report_sha256}."
                    else:
                        try:
                            parsed_report = parse_strict_json(raw_report)
                            expected_schema = f"nexvia-aegis-v9-holdout-{partition}-report/1.0"
                            if not isinstance(parsed_report, dict):
                                evidence_valid = False
                                evidence_error_msg = "MALFORMED_REPORT_JSON: Top-level report must be a JSON object."
                            elif parsed_report.get("partition") != partition:
                                evidence_valid = False
                                evidence_error_msg = f"REPORT_PARTITION_MISMATCH: Report partition '{parsed_report.get('partition')}' != expected '{partition}'."
                            elif parsed_report.get("ticket_nonce") != nonce:
                                evidence_valid = False
                                evidence_error_msg = f"REPORT_NONCE_MISMATCH: Report nonce '{parsed_report.get('ticket_nonce')}' != expected '{nonce}'."
                            else:
                                # Strict production status and simulation mode validation (F-02)
                                rep_status = parsed_report.get("status")
                                if rep_status != "COMPLETE_VALID":
                                    evidence_valid = False
                                    evidence_error_msg = f"MOCK_REPORT_REJECTED: Report status '{rep_status}' != 'COMPLETE_VALID'. Mock reports are strictly prohibited."
                                elif parsed_report.get("simulation_mode") != "PRODUCTION_PHYSICS":
                                    evidence_valid = False
                                    evidence_error_msg = f"MOCK_SIMULATION_REJECTED: Report simulation_mode '{parsed_report.get('simulation_mode')}' != 'PRODUCTION_PHYSICS'. Mock simulation is strictly prohibited."
                                elif parsed_report.get("schema_version") != expected_schema:
                                    evidence_valid = False
                                    evidence_error_msg = f"SCHEMA_VERSION_MISMATCH: Report schema_version '{parsed_report.get('schema_version')}' != '{expected_schema}'."
                        except Exception as e:
                            evidence_valid = False
                            evidence_error_msg = f"CORRUPTED_REPORT_PARSING_FAILED: Could not parse report JSON: {e}"

            if not evidence_valid:
                p_entry["status"] = "FAILED"
                p_entry["report_sha256"] = report_sha256
                ticket_entry["ticket_state"] = "FAILED_TERMINAL"
                _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)
                raise SecurityError(f"INVALID_OUTCOME_EVIDENCE: {evidence_error_msg}")

            p_entry["status"] = "CONSUMED"
            p_entry["report_sha256"] = report_sha256
            all_consumed = all(
                p["status"] == "CONSUMED" for p in ticket_entry["partitions"].values()
            )
            ticket_entry["ticket_state"] = "CLOSED" if all_consumed else "ACTIVE_PARTIAL"
        else:
            p_entry["status"] = "FAILED"
            p_entry["report_sha256"] = report_sha256
            ticket_entry["ticket_state"] = "FAILED_TERMINAL"

        _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

        return copy.deepcopy(ticket_entry)


def reconcile_stranded_claim(
    security_dir: Path | str | None,
    nonce: str,
    owner_confirmation: bool = False,
) -> bool:
    """Owner-controlled procedure to reconcile stranded claims resulting from supervisor crashes or SIGKILL.

    Enforces:
      - Automatic/implicit reconciliation at startup is strictly prohibited (requires owner_confirmation=True).
      - Checks both launcher_pid and worker_pid; fails closed if any process is still executing.
      - Preserves existing evidence and transitions partition to 'FAILED' (marker exit_code=-999).
      - Transitions ticket to 'FAILED_TERMINAL'.
      - Under no circumstances is a claimed partition ever restored to 'UNCLAIMED'.

    Returns:
        True if stranded claim was detected and transitioned to FAILED_TERMINAL, False otherwise.

    Raises:
        SecurityError: If owner confirmation is missing or if processes are still active.
    """
    if not owner_confirmation:
        raise SecurityError(
            "OWNER_CONFIRMATION_REQUIRED: Stranded claim reconciliation requires explicit owner confirmation. "
            "Implicit automatic recovery at startup is strictly prohibited."
        )

    sec_dir = resolve_security_dir(security_dir)

    with PersistentLedgerLock(sec_dir):
        ledger = read_ledger(sec_dir)

        if nonce not in ledger["active_tickets"]:
            return False

        ticket_entry = ledger["active_tickets"][nonce]
        modified = False

        for part_name, part_data in ticket_entry["partitions"].items():
            if part_data["status"] == "CLAIMED":
                launcher_pid = part_data.get("launcher_pid")
                worker_pid = part_data.get("worker_pid")

                # Verify process termination for both launcher and worker
                for pid, role in [(launcher_pid, "Launcher"), (worker_pid, "Worker")]:
                    if pid is not None:
                        try:
                            os.kill(pid, 0)
                            # Process is still alive!
                            raise SecurityError(
                                f"ACTIVE_PROCESS_DETECTED: {role} process (PID {pid}) is still active. "
                                "Cannot reconcile stranded claim while processes are executing."
                            )
                        except OSError as e:
                            if e.errno == errno.ESRCH:
                                # Process is dead
                                pass
                            elif e.errno == errno.EPERM:
                                raise SecurityError(
                                    f"PROCESS_EXISTENCE_UNCERTAIN: {role} process (PID {pid}) returned EPERM. "
                                    "Cannot verify process termination."
                                )
                            else:
                                raise SecurityError(
                                    f"PROCESS_CHECK_FAILED: {role} process (PID {pid}) check failed: {e}"
                                )

                # All recorded processes are confirmed dead; transition to terminal failure
                part_data["status"] = "FAILED"
                part_data["completed_at_utc"] = _current_utc_iso()
                part_data["exit_code"] = -999  # Marker for owner-reconciled stranded termination
                ticket_entry["ticket_state"] = "FAILED_TERMINAL"
                ticket_entry["active_partition"] = None
                modified = True

        if modified:
            _persist_ledger_crash_durable(sec_dir / LEDGER_FILE_NAME, ledger)

        return modified
