"""NEXVIA AEGIS Trusted Supervisory Launcher.

Implements the out-of-workspace supervisory execution harness, environment sanitization,
detached worktree execution, worker process-group supervision, and fail-closed outcome
verification under Contract AEGIS-V9-M4-CTR-01 (Revision 2.3).
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from nexvia_aegis.security.canonical import parse_strict_json
from nexvia_aegis.security.ledger import (
    ALLOWED_PARTITIONS,
    LEDGER_FILE_NAME,
    LOCK_FILE_NAME,
    SecurityError,
    execute_claim_transaction,
    execute_outcome_transaction,
    read_ledger,
    register_ticket,
    resolve_security_dir,
)
from nexvia_aegis.security.verifier import (
    RE_HEX_40,
    RE_HEX_64,
    validate_semantic_payload,
    verify_ticket_envelope,
)

OPERATIONAL_INTEGRITY_NOTICE = (
    "[SECURITY WARNING] Operational Boundary Notice: Filesystem permissions, "
    "read-only directory flags, and Git cleanliness alone DO NOT protect against a "
    "concurrent malicious process executing under the same user UID (501). "
    "Prior to live production launch, the project owner MUST suspend or terminate "
    "all autonomous agents and untrusted background processes."
)

DANGEROUS_ENV_VARS: frozenset[str] = frozenset({
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUSERBASE",
    "PYTHONSTARTUP",
    "PYTHONOPTIMIZE",
    "PYTHONHASHSEED",
    "PYTHONINSPECT",
    "PYTHONBREAKPOINT",
    "DYLD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "LD_AUDIT",
})


def sha256_file(path: Path | str) -> str:
    """Computes lowercase hex SHA-256 digest of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().lower()


def verify_trust_anchor(
    pubkey_anchor_path: Path | str,
    expected_pubkey_sha256: str,
) -> Ed25519PublicKey:
    """Verifies that the public key file matches the owner-pinned SHA-256 fingerprint.

    Args:
        pubkey_anchor_path: Path to PEM-encoded Ed25519 public key file.
        expected_pubkey_sha256: Expected 64-character lowercase hexadecimal SHA-256 digest.

    Returns:
        Loaded Ed25519PublicKey object.

    Raises:
        SecurityError: If file is missing, fingerprint mismatches, or key is invalid.
    """
    p = Path(pubkey_anchor_path)
    if not p.exists():
        raise SecurityError(
            f"TRUST_ANCHOR_FILE_NOT_FOUND: Public key file '{p}' does not exist."
        )
    if p.is_symlink():
        raise SecurityError(
            f"SYMLINK_TRUST_ANCHOR_REJECTED: Public key file '{p}' must not be a symlink."
        )

    raw_pem = p.read_bytes()
    computed_fp = hashlib.sha256(raw_pem).hexdigest().lower()
    expected_fp = expected_pubkey_sha256.strip().lower()

    if not hmac.compare_digest(computed_fp, expected_fp):
        raise SecurityError(
            f"TRUST_ANCHOR_FINGERPRINT_MISMATCH: Computed fingerprint '{computed_fp}' != expected '{expected_fp}'."
        )

    try:
        key = load_pem_public_key(raw_pem)
    except Exception as e:
        raise SecurityError(f"MALFORMED_TRUST_ANCHOR: Could not parse PEM public key: {e}") from e

    if not isinstance(key, Ed25519PublicKey):
        raise SecurityError(
            f"INVALID_KEY_TYPE: Expected Ed25519PublicKey, got {type(key).__name__}."
        )
    return key


def verify_launcher_integrity(
    launcher_path: Path | str | None = None,
    expected_launcher_sha256: str | None = None,
) -> str:
    """Verifies the integrity of the launcher script against an expected fingerprint.

    Args:
        launcher_path: Path to launcher script (defaults to this file).
        expected_launcher_sha256: Optional expected SHA-256 fingerprint.

    Returns:
        Actual SHA-256 hexadecimal digest of the launcher.

    Raises:
        SecurityError: If digest mismatches expected fingerprint.
    """
    p = Path(launcher_path) if launcher_path is not None else Path(__file__).resolve()
    if not p.exists():
        raise SecurityError(f"LAUNCHER_FILE_NOT_FOUND: Launcher script '{p}' not found.")

    raw = p.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest().lower()

    if expected_launcher_sha256 is not None:
        expected = expected_launcher_sha256.strip().lower()
        if not hmac.compare_digest(actual_sha, expected):
            raise SecurityError(
                f"LAUNCHER_DIGEST_MISMATCH: Launcher script SHA-256 {actual_sha} != expected {expected}."
            )
    return actual_sha


