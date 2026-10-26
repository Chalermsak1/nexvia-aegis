"""RFC 8785 JSON Canonicalization Scheme (JCS) and strict parsing primitives.

Provides deterministic canonical serialization and strict duplicate-key rejection
compliant with RFC 8785 and Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import json
from typing import Any

import rfc8785


def strict_json_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Rejects JSON objects containing duplicate keys before dictionary instantiation.

    Args:
        pairs: List of key-value pairs parsed from a JSON object.

    Returns:
        Dictionary containing unique key-value pairs.

    Raises:
        ValueError: If duplicate keys are encountered in the same JSON object.
    """
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(
                f"DUPLICATE_JSON_KEY_REJECTED: Key '{key}' appears multiple times in JSON object."
            )
        seen.add(key)
        result[key] = value
    return result


def parse_strict_json(raw_json: str | bytes) -> Any:
    """Parses JSON text with strict duplicate-key rejection fail-closed.

    Args:
        raw_json: String or UTF-8 encoded bytes representing JSON text.

    Returns:
        Parsed JSON data structure.

    Raises:
        ValueError: If JSON is malformed or contains duplicate keys.
    """
    if isinstance(raw_json, bytes):
        raw_json = raw_json.decode("utf-8")
    return json.loads(raw_json, object_pairs_hook=strict_json_pairs_hook)


def canonicalize_payload(payload: dict[str, Any]) -> bytes:
    """Canonicalizes a JSON dictionary into deterministic UTF-8 bytes per RFC 8785.

    Ensures:
      - Lexicographical sorting of object keys.
      - Minimal escaping (slashes remain unescaped; only quote, backslash, control chars escaped).
      - Rejection of non-standard numeric values (NaN, Infinity).
      - Zero arbitrary whitespace.

    Args:
        payload: Python dictionary representing the payload to canonicalize.

    Returns:
        Deterministic RFC 8785 canonical UTF-8 bytes.

    Raises:
        TypeError, ValueError, rfc8785.CanonicalizationError: If payload cannot be canonicalized.
    """
    if not isinstance(payload, dict):
        raise TypeError(f"Payload must be a dictionary, got {type(payload).__name__}.")
    return rfc8785.dumps(payload)
