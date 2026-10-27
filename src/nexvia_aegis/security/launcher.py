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
import threading
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
from nexvia_aegis.security.runtime_integrity import verify_runtime_integrity
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
    clean["PYTHONNOUSERSITE"] = "1"

    if extra_env:
        for k, v in extra_env.items():
            clean[k] = str(v)

    return clean


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

    # A dirty worktree may contain the only copy of partial evidence. Git refuses
    # removal without --force, which is the desired fail-closed behavior here.
    cmd = ["git", "worktree", "remove", str(wt_path)]
    try:
        subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[LAUNCHER WARNING] Retaining worktree '{wt_path}' for evidence review: {e.stderr}", file=sys.stderr)


def build_default_worker_command(
    python_executable: Path | str,
    execution_root: Path | str,
    partition: str,
    out_dir: Path | str,
) -> list[str]:
    """Builds the evaluator's actual CLI without accessing a manifest or episode."""
    if partition not in ALLOWED_PARTITIONS:
        raise SecurityError(f"INVALID_PARTITION: Unknown partition '{partition}'.")
    out_path = Path(out_dir).resolve()
    expected_leaf = "test_mix" if partition == "mixture" else "test_scen"
    if out_path.name != expected_leaf or out_path.parent.name != "v9":
        raise SecurityError(f"INVALID_OUTPUT_DIRECTORY: Expected results/v9/{expected_leaf}, got '{out_path}'.")
    return [
        str(python_executable),
        "-I",
        str(Path(execution_root) / "experiments" / "v9_evaluate_holdout.py"),
        "--partition", partition,
        "--out-dir", str(out_path),
        "--run-production",
    ]


def resolve_evidence_output_root(
    evidence_root: Path | str,
    nonce: str,
    repository_root: Path | str,
    execution_root: Path | str,
) -> Path:
    """Selects a durable ticket-scoped output tree outside both Git worktrees."""
    root_arg = Path(evidence_root)
    if not root_arg.is_absolute() or not root_arg.is_dir() or root_arg.is_symlink():
        raise SecurityError("INVALID_EVIDENCE_ROOT: Owner-approved evidence root must be an existing absolute directory, not a symlink.")
    root = root_arg.resolve()
    repo = Path(repository_root).resolve()
    execution = Path(execution_root).resolve()
    if (root.is_relative_to(repo) or root.is_relative_to(execution)
            or repo.is_relative_to(root) or execution.is_relative_to(root)):
        raise SecurityError("EVIDENCE_ROOT_NOT_ISOLATED: Evidence root must be outside the repository and execution worktree.")
    if not os.access(root, os.W_OK | os.X_OK):
        raise SecurityError(f"EVIDENCE_ROOT_NOT_WRITABLE: '{root}' is not writable.")
    if not RE_HEX_64.fullmatch(nonce):
        raise SecurityError("INVALID_NONCE: Ticket nonce must be 64 lowercase hexadecimal characters.")
    probe = root / f".nexvia_write_probe_{nonce[:12]}_{os.getpid()}"
    try:
        with probe.open("xb") as out:
            out.flush()
            os.fsync(out.fileno())
    except OSError as exc:
        raise SecurityError(f"EVIDENCE_ROOT_NOT_WRITABLE: Cannot create a probe in '{root}'.") from exc
    finally:
        probe.unlink(missing_ok=True)
    output_root = root / nonce / "results" / "v9"
    for ancestor in (root / nonce, root / nonce / "results", output_root):
        if ancestor.is_symlink() or (ancestor.exists() and not ancestor.is_dir()):
            raise SecurityError(f"INVALID_EVIDENCE_PATH: '{ancestor}' must be a directory and not a symlink.")
        if not ancestor.resolve().is_relative_to(root):
            raise SecurityError(f"EVIDENCE_PATH_ESCAPE: '{ancestor}' resolves outside the evidence root.")
    return output_root