def sanitize_environment(
    base_env: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Sanitizes environment dictionary by stripping dangerous library and python overrides.

    Args:
        base_env: Base environment dictionary (defaults to os.environ).
        extra_env: Additional variables to inject cleanly (e.g. auth credentials).

    Returns:
        New sanitized environment dictionary.
    """
    source = os.environ if base_env is None else base_env
    clean: dict[str, str] = {}

    for k, v in source.items():
        if k in DANGEROUS_ENV_VARS:
            continue
        clean[k] = v

    # Clean minimal defaults if missing
    clean["PYTHONUNBUFFERED"] = "1"
    clean["PYTHONDONTWRITEBYTECODE"] = "1"

    if extra_env:
        for k, v in extra_env.items():
            clean[k] = str(v)

    return clean


def verify_runtime_integrity(
    python_executable: Path | str,
    repo_or_worktree_dir: Path | str,
    expected_lockfile_sha256: str,
    expected_python_version: str | None = None,
) -> None:
    """Verifies that the Python runtime and dependency lockfile meet exact release standards.

    Args:
        python_executable: Path to python interpreter to be invoked.
        repo_or_worktree_dir: Directory containing uv.lock.
        expected_lockfile_sha256: 64-char hex expected SHA-256 of uv.lock.
        expected_python_version: Expected Python version (defaults to active 3.12.14).

    Raises:
        SecurityError: If interpreter fails, version differs, or lockfile hash mismatches.
    """
    py_path = Path(python_executable).resolve()
    if not py_path.exists():
        raise SecurityError(
            f"RUNTIME_INTEGRITY_MISMATCH: Python interpreter '{py_path}' does not exist."
        )

    # Check lockfile hash
    lock_path = Path(repo_or_worktree_dir) / "uv.lock"
    if not lock_path.exists():
        raise SecurityError(
            f"RUNTIME_INTEGRITY_MISMATCH: Lockfile uv.lock not found in '{repo_or_worktree_dir}'."
        )

    actual_lock_sha = sha256_file(lock_path)
    expected_lock = expected_lockfile_sha256.strip().lower()
    if not hmac.compare_digest(actual_lock_sha, expected_lock):
        raise SecurityError(
            f"RUNTIME_INTEGRITY_MISMATCH: uv.lock SHA-256 {actual_lock_sha} != expected {expected_lock}."
        )

    # Check python version
    target_ver = expected_python_version or f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    try:
        res = subprocess.run(
            [str(py_path), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"],
            capture_output=True,
            text=True,
            check=True,
        )
        actual_ver = res.stdout.strip()
    except Exception as e:
        raise SecurityError(
            f"RUNTIME_INTEGRITY_MISMATCH: Failed to query Python interpreter version from '{py_path}': {e}"
        ) from e

    if actual_ver != target_ver:
        raise SecurityError(
            f"RUNTIME_INTEGRITY_MISMATCH: Python interpreter version '{actual_ver}' != expected '{target_ver}'."
        )


def reconcile_execution_tree(
    repo_dir: Path | str,
    approved_commit: str,
    expected_hashes: dict[str, str],
    check_git_cleanliness: bool = True,
) -> None:
    """Verifies that the target execution tree matches the approved commit and frozen artifacts.

    Args:
        repo_dir: Path to the repository or worktree root.
        approved_commit: 40-char hex commit SHA-1.
        expected_hashes: Dictionary mapping artifact identifiers to expected SHA-256 hashes.
        check_git_cleanliness: Whether to enforce git status cleanliness.

    Raises:
        SecurityError: If commit differs, git tree is dirty, or any artifact digest mismatches.
    """
    root = Path(repo_dir).resolve()

    # 1. Commit check
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        current_commit = res.stdout.strip().lower()
    except Exception as e:
        raise SecurityError(f"EXECUTION_TREE_CHECK_FAILED: Could not resolve git commit: {e}") from e

    if current_commit != approved_commit.lower():
        raise SecurityError(
            f"COMMIT_MISMATCH: Execution tree HEAD '{current_commit}' != approved commit '{approved_commit.lower()}'."
        )

    # 2. Git Cleanliness check
    if check_git_cleanliness:
        try:
            status_res = subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            dirty_output = status_res.stdout.strip()
            if dirty_output:
                raise SecurityError(
                    f"DIRTY_EXECUTION_TREE: Uncommitted or untracked changes detected in execution tree:\n{dirty_output}"
                )
        except subprocess.CalledProcessError as e:
            raise SecurityError(f"EXECUTION_TREE_CHECK_FAILED: git status check failed: {e}") from e

    # 3. Artifact Hashes Reconciliation
    artifact_paths: dict[str, Path] = {
        "evaluator_artifact_sha256": root / "experiments" / "v9_evaluate_holdout.py",
        "policy_sha256": root / "results" / "v9" / "cal_r2" / "selected_policy.json",
        "mixture_manifest_sha256": root / "results" / "v9" / "manifests" / "test_mix_manifest_r1.json",
        "scenario_manifest_sha256": root / "results" / "v9" / "manifests" / "test_scen_manifest_r1.json",
        "lockfile_sha256": root / "uv.lock",
    }

    for key, path in artifact_paths.items():
        expected_sha = expected_hashes.get(key)
        if expected_sha is None:
            raise SecurityError(f"MISSING_EXPECTED_HASH: Expected hash for '{key}' not provided.")

        if not path.exists():
            raise SecurityError(f"ARTIFACT_FILE_NOT_FOUND: Required artifact '{path}' does not exist.")

        actual_sha = sha256_file(path)
        if not hmac.compare_digest(actual_sha, expected_sha.lower()):
            raise SecurityError(
                f"ARTIFACT_DIGEST_MISMATCH: Artifact '{path.name}' hash {actual_sha} != expected {expected_sha.lower()}."
            )


def prepare_detached_worktree(
    repo_dir: Path | str,
    approved_commit: str,
    worktree_dir: Path | str,
) -> Path:
    """Creates a pristine detached Git worktree checked out at approved_commit."""
    repo_root = Path(repo_dir).resolve()
    wt_path = Path(worktree_dir).resolve()

    if wt_path.exists():
        raise SecurityError(
            f"WORKTREE_TARGET_EXISTS: Detached worktree destination '{wt_path}' already exists."
        )

    cmd = ["git", "worktree", "add", "--detach", str(wt_path), approved_commit]
    try:
        subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise SecurityError(
            f"DETACHED_WORKTREE_CREATION_FAILED: Failed to create detached worktree at '{wt_path}': {e.stderr}"
        ) from e

    return wt_path


def cleanup_detached_worktree(
    repo_dir: Path | str,
    worktree_dir: Path | str,
) -> None:
    """Removes a detached Git worktree safely."""
    repo_root = Path(repo_dir).resolve()
    wt_path = Path(worktree_dir).resolve()

    if not wt_path.exists():
        return

    cmd = ["git", "worktree", "remove", "--force", str(wt_path)]
    try:
        subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)
    except Exception as e:
        print(f"[LAUNCHER WARNING] Could not remove detached worktree '{wt_path}': {e}", file=sys.stderr)


def supervise_worker(
    worker_cmd: list[str],
    cwd: Path | str,
    env: dict[str, str],
    timeout_seconds: int = 7200,
) -> tuple[int, int]:
    """Spawns and supervises a worker subprocess inside a new process group.

    Args:
        worker_cmd: Command list to execute.
        cwd: Working directory.
        env: Sanitized environment dictionary.
        timeout_seconds: Maximum allowed execution duration before termination.

    Returns:
        Tuple of (exit_code, worker_pid).

    Raises:
        SecurityError: On timeout, launch failure, or process error.
    """
    # Start in a new session (process group) so child processes are cleanly monitored and killed
    try:
        proc = subprocess.Popen(
            worker_cmd,
            cwd=str(cwd),
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        raise SecurityError(f"WORKER_SPAWN_FAILED: Could not launch worker process: {e}") from e

    worker_pid = proc.pid

    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return proc.returncode, worker_pid
    except subprocess.TimeoutExpired:
        # Graceful termination first (SIGTERM to process group)
        try:
            pgid = os.getpgid(worker_pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # Wait grace period of 5 seconds
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Forceful termination (SIGKILL to process group)
            try:
                pgid = os.getpgid(worker_pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()

        raise SecurityError(
            f"WORKER_TIMEOUT: Worker exceeded maximum execution timeout of {timeout_seconds} seconds."
        )


def validate_output_report(
    report_path: Path | str,
    expected_partition: str,
    expected_nonce: str,
    output_root: Path | str,
    expected_hashes: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Securely validates and reads worker output report from open file descriptor.

    Enforces:
      - File confinement within authorized partition directory under output root.
      - Regular file verification and rejection of symbolic links.
      - Reading bytes securely via open file descriptor with O_NOFOLLOW.
      - SHA-256 digest computation over the exact bytes read.
      - Strict JSON parsing with duplicate-key rejection.
      - Binding validation: partition, ticket_nonce, and accepted status.

    Returns:
        Tuple of (report_sha256_hex, parsed_report_payload).

    Raises:
        SecurityError: If report is missing, invalid, malformed, or unverified.
    """
    rep_p = Path(report_path)
    root_p = Path(output_root).resolve()

    # Reject symbolic links immediately before resolving
    if rep_p.is_symlink() or os.path.islink(str(rep_p)):
        raise SecurityError(f"SYMLINK_REPORT_REJECTED: Report '{rep_p}' must not be a symbolic link.")

    part_tag = "mix" if expected_partition == "mixture" else "scen"
    expected_part_dir = root_p / f"test_{part_tag}"

    resolved_rep = rep_p.resolve()
    if not resolved_rep.is_relative_to(expected_part_dir):
        raise SecurityError(
            f"OUT_OF_ROOT_REPORT_REJECTED: Report '{rep_p}' is outside authorized partition directory '{expected_part_dir}'."
        )

    if not rep_p.exists():
        raise SecurityError(f"REPORT_FILE_NOT_FOUND: Output report does not exist at '{rep_p}'.")

    # Secure open with O_NOFOLLOW to defend against TOCTOU symlink replacement races
    open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(rep_p), open_flags)
    except OSError as e:
        # ELOOP is raised by O_NOFOLLOW if target is a symbolic link
        if getattr(e, "errno", None) in (getattr(os, "ELOOP", 62), 62, 40):
            raise SecurityError(f"SYMLINK_REPORT_REJECTED: Report '{rep_p}' is a symlink: {e}") from e
        raise SecurityError(f"REPORT_OPEN_FAILED: Could not securely open report file '{rep_p}': {e}") from e

    try:
        raw_bytes = os.read(fd, 20 * 1024 * 1024)  # read up to 20MB
    finally:
        os.close(fd)

    report_sha256 = hashlib.sha256(raw_bytes).hexdigest().lower()

    try:
        report_payload = parse_strict_json(raw_bytes)
    except Exception as e:
        raise SecurityError(f"MALFORMED_REPORT_JSON: Could not parse report JSON: {e}") from e

    if not isinstance(report_payload, dict):
        raise SecurityError("MALFORMED_REPORT_JSON: Top-level report must be a JSON dictionary.")

    # Strict binding checks
    actual_part = report_payload.get("partition")
    if actual_part != expected_partition:
        raise SecurityError(
            f"REPORT_PARTITION_MISMATCH: Report partition '{actual_part}' != expected '{expected_partition}'."
        )

    actual_nonce = report_payload.get("ticket_nonce")
    if actual_nonce != expected_nonce:
        raise SecurityError(
            f"REPORT_NONCE_MISMATCH: Report ticket_nonce '{actual_nonce}' != expected '{expected_nonce}'."
        )

    # Strict production status and simulation mode validation (F-02)
    status = report_payload.get("status")
    if status != "COMPLETE_VALID":
        raise SecurityError(
            f"MOCK_REPORT_REJECTED: Expected report status 'COMPLETE_VALID', got '{status}'. "
            "Mock reports are strictly prohibited in production."
        )

    sim_mode = report_payload.get("simulation_mode")
    if sim_mode != "PRODUCTION_PHYSICS":
        raise SecurityError(
            f"MOCK_SIMULATION_REJECTED: Expected simulation_mode 'PRODUCTION_PHYSICS', got '{sim_mode}'. "
            "Mock simulation is strictly prohibited in production."
        )

    expected_schema = f"nexvia-aegis-v9-holdout-{expected_partition}-report/1.0"
    if report_payload.get("schema_version") != expected_schema:
        raise SecurityError(
            f"SCHEMA_VERSION_MISMATCH: Expected schema '{expected_schema}', got '{report_payload.get('schema_version')}'."
        )

    # Report Provenance & Artifact Verification (F-04)
    if expected_hashes is not None:
        run_cfg = report_payload.get("run_config")
        if not isinstance(run_cfg, dict):
            raise SecurityError("MALFORMED_REPORT_RUN_CONFIG: Report run_config must be a dictionary.")
        if run_cfg.get("partition") != expected_partition:
            raise SecurityError(
                f"PROVENANCE_PARTITION_MISMATCH: run_config partition '{run_cfg.get('partition')}' != '{expected_partition}'."
            )
        expected_pol_sha = expected_hashes.get("policy_sha256")
        if expected_pol_sha and run_cfg.get("selected_policy_raw_sha256") != expected_pol_sha:
            raise SecurityError(
                f"PROVENANCE_POLICY_MISMATCH: Report policy digest '{run_cfg.get('selected_policy_raw_sha256')}' != expected '{expected_pol_sha}'."
            )
        if expected_partition == "mixture":
            expected_man_sha = expected_hashes.get("mixture_manifest_sha256")
            if expected_man_sha and run_cfg.get("manifest_raw_sha256") != expected_man_sha:
                raise SecurityError(
                    f"PROVENANCE_MANIFEST_MISMATCH: Report mixture manifest digest '{run_cfg.get('manifest_raw_sha256')}' != expected '{expected_man_sha}'."
                )
        elif expected_partition == "scenario":
            expected_man_sha = expected_hashes.get("scenario_manifest_sha256")
            if expected_man_sha and run_cfg.get("manifest_raw_sha256") != expected_man_sha:
                raise SecurityError(
                    f"PROVENANCE_MANIFEST_MISMATCH: Report scenario manifest digest '{run_cfg.get('manifest_raw_sha256')}' != expected '{expected_man_sha}'."
                )

    # Artifact verification
    artifact_shas = report_payload.get("artifact_sha256")
    if not isinstance(artifact_shas, dict) or not artifact_shas:
        raise SecurityError("MALFORMED_ARTIFACT_SHAS: Report must contain non-empty artifact_sha256 map.")

    for art_path_str, recorded_sha in artifact_shas.items():
        p_candidate = Path(art_path_str)
        if not p_candidate.is_absolute():
            p_candidate = output_root.parent / art_path_str
        if not p_candidate.exists():
            p_candidate = rep_p.parent / Path(art_path_str).name
        if not p_candidate.exists():
            raise SecurityError(f"REPORT_ARTIFACT_NOT_FOUND: Output artifact '{art_path_str}' does not exist.")
        if p_candidate.is_symlink():
            raise SecurityError(f"SYMLINK_REPORT_ARTIFACT_REJECTED: Output artifact '{p_candidate}' must not be a symlink.")
        actual_art_sha = hashlib.sha256(p_candidate.read_bytes()).hexdigest().lower()
        if actual_art_sha != recorded_sha.lower():
            raise SecurityError(
                f"REPORT_ARTIFACT_DIGEST_MISMATCH: Artifact '{art_path_str}' sha {actual_art_sha} != expected {recorded_sha}."
            )

    # Phase 4 Audit Record Binding Validation
    auth_rec_sha = report_payload.get("authorization_record_sha256")
    if auth_rec_sha is not None:
        auth_file = rep_p.parent / "authorization_record.json"
        if not auth_file.exists():
            raise SecurityError(f"REPORT_ARTIFACT_NOT_FOUND: Authorization record '{auth_file}' does not exist.")
        if auth_file.is_symlink():
            raise SecurityError(f"SYMLINK_REPORT_ARTIFACT_REJECTED: Authorization record '{auth_file}' must not be a symlink.")
        actual_auth_sha = hashlib.sha256(auth_file.read_bytes()).hexdigest().lower()
        if actual_auth_sha != auth_rec_sha.lower():
            raise SecurityError(
                f"REPORT_ARTIFACT_DIGEST_MISMATCH: Authorization record digest {actual_auth_sha} != expected {auth_rec_sha}."
            )
        try:
            parsed_auth = parse_strict_json(auth_file.read_bytes())
            if not isinstance(parsed_auth, dict):
                raise SecurityError("MALFORMED_AUTHORIZATION_RECORD: Authorization record must be a JSON object.")
            if parsed_auth.get("schema_version") != "nexvia-aegis-v9-authorization-record/1.0":
                raise SecurityError(f"SCHEMA_VERSION_MISMATCH: Authorization record schema '{parsed_auth.get('schema_version')}' != expected 'nexvia-aegis-v9-authorization-record/1.0'.")
            if parsed_auth.get("ticket_nonce") != expected_nonce:
                raise SecurityError(f"REPORT_NONCE_MISMATCH: Authorization record nonce '{parsed_auth.get('ticket_nonce')}' != expected '{expected_nonce}'.")
            if parsed_auth.get("authorized_partition") != expected_partition:
                raise SecurityError(f"REPORT_PARTITION_MISMATCH: Authorization record partition '{parsed_auth.get('authorized_partition')}' != expected '{expected_partition}'.")
        except SecurityError:
            raise
        except Exception as e:
            raise SecurityError(f"MALFORMED_AUTHORIZATION_RECORD: Could not parse authorization record JSON: {e}") from e

    return report_sha256, report_payload


