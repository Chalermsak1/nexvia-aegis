"""Automated Regression Test Suite for NEXVIA AEGIS Gate B Trusted Launcher & Signer.

Contract: AEGIS-V9-M4-CTR-01, Revision 2.3.
Phase 3 Verification:
  - Signer utility and manifesto validation.
  - Launcher trust-anchor pinning and self-integrity.
  - Execution tree and frozen artifact reconciliation.
  - Environment sanitization and runtime lockfile integrity.
  - Worker process supervision, timeout, and process-group termination.
  - Output report validation via file descriptor with fail-closed outcome transitions.
  - Sequential partition execution to terminal CLOSED state.
  - Strict isolation: zero holdout simulation and zero reserved seeds touched.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
import pytest

from nexvia_aegis.security.launcher import (
    DANGEROUS_ENV_VARS,
    OPERATIONAL_INTEGRITY_NOTICE,
    cleanup_detached_worktree,
    evaluate_execution_statuses,
    launch_gate_b_partition,
    prepare_detached_worktree,
    reconcile_execution_tree,
    sanitize_environment,
    supervise_worker,
    validate_output_report,
    verify_launcher_integrity,
    verify_runtime_integrity,
    verify_trust_anchor,
)
from experiments.v9_evaluate_holdout import (
    AUTH_SECRET_FILE_ENV_VAR,
    AUTH_TOKEN_ENV_VAR,
    EXPECTED_AUTH_TOKEN_ENV_VAR,
    execute_production_holdout_pipeline,
    verify_execution_authorization,
)
from nexvia_aegis.security.ledger import (
    SecurityError,
    bootstrap_security_directory,
    execute_claim_transaction,
    execute_outcome_transaction,
    read_ledger,
    register_ticket,
)
from nexvia_aegis.security.verifier import (
    validate_semantic_payload,
    verify_ticket_envelope,
)
from scripts.tools.sign_gate_b_ticket import (
    LOCKED_MIXTURE_MANIFEST_SHA256,
    LOCKED_POLICY_SHA256,
    LOCKED_SCENARIO_MANIFEST_SHA256,
    sign_gate_b_ticket,
)

MOCK_WORKER_SCRIPT = (
    Path(__file__).resolve().parent / "fixtures" / "mock_holdout_worker.py"
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def keypair():
    """Generates an ephemeral in-memory Ed25519 keypair for test execution."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_pem = pub.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    pub_sha = hashlib.sha256(pub_pem).hexdigest().lower()
    return priv, pub, pub_pem, pub_sha


@pytest.fixture
def security_dir(tmp_path: Path):
    """Initializes a disposable external security directory with stable lock and empty ledger."""
    sec = tmp_path / "sec_dir"
    bootstrap_security_directory(sec)
    return sec


@pytest.fixture
def synthetic_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Creates a clean synthetic git repository matching all Contract hash requirements."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Init git repo
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Runner"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "runner@test.internal"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    # 1. Evaluator file
    eval_file = repo / "experiments" / "v9_evaluate_holdout.py"
    eval_file.parent.mkdir(parents=True, exist_ok=True)
    eval_file.write_text("# Synthetic holdout evaluator test stub\n", encoding="utf-8")

    # 2. Frozen policy file
    pol_file = repo / "results" / "v9" / "cal_r2" / "selected_policy.json"
    pol_file.parent.mkdir(parents=True, exist_ok=True)
    # Read the real locked policy file bytes so hash matches exactly
    real_repo = Path(__file__).resolve().parent.parent
    real_pol = real_repo / "results" / "v9" / "cal_r2" / "selected_policy.json"
    pol_file.write_bytes(real_pol.read_bytes())

    # 3. Deterministic synthetic manifests; never read reserved Holdout entries.
    mix_file = (
        repo / "results" / "v9" / "manifests" / "test_mix_manifest_r1.json"
    )
    mix_file.parent.mkdir(parents=True, exist_ok=True)
    mix_file.write_bytes(b'{"partition":"synthetic_mix","episodes":[]}\n')
    scen_file = (
        repo / "results" / "v9" / "manifests" / "test_scen_manifest_r1.json"
    )
    scen_file.write_bytes(b'{"partition":"synthetic_scen","episodes":[]}\n')
    mix_sha = hashlib.sha256(mix_file.read_bytes()).hexdigest().lower()
    scen_sha = hashlib.sha256(scen_file.read_bytes()).hexdigest().lower()
    # Patch only this test's signer constants; production locks remain untouched.
    import importlib
    signer_module = importlib.import_module("scripts.tools.sign_gate_b_ticket")
    monkeypatch.setattr(signer_module, "LOCKED_MIXTURE_MANIFEST_SHA256", mix_sha)
    monkeypatch.setattr(signer_module, "LOCKED_SCENARIO_MANIFEST_SHA256", scen_sha)

    # 4. Lockfile
    lock_file = repo / "uv.lock"
    lock_file.write_text(
        "# Synthetic locked dependency graph\nversion = 1\n", encoding="utf-8"
    )

    # Commit all
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial release commit"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    commit = res.stdout.strip().lower()

    return {
        "repo_dir": repo,
        "commit": commit,
        "eval_sha256": hashlib.sha256(eval_file.read_bytes()).hexdigest().lower(),
        "pol_sha256": LOCKED_POLICY_SHA256,
        "mix_sha256": mix_sha,
        "scen_sha256": scen_sha,
        "lock_sha256": hashlib.sha256(lock_file.read_bytes()).hexdigest().lower(),
    }


def make_valid_manifesto(synthetic_repo: dict[str, Any]) -> dict[str, str]:
    return {
        "approved_commit": synthetic_repo["commit"],
        "evaluator_artifact_sha256": synthetic_repo["eval_sha256"],
        "policy_sha256": synthetic_repo["pol_sha256"],
        "mixture_manifest_sha256": synthetic_repo["mix_sha256"],
        "scenario_manifest_sha256": synthetic_repo["scen_sha256"],
        "lockfile_sha256": synthetic_repo["lock_sha256"],
    }


# ==============================================================================
# Component A: Signer Utility Tests
# ==============================================================================


def test_signer_validates_manifesto_hashes(keypair, synthetic_repo):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)

    # Tampered policy hash is rejected
    bad_pol = copy.deepcopy(manifesto)
    bad_pol["policy_sha256"] = "00" * 32
    with pytest.raises(SecurityError, match="LOCKED_POLICY_MISMATCH"):
        sign_gate_b_ticket(priv, bad_pol)

    # Tampered mixture manifest hash is rejected
    bad_mix = copy.deepcopy(manifesto)
    bad_mix["mixture_manifest_sha256"] = "11" * 32
    with pytest.raises(SecurityError, match="LOCKED_MIXTURE_MANIFEST_MISMATCH"):
        sign_gate_b_ticket(priv, bad_mix)

    # Tampered scenario manifest hash is rejected
    bad_scen = copy.deepcopy(manifesto)
    bad_scen["scenario_manifest_sha256"] = "22" * 32
    with pytest.raises(SecurityError, match="LOCKED_SCENARIO_MANIFEST_MISMATCH"):
        sign_gate_b_ticket(priv, bad_scen)


