#!/usr/bin/env python3
"""NEXVIA AEGIS Release Manifesto Generator.

Computes the 6 authoritative artifact hashes and git commit binding required for
the signed Gate B authorization ticket under Contract AEGIS-V9-M4-CTR-01.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

LOCKED_POLICY_SHA256 = "5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2"
LOCKED_MIXTURE_MANIFEST_SHA256 = "70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db"
LOCKED_SCENARIO_MANIFEST_SHA256 = "55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d"


def sha256_file(path: Path) -> str:
    """Computes the raw SHA-256 lowercase hexadecimal digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def get_git_commit(repo_root: Path) -> str:
    """Retrieves the current 40-character lowercase hexadecimal commit SHA-1."""
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    commit = res.stdout.strip().lower()
    if len(commit) != 40:
        raise ValueError(f"Invalid git commit SHA-1: '{commit}'")
    return commit


def generate_manifesto(
    repo_root: Path | None = None,
    evaluator_path: Path | None = None,
    policy_path: Path | None = None,
    mixture_manifest_path: Path | None = None,
    scenario_manifest_path: Path | None = None,
    lockfile_path: Path | None = None,
) -> dict[str, str]:
    """Generates the release manifesto containing all 6 authoritative binding hashes.

    Validates that locked policy and manifest digests match exact contractual invariants.
    """
    root = (repo_root or _REPO_ROOT).resolve()

    eval_p = evaluator_path or (root / "experiments" / "v9_evaluate_holdout.py")
    pol_p = policy_path or (root / "results" / "v9" / "cal_r2" / "selected_policy.json")
    mix_p = mixture_manifest_path or (root / "results" / "v9" / "manifests" / "test_mix_manifest_r1.json")
    scen_p = scenario_manifest_path or (root / "results" / "v9" / "manifests" / "test_scen_manifest_r1.json")
    lock_p = lockfile_path or (root / "uv.lock")

    for p in (eval_p, pol_p, mix_p, scen_p, lock_p):
        if not p.exists():
            raise FileNotFoundError(f"Required artifact not found: {p}")

    commit = get_git_commit(root)
    eval_sha = sha256_file(eval_p)
    pol_sha = sha256_file(pol_p)
    mix_sha = sha256_file(mix_p)
    scen_sha = sha256_file(scen_p)
    lock_sha = sha256_file(lock_p)

    if pol_sha != LOCKED_POLICY_SHA256:
        raise ValueError(
            f"LOCKED_POLICY_MISMATCH: Computed {pol_sha} != expected {LOCKED_POLICY_SHA256}"
        )
    if mix_sha != LOCKED_MIXTURE_MANIFEST_SHA256:
        raise ValueError(
            f"LOCKED_MIXTURE_MANIFEST_MISMATCH: Computed {mix_sha} != expected {LOCKED_MIXTURE_MANIFEST_SHA256}"
        )
    if scen_sha != LOCKED_SCENARIO_MANIFEST_SHA256:
        raise ValueError(
            f"LOCKED_SCENARIO_MANIFEST_MISMATCH: Computed {scen_sha} != expected {LOCKED_SCENARIO_MANIFEST_SHA256}"
        )

    return {
        "approved_commit": commit,
        "evaluator_artifact_sha256": eval_sha,
        "policy_sha256": pol_sha,
        "mixture_manifest_sha256": mix_sha,
        "scenario_manifest_sha256": scen_sha,
        "lockfile_sha256": lock_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generates release manifesto binding hashes for Gate B authorization."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional destination path for release_manifesto.json",
    )
    args = parser.parse_args()

    try:
        manifesto = generate_manifesto()
        dumped = json.dumps(manifesto, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(dumped + "\n", encoding="utf-8")
            print(f"[MANIFESTO] Successfully generated release manifesto: {args.output}")
        else:
            print(dumped)
        return 0
    except Exception as e:
        print(f"[MANIFESTO ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