def evaluate_execution_statuses(
    exit_code: int,
    report_valid: bool,
    report_payload: dict[str, Any] | None,
) -> dict[str, str]:
    """Distinguishes execution completion, output integrity, provenance, and statistical acceptance."""
    exec_status = "COMPLETED" if exit_code == 0 else "PROCESS_ERROR"
    integrity_status = "INTEGRITY_VERIFIED" if report_valid else "INTEGRITY_FAILED"
    provenance_status = "PROVENANCE_VERIFIED" if report_valid else "PROVENANCE_FAILED"

    stat_status = "NOT_EVALUATED"
    if report_valid and report_payload:
        eval_summary = report_payload.get("evaluation_summary", {})
        m_accepted = eval_summary.get("m_accepted")
        stat_flag = eval_summary.get("statistical_acceptance", False)
        if m_accepted == 1 or stat_flag is True:
            stat_status = "ACCEPTED"
        else:
            stat_status = "REJECTED"

    return {
        "execution_completion": exec_status,
        "output_integrity": integrity_status,
        "execution_provenance": provenance_status,
        "statistical_acceptance": stat_status,
    }


def launch_gate_b_partition(
    security_dir: Path | str | None,
    ticket_path: Path | str,
    pubkey_anchor_path: Path | str,
    expected_pubkey_sha256: str,
    repo_dir: Path | str,
    partition: str,
    expected_launcher_sha256: str | None = None,
    python_executable: Path | str | None = None,
    timeout_seconds: int = 7200,
    use_detached_worktree: bool = True,
    worktree_dir: Path | str | None = None,
    custom_worker_cmd: list[str] | None = None,
    check_git_cleanliness: bool = True,
    public_key_obj: Ed25519PublicKey | None = None,
) -> dict[str, Any]:
    """Supervisory entry point executing a single Gate B partition under strict authorization.

    Returns:
        Execution audit dictionary containing final status and ledger state.

    Raises:
        SecurityError: On any authorization, integrity, or execution failure.
    """
    if partition not in ALLOWED_PARTITIONS:
        raise SecurityError(f"INVALID_PARTITION: Expected one of {sorted(ALLOWED_PARTITIONS)}, got '{partition}'.")

    # Step 0: Print Operational Boundary Notice
    print(OPERATIONAL_INTEGRITY_NOTICE)

    # Step 1: Verify launcher self-integrity
    verify_launcher_integrity(expected_launcher_sha256=expected_launcher_sha256)

    # Step 2: Verify public key trust anchor
    if public_key_obj is None:
        pubkey = verify_trust_anchor(pubkey_anchor_path, expected_pubkey_sha256)
    else:
        pubkey = public_key_obj

    # Step 3: Parse and cryptographically verify authorization ticket
    ticket_file = Path(ticket_path)
    if not ticket_file.exists():
        raise SecurityError(f"TICKET_FILE_NOT_FOUND: Ticket file '{ticket_file}' does not exist.")

    raw_ticket = ticket_file.read_bytes()
    verified_envelope = verify_ticket_envelope(raw_ticket, public_key_obj=pubkey)
    payload = verified_envelope["payload"]
    nonce = payload["nonce"]

    # Step 4: Register ticket with replay ledger if not already active (burns nonce)
    sec_dir = resolve_security_dir(security_dir)
    current_ledger = read_ledger(sec_dir)
    if nonce not in current_ledger["active_tickets"]:
        register_ticket(
            ticket_data=raw_ticket,
            security_dir=sec_dir,
            public_key_obj=pubkey,
        )

    # Step 5: Reconcile Execution Tree (Commit and 5 Frozen Artifact Hashes)
    repo_root = Path(repo_dir).resolve()
    reconcile_execution_tree(
        repo_dir=repo_root,
        approved_commit=payload["approved_commit"],
        expected_hashes=payload,
        check_git_cleanliness=check_git_cleanliness,
    )

    # Step 6: Prepare Worktree
    created_worktree: Path | None = None
    if use_detached_worktree:
        wt_target = Path(worktree_dir) if worktree_dir else (repo_root.parent / f"nexvia_wt_{nonce[:12]}_{partition}")
        execution_root = prepare_detached_worktree(repo_root, payload["approved_commit"], wt_target)
        created_worktree = execution_root
    else:
        execution_root = repo_root

    py_exe = Path(python_executable) if python_executable else (repo_root / ".venv" / "bin" / "python")

    try:
        # Step 7: Verify Runtime Integrity
        verify_runtime_integrity(
            python_executable=py_exe,
            repo_or_worktree_dir=execution_root,
            expected_lockfile_sha256=payload["lockfile_sha256"],
        )

        # Step 8: Atomic Under-Lock Claim Transaction
        # Partition status becomes CLAIMED before worker is launched
        claimed_entry = execute_claim_transaction(sec_dir, nonce, partition)

        # Step 9: Prepare Sanitized Worker Environment
        extra_env = {
            "V9_M4_TICKET_PATH": str(ticket_file.resolve()),
            "V9_M4_CLAIM_SECRET": claimed_entry.get("claim_secret", ""),
            "V9_M4_TICKET_NONCE": nonce,
            "V9_M4_PARTITION": partition,
            "V9_M4_SECURITY_DIR": str(sec_dir.resolve()),
            "V9_M4_PUBKEY_ANCHOR": str(Path(pubkey_anchor_path).resolve()),
            "V9_M4_EXPECTED_PUBKEY_SHA256": expected_pubkey_sha256,
        }
        worker_env = sanitize_environment(extra_env=extra_env)

        # Step 10: Determine Worker Command Line
        output_root = execution_root / payload["target_output_root"]
        part_tag = "mix" if partition == "mixture" else "scen"
        report_path = output_root / f"test_{part_tag}" / f"test_{part_tag}_report.json"

        if custom_worker_cmd:
            worker_cmd = copy.deepcopy(custom_worker_cmd)
        else:
            worker_cmd = [
                str(py_exe),
                str(execution_root / "experiments" / "v9_evaluate_holdout.py"),
                "--partition", partition,
                "--output-dir", str(output_root),
                "--run-production",
            ]

        # Step 11: Supervise Worker Subprocess
        exit_code, worker_pid = supervise_worker(
            worker_cmd=worker_cmd,
            cwd=execution_root,
            env=worker_env,
            timeout_seconds=timeout_seconds,
        )

        # Step 12: Validate Terminal Output Evidence
        report_sha256: str | None = None
        report_payload: dict[str, Any] | None = None
        report_valid = False

        if exit_code == 0:
            try:
                report_sha256, report_payload = validate_output_report(
                    report_path=report_path,
                    expected_partition=partition,
                    expected_nonce=nonce,
                    output_root=output_root,
                    expected_hashes=payload,
                )
                report_valid = True
            except SecurityError as e:
                # Evidence validation failed; mark fail-closed
                execute_outcome_transaction(
                    security_dir=sec_dir,
                    nonce=nonce,
                    partition=partition,
                    exit_code=1,  # treat as failed outcome
                    report_sha256="00" * 32,
                    worker_pid=worker_pid,
                    output_report_path=report_path,
                )
                raise

        # Step 13: Under-Lock Outcome Transaction
        updated_entry = execute_outcome_transaction(
            security_dir=sec_dir,
            nonce=nonce,
            partition=partition,
            exit_code=exit_code,
            report_sha256=report_sha256,
            worker_pid=worker_pid,
            output_report_path=report_path,
        )

        # Step 14: Distinguish Statuses
        status_triplet = evaluate_execution_statuses(
            exit_code=exit_code,
            report_valid=report_valid,
            report_payload=report_payload,
        )

        return {
            "ticket_nonce": nonce,
            "partition": partition,
            "exit_code": exit_code,
            "worker_pid": worker_pid,
            "report_sha256": report_sha256,
            "statuses": status_triplet,
            "ticket_state": updated_entry["ticket_state"],
            "partition_status": updated_entry["partitions"][partition]["status"],
        }

    finally:
        if created_worktree:
            cleanup_detached_worktree(repo_root, created_worktree)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS Trusted Supervisory Launcher (Gate B Confirmatory Evaluation)."
    )
    parser.add_argument("--ticket", required=True, type=Path, help="Path to gate_b_authorization_ticket.json.")
    parser.add_argument("--pubkey", required=True, type=Path, help="Path to PEM public verification key.")
    parser.add_argument("--pubkey-fingerprint", required=True, type=str, help="Pinned SHA-256 fingerprint of pubkey.")
    parser.add_argument("--repo-dir", type=Path, default=_REPO_ROOT, help="Path to repository root.")
    parser.add_argument("--partition", choices=["mixture", "scenario"], required=True, help="Partition to claim and run.")
    parser.add_argument("--security-dir", type=Path, default=None, help="Security directory (defaults to ~/.nexvia_security).")
    parser.add_argument("--launcher-fingerprint", type=str, default=None, help="Optional expected SHA-256 of launcher.")
    parser.add_argument("--timeout-seconds", type=int, default=7200, help="Worker execution timeout in seconds.")
    args = parser.parse_args()

    try:
        result = launch_gate_b_partition(
            security_dir=args.security_dir,
            ticket_path=args.ticket,
            pubkey_anchor_path=args.pubkey,
            expected_pubkey_sha256=args.pubkey_fingerprint,
            repo_dir=args.repo_dir,
            partition=args.partition,
            expected_launcher_sha256=args.launcher_fingerprint,
            timeout_seconds=args.timeout_seconds,
        )
        print(f"[LAUNCHER SUCCESS] Partition '{args.partition}' execution completed successfully.")
        print(f"[LAUNCHER RESULT] Nonce:          {result['ticket_nonce']}")
        print(f"[LAUNCHER RESULT] Status:         {result['partition_status']}")
        print(f"[LAUNCHER RESULT] Ticket State:   {result['ticket_state']}")
        print(f"[LAUNCHER RESULT] Audit Statuses: {result['statuses']}")
        return 0
    except SecurityError as e:
        print(f"[LAUNCHER SECURITY ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[LAUNCHER UNEXPECTED ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