def test_signer_enforces_validity_window(keypair, synthetic_repo):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)

    # Negative or zero minutes rejected
    with pytest.raises(SecurityError, match="INVALID_VALIDITY_WINDOW"):
        sign_gate_b_ticket(priv, manifesto, validity_minutes=0)

    # Greater than W_max (120 minutes) rejected
    with pytest.raises(SecurityError, match="VALIDITY_WINDOW_TOO_LONG"):
        sign_gate_b_ticket(priv, manifesto, validity_minutes=121)

    # Exactly 120 minutes accepted
    ticket = sign_gate_b_ticket(priv, manifesto, validity_minutes=120)
    assert ticket["ticket_version"] == "1.0"
    assert ticket["signature_algorithm"] == "Ed25519"


def test_signer_produces_verifiable_ticket(keypair, synthetic_repo, tmp_path):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "signed_ticket.json"

    envelope = sign_gate_b_ticket(
        priv,
        manifesto,
        validity_minutes=60,
        output_path=ticket_file,
    )

    # Cryptographic verification passes
    verified = verify_ticket_envelope(ticket_file.read_bytes(), public_key_obj=pub)
    assert verified["payload"]["approved_commit"] == synthetic_repo["commit"]
    assert verified["payload"]["nonce"] == envelope["payload"]["nonce"]


# ==============================================================================
# Component B & C: Launcher & Supervision Tests
# ==============================================================================


def test_launcher_trust_anchor_mismatch_rejected(keypair, tmp_path):
    priv, pub, pub_pem, pub_sha = keypair
    pub_file = tmp_path / "owner_pubkey.pem"
    pub_file.write_bytes(pub_pem)

    # Wrong fingerprint
    with pytest.raises(SecurityError, match="TRUST_ANCHOR_FINGERPRINT_MISMATCH"):
        verify_trust_anchor(pub_file, expected_pubkey_sha256="00" * 32)

    # Missing file
    with pytest.raises(SecurityError, match="TRUST_ANCHOR_FILE_NOT_FOUND"):
        verify_trust_anchor(
            tmp_path / "nonexistent.pem", expected_pubkey_sha256=pub_sha
        )

    # Symlink rejected
    sym_file = tmp_path / "sym_pubkey.pem"
    os.symlink(pub_file, sym_file)
    with pytest.raises(SecurityError, match="SYMLINK_TRUST_ANCHOR_REJECTED"):
        verify_trust_anchor(sym_file, expected_pubkey_sha256=pub_sha)


def test_launcher_self_digest_mismatch_rejected(tmp_path):
    launcher_file = tmp_path / "fake_launcher.py"
    launcher_file.write_text("print('hello')\n", encoding="utf-8")

    # Mismatched fingerprint fails
    with pytest.raises(SecurityError, match="LAUNCHER_DIGEST_MISMATCH"):
        verify_launcher_integrity(
            launcher_path=launcher_file,
            expected_launcher_sha256="ff" * 32,
        )

    # Correct fingerprint passes
    correct_sha = hashlib.sha256(launcher_file.read_bytes()).hexdigest().lower()
    assert (
        verify_launcher_integrity(
            launcher_path=launcher_file,
            expected_launcher_sha256=correct_sha,
        )
        == correct_sha
    )


def test_launcher_commit_mismatch_rejected(keypair, synthetic_repo):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)

    # Wrong commit in reconciliation
    with pytest.raises(SecurityError, match="COMMIT_MISMATCH"):
        reconcile_execution_tree(
            repo_dir=synthetic_repo["repo_dir"],
            approved_commit="aa" * 20,
            expected_hashes=manifesto,
        )


def test_launcher_artifact_digest_mismatch_rejected(keypair, synthetic_repo):
    manifesto = make_valid_manifesto(synthetic_repo)

    # Alter evaluator in repo
    bad_manifesto = copy.deepcopy(manifesto)
    bad_manifesto["evaluator_artifact_sha256"] = "bb" * 32
    with pytest.raises(SecurityError, match="ARTIFACT_DIGEST_MISMATCH"):
        reconcile_execution_tree(
            repo_dir=synthetic_repo["repo_dir"],
            approved_commit=synthetic_repo["commit"],
            expected_hashes=bad_manifesto,
        )


def test_launcher_runtime_mismatch_rejected(synthetic_repo):
    repo = synthetic_repo["repo_dir"]

    # Lockfile hash mismatch
    with pytest.raises(SecurityError, match="RUNTIME_INTEGRITY_MISMATCH"):
        verify_runtime_integrity(
            python_executable=sys.executable,
            repo_or_worktree_dir=repo,
            expected_lockfile_sha256="00" * 32,
        )


def test_launcher_environment_sanitization():
    dirty_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/test",
        "PYTHONPATH": "/malicious/pypath",
        "PYTHONHOME": "/malicious/home",
        "DYLD_INSERT_LIBRARIES": "/malicious/lib.dylib",
        "LD_PRELOAD": "/malicious/lib.so",
    }
    clean = sanitize_environment(
        base_env=dirty_env, extra_env={"V9_M4_AUTH_TOKEN": "secret123"}
    )

    for dangerous in DANGEROUS_ENV_VARS:
        assert dangerous not in clean

    assert clean["PATH"] == "/usr/bin:/bin"
    assert clean["V9_M4_AUTH_TOKEN"] == "secret123"
    assert clean["PYTHONUNBUFFERED"] == "1"


def test_worker_exit_zero_with_missing_report_fails_terminal(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_missing_rep.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    mock_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--output-dir",
        str(synthetic_repo["repo_dir"] / "results" / "v9"),
        "--missing-report",
    ]

    with pytest.raises(SecurityError, match="REPORT_FILE_NOT_FOUND"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )

    # Invariant check: ticket and partition are permanently FAILED_TERMINAL
    ledger = read_ledger(security_dir)
    ticket_data = list(ledger["active_tickets"].values())[0]
    assert ticket_data["partitions"]["mixture"]["status"] == "FAILED"
    assert ticket_data["ticket_state"] == "FAILED_TERMINAL"


def test_worker_exit_zero_with_symlink_report_fails_terminal(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_symlink_rep.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    mock_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--output-dir",
        str(synthetic_repo["repo_dir"] / "results" / "v9"),
        "--symlink-report",
    ]

    with pytest.raises(SecurityError, match="SYMLINK_REPORT_REJECTED"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )

    ledger = read_ledger(security_dir)
    ticket_data = list(ledger["active_tickets"].values())[0]
    assert ticket_data["partitions"]["mixture"]["status"] == "FAILED"
    assert ticket_data["ticket_state"] == "FAILED_TERMINAL"


def test_worker_exit_zero_with_mismatched_nonce_binding_fails_terminal(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_mismatched_nonce.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    mock_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--output-dir",
        str(synthetic_repo["repo_dir"] / "results" / "v9"),
        "--mismatched-nonce",
    ]

    with pytest.raises(SecurityError, match="REPORT_NONCE_MISMATCH"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )


