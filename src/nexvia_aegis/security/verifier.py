"""Signed Gate B Authorization Ticket verification engine.

Provides strict parsing, Ed25519 digital signature verification over RFC 8785 canonical
bytes, public key trust anchor validation, and payload schema verification.
Compliant with Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path
import re
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from nexvia_aegis.security.canonical import canonicalize_payload, parse_strict_json

REQUIRED_ENVELOPE_KEYS = {
    "ticket_version",
    "payload",
    "signature_algorithm",
    "signature_hex",
}

REQUIRED_PAYLOAD_KEYS = {
    "milestone",
    "gate",
    "scope",
    "approved_commit",
    "evaluator_artifact_sha256",
    "policy_sha256",
    "mixture_manifest_sha256",
    "scenario_manifest_sha256",
    "lockfile_sha256",
    "authorized_partitions",
    "issued_at_utc",
    "expires_at_utc",
    "nonce",
    "operator_identity",
    "target_output_root",
}

RE_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
RE_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
RE_HEX_128 = re.compile(r"^[0-9a-f]{128}$")


class SecurityError(Exception):
    """Raised when an authorization, cryptographic, or integrity invariant is violated."""


def parse_iso8601_utc(timestamp_str: str) -> datetime:
    """Parses an ISO 8601 UTC timestamp string ending in 'Z' or '+00:00'.

    Args:
        timestamp_str: ISO 8601 formatted timestamp.

    Returns:
        Timezone-aware datetime object in UTC.

    Raises:
        SecurityError: If timestamp is malformed or not in UTC.
    """
    if not isinstance(timestamp_str, str):
        raise SecurityError(
            f"INVALID_TIMESTAMP_TYPE: Expected ISO 8601 string, got {type(timestamp_str).__name__}."
        )

    ts = timestamp_str.strip()
    if ts.endswith("Z"):
        normalized = ts[:-1] + "+00:00"
    elif ts.endswith("+00:00"):
        normalized = ts
    else:
        raise SecurityError(
            f"INVALID_TIMEZONE: Timestamp '{timestamp_str}' must explicitly end with 'Z' or '+00:00'."
        )

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise SecurityError(
            f"MALFORMED_ISO8601_TIMESTAMP: Could not parse '{timestamp_str}': {e}"
        ) from e

    if dt.tzinfo != timezone.utc:
        raise SecurityError(
            f"NON_UTC_TIMEZONE: Timestamp '{timestamp_str}' must be in UTC timezone."
        )
    return dt


def verify_ticket_envelope(
    raw_ticket: str | bytes,
    pubkey_anchor_path: Path | None = None,
    expected_pubkey_sha256: str | None = None,
    public_key_obj: Ed25519PublicKey | None = None,
) -> dict[str, Any]:
    """Strictly parses and cryptographically verifies an Ed25519 authorization ticket envelope.

    Verification sequence:
      1. Syntactic parse with duplicate-key rejection (fail-closed).
      2. Envelope whitelist and structure validation.
      3. Public key trust anchor verification (fingerprint check).
      4. RFC 8785 canonicalization of payload object.
      5. Ed25519 signature verification over canonical bytes.

    Args:
        raw_ticket: Raw JSON text or bytes of the authorization ticket.
        pubkey_anchor_path: Path to PEM-encoded Ed25519 public key anchor.
        expected_pubkey_sha256: Expected SHA-256 hex fingerprint of the public key file.
        public_key_obj: Optional pre-loaded Ed25519PublicKey object (primarily for tests).

    Returns:
        Parsed envelope dictionary containing verified payload.

    Raises:
        SecurityError: On any verification, syntactic, or cryptographic failure.
    """
    try:
        envelope = parse_strict_json(raw_ticket)
    except Exception as e:
        raise SecurityError(f"TICKET_PARSE_FAILED: {e}") from e

    if not isinstance(envelope, dict):
        raise SecurityError("MALFORMED_TICKET_ENVELOPE: Top-level ticket must be a JSON object.")

    # 1. Envelope Whitelist Validation
    envelope_keys = set(envelope.keys())
    if envelope_keys != REQUIRED_ENVELOPE_KEYS:
        extra = envelope_keys - REQUIRED_ENVELOPE_KEYS
        missing = REQUIRED_ENVELOPE_KEYS - envelope_keys
        if extra:
            raise SecurityError(
                f"UNRECOGNIZED_ENVELOPE_FIELD: Unrecognized field(s) {sorted(extra)} in ticket envelope."
            )
        if missing:
            raise SecurityError(
                f"MISSING_ENVELOPE_FIELD: Missing required envelope field(s) {sorted(missing)}."
            )

    if envelope["ticket_version"] != "1.0":
        raise SecurityError(
            f"UNSUPPORTED_TICKET_VERSION: Version '{envelope['ticket_version']}' is not supported (expected '1.0')."
        )

    if envelope["signature_algorithm"] != "Ed25519":
        raise SecurityError(
            f"UNSUPPORTED_SIGNATURE_ALGORITHM: Algorithm '{envelope['signature_algorithm']}' is not supported (expected 'Ed25519')."
        )

    sig_hex = envelope["signature_hex"]
    if not isinstance(sig_hex, str) or not RE_HEX_128.match(sig_hex):
        raise SecurityError(
            "INVALID_SIGNATURE_FORMAT: signature_hex must be exactly 128 lowercase hexadecimal characters."
        )

    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise SecurityError("MALFORMED_PAYLOAD: Ticket payload must be a JSON object.")

    # 2. Resolve and Validate Public Key Trust Anchor
    if public_key_obj is not None:
        if not isinstance(public_key_obj, Ed25519PublicKey):
            raise SecurityError(
                f"INVALID_KEY_TYPE: Expected Ed25519PublicKey, got {type(public_key_obj).__name__}."
            )
        pubkey = public_key_obj
    else:
        if pubkey_anchor_path is None:
            raise SecurityError(
                "MISSING_TRUST_ANCHOR: Neither public_key_obj nor pubkey_anchor_path was provided."
            )
        anchor_path = Path(pubkey_anchor_path)
        if not anchor_path.exists():
            raise SecurityError(
                f"TRUST_ANCHOR_NOT_FOUND: Public key file not found at {anchor_path}."
            )
        if anchor_path.is_symlink():
            raise SecurityError(
                f"SYMLINK_TRUST_ANCHOR_REJECTED: Public key anchor at {anchor_path} must not be a symbolic link."
            )

        raw_key_bytes = anchor_path.read_bytes()
        if expected_pubkey_sha256 is not None:
            actual_fingerprint = hashlib.sha256(raw_key_bytes).hexdigest().lower()
            if not hmac.compare_digest(actual_fingerprint, expected_pubkey_sha256.lower()):
                raise SecurityError(
                    f"TRUST_ANCHOR_FINGERPRINT_MISMATCH: Anchor fingerprint {actual_fingerprint} "
                    f"does not match expected fingerprint {expected_pubkey_sha256.lower()}."
                )

        try:
            loaded_key = load_pem_public_key(raw_key_bytes)
        except Exception as e:
            raise SecurityError(
                f"CORRUPT_PUBLIC_KEY: Could not load PEM public key from {anchor_path}: {e}"
            ) from e

        if not isinstance(loaded_key, Ed25519PublicKey):
            raise SecurityError(
                f"INVALID_KEY_TYPE: Loaded key from {anchor_path} is {type(loaded_key).__name__}, "
                "expected Ed25519PublicKey."
            )
        pubkey = loaded_key

    # 3. RFC 8785 Canonicalization of Payload
    try:
        canonical_bytes = canonicalize_payload(payload)
    except Exception as e:
        raise SecurityError(f"CANONICALIZATION_FAILED: Could not canonicalize payload: {e}") from e

    # 4. Cryptographic Verification
    sig_bytes = bytes.fromhex(sig_hex)
    try:
        pubkey.verify(sig_bytes, canonical_bytes)
    except InvalidSignature as e:
        raise SecurityError(
            "INVALID_TICKET_SIGNATURE: Cryptographic Ed25519 signature verification failed."
        ) from e

    return envelope


def validate_semantic_payload(
    payload: dict[str, Any],
    current_time_iso: str | None = None,
    max_validity_window_minutes: int = 120,
) -> None:
    """Validates semantic claims, field constraints, and validity window of a verified ticket payload.

    Note: Must ONLY be called on a payload that has already passed cryptographic signature verification.

    Args:
        payload: The signed payload dictionary from a verified ticket envelope.
        current_time_iso: Optional ISO 8601 UTC timestamp to validate claim against ticket window.
        max_validity_window_minutes: Maximum allowed window between issued_at_utc and expires_at_utc.

    Raises:
        SecurityError: If any semantic claim, hash format, or timestamp constraint is violated.
    """
    if not isinstance(payload, dict):
        raise SecurityError("MALFORMED_PAYLOAD: Payload must be a dictionary.")

    payload_keys = set(payload.keys())
    if payload_keys != REQUIRED_PAYLOAD_KEYS:
        extra = payload_keys - REQUIRED_PAYLOAD_KEYS
        missing = REQUIRED_PAYLOAD_KEYS - payload_keys
        if extra:
            raise SecurityError(
                f"UNRECOGNIZED_TICKET_FIELD: Unrecognized field(s) {sorted(extra)} in ticket payload."
            )
        if missing:
            raise SecurityError(
                f"MISSING_TICKET_FIELD: Missing required field(s) {sorted(missing)} in ticket payload."
            )

    # Invariant Literal Checks
    if payload["milestone"] != "V9-M4":
        raise SecurityError(
            f"INVALID_MILESTONE: Expected milestone 'V9-M4', got '{payload['milestone']}'."
        )
    if payload["gate"] != "GATE_B":
        raise SecurityError(
            f"INVALID_GATE: Expected gate 'GATE_B', got '{payload['gate']}'."
        )
    if payload["scope"] != "CONFIRMATORY_HOLDOUT_EVALUATION":
        raise SecurityError(
            f"INVALID_SCOPE: Expected scope 'CONFIRMATORY_HOLDOUT_EVALUATION', got '{payload['scope']}'."
        )
    if payload["target_output_root"] != "results/v9":
        raise SecurityError(
            f"INVALID_TARGET_OUTPUT_ROOT: Expected 'results/v9', got '{payload['target_output_root']}'."
        )

    partitions = payload["authorized_partitions"]
    if not isinstance(partitions, list) or sorted(partitions) != ["mixture", "scenario"]:
        raise SecurityError(
            f"INVALID_PARTITIONS: authorized_partitions must be ['mixture', 'scenario'], got {partitions}."
        )

    # Hash and Identifier Formats
    commit = payload["approved_commit"]
    if not isinstance(commit, str) or not RE_HEX_40.match(commit):
        raise SecurityError(
            f"INVALID_COMMIT_HASH: approved_commit must be a 40-character lowercase hex SHA-1, got '{commit}'."
        )

    hash_fields = [
        "evaluator_artifact_sha256",
        "policy_sha256",
        "mixture_manifest_sha256",
        "scenario_manifest_sha256",
        "lockfile_sha256",
        "nonce",
    ]
    for field in hash_fields:
        val = payload[field]
        if not isinstance(val, str) or not RE_HEX_64.match(val):
            raise SecurityError(
                f"INVALID_HASH_FORMAT: Field '{field}' must be a 64-character lowercase hex SHA-256, got '{val}'."
            )

    operator = payload["operator_identity"]
    if not isinstance(operator, str) or not operator.strip():
        raise SecurityError("INVALID_OPERATOR_IDENTITY: operator_identity must be a non-empty string.")

    # Timestamp & Validity Window Validation
    dt_issued = parse_iso8601_utc(payload["issued_at_utc"])
    dt_expires = parse_iso8601_utc(payload["expires_at_utc"])

    if dt_expires <= dt_issued:
        raise SecurityError(
            f"INVALID_VALIDITY_WINDOW: expires_at_utc ({payload['expires_at_utc']}) "
            f"must be strictly after issued_at_utc ({payload['issued_at_utc']})."
        )

    window_seconds = (dt_expires - dt_issued).total_seconds()
    max_seconds = max_validity_window_minutes * 60
    if window_seconds > max_seconds:
        raise SecurityError(
            f"VALIDITY_WINDOW_TOO_LONG: Validity window ({window_seconds:.0f}s) "
            f"exceeds maximum allowed {max_seconds}s ({max_validity_window_minutes} minutes)."
        )

    if current_time_iso is not None:
        dt_current = parse_iso8601_utc(current_time_iso)
        if dt_current < dt_issued:
            raise SecurityError(
                f"TICKET_NOT_YET_VALID: Current time ({current_time_iso}) precedes ticket issuance ({payload['issued_at_utc']})."
            )
        if dt_current > dt_expires:
            raise SecurityError(
                f"TICKET_EXPIRED: Current time ({current_time_iso}) exceeds ticket expiry ({payload['expires_at_utc']})."
            )
