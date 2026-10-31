#!/usr/bin/env python3
"""Read-only diagnosis of a truncated final ledger line; never repairs it."""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .development_ledger import LedgerError, inspect_bytes
else:
    from development_ledger import LedgerError, inspect_bytes


def diagnose(raw):
    if not isinstance(raw, bytes) or not raw:
        raise LedgerError("empty or invalid ledger")
    whole_hash = hashlib.sha256(raw).hexdigest()
    if raw.endswith(b"\n"):
        result = inspect_bytes(raw)
        return {"inspection": "COMPLETE_VISIBLE_BYTES", "input_sha256": whole_hash,
                "valid_prefix_bytes": len(raw), "suffix_bytes": 0,
                "prefix_state": result["state"], "prefix_counts": result["counts"],
                "prefix_event_counts": result["event_counts"], "claim_complete": False}
    last_newline = raw.rfind(b"\n")
    if last_newline < 0:
        raise LedgerError("no complete header in visible bytes")
    prefix, suffix = raw[:last_newline + 1], raw[last_newline + 1:]
    # Entire complete-line prefix must independently validate. Never skip a bad
    # complete line and never infer the status or durability of the suffix.
    result = inspect_bytes(prefix)
    return {"inspection": "TRUNCATED_FINAL_LINE", "input_sha256": whole_hash,
            "valid_prefix_bytes": len(prefix), "valid_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
            "suffix_bytes": len(suffix), "suffix_sha256": hashlib.sha256(suffix).hexdigest(),
            "prefix_state": result["state"], "prefix_counts": result["counts"],
            "prefix_event_counts": result["event_counts"], "claim_complete": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = diagnose(args.input.read_bytes())
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