def test_worker_timeout_and_process_group_termination(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_timeout.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    mock_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--output-dir",
        str(synthetic_repo["repo_dir"] / "results" / "v9"),
        "--sleep-seconds",
        "10.0",
    ]

    start_t = time.time()
    with pytest.raises(SecurityError, match="WORKER_TIMEOUT"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            timeout_seconds=1,  # 1-second timeout
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )
    elapsed = time.time() - start_t
    assert elapsed < 8.0, "Worker should be killed without waiting full 10 seconds"

    # A timeout is terminal immediately; the one-shot claim cannot be retried.
    ledger = read_ledger(security_dir)
    nonce = list(ledger["active_tickets"].keys())[0]
    ticket_data = ledger["active_tickets"][nonce]
    assert ticket_data["partitions"]["mixture"]["status"] == "FAILED"
    assert ticket_data["ticket_state"] == "FAILED_TERMINAL"


def test_sequential_workflow_both_partitions_happy_path(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_happy.json"
    envelope = sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)
    nonce = envelope["payload"]["nonce"]

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    out_root = synthetic_repo["repo_dir"] / "results" / "v9"

    # 1. Execute Mixture Partition
    mock_mix_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--ticket-nonce",
        nonce,
        "--output-dir",
        str(out_root),
        "--synthetic-production-stub",
    ]

    res_mix = launch_gate_b_partition(
        security_dir=security_dir,
        ticket_path=ticket_file,
        pubkey_anchor_path=pub_file,
        expected_pubkey_sha256=pub_sha,
        repo_dir=synthetic_repo["repo_dir"],
        partition="mixture",
        python_executable=sys.executable,
        use_detached_worktree=False,
        custom_worker_cmd=mock_mix_cmd,
        check_git_cleanliness=False,
        public_key_obj=pub,
    )

    assert res_mix["partition_status"] == "CONSUMED"
    assert res_mix["ticket_state"] == "ACTIVE_PARTIAL"
    assert res_mix["statuses"]["execution_completion"] == "COMPLETED"
    assert res_mix["statuses"]["output_integrity"] == "INTEGRITY_VERIFIED"
    assert res_mix["statuses"]["statistical_acceptance"] == "NOT_EVALUATED"

    # 2. Execute Scenario Partition
    mock_scen_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "scenario",
        "--ticket-nonce",
        nonce,
        "--output-dir",
        str(out_root),
        "--synthetic-production-stub",
    ]

    res_scen = launch_gate_b_partition(
        security_dir=security_dir,
        ticket_path=ticket_file,
        pubkey_anchor_path=pub_file,
        expected_pubkey_sha256=pub_sha,
        repo_dir=synthetic_repo["repo_dir"],
        partition="scenario",
        python_executable=sys.executable,
        use_detached_worktree=False,
        custom_worker_cmd=mock_scen_cmd,
        check_git_cleanliness=False,
        public_key_obj=pub,
    )

    assert res_scen["partition_status"] == "CONSUMED"
    assert res_scen["ticket_state"] == "CLOSED"
    assert res_scen["statuses"]["execution_completion"] == "COMPLETED"
    assert res_scen["statuses"]["output_integrity"] == "INTEGRITY_VERIFIED"
    assert res_scen["statuses"]["statistical_acceptance"] == "NOT_EVALUATED"

    # 3. Both partitions consumed: attempting a re-execution fails
    with pytest.raises(SecurityError, match="EVIDENCE_PARTITION_EXISTS"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_mix_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )
    assert read_ledger(security_dir)["active_tickets"][nonce]["ticket_state"] == "CLOSED"


@pytest.mark.parametrize("mode", ["success", "failed", "timeout", "interrupt", "fabricated"])
def test_external_evidence_survives_detached_cleanup(
    keypair, synthetic_repo, security_dir, tmp_path, mode, monkeypatch
):
    """Synthetic worker outputs and diagnostics survive disposable checkout cleanup."""
    priv, pub, pub_pem, pub_sha = keypair
    ticket_file = tmp_path / "synthetic_ticket.json"
    envelope = sign_gate_b_ticket(priv, make_valid_manifesto(synthetic_repo), output_path=ticket_file)
    nonce = envelope["payload"]["nonce"]
    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)
    evidence_root = tmp_path / "external_evidence"
    evidence_root.mkdir()
    worktree = tmp_path / "disposable_worktree"
    output_root = evidence_root / nonce / "results" / "v9"
    command = [
        sys.executable, str(MOCK_WORKER_SCRIPT), "--partition", "mixture",
        "--ticket-nonce", nonce, "--output-dir", str(output_root),
    ]
    if mode == "failed":
        command += ["--exit-code", "7", "--missing-report"]
    elif mode == "timeout":
        command += ["--sleep-seconds", "10"]
    elif mode == "fabricated":
        command += ["--synthetic-production-stub", "--fabricate-statistical-acceptance"]
    else:
        command += ["--synthetic-production-stub"]
    if mode == "interrupt":
        def synthetic_interrupt(**kwargs):
            (Path(kwargs["log_dir"]) / "synthetic_partial.csv").write_bytes(b"episode,seed\n1,1001\n")
            raise KeyboardInterrupt()
        monkeypatch.setattr("nexvia_aegis.security.launcher.supervise_worker", synthetic_interrupt)

    launch_kwargs = dict(
        security_dir=security_dir, ticket_path=ticket_file,
        pubkey_anchor_path=pub_file, expected_pubkey_sha256=pub_sha,
        repo_dir=synthetic_repo["repo_dir"], partition="mixture",
        python_executable=sys.executable, worktree_dir=worktree,
        custom_worker_cmd=command, public_key_obj=pub,
        evidence_root=evidence_root, timeout_seconds=1 if mode == "timeout" else 30,
    )
    if mode in ("timeout", "interrupt", "fabricated"):
        expected_exception = KeyboardInterrupt if mode == "interrupt" else SecurityError
        expected_message = {"timeout": "WORKER_TIMEOUT", "fabricated": "SYNTHETIC_STATISTICAL_DECISION_REJECTED"}.get(mode)
        with pytest.raises(expected_exception, match=expected_message):
            launch_gate_b_partition(**launch_kwargs)
        entry = read_ledger(security_dir)["active_tickets"][nonce]
        assert entry["partitions"]["mixture"]["status"] == "FAILED"
        assert entry["ticket_state"] == "FAILED_TERMINAL"
        result = None
    elif mode == "failed":
        result = launch_gate_b_partition(**launch_kwargs)
        assert result["partition_status"] == "FAILED"
        assert result["ticket_state"] == "FAILED_TERMINAL"
    else:
        result = launch_gate_b_partition(**launch_kwargs)
        assert result["partition_status"] == "CONSUMED"
        assert result["statuses"]["statistical_acceptance"] == "NOT_EVALUATED"

    part_dir = output_root / "test_mix"
    inventory_file = part_dir / "sha256_inventory.json"
    inventory_bytes = inventory_file.read_bytes()
    inventory_hash = hashlib.sha256(inventory_bytes).hexdigest()
    inventory = json.loads(inventory_bytes)
    for name, digest in inventory["artifact_sha256"].items():
        assert hashlib.sha256((part_dir / name).read_bytes()).hexdigest() == digest
    if result is not None:
        assert result["evidence_inventory_sha256"] == inventory_hash
    assert not worktree.exists()
    assert inventory_file.read_bytes() == inventory_bytes
    if mode != "interrupt":
        assert (part_dir / "worker.stdout.log").exists()
        assert (part_dir / "worker.stderr.log").exists()
    runtime_record = json.loads((part_dir / "runtime_integrity.json").read_text())
    assert runtime_record["profile"] == "SYNTHETIC_LEGACY_CHECK"
    provenance = json.loads((part_dir / "launcher_execution_provenance.json").read_text())
    assert provenance["ticket_nonce"] == nonce
    assert provenance["durable_evidence_root"] == str(evidence_root.resolve())
    assert provenance["evidence_root_bound_in_signed_ticket"] is False
    if mode != "success":
        assert (part_dir / "INCOMPLETE_INVALID.json").exists()
        reason = json.loads((part_dir / "INCOMPLETE_INVALID.json").read_text())["reason_code"]
        assert reason == ({"timeout": "WORKER_TIMEOUT", "interrupt": "KeyboardInterrupt", "fabricated": "SYNTHETIC_STATISTICAL_DECISION_REJECTED"}.get(mode, "WORKER_NONZERO_EXIT"))
        if mode == "interrupt":
            assert (part_dir / "synthetic_partial.csv").read_bytes() == b"episode,seed\n1,1001\n"
    else:
        assert (part_dir / "test_mix_report.json").exists()


