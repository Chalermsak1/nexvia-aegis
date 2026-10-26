#!/usr/bin/env python3
"""NEXVIA AEGIS Gate B Replay Ledger Bootstrap Utility.

Performs strict, one-time owner-controlled initialization of the external security
directory (~/.nexvia_security/), stable lock file, and replay ledger.
Enforces anti-reinitialization invariants per Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is on sys.path for direct script execution
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from nexvia_aegis.security.ledger import (
    LOCK_FILE_NAME,
    LEDGER_FILE_NAME,
    SecurityError,
    bootstrap_security_directory,
    resolve_security_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time owner bootstrap utility for NEXVIA AEGIS Gate B Replay Ledger."
    )
    parser.add_argument(
        "--security-dir",
        type=str,
        default=None,
        help="Target security directory (defaults to ~/.nexvia_security).",
    )
    args = parser.parse_args()

    try:
        target_dir = resolve_security_dir(args.security_dir)
        print(f"[BOOTSTRAP] Initializing security directory: {target_dir}")
        lock_path, ledger_path = bootstrap_security_directory(target_dir)
        print(f"[BOOTSTRAP] Successfully initialized stable lock file: {lock_path} (mode 0600)")
        print(f"[BOOTSTRAP] Successfully initialized persistent ledger:   {ledger_path} (mode 0600)")
        print("[BOOTSTRAP] Status: INITIALIZATION_SUCCESSFUL")
        return 0
    except SecurityError as e:
        print(f"[BOOTSTRAP ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[BOOTSTRAP UNEXPECTED ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