def write_evidence_inventory(partition_dir: Path | str) -> Path:
    """Writes an exclusive, synced SHA-256 inventory of files retained so far."""
    part_dir = Path(partition_dir)
    inventory = part_dir / "sha256_inventory.json"
    if inventory.exists():
        raise SecurityError(f"EVIDENCE_INVENTORY_EXISTS: '{inventory}' already exists.")
    hashes: dict[str, str] = {}
    for candidate in sorted(part_dir.rglob("*")):
        if candidate.is_symlink():
            raise SecurityError(f"INVALID_EVIDENCE_PATH: '{candidate}' is a symbolic link.")
        if candidate == inventory or candidate.is_dir():
            continue
        if not candidate.is_file():
            raise SecurityError(f"INVALID_EVIDENCE_PATH: '{candidate}' is not a regular file.")
        hashes[str(candidate.relative_to(part_dir))] = sha256_file(candidate)
    payload = {"schema_version": "nexvia-aegis-evidence-inventory/1.0", "artifact_sha256": hashes}
    with inventory.open("x", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    dir_fd = os.open(part_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return inventory


def write_incomplete_marker(partition_dir: Path | str, reason: str) -> None:
    """Leaves a durable, non-overwriting marker without serializing secrets."""
    part_dir = Path(partition_dir)
    part_dir.mkdir(parents=True, exist_ok=True)
    marker = part_dir / "INCOMPLETE_INVALID.json"
    if marker.is_symlink():
        raise SecurityError(f"INVALID_EVIDENCE_PATH: '{marker}' is a symbolic link.")
    if marker.exists():
        return
    with marker.open("x", encoding="utf-8") as out:
        json.dump({"status": "INCOMPLETE_INVALID", "reason_code": reason, "created_utc": datetime.now(timezone.utc).isoformat()}, out)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    dir_fd = os.open(part_dir, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def verify_evaluator_cli(python_executable: Path | str, execution_root: Path | str) -> None:
    """Checks the real evaluator parser via --help before any ledger claim."""
    evaluator = Path(execution_root) / "experiments" / "v9_evaluate_holdout.py"
    result = subprocess.run(
        [str(python_executable), "-I", str(evaluator), "--help"],
        cwd=execution_root,
        env=sanitize_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or "--out-dir" not in result.stdout or "--run-production" not in result.stdout:
        raise SecurityError("EVALUATOR_CLI_PREFLIGHT_FAILED: Evaluator help/parser does not expose required production arguments.")


def supervise_worker(
    worker_cmd: list[str],
    cwd: Path | str,
    env: dict[str, str],
    timeout_seconds: int = 7200,
    log_dir: Path | str | None = None,
    redacted_values: tuple[str, ...] = (),
    max_log_bytes: int = 8 * 1024 * 1024,
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
    if max_log_bytes <= 0:
        raise SecurityError("INVALID_LOG_BOUND: max_log_bytes must be positive.")
    target = Path(log_dir) if log_dir is not None else None
    if target is not None:
        target.mkdir(parents=True, exist_ok=True)
        if any((target / name).exists() or (target / name).is_symlink()
               for name in ("worker.stdout.log", "worker.stderr.log")):
            raise SecurityError(f"WORKER_LOG_EXISTS: Refusing to overwrite logs in '{target}'.")
    # Start in a new process group; the launcher never prints the worker environment.
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
    threads: list[threading.Thread] = []
    log_errors: list[Exception] = []
    if target is not None:
        secrets = tuple(value.encode("utf-8") for value in redacted_values if value)

        def drain(stream: Any, path: Path) -> None:
            try:
                pending = b""
                holdback = max((len(secret) for secret in secrets), default=1) - 1
                written = 0
                truncated = False
                with path.open("xb") as out:
                    while True:
                        chunk = stream.read(4096)
                        if not chunk:
                            break
                        pending += chunk
                        for secret in secrets:
                            pending = pending.replace(secret, b"*" * len(secret))
                        ready_len = max(0, len(pending) - holdback)
                        ready, pending = pending[:ready_len], pending[ready_len:]
                        remaining = max_log_bytes - written
                        if remaining > 0:
                            block = ready[:remaining]
                            out.write(block)
                            written += len(block)
                        if len(ready) > remaining:
                            truncated = True
                    for secret in secrets:
                        pending = pending.replace(secret, b"*" * len(secret))
                    remaining = max_log_bytes - written
                    if remaining > 0:
                        out.write(pending[:remaining])
                    if len(pending) > remaining:
                        truncated = True
                    if truncated:
                        out.write(b"\n[LOG_TRUNCATED_AT_BOUND]\n")
                    out.flush()
                    os.fsync(out.fileno())
            except Exception as exc:
                log_errors.append(exc)
            finally:
                stream.close()

        for stream, filename in ((proc.stdout, "worker.stdout.log"), (proc.stderr, "worker.stderr.log")):
            assert stream is not None
            thread = threading.Thread(target=drain, args=(stream, target / filename), daemon=True)
            thread.start()
            threads.append(thread)

    def terminate_group() -> None:
        try:
            os.killpg(os.getpgid(worker_pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(worker_pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()

    try:
        if threads:
            proc.wait(timeout=timeout_seconds)
        else:
            proc.communicate(timeout=timeout_seconds)
        return proc.returncode, worker_pid
    except subprocess.TimeoutExpired as exc:
        terminate_group()
        raise SecurityError(
            f"WORKER_TIMEOUT: Worker exceeded maximum execution timeout of {timeout_seconds} seconds."
        ) from exc
    except BaseException:
        terminate_group()
        raise
    finally:
        for thread in threads:
            thread.join(timeout=10)
            if thread.is_alive():
                raise SecurityError("WORKER_LOG_FAILURE: Log drain did not finish after worker exit.")
        if log_errors:
            raise SecurityError(f"WORKER_LOG_FAILURE: Could not persist worker logs: {log_errors[0]}") from log_errors[0]


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
        stat_flag = eval_summary.get("statistical_acceptance") if isinstance(eval_summary, dict) else None
        if stat_flag is True:
            stat_status = "ACCEPTED"
        elif stat_flag is False:
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
    evidence_root: Path | str | None = None,
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

    sec_dir = resolve_security_dir(security_dir)
    # All safe read-only checks precede ticket registration and the one-shot claim.
    repo_root = Path(repo_dir).resolve()
    reconcile_execution_tree(
        repo_dir=repo_root,
        approved_commit=payload["approved_commit"],
        expected_hashes=payload,
        check_git_cleanliness=check_git_cleanliness,
    )

    created_worktree: Path | None = None
    if use_detached_worktree:
        wt_target = Path(worktree_dir) if worktree_dir else (repo_root.parent / f"nexvia_wt_{nonce[:12]}_{partition}")
        execution_root = prepare_detached_worktree(repo_root, payload["approved_commit"], wt_target)
        created_worktree = execution_root
    else:
        execution_root = repo_root

    py_exe = Path(python_executable) if python_executable else (repo_root / ".venv" / "bin" / "python")
    claim_committed = False
    outcome_committed = False
    part_dir: Path | None = None
    worker_pid: int | None = None
    report_path: Path | None = None

    try:
        runtime_report = verify_runtime_integrity(
            python_executable=py_exe,
            repo_or_worktree_dir=execution_root,
            expected_lockfile_sha256=payload["lockfile_sha256"],
            approved_venv_root=repo_root / ".venv" if custom_worker_cmd is None else None,
            synthetic_legacy_check=custom_worker_cmd is not None,
        )

        part_tag = "mix" if partition == "mixture" else "scen"
        if evidence_root is not None:
            output_root = resolve_evidence_output_root(evidence_root, nonce, repo_root, execution_root)
        elif custom_worker_cmd is not None and not use_detached_worktree:
            # Compatibility path for isolated synthetic tests only. The CLI never exposes it.
            output_root = execution_root / payload["target_output_root"]
        else:
            raise SecurityError("EVIDENCE_ROOT_REQUIRED: Production execution requires an explicit durable evidence root.")
        part_dir = output_root / f"test_{part_tag}"
        report_path = part_dir / f"test_{part_tag}_report.json"
        if part_dir.exists() or part_dir.is_symlink():
            raise SecurityError(f"EVIDENCE_PARTITION_EXISTS: Refusing to overwrite '{part_dir}'.")

        if custom_worker_cmd is not None:
            worker_cmd = copy.deepcopy(custom_worker_cmd)
        else:
            worker_cmd = build_default_worker_command(py_exe, execution_root, partition, part_dir)
            verify_evaluator_cli(py_exe, execution_root)
            # Ticket v1 signs only the relative literal "results/v9". It does not
            # authorize an absolute durable root. Never spend a production claim
            # under an operator-supplied, unsigned reinterpretation of that field.
            raise SecurityError(
                "EVIDENCE_ROOT_NOT_TICKET_BOUND: A dated contract amendment and signed root binding are required."
            )

        current_ledger = read_ledger(sec_dir)
        if nonce not in current_ledger["active_tickets"]:
            register_ticket(ticket_data=raw_ticket, security_dir=sec_dir, public_key_obj=pubkey)
        claimed_entry = execute_claim_transaction(sec_dir, nonce, partition)
        claim_committed = True
        part_dir.mkdir(parents=True, exist_ok=False)
        if evidence_root is not None:
            runtime_record = part_dir / "runtime_integrity.json"
            with runtime_record.open("x", encoding="utf-8") as out:
                json.dump(runtime_report, out, indent=2, sort_keys=True)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            provenance_record = part_dir / "launcher_execution_provenance.json"
            provenance = {
                "schema_version": "nexvia-aegis-launcher-provenance/1.0",
                "ticket_nonce": nonce,
                "ticket_sha256": hashlib.sha256(raw_ticket).hexdigest(),
                "partition": partition,
                "approved_commit": payload["approved_commit"],
                "claimed_at_utc": claimed_entry["partitions"][partition]["claimed_at_utc"],
                "execution_checkout": str(execution_root),
                "durable_evidence_root": str(Path(evidence_root).resolve()),
                "target_output_root_signed_literal": payload["target_output_root"],
                "runtime_integrity_sha256": sha256_file(runtime_record),
                "launcher_sha256": verify_launcher_integrity(expected_launcher_sha256=expected_launcher_sha256),
                "evidence_root_bound_in_signed_ticket": False,
            }
            with provenance_record.open("x", encoding="utf-8") as out:
                json.dump(provenance, out, indent=2, sort_keys=True)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            dir_fd = os.open(part_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

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

        exit_code, worker_pid = supervise_worker(
            worker_cmd=worker_cmd,
            cwd=execution_root,
            env=worker_env,
            timeout_seconds=timeout_seconds,
            log_dir=part_dir if evidence_root is not None else None,
            redacted_values=(str(claimed_entry.get("claim_secret", "")),),
        )

        report_sha256: str | None = None
        report_payload: dict[str, Any] | None = None
        report_valid = False

        if exit_code == 0:
            report_sha256, report_payload = validate_output_report(
                report_path=report_path,
                expected_partition=partition,
                expected_nonce=nonce,
                output_root=output_root,
                expected_hashes=payload,
            )
            if custom_worker_cmd is not None:
                summary = report_payload.get("evaluation_summary", {})
                if isinstance(summary, dict) and "statistical_acceptance" in summary:
                    raise SecurityError("SYNTHETIC_STATISTICAL_DECISION_REJECTED: Mock worker cannot establish a statistical result.")
            report_valid = True
        else:
            write_incomplete_marker(part_dir, "WORKER_NONZERO_EXIT")

        inventory_path = write_evidence_inventory(part_dir) if evidence_root is not None else None
        updated_entry = execute_outcome_transaction(
            security_dir=sec_dir,
            nonce=nonce,
            partition=partition,
            exit_code=exit_code,
            report_sha256=report_sha256,
            worker_pid=worker_pid,
            output_report_path=report_path,
        )
        outcome_committed = True

        # Step 14: Distinguish Statuses
        status_triplet = evaluate_execution_statuses(
            exit_code=exit_code,
            report_valid=report_valid,
            report_payload=report_payload,
        )
        if custom_worker_cmd is not None:
            # Test injection cannot produce a confirmatory decision, even if its
            # synthetic JSON claims an explicit acceptance Boolean.
            status_triplet["execution_provenance"] = "SYNTHETIC_WORKER"
            status_triplet["statistical_acceptance"] = "NOT_EVALUATED"

        return {
            "ticket_nonce": nonce,
            "partition": partition,
            "exit_code": exit_code,
            "worker_pid": worker_pid,
            "report_sha256": report_sha256,
            "statuses": status_triplet,
            "ticket_state": updated_entry["ticket_state"],
            "partition_status": updated_entry["partitions"][partition]["status"],
            "evidence_directory": str(part_dir),
            "evidence_inventory_sha256": sha256_file(inventory_path) if inventory_path else None,
        }

    except BaseException as exc:
        if claim_committed and not outcome_committed:
            assert part_dir is not None
            try:
                error_code = str(exc).split(":", 1)[0]
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", error_code):
                    error_code = type(exc).__name__
                write_incomplete_marker(part_dir, error_code)
                if evidence_root is not None and not (part_dir / "sha256_inventory.json").exists():
                    write_evidence_inventory(part_dir)
            except Exception as preservation_error:
                print(f"[LAUNCHER WARNING] Evidence preservation needs owner review: {preservation_error}", file=sys.stderr)
            try:
                execute_outcome_transaction(
                    security_dir=sec_dir, nonce=nonce, partition=partition,
                    exit_code=1, worker_pid=worker_pid, output_report_path=report_path,
                )
            except SecurityError as ledger_error:
                print(f"[LAUNCHER WARNING] Claim may require owner reconciliation: {ledger_error}", file=sys.stderr)
        raise
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
    parser.add_argument("--launcher-fingerprint", type=str, required=True, help="Owner-pinned SHA-256 of launcher module.")
    parser.add_argument("--evidence-root", type=Path, required=True, help="Existing owner-approved durable directory outside Git worktrees.")
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
            evidence_root=args.evidence_root,
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
