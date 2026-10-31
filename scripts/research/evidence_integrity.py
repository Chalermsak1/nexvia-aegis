"""Checks for self-reported source metadata, not independent attestation."""
import re


def validate_source_maps(before, after):
    if not isinstance(before, dict) or not before or not isinstance(after, dict) or before != after:
        raise ValueError("missing or inconsistent source hashes")
    for path, digest in before.items():
        if not isinstance(path, str) or not path or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("invalid source hash metadata")


def validate_source_metadata(data):
    if data.get("classification") != "EXPLORATORY_SIMULATION" or data.get("sources_unchanged") is not True:
        raise ValueError("invalid experimental identity")
    validate_source_maps(data.get("source_sha256_before"), data.get("source_sha256_after"))