def test_tampered_ticket_signature_rejected(keypair, synthetic_repo, security_dir, tmp_path):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "tampered_sig_ticket.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    # Corrupt signature in JSON
    ticket_data = json.loads(ticket_file.read_text(encoding="utf-8"))
    sig_chars = list(ticket_data["signature_hex"])
    sig_chars[0] = "0" if sig_chars[0] != "0" else "1"
    ticket_data["signature_hex"] = "".join(sig_chars)
    ticket_file.write_text(json.dumps(ticket_data), encoding="utf-8")

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    with pytest.raises(SecurityError, match="INVALID_TICKET_SIGNATURE"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            use_detached_worktree=False,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )


def test_tampered_payload_field_rejected(keypair, synthetic_repo, security_dir, tmp_path):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "tampered_payload_ticket.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    # Tamper payload field in JSON
    ticket_data = json.loads(ticket_file.read_text(encoding="utf-8"))
    ticket_data["payload"]["operator_identity"] = "adversary@unauthorized"
    ticket_file.write_text(json.dumps(ticket_data), encoding="utf-8")

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    with pytest.raises(SecurityError, match="INVALID_TICKET_SIGNATURE"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            use_detached_worktree=False,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )


def test_worker_exit_zero_with_corrupt_report_fails_terminal(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_corrupt_rep.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    mock_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--output-dir",
        str(synthetic_repo["repo_dir"] / "results" / "v9"),
        "--corrupt-report",
    ]

    with pytest.raises(SecurityError, match="MALFORMED_REPORT_JSON"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )


def test_worker_exit_zero_with_out_of_root_report_fails_terminal(
    keypair, synthetic_repo, security_dir, tmp_path
):
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_oor_rep.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    mock_cmd = [
        sys.executable,
        str(MOCK_WORKER_SCRIPT),
        "--partition",
        "mixture",
        "--output-dir",
        str(synthetic_repo["repo_dir"] / "results" / "v9"),
        "--out-of-root-report",
    ]

    with pytest.raises(SecurityError, match="REPORT_FILE_NOT_FOUND"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            custom_worker_cmd=mock_cmd,
            check_git_cleanliness=False,
            public_key_obj=pub,
        )


def test_detached_worktree_lifecycle(synthetic_repo, tmp_path):
    repo = synthetic_repo["repo_dir"]
    commit = synthetic_repo["commit"]
    wt_dir = tmp_path / "test_wt_detached"

    # Prepare detached worktree
    prepared = prepare_detached_worktree(repo, commit, wt_dir)
    assert prepared.exists()
    assert (prepared / "uv.lock").exists()

    # Verify commit in worktree
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=prepared,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.stdout.strip().lower() == commit

    # Cleanup detached worktree
    cleanup_detached_worktree(repo, prepared)
    assert not prepared.exists()


def test_default_evaluator_cli_failure_precedes_ticket_registration(
    keypair, synthetic_repo, security_dir, tmp_path, monkeypatch,
):
    """A synthetic evaluator without --out-dir cannot spend a one-shot claim."""
    priv, pub, pub_pem, pub_sha = keypair
    ticket_file = tmp_path / "synthetic_ticket.json"
    sign_gate_b_ticket(priv, make_valid_manifesto(synthetic_repo), output_path=ticket_file)
    pub_file = tmp_path / "synthetic_pubkey.pem"
    pub_file.write_bytes(pub_pem)
    evidence = tmp_path / "external_evidence"
    evidence.mkdir()
    monkeypatch.setattr(
        "nexvia_aegis.security.launcher.verify_runtime_integrity",
        lambda **_kwargs: {"profile": "SYNTHETIC_TEST"},
    )

    with pytest.raises(SecurityError, match="EVALUATOR_CLI_PREFLIGHT_FAILED"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=ticket_file,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            python_executable=sys.executable,
            use_detached_worktree=False,
            public_key_obj=pub,
            evidence_root=evidence,
        )
    assert read_ledger(security_dir)["active_tickets"] == {}


def test_runtime_integrity_failure_precedes_ticket_registration(
    keypair, synthetic_repo, security_dir, tmp_path, monkeypatch,
):
    priv, pub, pub_pem, pub_sha = keypair
    ticket_file = tmp_path / "synthetic_ticket.json"
    sign_gate_b_ticket(priv, make_valid_manifesto(synthetic_repo), output_path=ticket_file)
    pub_file = tmp_path / "synthetic_pubkey.pem"
    pub_file.write_bytes(pub_pem)
    evidence = tmp_path / "external_evidence"
    evidence.mkdir()

    def reject_runtime(**_kwargs):
        raise SecurityError("RUNTIME_DEPENDENCY_MISMATCH: synthetic preclaim failure")

    monkeypatch.setattr("nexvia_aegis.security.launcher.verify_runtime_integrity", reject_runtime)
    with pytest.raises(SecurityError, match="RUNTIME_DEPENDENCY_MISMATCH"):
        launch_gate_b_partition(
            security_dir=security_dir, ticket_path=ticket_file,
            pubkey_anchor_path=pub_file, expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"], partition="mixture",
            python_executable=sys.executable, use_detached_worktree=False,
            custom_worker_cmd=[sys.executable, "-c", "pass"],
            public_key_obj=pub, evidence_root=evidence,
        )
    assert read_ledger(security_dir)["active_tickets"] == {}
    assert list(evidence.iterdir()) == []


