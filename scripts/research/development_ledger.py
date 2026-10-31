"""Append-only, single-writer ledger for exploratory development assignments.

This is NOT an authorization, release, confirmatory, or safety-evidence system.
No operation resumes, truncates, repairs, or reruns an existing ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA = "nexvia-development-ledger/1"
EVENT_SCHEMA = "nexvia-development-ledger/2"
ZERO_HASH = "0" * 64


class LedgerError(ValueError):
    """Invalid ledger, transition, or caller input."""


class LedgerWriteError(OSError):
    """A write or durability operation failed; writer cannot be reused."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError("duplicate JSON key")
        result[key] = value
    return result


def _validate_json(value: Any) -> None:
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        for item in value.values():
            _validate_json(item)
        return
    raise LedgerError("values must be JSON objects with string keys")


def _encode(value: Any) -> bytes:
    _validate_json(value)
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError) as exc:
        raise LedgerError("value is not valid finite JSON") from exc


def _entry(index: int, previous: str, payload: dict) -> dict:
    body = {"index": index, "previous_sha256": previous, "payload": payload}
    return {**body, "sha256": hashlib.sha256(_encode(body)).hexdigest()}


def _assignment_ids(assignments: Any) -> list[str]:
    if not isinstance(assignments, list) or not assignments:
        raise LedgerError("a nonempty assignment list is required")
    ids = []
    for item in assignments:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise LedgerError("each assignment needs a nonempty string id")
        ids.append(item["id"])
    if len(set(ids)) != len(ids):
        raise LedgerError("duplicate assignment id")
    _encode(assignments)
    return ids


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DevelopmentLedger:
    """New-file-only writer; one thread owns the writer until close.

    Call start() and await its return before doing work; complete() records a
    terminal COMPLETED or ERROR result. Failed writes poison this writer.
    """

    def __init__(self, path: Path, fd: int, assignments: list[dict], study: str, record_events: bool):
        self.path = path
        self._fd = fd
        self._states = {k: "ASSIGNED" for k in _assignment_ids(assignments)}
        self._event_counts = {k: 0 for k in self._states}
        self._record_events = record_events
        self._last_hash = ZERO_HASH
        self._index = 0
        self._poisoned = False
        self._closed = False
        self._finalized = False
        self._append({"kind": "HEADER", "schema": EVENT_SCHEMA if record_events else SCHEMA, "classification": "EXPLORATORY_SIMULATION",
                      "study": study, "assignments": assignments})

    @classmethod
    def create(cls, path: str | Path, *, study: str, assignments: list[dict], record_events: bool = False) -> "DevelopmentLedger":
        path = Path(path)
        if not isinstance(study, str) or not study.strip():
            raise LedgerError("study must be a nonempty string")
        if type(record_events) is not bool:
            raise LedgerError("record_events must be boolean")
        _assignment_ids(assignments)
        _encode(study)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            _fsync_directory(path.parent)
            return cls(path, fd, assignments, study, record_events)
        except BaseException:
            os.close(fd)
            # Evidence stays at the unique path, even if initialization failed.
            raise

    def _append(self, payload: dict) -> None:
        if self._closed or self._poisoned or self._finalized:
            raise LedgerError("writer is closed, failed, or finalized")
        entry = _entry(self._index, self._last_hash, payload)
        encoded = _encode(entry) + b"\n"
        try:
            remaining = memoryview(encoded)
            while remaining:
                written = os.write(self._fd, remaining)
                if written <= 0:
                    raise OSError("write made no progress")
                remaining = remaining[written:]
            os.fsync(self._fd)
        except OSError as exc:
            self._poisoned = True
            raise LedgerWriteError("ledger write or fsync failed; inspect and preserve file") from exc
        self._last_hash = entry["sha256"]
        self._index += 1

    def start(self, assignment_id: str) -> None:
        if not isinstance(assignment_id, str) or self._states.get(assignment_id) != "ASSIGNED":
            raise LedgerError("assignment is missing or already started")
        self._append({"kind": "START", "id": assignment_id})
        self._states[assignment_id] = "STARTED"

    def complete(self, assignment_id: str, *, status: str, details: dict) -> None:
        if not isinstance(assignment_id, str) or self._states.get(assignment_id) != "STARTED":
            raise LedgerError("assignment is not started or is already terminal")
        if status not in ("COMPLETED", "ERROR") or not isinstance(details, dict):
            raise LedgerError("status must be COMPLETED or ERROR and details must be an object")
        self._append({"kind": "TERMINAL", "id": assignment_id, "status": status, "details": details})
        self._states[assignment_id] = status

    def event(self, assignment_id: str, *, details: dict) -> None:
        """Append one ordered, fsynced event for a started v2 assignment."""
        if not self._record_events or not isinstance(assignment_id, str) or self._states.get(assignment_id) != "STARTED":
            raise LedgerError("events require a started v2 assignment")
        if not isinstance(details, dict):
            raise LedgerError("event details must be an object")
        self._append({"kind": "EVENT", "id": assignment_id, "event_index": self._event_counts[assignment_id], "details": details})
        self._event_counts[assignment_id] += 1

    def finalize(self) -> None:
        if any(state in ("ASSIGNED", "STARTED") for state in self._states.values()):
            raise LedgerError("cannot finalize with unfinished assignments")
        errors = sum(state == "ERROR" for state in self._states.values())
        self._append({"kind": "FINAL", "assignments": len(self._states), "errors": errors})
        self._finalized = True

    def close(self) -> None:
        if not self._closed:
            os.close(self._fd)
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def inspect(path: str | Path) -> dict:
    """Validate the entire visible log; incomplete work remains explicit.

    Corrupt or truncated records raise LedgerError and are never ignored.
    This cannot prove an fsync succeeded or that a hash chain is authentic.
    """
    return inspect_bytes(Path(path).read_bytes())


