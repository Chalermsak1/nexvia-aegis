#!/usr/bin/env python3
"""NEXVIA AEGIS Gate B Ticket Signer Utility.

Owner-controlled offline utility for signing Gate B authorization tickets under
Contract AEGIS-V9-M4-CTR-01.

Enforces:
  - Exact binding to Final Commit and 5 frozen artifact SHA-256 digests.
  - Contractual invariance of policy and manifest hashes.
  - Strict maximum validity window (W_max = 120 minutes).
  - RFC 8785 JSON Canonicalization Scheme (JCS).
  - Pure Ed25519 digital signature envelope.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import secrets
import sys
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from nexvia_aegis.security.canonical import canonicalize_payload, parse_strict_json
from nexvia_aegis.security.verifier import (
    RE_HEX_40,
    RE_HEX_64,
    SecurityError,
    validate_semantic_payload,
)

MAX_VALIDITY_MINUTES = 120

LOCKED_POLICY_SHA256 = "5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2"
LOCKED_MIXTURE_MANIFEST_SHA256 = "70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db"
LOCKED_SCENARIO_MANIFEST_SHA256 = "55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d"


def load_private_key(
    privkey_source: Path | str | bytes | Ed25519PrivateKey,
    passphrase: bytes | None = None,
) -> Ed25519PrivateKey:
    """Loads an Ed25519 private key from instance, PEM bytes, or PEM file path."""
    if isinstance(privkey_source, Ed25519PrivateKey):
        return privkey_source

    raw_bytes: bytes
    if isinstance(privkey_source, (str, Path)):
        p = Path(privkey_source)
        if not p.exists():
            raise SecurityError(f"PRIVATE_KEY_FILE_NOT_FOUND: Private key file '{p}' does not exist.")
        raw_bytes = p.read_bytes()
    elif isinstance(privkey_source, bytes):
        raw_bytes = privkey_source
    else:
        raise SecurityError(
            f"INVALID_PRIVATE_KEY_SOURCE: Expected Path, bytes, or Ed25519PrivateKey, got {type(privkey_source).__name__}."
        )

    try:
        key = load_pem_private_key(raw_bytes, password=passphrase)
    except Exception as e:
        raise SecurityError(f"FAILED_TO_LOAD_PRIVATE_KEY: Could not parse PEM private key: {e}") from e

    if not isinstance(key, Ed25519PrivateKey):
        raise SecurityError(
            f"INVALID_KEY_TYPE: Expected Ed25519PrivateKey, got {type(key).__name__}."
        )
    return key


def load_manifesto(manifesto_source: Path | str | dict[str, Any]) -> dict[str, Any]:
    """Loads and strictly parses a release manifesto."""
    if isinstance(manifesto_source, dict):
        return dict(manifesto_source)

    p = Path(manifesto_source)
    if not p.exists():
        raise SecurityError(f"MANIFESTO_FILE_NOT_FOUND: Manifesto file '{p}' does not exist.")

    raw = p.read_bytes()
    try:
        data = parse_strict_json(raw)
    except Exception as e:
        raise SecurityError(f"MANIFESTO_PARSE_FAILED: Could not parse JSON manifesto: {e}") from e

    if not isinstance(data, dict):
        raise SecurityError("MALFORMED_MANIFESTO: Manifesto must be a JSON object.")
    return data


def validate_manifesto_hashes(manifesto: dict[str, Any]) -> None:
    """Validates required keys and contractual hashes in release manifesto."""
    required = {
        "approved_commit",
        "evaluator_artifact_sha256",
        "policy_sha256",
        "mixture_manifest_sha256",
        "scenario_manifest_sha256",
        "lockfile_sha256",
    }
    missing = required - set(manifesto.keys())
    if missing:
        raise SecurityError(f"INCOMPLETE_MANIFESTO: Missing required manifesto fields {sorted(missing)}.")

    commit = str(manifesto["approved_commit"]).lower()
    if not RE_HEX_40.match(commit):
        raise SecurityError(f"INVALID_APPROVED_COMMIT: Expected 40-char hex commit SHA-1, got '{commit}'.")

    for field in ("evaluator_artifact_sha256", "policy_sha256", "mixture_manifest_sha256", "scenario_manifest_sha256", "lockfile_sha256"):
        val = str(manifesto[field]).lower()
        if not RE_HEX_64.match(val):
            raise SecurityError(f"INVALID_{field.upper()}: Expected 64-char hex SHA-256, got '{val}'.")

    # Strict contract invariant verification
    pol_sha = str(manifesto["policy_sha256"]).lower()
    if pol_sha != LOCKED_POLICY_SHA256:
        raise SecurityError(
            f"LOCKED_POLICY_MISMATCH: Manifesto policy hash {pol_sha} != locked {LOCKED_POLICY_SHA256}."
        )

    mix_sha = str(manifesto["mixture_manifest_sha256"]).lower()
    if mix_sha != LOCKED_MIXTURE_MANIFEST_SHA256:
        raise SecurityError(
            f"LOCKED_MIXTURE_MANIFEST_MISMATCH: Manifesto mixture manifest hash {mix_sha} != locked {LOCKED_MIXTURE_MANIFEST_SHA256}."
        )

    scen_sha = str(manifesto["scenario_manifest_sha256"]).lower()
    if scen_sha != LOCKED_SCENARIO_MANIFEST_SHA256:
        raise SecurityError(
            f"LOCKED_SCENARIO_MANIFEST_MISMATCH: Manifesto scenario manifest hash {scen_sha} != locked {LOCKED_SCENARIO_MANIFEST_SHA256}."
        )


def sign_gate_b_ticket(
    privkey_source: Path | str | bytes | Ed25519PrivateKey,
    manifesto_source: Path | str | dict[str, Any],
    validity_minutes: int = 120,
    operator_identity: str = "chalermsak@project-owner",
    target_output_root: str = "results/v9",
    passphrase: bytes | None = None,
    nonce: str | None = None,
    issued_at_utc: str | None = None,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Generates and cryptographically signs a Gate B authorization ticket.

    Args:
        privkey_source: Ed25519 private key or path/bytes.
        manifesto_source: Release manifesto dictionary or path.
        validity_minutes: Duration of authorization window in minutes (1 <= W <= 120).
        operator_identity: Authorized operator identifier.
        target_output_root: Relative authorized output root ('results/v9').
        passphrase: Optional passphrase for encrypted private key.
        nonce: Optional 64-char hex nonce (generated randomly if None).
        issued_at_utc: Optional ISO 8601 UTC issuance timestamp.
        output_path: Optional file path to persist signed ticket JSON.

    Returns:
        Signed ticket envelope dictionary.

    Raises:
        SecurityError: On invalid parameters, manifesto tampering, or cryptographic error.
    """
    if validity_minutes <= 0:
        raise SecurityError(
            f"INVALID_VALIDITY_WINDOW: validity_minutes must be > 0, got {validity_minutes}."
        )
    if validity_minutes > MAX_VALIDITY_MINUTES:
        raise SecurityError(
            f"VALIDITY_WINDOW_TOO_LONG: validity_minutes ({validity_minutes}) exceeds maximum allowed {MAX_VALIDITY_MINUTES}."
        )

    manifesto = load_manifesto(manifesto_source)
    validate_manifesto_hashes(manifesto)

    privkey = load_private_key(privkey_source, passphrase=passphrase)

    # Timestamps
    if issued_at_utc is not None:
        ts_issued = issued_at_utc
        # Verify format
        if not (ts_issued.endswith("Z") or ts_issued.endswith("+00:00")):
            raise SecurityError(f"INVALID_ISSUED_AT: Timestamp '{ts_issued}' must end with 'Z' or '+00:00'.")
        dt_issued = datetime.fromisoformat(ts_issued[:-1] + "+00:00" if ts_issued.endswith("Z") else ts_issued)
    else:
        dt_issued = datetime.now(timezone.utc).replace(microsecond=0)
        ts_issued = dt_issued.strftime("%Y-%m-%dT%H:%M:%SZ")

    dt_expires = dt_issued + timedelta(minutes=validity_minutes)
    ts_expires = dt_expires.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Nonce
    if nonce is not None:
        clean_nonce = str(nonce).lower()
        if not RE_HEX_64.match(clean_nonce):
            raise SecurityError(f"INVALID_NONCE_FORMAT: Expected 64-char hex nonce, got '{nonce}'.")
    else:
        clean_nonce = secrets.token_hex(32).lower()

    payload: dict[str, Any] = {
        "milestone": "V9-M4",
        "gate": "GATE_B",
        "scope": "CONFIRMATORY_HOLDOUT_EVALUATION",
        "approved_commit": str(manifesto["approved_commit"]).lower(),
        "evaluator_artifact_sha256": str(manifesto["evaluator_artifact_sha256"]).lower(),
        "policy_sha256": str(manifesto["policy_sha256"]).lower(),
        "mixture_manifest_sha256": str(manifesto["mixture_manifest_sha256"]).lower(),
        "scenario_manifest_sha256": str(manifesto["scenario_manifest_sha256"]).lower(),
        "lockfile_sha256": str(manifesto["lockfile_sha256"]).lower(),
        "authorized_partitions": ["mixture", "scenario"],
        "issued_at_utc": ts_issued,
        "expires_at_utc": ts_expires,
        "nonce": clean_nonce,
        "operator_identity": operator_identity,
        "target_output_root": target_output_root,
    }

    # Strict semantic payload validation
    validate_semantic_payload(payload, current_time_iso=ts_issued)

    # RFC 8785 JCS Canonicalization
    canonical_bytes = canonicalize_payload(payload)

    # Ed25519 digital signature
    signature_bytes = privkey.sign(canonical_bytes)
    sig_hex = signature_bytes.hex().lower()

    envelope: dict[str, Any] = {
        "ticket_version": "1.0",
        "payload": payload,
        "signature_algorithm": "Ed25519",
        "signature_hex": sig_hex,
    }

    if output_path is not None:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        dumped = json.dumps(envelope, indent=2) + "\n"
        out_p.write_text(dumped, encoding="utf-8")

    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS Gate B Ticket Signer Utility (Offline Out-of-Band Tool)."
    )
    parser.add_argument(
        "--privkey",
        required=True,
        type=Path,
        help="Path to PEM-encoded Ed25519 private key.",
    )
    parser.add_argument(
        "--manifesto",
        required=True,
        type=Path,
        help="Path to release_manifesto.json containing authoritative artifact digests.",
    )
    parser.add_argument(
        "--validity-minutes",
        type=int,
        default=120,
        help=f"Validity window duration in minutes (default 120, max {MAX_VALIDITY_MINUTES}).",
    )
    parser.add_argument(
        "--operator",
        type=str,
        default="chalermsak@project-owner",
        help="Authorized operator identity.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Output destination path for gate_b_authorization_ticket.json.",
    )
    args = parser.parse_args()

    try:
        envelope = sign_gate_b_ticket(
            privkey_source=args.privkey,
            manifesto_source=args.manifesto,
            validity_minutes=args.validity_minutes,
            operator_identity=args.operator,
            output_path=args.output,
        )
        print(f"[SIGNER] Successfully signed Gate B authorization ticket: {args.output}")
        print(f"[SIGNER] Ticket Nonce:   {envelope['payload']['nonce']}")
        print(f"[SIGNER] Validity Window: {envelope['payload']['issued_at_utc']} -> {envelope['payload']['expires_at_utc']}")
        return 0
    except SecurityError as e:
        print(f"[SIGNER SECURITY ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[SIGNER UNEXPECTED ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
