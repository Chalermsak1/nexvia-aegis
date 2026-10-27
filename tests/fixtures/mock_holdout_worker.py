#!/usr/bin/env python3
"""Synthetic Mock Holdout Worker for NEXVIA AEGIS Gate B Authorization Tests.

Simulates the execution of holdout evaluation without accessing any real seeds,
generating holdout episodes, loading holdout data, or running physics simulation.
Enforces strict test isolation under Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic Mock Holdout Worker.")
    parser.add_argument("--partition", choices=["mixture", "scenario"], required=True)
    parser.add_argument("--ticket-nonce", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--missing-report", action="store_true")
    parser.add_argument("--corrupt-report", action="store_true")
    parser.add_argument("--symlink-report", action="store_true")
    parser.add_argument("--mismatched-nonce", action="store_true")
    parser.add_argument("--mismatched-partition", action="store_true")
    parser.add_argument("--out-of-root-report", action="store_true")
    parser.add_argument("--synthetic-production-stub", action="store_true", help="Stub valid production report format for launcher testing.")
    args = parser.parse_args()

    # Sleep if requested (for timeout testing)
    if args.sleep_seconds > 0:
        time.sleep(args.sleep_seconds)

    # If exit-code is non-zero, exit early unless asked to write files
    if args.exit_code != 0 and args.missing_report:
        return args.exit_code

    part = args.partition
    part_tag = "mix" if part == "mixture" else "scen"
    nonce = args.ticket_nonce or os.environ.get("V9_M4_TICKET_NONCE", "00" * 32)

    if args.mismatched_nonce:
        nonce = "ff" * 32
    if args.mismatched_partition:
        part = "scenario" if part == "mixture" else "mixture"

    out_dir = args.output_dir.resolve()
    part_dir = out_dir / f"test_{part_tag}"
    part_dir.mkdir(parents=True, exist_ok=True)

    if args.out_of_root_report:
        report_path = Path("/tmp") / f"test_{part_tag}_report.json"
    else:
        report_path = part_dir / f"test_{part_tag}_report.json"

    if args.missing_report:
        return args.exit_code

    if args.symlink_report:
        target = part_dir / "real_dummy_report.json"
        target.write_text('{"status": "DUMMY"}', encoding="utf-8")
        if report_path.exists() or report_path.is_symlink():
            report_path.unlink()
        os.symlink(target, report_path)
        return args.exit_code

    if args.corrupt_report:
        report_path.write_bytes(b"NOT_A_VALID_JSON_{{{[[[")
        return args.exit_code

    # Write synthetic dummy output CSVs
    episodes_csv = part_dir / f"test_{part_tag}_episodes.csv"
    episodes_data = b"episode_id,seed,scenario,m_accepted\n1,1001,flat,1\n"
    episodes_csv.write_bytes(episodes_data)

    summary_csv = part_dir / f"test_{part_tag}_summary.csv"
    summary_data = b"partition,n_episodes,m_accepted\n" + part.encode("utf-8") + b",1,1\n"
    summary_csv.write_bytes(summary_data)

    # Optional ledger claim binding if running under supervisory launcher with claim secret
    claim_secret = os.environ.get("V9_M4_CLAIM_SECRET")
    sec_dir_env = os.environ.get("V9_M4_SECURITY_DIR")
    if claim_secret and sec_dir_env:
        try:
            repo_r = Path(__file__).resolve().parent.parent.parent
            if str(repo_r / "src") not in sys.path:
                sys.path.insert(0, str(repo_r / "src"))
            from nexvia_aegis.security.ledger import (
                PersistentLedgerLock,
                read_ledger,
                _persist_ledger_crash_durable,
                LEDGER_FILE_NAME,
            )
            sec_p = Path(sec_dir_env)
            with PersistentLedgerLock(sec_p):
                led = read_ledger(sec_p)
                if nonce in led["active_tickets"]:
                    tent = led["active_tickets"][nonce]
                    pent = tent["partitions"].get(part)
                    if pent and pent.get("status") == "CLAIMED":
                        pent["worker_pid"] = os.getpid()
                        pent["claim_secret_hash"] = f"CLAIM_BOUND_TO_PID_{os.getpid()}"
                        _persist_ledger_crash_durable(sec_p / LEDGER_FILE_NAME, led)
        except Exception:
            pass

    if args.synthetic_production_stub:
        status_val = "COMPLETE_VALID"
        sim_mode_val = "PRODUCTION_PHYSICS"
    else:
        status_val = "COMPLETE_MOCK_VERIFIED"
        sim_mode_val = "MOCK_SYNTHETIC"

    report_payload = {
        "schema_version": f"nexvia-aegis-v9-holdout-{part}-report/1.0",
        "status": status_val,
        "partition": part,
        "ticket_nonce": nonce,
        "simulation_mode": sim_mode_val,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_summary": {
            "partition": part,
            "n_episodes": 1,
            "m_accepted": 1,
            "coverage": 1.0,
            "tsr": 1.0,
        },
        "artifact_sha256": {
            str(episodes_csv): sha256_bytes(episodes_data),
            str(summary_csv): sha256_bytes(summary_data),
        },
    }

    if args.synthetic_production_stub:
        # Provenance metadata binding (F-04)
        policy_sha = "5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2"
        manifest_sha = (
            "70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db"
            if part == "mixture"
            else "55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d"
        )
        ticket_p = os.environ.get("V9_M4_TICKET_PATH")
        if ticket_p and Path(ticket_p).exists():
            try:
                t_raw = json.loads(Path(ticket_p).read_text(encoding="utf-8"))
                t_payload = t_raw.get("payload", {})
                policy_sha = t_payload.get("policy_sha256", policy_sha)
                if part == "mixture":
                    manifest_sha = t_payload.get("mixture_manifest_sha256", manifest_sha)
                else:
                    manifest_sha = t_payload.get("scenario_manifest_sha256", manifest_sha)
            except Exception:
                pass

        report_payload["run_config"] = {
            "partition": part,
            "selected_policy_raw_sha256": policy_sha,
            "manifest_raw_sha256": manifest_sha,
        }

        # Phase 4 Audit Record Binding
        auth_record_file = part_dir / "authorization_record.json"
        auth_record = {
            "schema_version": "nexvia-aegis-v9-authorization-record/1.0",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "ticket_nonce": nonce,
            "authorized_partition": part,
            "approved_commit": "c511a0bcae93ed969ffb50504017ca2be88fde95",
            "evaluator_artifact_sha256": "0" * 64,
            "policy_sha256": policy_sha,
            "manifest_sha256": manifest_sha,
            "lockfile_sha256": "0" * 64,
            "statuses": {
                "execution_completion": "COMPLETED",
                "output_integrity": "INTEGRITY_VERIFIED",
                "execution_provenance": "PROVENANCE_VERIFIED",
                "statistical_acceptance": "NOT_EVALUATED",
            },
        }
        auth_bytes = json.dumps(auth_record, indent=2).encode("utf-8")
        auth_record_file.write_bytes(auth_bytes)
        auth_sha = sha256_bytes(auth_bytes)
        report_payload["artifact_sha256"][str(auth_record_file)] = auth_sha
        report_payload["authorization_record_sha256"] = auth_sha

    report_bytes = json.dumps(report_payload, indent=2).encode("utf-8")
    report_path.write_bytes(report_bytes)

    return args.exit_code


if __name__ == "__main__":
    sys.exit(main())
