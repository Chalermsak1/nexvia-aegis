#!/usr/bin/env python3
"""NEXVIA AEGIS Launcher Execution Helper Script.

Provides a CLI entry point for running the trusted supervisory launcher.
"""

from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from nexvia_aegis.security.launcher import main

if __name__ == "__main__":
    sys.exit(main())