def inspect_bytes(raw: bytes) -> dict:
    """Validate a supplied complete byte sequence without touching a file."""
    if not isinstance(raw, bytes):
        raise LedgerError("ledger content must be bytes")
    if not raw or not raw.endswith(b"\n"):
        raise LedgerError("empty or truncated ledger")
    previous = ZERO_HASH
    states: dict[str, str] | None = None
    event_counts: dict[str, int] = {}
    schema = None
    finalized = False
    records = []
    for index, line in enumerate(raw[:-1].split(b"\n")):
        try:
            obj = json.loads(line, object_pairs_hook=_unique_object, parse_constant=lambda _: (_ for _ in ()).throw(LedgerError("nonfinite value")))
        except (ValueError, UnicodeDecodeError) as exc:
            raise LedgerError("invalid JSON record") from exc
        if not isinstance(obj, dict) or set(obj) != {"index", "previous_sha256", "payload", "sha256"}:
            raise LedgerError("invalid record envelope")
        if type(obj["index"]) is not int or obj["index"] != index or obj["previous_sha256"] != previous:
            raise LedgerError("invalid record ordering or chain")
        payload = obj["payload"]
        if not isinstance(payload, dict) or obj != _entry(index, previous, payload) or line != _encode(obj):
            raise LedgerError("invalid record hash or noncanonical encoding")
        previous = obj["sha256"]
        if finalized:
            raise LedgerError("record after finalization")
        kind = payload.get("kind")
        if index == 0:
            if set(payload) != {"kind", "schema", "classification", "study", "assignments"} or kind != "HEADER" or payload["schema"] not in (SCHEMA, EVENT_SCHEMA) or payload["classification"] != "EXPLORATORY_SIMULATION" or not isinstance(payload["study"], str) or not payload["study"].strip():
                raise LedgerError("invalid header")
            states = {k: "ASSIGNED" for k in _assignment_ids(payload["assignments"])}
            event_counts = {k: 0 for k in states}
            schema = payload["schema"]
        elif states is None:
            raise LedgerError("missing header")
        elif kind == "START":
            if set(payload) != {"kind", "id"} or not isinstance(payload["id"], str) or states.get(payload["id"]) != "ASSIGNED":
                raise LedgerError("invalid or duplicate start")
            states[payload["id"]] = "STARTED"
        elif kind == "EVENT":
            if (schema != EVENT_SCHEMA or set(payload) != {"kind", "id", "event_index", "details"}
                    or not isinstance(payload["id"], str) or states.get(payload["id"]) != "STARTED"
                    or type(payload["event_index"]) is not int or payload["event_index"] != event_counts[payload["id"]]
                    or not isinstance(payload["details"], dict)):
                raise LedgerError("invalid or duplicate event")
            event_counts[payload["id"]] += 1
        elif kind == "TERMINAL":
            if set(payload) != {"kind", "id", "status", "details"} or not isinstance(payload["id"], str) or states.get(payload["id"]) != "STARTED" or payload["status"] not in ("COMPLETED", "ERROR") or not isinstance(payload["details"], dict):
                raise LedgerError("invalid or duplicate terminal")
            states[payload["id"]] = payload["status"]
        elif kind == "FINAL":
            errors = sum(s == "ERROR" for s in states.values())
            if set(payload) != {"kind", "assignments", "errors"} or type(payload["assignments"]) is not int or type(payload["errors"]) is not int or payload["assignments"] != len(states) or payload["errors"] != errors or any(s in ("ASSIGNED", "STARTED") for s in states.values()):
                raise LedgerError("invalid or premature finalization")
            finalized = True
        else:
            raise LedgerError("unknown record type")
        records.append(payload)
    if states is None:
        raise LedgerError("missing header")
    counts = {s: sum(v == s for v in states.values()) for s in ("ASSIGNED", "STARTED", "COMPLETED", "ERROR")}
    return {"integrity": "VALID_SELF_REPORTED_CHAIN", "finalized": finalized,
            "state": ("INCOMPLETE" if not finalized else ("FINALIZED_WITH_ERRORS" if counts["ERROR"] else "FINALIZED")),
            "counts": counts, "assignments": states, "event_counts": event_counts, "schema": schema,
            "last_sha256": previous, "records": records}
