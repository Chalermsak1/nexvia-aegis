"""Tests for RFC 8785 JSON Canonicalization Scheme and Signed Gate B Ticket Verification.

Verifies RFC 8785 conformance, Ed25519 digital signature validation, public key trust anchor
fingerprinting, and semantic payload integrity according to Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import rfc8785

from nexvia_aegis.security.canonical import (
    canonicalize_payload,
    parse_strict_json,
    strict_json_pairs_hook,
)
from nexvia_aegis.security.verifier import (
    SecurityError,
    parse_iso8601_utc,
    validate_semantic_payload,
    verify_ticket_envelope,
)


@pytest.fixture
def dummy_ed25519_keypair():
    """Generates an ephemeral, dynamic Ed25519 keypair for unit testing."""
    privkey = Ed25519PrivateKey.generate()
    pubkey = privkey.public_key()
    return privkey, pubkey


@pytest.fixture
def sample_valid_payload():
    """Returns a syntactically and semantically valid Gate B ticket payload."""
    return {
        "milestone": "V9-M4",
        "gate": "GATE_B",
        "scope": "CONFIRMATORY_HOLDOUT_EVALUATION",
        "approved_commit": "c511a0bcae93ed969ffb50504017ca2be88fde95",
        "evaluator_artifact_sha256": "4b83f090b82f8d2eb929a75ff72d9a48970891d4e08f8702c89280d463b7852c",
        "policy_sha256": "5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2",
        "mixture_manifest_sha256": "70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db",
        "scenario_manifest_sha256": "55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d",
        "lockfile_sha256": "345628a865b28e9c5422fd4bc52fd6e23864bd58feaa4b418e8389192c0e7d56",
        "authorized_partitions": ["mixture", "scenario"],
        "issued_at_utc": "2026-10-26T06:00:00Z",
        "expires_at_utc": "2026-10-26T08:00:00Z",
        "nonce": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "operator_identity": "test_operator@chalermsak",
        "target_output_root": "results/v9",
    }


def make_signed_ticket(payload: dict, privkey: Ed25519PrivateKey) -> dict:
    """Helper to construct a signed ticket envelope from a payload dict."""
    canonical_bytes = canonicalize_payload(payload)
    sig_bytes = privkey.sign(canonical_bytes)
    return {
        "ticket_version": "1.0",
        "payload": payload,
        "signature_algorithm": "Ed25519",
        "signature_hex": sig_bytes.hex().lower(),
    }


# ==============================================================================
# 1. RFC 8785 Canonicalization Tests
# ==============================================================================

class TestRFC8785Canonicalization:
    def test_key_sorting_order(self):
        """Keys must be ordered lexicographically by UTF-16 / UTF-8 code points."""
        d = {"z": 1, "a": 2, "m": 3, "b": 4}
        out = canonicalize_payload(d)
        assert out == b'{"a":2,"b":4,"m":3,"z":1}'

    def test_whitespace_omission(self):
        """Zero extraneous whitespace between elements and keys."""
        d = {"alpha": [1, 2, 3], "beta": "value"}
        out = canonicalize_payload(d)
        assert out == b'{"alpha":[1,2,3],"beta":"value"}'

    def test_unescaped_forward_slashes(self):
        """RFC 8785 mandates minimal escaping: forward slashes must remain unescaped."""
        d = {"path": "results/v9/test_mix/report.json"}
        out = canonicalize_payload(d)
        assert out == b'{"path":"results/v9/test_mix/report.json"}'
        assert b"\\/" not in out

    def test_minimal_escaping_quotes_and_backslashes(self):
        """Quotes and backslashes must be escaped."""
        d = {"str": 'quote: ", backslash: \\'}
        out = canonicalize_payload(d)
        assert out == b'{"str":"quote: \\", backslash: \\\\"}'

    def test_nan_and_inf_rejected(self):
        """Non-standard float representations must raise FloatDomainError."""
        with pytest.raises(rfc8785.FloatDomainError):
            canonicalize_payload({"bad": float("nan")})
        with pytest.raises(rfc8785.FloatDomainError):
            canonicalize_payload({"bad": float("inf")})

    def test_strict_duplicate_key_rejection(self):
        """Raw JSON text containing duplicate keys must be rejected fail-closed."""
        dup_json = '{"key": "first", "other": 1, "key": "second"}'
        with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY_REJECTED"):
            parse_strict_json(dup_json)

    def test_canonical_determinism(self):
        """Identical logical payloads constructed with differing key orders must yield identical bytes."""
        d1 = {"first": 1, "second": 2, "nested": {"b": 20, "a": 10}}
        d2 = {"nested": {"a": 10, "b": 20}, "second": 2, "first": 1}
        assert canonicalize_payload(d1) == canonicalize_payload(d2)


# ==============================================================================
# 2. Cryptographic Envelope Verification Tests
# ==============================================================================

class TestEnvelopeVerification:
    def test_valid_ticket_passes_verification(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)
        raw_ticket = json.dumps(ticket)

        verified = verify_ticket_envelope(raw_ticket, public_key_obj=pubkey)
        assert verified["ticket_version"] == "1.0"
        assert verified["payload"]["milestone"] == "V9-M4"

    def test_signature_bitflip_fails(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)

        # Flip last byte in hex string
        bad_sig = list(ticket["signature_hex"])
        bad_sig[-1] = "0" if bad_sig[-1] != "0" else "1"
        ticket["signature_hex"] = "".join(bad_sig)

        with pytest.raises(SecurityError, match="INVALID_TICKET_SIGNATURE"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_payload_tampering_fails(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)

        # Alter one field in payload without resigning
        ticket["payload"]["scope"] = "TAMPERED_SCOPE"

        with pytest.raises(SecurityError, match="INVALID_TICKET_SIGNATURE"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_missing_envelope_field(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)
        del ticket["signature_algorithm"]

        with pytest.raises(SecurityError, match="MISSING_ENVELOPE_FIELD"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_unrecognized_envelope_field(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)
        ticket["extra_attacker_field"] = "malicious"

        with pytest.raises(SecurityError, match="UNRECOGNIZED_ENVELOPE_FIELD"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_unsupported_ticket_version(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)
        ticket["ticket_version"] = "2.0"

        with pytest.raises(SecurityError, match="UNSUPPORTED_TICKET_VERSION"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_unsupported_signature_algorithm(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)
        ticket["signature_algorithm"] = "RSA-SHA256"

        with pytest.raises(SecurityError, match="UNSUPPORTED_SIGNATURE_ALGORITHM"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_invalid_signature_hex_length(self, sample_valid_payload, dummy_ed25519_keypair):
        privkey, pubkey = dummy_ed25519_keypair
        ticket = make_signed_ticket(sample_valid_payload, privkey)
        ticket["signature_hex"] = "abcd"  # Not 128 chars

        with pytest.raises(SecurityError, match="INVALID_SIGNATURE_FORMAT"):
            verify_ticket_envelope(json.dumps(ticket), public_key_obj=pubkey)

    def test_public_key_anchor_file_and_fingerprint_match(
        self, sample_valid_payload, dummy_ed25519_keypair
    ):
        privkey, pubkey = dummy_ed25519_keypair
        pem_bytes = pubkey.public_bytes(
            encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
        )
        import hashlib
        expected_fp = hashlib.sha256(pem_bytes).hexdigest()

        ticket = make_signed_ticket(sample_valid_payload, privkey)

        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(pem_bytes)
            anchor_path = Path(f.name)

        try:
            verified = verify_ticket_envelope(
                json.dumps(ticket),
                pubkey_anchor_path=anchor_path,
                expected_pubkey_sha256=expected_fp,
            )
            assert verified["payload"]["milestone"] == "V9-M4"
        finally:
            anchor_path.unlink()

    def test_public_key_anchor_fingerprint_mismatch(
        self, sample_valid_payload, dummy_ed25519_keypair
    ):
        privkey, pubkey = dummy_ed25519_keypair
        pem_bytes = pubkey.public_bytes(
            encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
        )
        ticket = make_signed_ticket(sample_valid_payload, privkey)

        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(pem_bytes)
            anchor_path = Path(f.name)

        try:
            with pytest.raises(SecurityError, match="TRUST_ANCHOR_FINGERPRINT_MISMATCH"):
                verify_ticket_envelope(
                    json.dumps(ticket),
                    pubkey_anchor_path=anchor_path,
                    expected_pubkey_sha256="0" * 64,  # Incorrect fingerprint
                )
        finally:
            anchor_path.unlink()


# ==============================================================================
# 3. Semantic Payload Validation Tests
# ==============================================================================

class TestSemanticValidation:
    def test_valid_payload_passes(self, sample_valid_payload):
        validate_semantic_payload(sample_valid_payload, current_time_iso="2026-10-26T07:00:00Z")

    def test_unrecognized_payload_field_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["extra_field"] = "not_allowed"
        with pytest.raises(SecurityError, match="UNRECOGNIZED_TICKET_FIELD"):
            validate_semantic_payload(bad)

    def test_missing_payload_field_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        del bad["nonce"]
        with pytest.raises(SecurityError, match="MISSING_TICKET_FIELD"):
            validate_semantic_payload(bad)

    def test_invalid_milestone_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["milestone"] = "V10-M1"
        with pytest.raises(SecurityError, match="INVALID_MILESTONE"):
            validate_semantic_payload(bad)

    def test_invalid_gate_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["gate"] = "GATE_C"
        with pytest.raises(SecurityError, match="INVALID_GATE"):
            validate_semantic_payload(bad)

    def test_invalid_scope_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["scope"] = "DEV_DEBUG"
        with pytest.raises(SecurityError, match="INVALID_SCOPE"):
            validate_semantic_payload(bad)

    def test_invalid_target_output_root(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["target_output_root"] = "/tmp/spoofed"
        with pytest.raises(SecurityError, match="INVALID_TARGET_OUTPUT_ROOT"):
            validate_semantic_payload(bad)

    def test_invalid_partitions_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["authorized_partitions"] = ["mixture"]  # Missing scenario
        with pytest.raises(SecurityError, match="INVALID_PARTITIONS"):
            validate_semantic_payload(bad)

    def test_malformed_commit_sha1(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["approved_commit"] = "c511a0b"  # Short SHA
        with pytest.raises(SecurityError, match="INVALID_COMMIT_HASH"):
            validate_semantic_payload(bad)

    def test_malformed_artifact_sha256(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["policy_sha256"] = "NOT_A_VALID_HEX_64_CHARS"
        with pytest.raises(SecurityError, match="INVALID_HASH_FORMAT"):
            validate_semantic_payload(bad)

    def test_empty_operator_identity_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["operator_identity"] = "   "
        with pytest.raises(SecurityError, match="INVALID_OPERATOR_IDENTITY"):
            validate_semantic_payload(bad)

    def test_inverted_validity_window(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["issued_at_utc"] = "2026-10-26T09:00:00Z"
        bad["expires_at_utc"] = "2026-10-26T08:00:00Z"
        with pytest.raises(SecurityError, match="INVALID_VALIDITY_WINDOW"):
            validate_semantic_payload(bad)

    def test_validity_window_too_long(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["issued_at_utc"] = "2026-10-26T06:00:00Z"
        bad["expires_at_utc"] = "2026-10-26T09:00:00Z"  # 180 minutes > 120 minutes
        with pytest.raises(SecurityError, match="VALIDITY_WINDOW_TOO_LONG"):
            validate_semantic_payload(bad, max_validity_window_minutes=120)

    def test_ticket_not_yet_valid_at_check_time(self, sample_valid_payload):
        with pytest.raises(SecurityError, match="TICKET_NOT_YET_VALID"):
            validate_semantic_payload(sample_valid_payload, current_time_iso="2026-10-26T05:59:59Z")

    def test_ticket_expired_at_check_time(self, sample_valid_payload):
        with pytest.raises(SecurityError, match="TICKET_EXPIRED"):
            validate_semantic_payload(sample_valid_payload, current_time_iso="2026-10-26T08:00:01Z")

    def test_non_utc_timestamp_rejected(self, sample_valid_payload):
        bad = dict(sample_valid_payload)
        bad["issued_at_utc"] = "2026-10-26T06:00:00+07:00"
        with pytest.raises(SecurityError, match="INVALID_TIMEZONE"):
            validate_semantic_payload(bad)