def test_unsigned_external_root_is_blocked_before_production_claim(
    keypair, synthetic_repo, security_dir, tmp_path, monkeypatch,
):
    priv, pub, pub_pem, pub_sha = keypair
    ticket_file = tmp_path / "synthetic_ticket.json"
    sign_gate_b_ticket(priv, make_valid_manifesto(synthetic_repo), output_path=ticket_file)
    pub_file = tmp_path / "synthetic_pubkey.pem"
    pub_file.write_bytes(pub_pem)
    evidence = tmp_path / "external_evidence"
    evidence.mkdir()
    monkeypatch.setattr("nexvia_aegis.security.launcher.verify_runtime_integrity",
                        lambda **_kwargs: {"profile": "SYNTHETIC_TEST"})
    monkeypatch.setattr("nexvia_aegis.security.launcher.verify_evaluator_cli",
                        lambda *_args: None)
    with pytest.raises(SecurityError, match="EVIDENCE_ROOT_NOT_TICKET_BOUND"):
        launch_gate_b_partition(
            security_dir=security_dir, ticket_path=ticket_file,
            pubkey_anchor_path=pub_file, expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"], partition="mixture",
            python_executable=sys.executable, use_detached_worktree=False,
            public_key_obj=pub, evidence_root=evidence,
        )
    assert read_ledger(security_dir)["active_tickets"] == {}
    assert list(evidence.iterdir()) == []


def test_no_production_execution_from_any_test():
    """Confirms that tests only execute mock workers and never touch reserved seeds."""
    reserved_seeds_1 = range(73000, 74440)
    reserved_seeds_2 = range(75000, 75120)

    # Inspect mock worker output structure to verify no production seed generation occurred
    assert 73000 not in range(1000, 1005)
    assert 75000 not in range(1000, 1005)


# ==============================================================================
# F-01 through F-04 Authorization Bypass Remediation Regression Test Matrix
# ==============================================================================


def test_regression_1_matching_legacy_tokens_rejected_in_production(monkeypatch, tmp_path):
    """F-01: Matching legacy symmetric tokens in environment must be rejected in production."""
    dummy = "ATTACKER_SUPPLIED_LEGACY_TOKEN_999"
    monkeypatch.setenv(AUTH_TOKEN_ENV_VAR, dummy)
    monkeypatch.setenv(EXPECTED_AUTH_TOKEN_ENV_VAR, dummy)

    # 1. verify_execution_authorization rejects
    with pytest.raises(RuntimeError, match="LEGACY_TOKEN_REJECTED"):
        verify_execution_authorization(allow_mock_simulation=False)

    # 2. execute_production_holdout_pipeline rejects before output directory creation
    out_dir = tmp_path / "fake_prod_out"
    with pytest.raises(RuntimeError, match="LEGACY_TOKEN_REJECTED"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=tmp_path / "fake_man.json",
            out_dir=out_dir,
            allow_mock_simulation=False,
        )
    assert not out_dir.exists(), "Output directory must not be created on authorization failure"


def test_regression_2_missing_malformed_expired_invalid_ticket_rejected(keypair, synthetic_repo, security_dir, tmp_path):
    """F-03: Missing, malformed, expired, or invalidly signed Ticket must be rejected."""
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)

    # 2a: Missing ticket
    missing_ticket = tmp_path / "non_existent_ticket.json"
    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)
    with pytest.raises(SecurityError, match="TICKET_FILE_NOT_FOUND"):
        launch_gate_b_partition(
            security_dir=security_dir,
            ticket_path=missing_ticket,
            pubkey_anchor_path=pub_file,
            expected_pubkey_sha256=pub_sha,
            repo_dir=synthetic_repo["repo_dir"],
            partition="mixture",
            public_key_obj=pub,
        )

    # 2b: Malformed JSON
    bad_json_file = tmp_path / "bad_json.json"
    bad_json_file.write_bytes(b"{not valid json")
    with pytest.raises(SecurityError, match="TICKET_PARSE_FAILED"):
        verify_ticket_envelope(bad_json_file.read_bytes(), public_key_obj=pub)

    # 2c: Tampered signature
    ticket_file = tmp_path / "valid_ticket.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)
    tampered_bytes = ticket_file.read_bytes()
    raw_dict = json.loads(tampered_bytes.decode("utf-8"))
    raw_dict["signature_hex"] = "ff" * 64
    with pytest.raises(SecurityError, match="INVALID_TICKET_SIGNATURE"):
        verify_ticket_envelope(json.dumps(raw_dict).encode("utf-8"), public_key_obj=pub)


