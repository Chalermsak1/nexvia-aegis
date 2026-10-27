"""Synthetic-only checks for the V9-M4 launcher and durable evidence path."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v9_evaluate_holdout import enforce_holdout_output_directory
from nexvia_aegis.security.launcher import (
    build_default_worker_command,
    cleanup_detached_worktree,
    prepare_detached_worktree,
    resolve_evidence_output_root,
    supervise_worker,
    write_evidence_inventory,
)
from nexvia_aegis.security.ledger import SecurityError


@pytest.mark.parametrize("partition,leaf", [("mixture", "test_mix"), ("scenario", "test_scen")])
def test_default_command_matches_real_evaluator_cli_without_running_it(tmp_path: Path, partition: str, leaf: str):
    repo = Path(__file__).resolve().parent.parent
    out_dir = tmp_path / "evidence" / "results" / "v9" / leaf
    command = build_default_worker_command(sys.executable, repo, partition, out_dir)
    assert command == [
        sys.executable, str(repo / "experiments" / "v9_evaluate_holdout.py"),
        "--partition", partition, "--out-dir", str(out_dir), "--run-production",
    ]
    assert enforce_holdout_output_directory(out_dir, partition) == out_dir.resolve()
    help_result = subprocess.run(
        [sys.executable, str(repo / "experiments" / "v9_evaluate_holdout.py"), "--help"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    assert "--out-dir" in help_result.stdout
    assert "--run-production" in help_result.stdout


def test_default_command_rejects_wrong_partition_path(tmp_path: Path):
    with pytest.raises(SecurityError, match="INVALID_OUTPUT_DIRECTORY"):
        build_default_worker_command(sys.executable, tmp_path, "mixture", tmp_path / "results" / "v9")


def test_evidence_root_is_external_writable_and_no_overwrite(tmp_path: Path):
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    evidence = tmp_path / "evidence"
    repo.mkdir()
    worktree.mkdir()
    evidence.mkdir()
    nonce = "ab" * 32
    out_root = resolve_evidence_output_root(evidence, nonce, repo, worktree)
    assert out_root == evidence / nonce / "results" / "v9"
    assert list(evidence.iterdir()) == []  # write probe was removed
    with pytest.raises(SecurityError, match="EVIDENCE_ROOT_NOT_ISOLATED"):
        resolve_evidence_output_root(tmp_path, nonce, repo, worktree)
    (evidence / nonce).symlink_to(tmp_path / "escape", target_is_directory=True)
    with pytest.raises(SecurityError, match="INVALID_EVIDENCE_PATH"):
        resolve_evidence_output_root(evidence, nonce, repo, worktree)


def test_inventory_survives_cleanup_and_refuses_overwrite(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repo, check=True)
    (repo / "README.md").write_text("synthetic checkout\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "synthetic baseline"], cwd=repo, capture_output=True, check=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    worktree = prepare_detached_worktree(repo, commit, tmp_path / "worktree")
    part_dir = tmp_path / "evidence" / "results" / "v9" / "test_mix"
    part_dir.mkdir(parents=True)
    raw_file = part_dir / "synthetic_episodes.csv"
    raw_file.write_bytes(b"episode,seed\n1,1001\n")
    expected = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    inventory = write_evidence_inventory(part_dir)
    inventory_digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
    assert json.loads(inventory.read_text())["artifact_sha256"][raw_file.name] == expected
    with pytest.raises(SecurityError, match="EVIDENCE_INVENTORY_EXISTS"):
        write_evidence_inventory(part_dir)
    cleanup_detached_worktree(repo, worktree)
    assert not worktree.exists()
    assert hashlib.sha256(raw_file.read_bytes()).hexdigest() == expected
    assert hashlib.sha256(inventory.read_bytes()).hexdigest() == inventory_digest


def test_cleanup_keeps_dirty_worktree_as_last_copy(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repo, check=True)
    (repo / "README.md").write_text("synthetic checkout\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "synthetic baseline"], cwd=repo, capture_output=True, check=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    worktree = prepare_detached_worktree(repo, commit, tmp_path / "worktree")
    only_copy = worktree / "synthetic_partial.csv"
    only_copy.write_bytes(b"partial,1001\n")
    digest = hashlib.sha256(only_copy.read_bytes()).hexdigest()
    cleanup_detached_worktree(repo, worktree)
    assert only_copy.exists()
    assert hashlib.sha256(only_copy.read_bytes()).hexdigest() == digest


def test_worker_logs_are_bounded_redacted_and_durable(tmp_path: Path):
    secret = "SYNTHETIC_CLAIM_SECRET_" + "x" * 48
    code = "import sys; sys.stdout.write('A'*4090 + %r + 'Z'*2000); sys.stderr.write(%r)" % (secret, secret)
    exit_code, pid = supervise_worker(
        [sys.executable, "-c", code], tmp_path, {},
        log_dir=tmp_path / "logs", redacted_values=(secret,), max_log_bytes=5000,
    )
    assert exit_code == 0 and pid > 0
    stdout = (tmp_path / "logs" / "worker.stdout.log").read_bytes()
    stderr = (tmp_path / "logs" / "worker.stderr.log").read_bytes()
    assert secret.encode() not in stdout + stderr
    assert b"[LOG_TRUNCATED_AT_BOUND]" in stdout
    assert len(stdout) <= 5000 + len(b"\n[LOG_TRUNCATED_AT_BOUND]\n")
    assert b"*" * len(secret) in stderr


def test_worker_timeout_preserves_partial_log(tmp_path: Path):
    code = "import time; print('synthetic partial', flush=True); time.sleep(5)"
    with pytest.raises(SecurityError, match="WORKER_TIMEOUT"):
        supervise_worker(
            [sys.executable, "-c", code], tmp_path, {}, timeout_seconds=1,
            log_dir=tmp_path / "logs",
        )
    assert b"synthetic partial" in (tmp_path / "logs" / "worker.stdout.log").read_bytes()
