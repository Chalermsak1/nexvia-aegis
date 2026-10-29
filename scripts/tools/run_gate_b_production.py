#!/usr/bin/env python3
"""NEXVIA AEGIS Gate B Production Evaluation Orchestrator.

Executes single-shot confirmatory holdout evaluation on locked partitions:
  - Mixture Holdout (D_test^mix, N=1,440 episodes)
  - Scenario Holdout (D_test^scen, N=1,440 episodes)

Enforces:
  - RFC 8785 canonical verification of Ed25519 signed Gate B ticket.
  - Pinned trust anchor public key verification.
  - Exact binding to approved git commit, evaluator hash, policy hash, and manifest hashes.
  - Persistent atomic anti-replay ledger claims and single-use claim secrets in ~/.nexvia_security/.
  - In-worker fail-closed authorization binding and crash-durable state persistence.
  - Sequential execution of both partitions to terminal CLOSED state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from nexvia_aegis.security.canonical import parse_strict_json
from nexvia_aegis.security.launcher import verify_trust_anchor
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
    validate_semantic_payload,
    verify_ticket_envelope,
)


def sha256_file(path: Path | str) -> str:
    """Computes lowercase hex SHA-256 digest of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().lower()


def run_production_partition(
    partition: str,
    ticket_path: Path,
    sec_dir: Path,
    repo_dir: Path,
    pubkey_obj: Any,
) -> dict[str, Any]:
    """Claims and executes a single production holdout partition."""
    part_tag = "mix" if partition == "mixture" else "scen"
    raw_ticket = ticket_path.read_bytes()
    verified_envelope = verify_ticket_envelope(raw_ticket, public_key_obj=pubkey_obj)
    payload = verified_envelope["payload"]
    nonce = payload["nonce"]

    # Register ticket if not already active in ledger
    current_ledger = read_ledger(sec_dir)
    if nonce not in current_ledger["active_tickets"]:
        print(f"[{partition.upper()}] Registering Gate B ticket in replay ledger...")
        register_ticket(ticket_data=raw_ticket, security_dir=sec_dir, public_key_obj=pubkey_obj)

    # Claim partition execution right under lock
    print(f"[{partition.upper()}] Committing atomic claim transaction in ledger...")
    claim_entry = execute_claim_transaction(sec_dir, nonce, partition)
    claim_secret = claim_entry["claim_secret"]
    print(f"[{partition.upper()}] Claim committed successfully. Worker claim secret bound.")

    # Target output paths
    out_dir = repo_dir / "results" / "v9" / f"test_{part_tag}"
    report_path = out_dir / f"test_{part_tag}_report.json"

    # Prepare sanitized worker environment
    env = dict(os.environ)
    env["V9_M4_TICKET_PATH"] = str(ticket_path.resolve())
    env["V9_M4_SECURITY_DIR"] = str(sec_dir.resolve())
    env["V9_M4_CLAIM_SECRET"] = claim_secret
    env["V9_M4_TICKET_NONCE"] = nonce
    env["V9_M4_PARTITION"] = partition
    env["V9_M4_REPO_DIR"] = str(repo_dir.resolve())
    env["PYTHONPATH"] = f"{repo_dir}:{repo_dir / 'src'}"
    env["PYTHONUNBUFFERED"] = "1"

    worker_cmd = [
        sys.executable,
        str(repo_dir / "experiments" / "v9_evaluate_holdout.py"),
        "--partition", partition,
        "--run-production",
    ]

    print(f"[{partition.upper()}] Launching production evaluation worker:")
    print(f"  Command:   {' '.join(worker_cmd)}")
    print(f"  Output:    {out_dir}")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")

    start_time = time.time()
    proc = subprocess.Popen(
        worker_cmd,
        cwd=repo_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    worker_pid = proc.pid
    output_lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        output_lines.append(line)
        if any(marker in line for marker in ["[M4-PROD]", "[EVAL]", "Progress:", "Hypothesis", "COMPLETE", "ERROR", "EXCEPTION"]):
            sys.stdout.write(f"  [{partition}] {line}")
            sys.stdout.flush()

    proc.wait()
    exit_code = proc.returncode
    elapsed = time.time() - start_time
    print(f"[{partition.upper()}] Worker process exited with code {exit_code} in {elapsed:.2f}s")

    if exit_code != 0:
        print(f"[{partition.upper()}] Worker failure detected! Recording FAILED outcome...", file=sys.stderr)
        execute_outcome_transaction(
            security_dir=sec_dir,
            nonce=nonce,
            partition=partition,
            exit_code=exit_code,
            worker_pid=worker_pid,
            output_report_path=report_path if report_path.exists() else None,
        )
        raise RuntimeError(f"Holdout worker for partition '{partition}' failed with exit code {exit_code}")

    if not report_path.exists():
        execute_outcome_transaction(
            security_dir=sec_dir,
            nonce=nonce,
            partition=partition,
            exit_code=1,
            worker_pid=worker_pid,
        )
        raise RuntimeError(f"Expected report file '{report_path}' was not generated.")

    report_sha = sha256_file(report_path)
    print(f"[{partition.upper()}] Generated report digest: {report_sha}")

    # Commit outcome transaction
    print(f"[{partition.upper()}] Committing outcome transaction to ledger...")
    updated_ticket = execute_outcome_transaction(
        security_dir=sec_dir,
        nonce=nonce,
        partition=partition,
        exit_code=0,
        report_sha256=report_sha,
        worker_pid=worker_pid,
        output_report_path=report_path,
    )
    print(f"[{partition.upper()}] Partition status: {updated_ticket['partitions'][partition]['status']}")
    print(f"[{partition.upper()}] Ticket state:     {updated_ticket['ticket_state']}")

    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "partition": partition,
        "exit_code": exit_code,
        "elapsed_seconds": elapsed,
        "report_path": str(report_path),
        "report_sha256": report_sha,
        "report_data": report_data,
        "ticket_state": updated_ticket["ticket_state"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS Gate B Confirmatory Evaluation Orchestrator."
    )
    parser.add_argument(
        "--ticket",
        type=Path,
        default=_REPO_ROOT / "configs" / "gate_b_authorization_ticket.json",
        help="Path to signed Gate B authorization ticket.",
    )
    parser.add_argument(
        "--security-dir",
        type=Path,
        default=None,
        help="Path to external security directory (defaults to ~/.nexvia_security).",
    )
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=_REPO_ROOT,
        help="Repository root directory.",
    )
    parser.add_argument(
        "--partition",
        choices=["mixture", "scenario", "both"],
        default="both",
        help="Partition(s) to evaluate (default: both).",
    )
    args = parser.parse_args()

    sec_dir = resolve_security_dir(args.security_dir)
    ticket_file = args.ticket.resolve()
    repo_root = args.repo_dir.resolve()

    if not ticket_file.exists():
        print(f"[ERROR] Ticket file '{ticket_file}' not found.", file=sys.stderr)
        return 1

    # Verify trust anchor
    pub_path = sec_dir / "gate_b_owner_pubkey.pem"
    sha_path = sec_dir / "gate_b_owner_pubkey.sha256"
    if not pub_path.exists() or not sha_path.exists():
        print(f"[ERROR] Public key or fingerprint not found in '{sec_dir}'.", file=sys.stderr)
        return 1

    expected_fp = sha_path.read_text(encoding="utf-8").strip().lower()
    pubkey = verify_trust_anchor(pub_path, expected_pubkey_sha256=expected_fp)

    # Verify ticket envelope
    raw_ticket = ticket_file.read_bytes()
    envelope = verify_ticket_envelope(raw_ticket, public_key_obj=pubkey)
    payload = envelope["payload"]
    nonce = payload["nonce"]

    print("=" * 80)
    print("      NEXVIA AEGIS V9-M4 — CONFIRMATORY HOLDOUT EVALUATION ORCHESTRATOR")
    print("=" * 80)
    print(f"Candidate Commit:   {payload['approved_commit']}")
    print(f"Ticket Nonce:       {nonce}")
    print(f"Operator:           {payload['operator_identity']}")
    print(f"Validity Window:    {payload['issued_at_utc']} -> {payload['expires_at_utc']}")
    print(f"Security Directory: {sec_dir}")
    print(f"Target Output Root: {payload['target_output_root']}")
    print("=" * 80)

    partitions_to_run = ["mixture", "scenario"] if args.partition == "both" else [args.partition]
    results: list[dict[str, Any]] = []

    for part in partitions_to_run:
        print(f"\n>>> STARTING PARTITION: {part.upper()} <<<")
        res = run_production_partition(
            partition=part,
            ticket_path=ticket_file,
            sec_dir=sec_dir,
            repo_dir=repo_root,
            pubkey_obj=pubkey,
        )
        results.append(res)
        print(f">>> COMPLETED PARTITION: {part.upper()} <<<\n")

    print("=" * 80)
    print("      ALL HOLDOUT PARTITIONS COMPLETED AND COMMITTED SUCCESSFULLY")
    print("=" * 80)
    for res in results:
        print(f"Partition:  {res['partition']}")
        print(f"Report:     {res['report_path']}")
        print(f"SHA-256:    {res['report_sha256']}")
        print(f"Status:     {res['report_data'].get('status')}")
        print(f"Class:      {res['report_data'].get('evaluation_summary', {}).get('overall_evaluation_classification')}")
        print("-" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
