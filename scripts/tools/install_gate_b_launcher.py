#!/usr/bin/env python3
"""NEXVIA AEGIS Launcher Installation & Verification Utility.

Installs the trusted supervisory launcher outside the agent-writable workspace
(default destination: ~/.nexvia_security/bin/launch_gate_b_production.py)
and computes the authoritative SHA-256 fingerprint for owner offline pinning.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from nexvia_aegis.security.ledger import resolve_security_dir


def install_launcher(
    security_dir: Path | str | None = None,
    destination_file: Path | str | None = None,
) -> tuple[Path, str]:
    """Installs the launcher script to an out-of-workspace location with strict permissions.

    Returns:
        Tuple of (installed_path, sha256_fingerprint).
    """
    source_file = _REPO_ROOT / "src" / "nexvia_aegis" / "security" / "launcher.py"
    if not source_file.exists():
        raise FileNotFoundError(f"Source launcher file '{source_file}' does not exist.")

    if destination_file is not None:
        dest = Path(destination_file).expanduser().resolve()
    else:
        sec_dir = resolve_security_dir(security_dir)
        bin_dir = sec_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(bin_dir, stat.S_IRWXU)  # 0700
        dest = bin_dir / "launch_gate_b_production.py"

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Read and copy
    raw_content = source_file.read_bytes()
    dest.write_bytes(raw_content)

    # Set strict permissions: read and execute for owner only (0500 or 0700)
    os.chmod(dest, stat.S_IRWXU)

    # Compute SHA-256 fingerprint
    fingerprint = hashlib.sha256(raw_content).hexdigest().lower()

    return dest, fingerprint


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Installs NEXVIA AEGIS Gate B Trusted Launcher to external directory."
    )
    parser.add_argument(
        "--security-dir",
        type=str,
        default=None,
        help="Target security directory (defaults to ~/.nexvia_security).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Explicit destination file path for launcher script.",
    )
    args = parser.parse_args()

    try:
        dest_path, fp = install_launcher(security_dir=args.security_dir, destination_file=args.dest)
        print(f"[INSTALL] Successfully installed Trusted Launcher to: {dest_path}")
        print(f"[INSTALL] Permissions: 0700 (Owner read, write, execute only)")
        print(f"[INSTALL] Launcher SHA-256 Fingerprint: {fp}")
        print("[INSTALL] The owner must record this fingerprint in the offline decision log.")
        return 0
    except Exception as e:
        print(f"[INSTALL ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