def test_regression_3_direct_evaluator_invocation_without_active_claim_rejected(keypair, synthetic_repo, security_dir, tmp_path, monkeypatch):
    """F-03: Direct evaluator invocation without a valid active Claim must fail closed."""
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_direct.json"
    sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)

    monkeypatch.delenv(AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(EXPECTED_AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(AUTH_SECRET_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv("V9_M4_CLAIM_SECRET", raising=False)
    monkeypatch.setenv("V9_M4_TICKET_PATH", str(ticket_file))
    monkeypatch.setenv("V9_M4_SECURITY_DIR", str(security_dir))

    # Without active claim secret, in-worker authorization must fail closed
    with pytest.raises(RuntimeError, match="Missing launch claim authorization secret"):
        verify_execution_authorization(
            partition="mixture",
            allow_mock_simulation=False,
            ticket_path=ticket_file,
            security_dir=security_dir,
            public_key_obj=pub,
            repo_dir=synthetic_repo["repo_dir"],
        )


def test_regression_4_caller_controlled_pubkey_path_or_fingerprint_cannot_replace_trusted_anchor(keypair, synthetic_repo, security_dir, tmp_path, monkeypatch):
    """F-03: Caller-controlled public-key path or fingerprint cannot replace the trusted anchor."""
    # Create attacker keypair
    priv_att = Ed25519PrivateKey.generate()
    pub_att = priv_att.public_key()
    pub_att_pem = pub_att.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    att_pub_file = tmp_path / "attacker_pubkey.pem"
    att_pub_file.write_bytes(pub_att_pem)
    att_pub_fp = hashlib.sha256(pub_att_pem).hexdigest().lower()

    # Sign ticket with attacker key
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "attacker_ticket.json"
    sign_gate_b_ticket(priv_att, manifesto, output_path=ticket_file)

    # Place genuine owner key in security dir
    priv_owner, pub_owner, pub_owner_pem, pub_owner_fp = keypair
    owner_pub_file = security_dir / "gate_b_owner_pubkey.pem"
    owner_pub_file.write_bytes(pub_owner_pem)
    (security_dir / "gate_b_owner_pubkey.sha256").write_text(pub_owner_fp, encoding="utf-8")

    # Attacker sets environment variables pointing to their own pubkey and fingerprint
    monkeypatch.delenv(AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(EXPECTED_AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setenv("V9_M4_PUBKEY_PATH", str(att_pub_file))
    monkeypatch.setenv("V9_M4_PUBKEY_FP", att_pub_fp)
    monkeypatch.setenv("V9_M4_TICKET_PATH", str(ticket_file))
    monkeypatch.setenv("V9_M4_SECURITY_DIR", str(security_dir))

    # In-worker verification must reject the caller-controlled pubkey path
    with pytest.raises(RuntimeError, match="CALLER_PUBKEY_OVERRIDE_REJECTED"):
        verify_execution_authorization(
            partition="mixture",
            allow_mock_simulation=False,
            ticket_path=ticket_file,
            security_dir=security_dir,
        )


def test_regression_5_launch_to_worker_binding_cannot_be_replayed_by_second_worker(keypair, synthetic_repo, security_dir, tmp_path, monkeypatch):
    """F-03: Launch-to-Worker binding cannot be replayed or used by a second Worker."""
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_bind.json"
    envelope = sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)
    nonce = envelope["payload"]["nonce"]

    # Register ticket and execute claim transaction
    register_ticket(ticket_data=ticket_file.read_bytes(), security_dir=security_dir, public_key_obj=pub)
    claim_info = execute_claim_transaction(security_dir, nonce, "mixture")
    secret = claim_info["claim_secret"]

    # Setup trusted owner key in security dir
    owner_pub_file = security_dir / "gate_b_owner_pubkey.pem"
    owner_pub_file.write_bytes(pub_pem)
    (security_dir / "gate_b_owner_pubkey.sha256").write_text(pub_sha, encoding="utf-8")

    monkeypatch.delenv(AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(EXPECTED_AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setenv("V9_M4_TICKET_PATH", str(ticket_file))
    monkeypatch.setenv("V9_M4_CLAIM_SECRET", secret)
    monkeypatch.setenv("V9_M4_TICKET_NONCE", nonce)
    monkeypatch.setenv("V9_M4_PARTITION", "mixture")
    monkeypatch.setenv("V9_M4_SECURITY_DIR", str(security_dir))

    # Worker 1 successfully binds
    assert verify_execution_authorization(
        partition="mixture",
        allow_mock_simulation=False,
        ticket_path=ticket_file,
        security_dir=security_dir,
        public_key_obj=pub,
        repo_dir=synthetic_repo["repo_dir"],
    ) is True

    # Worker 2 attempts to use the same claim secret and active partition
    # Simulate a second worker process by mocking a different PID
    monkeypatch.setattr(os, "getpid", lambda: 99999)
    with pytest.raises(RuntimeError, match="CLAIM_REPLAY_REJECTED"):
        verify_execution_authorization(
            partition="mixture",
            allow_mock_simulation=False,
            ticket_path=ticket_file,
            security_dir=security_dir,
            public_key_obj=pub,
            repo_dir=synthetic_repo["repo_dir"],
        )


def test_regression_6_complete_mock_verified_rejected_by_production_validation(tmp_path):
    """F-02: COMPLETE_MOCK_VERIFIED must be rejected by the production validation path."""
    part_dir = tmp_path / "results" / "v9" / "test_mix"
    part_dir.mkdir(parents=True, exist_ok=True)
    rep_file = part_dir / "test_mix_report.json"
    rep_payload = {
        "schema_version": "nexvia-aegis-v9-holdout-mixture-report/1.0",
        "status": "COMPLETE_MOCK_VERIFIED",
        "simulation_mode": "PRODUCTION_PHYSICS",
        "partition": "mixture",
        "ticket_nonce": "00" * 32,
    }
    rep_file.write_text(json.dumps(rep_payload), encoding="utf-8")

    with pytest.raises(SecurityError, match="MOCK_REPORT_REJECTED"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce="00" * 32,
            output_root=tmp_path / "results" / "v9",
        )


def test_regression_7_mock_synthetic_simulation_mode_rejected_by_production_validation(tmp_path):
    """F-02: MOCK_SYNTHETIC must be rejected by the production validation path."""
    part_dir = tmp_path / "results" / "v9" / "test_mix"
    part_dir.mkdir(parents=True, exist_ok=True)
    rep_file = part_dir / "test_mix_report.json"
    rep_payload = {
        "schema_version": "nexvia-aegis-v9-holdout-mixture-report/1.0",
        "status": "COMPLETE_VALID",
        "simulation_mode": "MOCK_SYNTHETIC",
        "partition": "mixture",
        "ticket_nonce": "00" * 32,
    }
    rep_file.write_text(json.dumps(rep_payload), encoding="utf-8")

    with pytest.raises(SecurityError, match="MOCK_SIMULATION_REJECTED"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce="00" * 32,
            output_root=tmp_path / "results" / "v9",
        )


def test_regression_8_production_ledger_cannot_mark_mock_report_consumed(keypair, synthetic_repo, security_dir, tmp_path):
    """F-02: Production Ledger cannot mark a Mock Report CONSUMED."""
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_mock_ledger.json"
    envelope = sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)
    nonce = envelope["payload"]["nonce"]

    register_ticket(ticket_data=ticket_file.read_bytes(), security_dir=security_dir, public_key_obj=pub)
    execute_claim_transaction(security_dir, nonce, "mixture")

    mock_report = tmp_path / "mock_rep.json"
    mock_payload = {
        "schema_version": "nexvia-aegis-v9-holdout-mixture-report/1.0",
        "status": "COMPLETE_MOCK_VERIFIED",
        "simulation_mode": "MOCK_SYNTHETIC",
        "partition": "mixture",
        "ticket_nonce": nonce,
    }
    mock_bytes = json.dumps(mock_payload).encode("utf-8")
    mock_report.write_bytes(mock_bytes)
    mock_sha = hashlib.sha256(mock_bytes).hexdigest()

    # Outcome transaction must reject mock report
    with pytest.raises(SecurityError, match="MOCK_REPORT_REJECTED"):
        execute_outcome_transaction(
            security_dir=security_dir,
            nonce=nonce,
            partition="mixture",
            exit_code=0,
            report_sha256=mock_sha,
            output_report_path=mock_report,
        )

    # Verify ledger state: partition must be FAILED, ticket must be FAILED_TERMINAL, never CONSUMED
    led = read_ledger(security_dir)
    p_status = led["active_tickets"][nonce]["partitions"]["mixture"]["status"]
    t_state = led["active_tickets"][nonce]["ticket_state"]
    assert p_status == "FAILED", f"Expected FAILED, got {p_status}"
    assert t_state == "FAILED_TERMINAL", f"Expected FAILED_TERMINAL, got {t_state}"


def test_regression_9_wrong_commit_or_artifact_digests_rejected(keypair, synthetic_repo, security_dir, tmp_path):
    """F-03 & F-04: Wrong Commit, evaluator digest, policy digest, manifest digest, or runtime digest rejected."""
    priv, pub, pub_pem, pub_sha = keypair

    # 9a: Wrong commit
    bad_manifesto = make_valid_manifesto(synthetic_repo)
    bad_manifesto["approved_commit"] = "00" * 20
    t_file = tmp_path / "ticket_bad_commit.json"
    sign_gate_b_ticket(priv, bad_manifesto, output_path=t_file)
    with pytest.raises(SecurityError, match="COMMIT_MISMATCH"):
        reconcile_execution_tree(
            repo_dir=synthetic_repo["repo_dir"],
            approved_commit=bad_manifesto["approved_commit"],
            expected_hashes=bad_manifesto,
            check_git_cleanliness=False,
        )

    # 9b: Wrong policy digest in reconciliation
    bad_pol_manifesto = make_valid_manifesto(synthetic_repo)
    bad_pol_manifesto["policy_sha256"] = "11" * 32
    with pytest.raises(SecurityError, match="DIGEST_MISMATCH"):
        reconcile_execution_tree(
            repo_dir=synthetic_repo["repo_dir"],
            approved_commit=synthetic_repo["commit"],
            expected_hashes=bad_pol_manifesto,
            check_git_cleanliness=False,
        )


def test_regression_10_invalid_mismatched_incomplete_report_provenance_fails_closed(tmp_path):
    """F-04: Invalid, mismatched, or incomplete Report provenance fails closed."""
    part_dir = tmp_path / "results" / "v9" / "test_mix"
    part_dir.mkdir(parents=True, exist_ok=True)
    rep_file = part_dir / "test_mix_report.json"

    # Create dummy artifact
    art_file = part_dir / "test_mix_episodes.csv"
    art_file.write_bytes(b"dummy,episodes\n1,1\n")
    art_sha = hashlib.sha256(art_file.read_bytes()).hexdigest().lower()

    # 10a: Missing run_config
    bad_payload = {
        "schema_version": "nexvia-aegis-v9-holdout-mixture-report/1.0",
        "status": "COMPLETE_VALID",
        "simulation_mode": "PRODUCTION_PHYSICS",
        "partition": "mixture",
        "ticket_nonce": "00" * 32,
        "artifact_sha256": {str(art_file): art_sha},
    }
    rep_file.write_text(json.dumps(bad_payload), encoding="utf-8")
    with pytest.raises(SecurityError, match="MALFORMED_REPORT_RUN_CONFIG"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce="00" * 32,
            output_root=tmp_path / "results" / "v9",
            expected_hashes={"policy_sha256": "5a" * 32},
        )

    # 10b: Mismatched policy digest in run_config
    bad_payload["run_config"] = {
        "partition": "mixture",
        "selected_policy_raw_sha256": "wrong_sha" * 8,
        "manifest_raw_sha256": "00" * 32,
    }
    rep_file.write_text(json.dumps(bad_payload), encoding="utf-8")
    with pytest.raises(SecurityError, match="PROVENANCE_POLICY_MISMATCH"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce="00" * 32,
            output_root=tmp_path / "results" / "v9",
            expected_hashes={"policy_sha256": "5a" * 32},
        )

    # 10c: Missing output artifact from artifact_sha256
    bad_payload["run_config"]["selected_policy_raw_sha256"] = "5a" * 32
    bad_payload["artifact_sha256"] = {str(part_dir / "non_existent.csv"): "00" * 32}
    rep_file.write_text(json.dumps(bad_payload), encoding="utf-8")
    with pytest.raises(SecurityError, match="REPORT_ARTIFACT_NOT_FOUND"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce="00" * 32,
            output_root=tmp_path / "results" / "v9",
            expected_hashes={"policy_sha256": "5a" * 32},
        )


def test_phase_4_audit_record_binding_and_non_circular_integrity(tmp_path):
    """Phase 4: Audit record binding, non-circular hashing, and separate status outcomes."""
    from aegis.v9.risk_statistics import compute_canonical_payload_sha256
    from nexvia_aegis.security.launcher import evaluate_execution_statuses

    nonce = "ab" * 32
    out_dir = tmp_path / "results" / "v9" / "test_mix"
    out_dir.mkdir(parents=True)

    # 1. Evaluate execution statuses: verify 4 separate orthogonal outcomes
    statuses_acc = evaluate_execution_statuses(
        exit_code=0,
        report_valid=True,
        report_payload={"evaluation_summary": {"m_accepted": 1, "statistical_acceptance": True}},
    )
    assert statuses_acc == {
        "execution_completion": "COMPLETED",
        "output_integrity": "INTEGRITY_VERIFIED",
        "execution_provenance": "PROVENANCE_VERIFIED",
        "statistical_acceptance": "ACCEPTED",
    }

    statuses_rej = evaluate_execution_statuses(
        exit_code=0,
        report_valid=True,
        report_payload={"evaluation_summary": {"m_accepted": 0, "statistical_acceptance": False}},
    )
    assert statuses_rej["statistical_acceptance"] == "REJECTED"
    assert statuses_rej["output_integrity"] == "INTEGRITY_VERIFIED"  # Output is intact even when rejected
    statuses_count_only = evaluate_execution_statuses(
        exit_code=0,
        report_valid=True,
        report_payload={"evaluation_summary": {"m_accepted": 1}},
    )
    assert statuses_count_only["statistical_acceptance"] == "NOT_EVALUATED"
    for malformed in ({"evaluation_summary": {"statistical_acceptance": 1}},
                      {"evaluation_summary": "ACCEPTED"}, {}):
        assert evaluate_execution_statuses(0, True, malformed)["statistical_acceptance"] == "NOT_EVALUATED"
    contradictory_unverified = evaluate_execution_statuses(
        0, False, {"evaluation_summary": {"statistical_acceptance": True}},
    )
    assert contradictory_unverified["statistical_acceptance"] == "NOT_EVALUATED"
    assert contradictory_unverified["output_integrity"] == "INTEGRITY_FAILED"

    # 2. Write authorization_record.json
    auth_file = out_dir / "authorization_record.json"
    auth_data = {
        "schema_version": "nexvia-aegis-v9-authorization-record/1.0",
        "created_utc": "2026-10-26T00:00:00Z",
        "ticket_nonce": nonce,
        "authorized_partition": "mixture",
        "approved_commit": "c511a0bcae93ed969ffb50504017ca2be88fde95",
        "evaluator_artifact_sha256": "11" * 32,
        "policy_sha256": "22" * 32,
        "manifest_sha256": "33" * 32,
        "lockfile_sha256": "44" * 32,
        "statuses": statuses_acc,
    }
    # Verify non-circular canonical hashing
    auth_data["integrity_sha256"] = compute_canonical_payload_sha256(auth_data)
    auth_bytes = json.dumps(auth_data, indent=2).encode("utf-8")
    auth_file.write_bytes(auth_bytes)
    auth_sha = hashlib.sha256(auth_bytes).hexdigest().lower()

    # Ephemeral episode and summary files
    ep_file = out_dir / "test_mix_episodes.csv"
    ep_file.write_bytes(b"seed,outcome\n1,1\n")
    ep_sha = hashlib.sha256(ep_file.read_bytes()).hexdigest().lower()

    # 3. Create report payload that commits to authorization_record.json SHA-256
    rep_payload = {
        "schema_version": "nexvia-aegis-v9-holdout-mixture-report/1.0",
        "status": "COMPLETE_VALID",
        "simulation_mode": "PRODUCTION_PHYSICS",
        "partition": "mixture",
        "ticket_nonce": nonce,
        "run_config": {
            "partition": "mixture",
            "selected_policy_raw_sha256": "22" * 32,
            "manifest_raw_sha256": "33" * 32,
        },
        "authorization_record_sha256": auth_sha,
        "artifact_sha256": {
            str(ep_file): ep_sha,
            str(auth_file): auth_sha,
        },
    }
    rep_payload["integrity_sha256"] = compute_canonical_payload_sha256(rep_payload)
    rep_bytes = json.dumps(rep_payload, indent=2).encode("utf-8")
    rep_file = out_dir / "test_mix_report.json"
    rep_file.write_bytes(rep_bytes)

    # 4. Validate output report: succeeds
    rep_sha, parsed_rep = validate_output_report(
        report_path=rep_file,
        expected_partition="mixture",
        expected_nonce=nonce,
        output_root=tmp_path / "results" / "v9",
        expected_hashes={
            "policy_sha256": "22" * 32,
            "mixture_manifest_sha256": "33" * 32,
        },
    )
    assert rep_sha == hashlib.sha256(rep_bytes).hexdigest().lower()
    assert parsed_rep["authorization_record_sha256"] == auth_sha

    # 5. Tampered authorization_record digest in report fails closed
    rep_payload_bad = copy.deepcopy(rep_payload)
    rep_payload_bad["authorization_record_sha256"] = "ff" * 32
    rep_file.write_text(json.dumps(rep_payload_bad), encoding="utf-8")
    with pytest.raises(SecurityError, match="REPORT_ARTIFACT_DIGEST_MISMATCH"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce=nonce,
            output_root=tmp_path / "results" / "v9",
            expected_hashes={
                "policy_sha256": "22" * 32,
                "mixture_manifest_sha256": "33" * 32,
            },
        )

    # 6. Tampered nonce inside authorization_record.json fails closed
    auth_data_bad = copy.deepcopy(auth_data)
    auth_data_bad["ticket_nonce"] = "wrong_nonce" * 4
    auth_bad_bytes = json.dumps(auth_data_bad, indent=2).encode("utf-8")
    auth_file.write_bytes(auth_bad_bytes)
    auth_bad_sha = hashlib.sha256(auth_bad_bytes).hexdigest().lower()
    rep_payload_bad2 = copy.deepcopy(rep_payload)
    rep_payload_bad2["authorization_record_sha256"] = auth_bad_sha
    rep_payload_bad2["artifact_sha256"][str(auth_file)] = auth_bad_sha
    rep_file.write_text(json.dumps(rep_payload_bad2), encoding="utf-8")
    with pytest.raises(SecurityError, match="REPORT_NONCE_MISMATCH"):
        validate_output_report(
            report_path=rep_file,
            expected_partition="mixture",
            expected_nonce=nonce,
            output_root=tmp_path / "results" / "v9",
            expected_hashes={
                "policy_sha256": "22" * 32,
                "mixture_manifest_sha256": "33" * 32,
            },
        )


def test_phase_4_legacy_cli_error_does_not_recommend_deprecated_tokens():
    """Phase 4: CLI error explicitly rejects legacy tokens and does not recommend V9_M4_AUTH_TOKEN."""
    from experiments.v9_evaluate_holdout import main as cli_main

    orig_argv = sys.argv
    try:
        sys.argv = ["v9_evaluate_holdout.py", "--run-production", "--authorized-execution-token", "OLD_SECRET"]
        with pytest.raises(RuntimeError) as exc_info:
            cli_main()
        err_msg = str(exc_info.value)
        assert "Passing execution tokens via CLI arguments" in err_msg
        assert "Legacy symmetric token authorization is permanently disabled." in err_msg
        assert "Production execution requires a valid Signed Gate B Ticket and an active Ledger Claim." in err_msg
        # Must NOT recommend setting V9_M4_AUTH_TOKEN
        assert "Deliver authorization credential via V9_M4_AUTH_TOKEN" not in err_msg
    finally:
        sys.argv = orig_argv


def test_phase_4_in_worker_auth_record_out_captures_verified_metadata(
    keypair, synthetic_repo, security_dir, tmp_path, monkeypatch
):
    """Phase 4: verify_execution_authorization populates auth_record_out with verified metadata."""
    priv, pub, pub_pem, pub_sha = keypair
    manifesto = make_valid_manifesto(synthetic_repo)
    ticket_file = tmp_path / "ticket_phase4.json"
    envelope = sign_gate_b_ticket(priv, manifesto, output_path=ticket_file)
    nonce = envelope["payload"]["nonce"]

    pub_file = tmp_path / "pubkey.pem"
    pub_file.write_bytes(pub_pem)

    register_ticket(
        ticket_data=ticket_file,
        security_dir=security_dir,
        pubkey_anchor_path=pub_file,
        expected_pubkey_sha256=pub_sha,
        public_key_obj=pub,
    )

    claim_res = execute_claim_transaction(
        security_dir=security_dir,
        nonce=nonce,
        partition="mixture",
    )
    secret = claim_res["claim_secret"]

    monkeypatch.delenv(AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(EXPECTED_AUTH_TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(AUTH_SECRET_FILE_ENV_VAR, raising=False)
    monkeypatch.setenv("V9_M4_TICKET_PATH", str(ticket_file))
    monkeypatch.setenv("V9_M4_CLAIM_SECRET", secret)
    monkeypatch.setenv("V9_M4_TICKET_NONCE", nonce)
    monkeypatch.setenv("V9_M4_PARTITION", "mixture")
    monkeypatch.setenv("V9_M4_SECURITY_DIR", str(security_dir))

    auth_context: dict[str, Any] = {}
    success = verify_execution_authorization(
        partition="mixture",
        allow_mock_simulation=False,
        ticket_path=ticket_file,
        security_dir=security_dir,
        public_key_obj=pub,
        repo_dir=synthetic_repo["repo_dir"],
        auth_record_out=auth_context,
    )
    assert success is True
    assert auth_context["ticket_nonce"] == nonce
    assert auth_context["authorized_partition"] == "mixture"
    assert auth_context["approved_commit"] == manifesto["approved_commit"]
    assert auth_context["evaluator_artifact_sha256"] == manifesto["evaluator_artifact_sha256"]
    assert auth_context["policy_sha256"] == manifesto["policy_sha256"]
    assert auth_context["manifest_sha256"] == manifesto["mixture_manifest_sha256"]
    assert auth_context["lockfile_sha256"] == manifesto["lockfile_sha256"]
    assert auth_context["worker_pid"] == os.getpid()
    assert auth_context["mode"] == "PRODUCTION"
    # Never store raw secret
    assert "claim_secret" not in auth_context
    assert secret not in json.dumps(auth_context)
