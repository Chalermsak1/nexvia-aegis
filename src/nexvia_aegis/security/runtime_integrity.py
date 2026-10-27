"""Read-only, isolated pre-claim verification of a locked Python environment.

Installed RECORD hashes detect accidental drift. They are not substitutes for
independently authenticated wheel archives or an owner-controlled machine.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib
from typing import Any

from nexvia_aegis.security.ledger import SecurityError


_MARKER = re.compile(r"^(sys_platform|implementation_name|platform_python_implementation)\s*(==|!=)\s*'([^']+)'$")
_MODULES = ("cryptography", "gymnasium", "matplotlib", "mujoco", "numpy", "rfc8785", "scipy")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _marker_true(marker: str | None) -> bool:
    if marker is None:
        return True
    match = _MARKER.fullmatch(marker)
    if match is None:
        raise SecurityError(f"UNSUPPORTED_LOCK_MARKER: Cannot safely resolve '{marker}'.")
    actual = {
        "sys_platform": sys.platform,
        "implementation_name": sys.implementation.name,
        "platform_python_implementation": platform.python_implementation(),
    }[match.group(1)]
    expected = match.group(3)
    return (actual == expected) if match.group(2) == "==" else (actual != expected)


def _locked_packages(lock_path: Path, include_dev: bool) -> dict[str, str]:
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SecurityError(f"INVALID_RUNTIME_LOCKFILE: Cannot parse uv.lock: {exc}") from exc
    by_name = {_normalize(p["name"]): p for p in lock.get("package", [])}
    root = by_name.get("nexvia-aegis")
    if root is None or len(by_name) != len(lock.get("package", [])):
        raise SecurityError("INVALID_RUNTIME_LOCKFILE: Missing project or duplicate package name.")
    selected: dict[str, str] = {}
    pending: list[tuple[str, tuple[str, ...]]] = [("nexvia-aegis", ())]
    visited: set[tuple[str, tuple[str, ...]]] = set()
    while pending:
        name, extras = pending.pop()
        key = (_normalize(name), extras)
        if key in visited:
            continue
        visited.add(key)
        package = by_name.get(key[0])
        if package is None:
            raise SecurityError(f"INVALID_RUNTIME_LOCKFILE: Dependency '{name}' is absent.")
        selected[key[0]] = str(package["version"])
        deps = list(package.get("dependencies", []))
        for extra in extras:
            if extra not in package.get("optional-dependencies", {}):
                raise SecurityError(f"INVALID_RUNTIME_LOCKFILE: Extra '{extra}' is absent for '{name}'.")
            deps.extend(package["optional-dependencies"][extra])
        if name == "nexvia-aegis" and include_dev:
            deps.extend(package.get("dev-dependencies", {}).get("dev", []))
        for dep in deps:
            if _marker_true(dep.get("marker")):
                pending.append((dep["name"], tuple(sorted(dep.get("extra", [])))))
    return selected


_PROBE = r'''
import base64
import hashlib
from importlib import metadata, util
import json
from pathlib import Path
import site
import sys
import sysconfig

config = json.loads(sys.stdin.read())
venv = Path(config["venv"]).resolve()
execution = Path(config["execution"]).resolve()
site_path = Path(sysconfig.get_paths()["purelib"]).resolve()
before = [str(Path(item).resolve()) for item in sys.path if item]
sys.path.insert(0, str(execution))
sys.path.insert(0, str(execution / "src"))
packages = {}
for dist in metadata.distributions(path=[str(site_path)]):
    name = "-".join(filter(None, __import__("re").split(r"[-_.]+", dist.metadata["Name"].lower())))
    if name in packages:
        raise RuntimeError("DUPLICATE_INSTALLED_DISTRIBUTION: " + name)
    files = dist.files
    if files is None:
        raise RuntimeError("DISTRIBUTION_WITHOUT_RECORD: " + name)
    hashes = []
    for item in files:
        candidate = Path(dist.locate_file(item)).resolve()
        if not candidate.is_relative_to(venv):
            raise RuntimeError("DISTRIBUTION_PATH_ESCAPE: " + name)
        if not candidate.is_file():
            raise RuntimeError("DISTRIBUTION_FILE_MISSING: " + name + ":" + str(item))
        if item.hash is not None:
            if item.hash.mode != "sha256":
                raise RuntimeError("UNSUPPORTED_RECORD_HASH: " + name)
            digest = hashlib.sha256(candidate.read_bytes()).digest()
            expected = base64.urlsafe_b64decode(item.hash.value + "=" * (-len(item.hash.value) % 4))
            if digest != expected:
                raise RuntimeError("DISTRIBUTION_RECORD_MISMATCH: " + name + ":" + str(item))
            hashes.append(str(item) + ":" + digest.hex())
    if not hashes:
        raise RuntimeError("DISTRIBUTION_WITHOUT_HASHED_FILES: " + name)
    packages[name] = {
        "version": dist.version,
        "record_file_count": len(hashes),
        "record_digest": hashlib.sha256("\n".join(sorted(hashes)).encode()).hexdigest(),
    }
origins = {}
for name in config["modules"] + ["aegis", "nexvia_aegis"]:
    spec = util.find_spec(name)
    origins[name] = str(Path(spec.origin).resolve()) if spec and spec.origin else None
print(json.dumps({
    "executable": str(Path(sys.executable).absolute()),
    "prefix": str(Path(sys.prefix).resolve()),
    "base_prefix": str(Path(sys.base_prefix).resolve()),
    "python_version": ".".join(str(v) for v in sys.version_info[:3]),
    "isolated": bool(sys.flags.isolated),
    "user_site_enabled": site.ENABLE_USER_SITE,
    "site_packages": str(site_path),
    "sys_path_before_project_insertion": before,
    "packages": packages,
    "import_origins": origins,
}, sort_keys=True))
'''


def verify_runtime_integrity(
    python_executable: Path | str,
    repo_or_worktree_dir: Path | str,
    expected_lockfile_sha256: str,
    expected_python_version: str | None = None,
    *,
    approved_venv_root: Path | str | None = None,
    include_dev: bool = True,
    synthetic_legacy_check: bool = False,
) -> dict[str, Any]:
    """Verify the actual worker interpreter and installed lock closure before claim.

    synthetic_legacy_check exists only for old isolated fixture repositories that
    intentionally have no environment; the production launcher never enables it.
    """
    execution = Path(repo_or_worktree_dir).resolve()
    py = Path(os.path.abspath(str(python_executable)))
    lock_path = execution / "uv.lock"
    if not py.exists() or not lock_path.is_file():
        raise SecurityError("RUNTIME_INTEGRITY_MISMATCH: Interpreter or uv.lock is missing.")
    actual_lock = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if actual_lock != expected_lockfile_sha256.lower():
        raise SecurityError("RUNTIME_INTEGRITY_MISMATCH: uv.lock SHA-256 mismatch.")
    version = expected_python_version or f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if synthetic_legacy_check:
        result = subprocess.run([str(py), "-I", "-c", "import sys;print('.'.join(map(str,sys.version_info[:3])))"],
                                capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0 or result.stdout.strip() != version:
            raise SecurityError("RUNTIME_INTEGRITY_MISMATCH: Synthetic interpreter version mismatch.")
        return {"profile": "SYNTHETIC_LEGACY_CHECK", "lockfile_sha256": actual_lock, "python_version": version}

    if approved_venv_root is None:
        raise SecurityError("RUNTIME_VENV_REQUIRED: An approved virtual environment path is required.")
    venv = Path(approved_venv_root).resolve()
    expected_py = Path(os.path.abspath(str(Path(approved_venv_root) / "bin" / "python")))
    if py != expected_py or not (venv / "pyvenv.cfg").is_file():
        raise SecurityError("RUNTIME_INTERPRETER_LOCATION_MISMATCH: Worker must use the approved .venv/bin/python.")
    expected_packages = _locked_packages(lock_path, include_dev=include_dev)
    config = {"venv": str(venv), "execution": str(execution), "modules": list(_MODULES)}
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP", "PYTHONINSPECT"}}
    env["PYTHONNOUSERSITE"] = "1"
    try:
        result = subprocess.run([str(py), "-I", "-c", _PROBE], input=json.dumps(config),
                                capture_output=True, text=True, env=env, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SecurityError(f"RUNTIME_PROBE_FAILED: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise SecurityError(f"RUNTIME_PROBE_FAILED: {result.stderr.strip()[-500:]}")
    try:
        observed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SecurityError("RUNTIME_PROBE_FAILED: Probe did not return JSON.") from exc
    if observed["python_version"] != version or not observed["isolated"] or observed["user_site_enabled"] is not False:
        raise SecurityError("RUNTIME_ISOLATION_MISMATCH: Python version or isolated mode differs.")
    if Path(observed["prefix"]) != venv or Path(observed["base_prefix"]) == venv:
        raise SecurityError("RUNTIME_ISOLATION_MISMATCH: Interpreter is not running from the approved venv.")
    site_dir = Path(observed["site_packages"])
    if not site_dir.is_relative_to(venv):
        raise SecurityError("RUNTIME_SITE_PATH_MISMATCH: site-packages is outside the approved venv.")
    # A locked editable install may add this checkout's src directory through
    # a .pth file. Accept only the exact execution checkout, never another one.
    allowed = [venv, Path(observed["base_prefix"]), execution, execution / "src"]
    for entry in observed["sys_path_before_project_insertion"]:
        path = Path(entry)
        if not any(path.is_relative_to(root) for root in allowed):
            raise SecurityError(f"RUNTIME_IMPORT_PATH_ESCAPE: Unexpected interpreter path '{path}'.")
    installed = {name: entry["version"] for name, entry in observed["packages"].items()}
    if installed != expected_packages:
        missing = sorted(expected_packages.keys() - installed.keys())
        extra = sorted(installed.keys() - expected_packages.keys())
        mismatched = sorted(name for name in expected_packages.keys() & installed.keys()
                            if expected_packages[name] != installed[name])
        raise SecurityError(f"RUNTIME_DEPENDENCY_MISMATCH: missing={missing}, extra={extra}, wrong_version={mismatched}.")
    origins = observed["import_origins"]
    for module in _MODULES:
        origin = origins.get(module)
        if origin is None or not Path(origin).is_relative_to(site_dir):
            raise SecurityError(f"RUNTIME_IMPORT_ORIGIN_MISMATCH: '{module}' did not resolve inside the approved venv.")
    for module, root in (("aegis", execution), ("nexvia_aegis", execution / "src")):
        origin = origins.get(module)
        if origin is None or not Path(origin).is_relative_to(root):
            raise SecurityError(f"RUNTIME_IMPORT_ORIGIN_MISMATCH: '{module}' did not resolve in the execution checkout.")
    return {
        "schema_version": "nexvia-aegis-runtime-integrity/1.0",
        "verification": "LOCK_CLOSURE_VERSIONS_IMPORT_ORIGINS_AND_INSTALLED_RECORDS",
        "wheel_archive_sha256_verified": False,
        "lockfile_sha256": actual_lock,
        "python_version": version,
        "interpreter": observed["executable"],
        "virtual_environment": str(venv),
        "execution_checkout": str(execution),
        "site_packages": str(site_dir),
        "installed_packages": observed["packages"],
        "import_origins": origins,
        "package_count": len(installed),
    }
