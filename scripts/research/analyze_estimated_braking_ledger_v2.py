#!/usr/bin/env python3
"""Validate and summarize exploratory estimated-state braking records."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import itertools

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.development_ledger import inspect
from scripts.research.evidence_integrity import validate_source_maps


def analyze(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    ledger = inspect(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("ledger changed during inspection")
    header = ledger["records"][0]
    if header["study"] != "V9-M5 exploratory estimated braking v2":
        raise ValueError("unexpected study")
    assignments, groups, scientific_keys, case_configs = {}, {}, set(), {}
    for a in header["assignments"]:
        key = (a["case"]["name"], a["seed"], a["arm"])
        if key[0] in case_configs and case_configs[key[0]] != a["case"]:
            raise ValueError("inconsistent configuration for case")
        case_configs[key[0]] = a["case"]
        if key in scientific_keys or a["arm"] not in ("ORACLE_STATE_CBF_BRAKE", "ESTIMATED_STATE_CBF_BRAKE"):
            raise ValueError("duplicate or unsupported assignment")
        scientific_keys.add(key)
        assignments[a["id"]] = a
        g = groups.setdefault((key[0], key[2]), {"assigned": 0, "completed": 0, "errors": 0, "incomplete": 0,
            "no_command": 0, "steps_applied": 0, "positive_force_dot_steps": 0, "episodes_with_safety_violation": 0,
            "cbf_residual_missing_steps": 0, "cbf_residual_violation_steps": 0, "final_speeds": []})
        g["assigned"] += 1
    seeds = {a["seed"] for a in assignments.values()}
    expected = set(itertools.product(case_configs, seeds, ("ORACLE_STATE_CBF_BRAKE", "ESTIMATED_STATE_CBF_BRAKE")))
    if scientific_keys != expected:
        raise ValueError("assignment grid is incomplete or unpaired")
    terminals = {r["id"]: r for r in ledger["records"] if r["kind"] == "TERMINAL"}
    for identifier, a in assignments.items():
        group = groups[(a["case"]["name"], a["arm"])]
        record = terminals.get(identifier)
        if record is None:
            group["incomplete"] += 1
            continue
        if record["status"] == "ERROR":
            group["errors"] += 1
            continue
        detail = record["details"]
        validate_source_maps(a.get("source_sha256"), detail.get("source_sha256_after"))
        row = detail["episode"]
        if row["controller"] != a["arm"] or row["seed"] != a["seed"] or row["case"] != a["case"]["name"]:
            raise ValueError("episode identity mismatch")
        if type(row["no_command"]) is not bool or not isinstance(row["events"], list) or len(row["events"]) > a["max_steps"]:
            raise ValueError("invalid event data")
        applied, missing, positive, safety, violations, final_speed, no_command = 0, 0, 0, False, 0, None, False
        for step, event in enumerate(row["events"]):
            if event.get("step") != step or no_command:
                raise ValueError("invalid step order")
            if event.get("status") == "NO_COMMAND":
                if not isinstance(event.get("reason"), str) or not event["reason"]:
                    raise ValueError("missing no-command reason")
                no_command = True
                continue
            if event.get("status") != "STEP":
                raise ValueError("unknown event status")
            values = [event.get("true_speed_before"), event.get("true_speed_after"), event.get("force_dot_true_velocity_before")]
            if any(type(x) not in (int, float) or not math.isfinite(x) for x in values) or min(values[:2]) < 0 or type(event.get("safety_violation")) is not bool:
                raise ValueError("invalid physics observation")
            def vector(name):
                result = event.get(name)
                if not isinstance(result, list) or len(result) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in result):
                    raise ValueError("missing or invalid vector")
                return result
            force = vector("force")
            before = vector("true_velocity_before")
            after = vector("true_velocity_after")
            vector("true_position_before")
            if (not math.isclose(math.sqrt(sum(x*x for x in before)), values[0], rel_tol=1e-10, abs_tol=1e-10)
                    or not math.isclose(math.sqrt(sum(x*x for x in after)), values[1], rel_tol=1e-10, abs_tol=1e-10)
                    or not math.isclose(sum(x*y for x, y in zip(force, before)), values[2], rel_tol=1e-10, abs_tol=1e-10)):
                raise ValueError("physics vector and score disagree")
            command = event.get("command")
            if a["arm"] == "ESTIMATED_STATE_CBF_BRAKE":
                vector("estimated_position")
                vector("estimated_velocity")
                if (type(event.get("measurement_sequence")) is not int or event["measurement_sequence"] != step
                        or type(event.get("measurement_acquired_seconds")) not in (int, float)
                        or not math.isfinite(event["measurement_acquired_seconds"])
                        or not isinstance(command, dict) or command.get("status") != "COMMAND_PROPOSED"
                        or command.get("projected_force") != force):
                    raise ValueError("incomplete or inconsistent estimated command")
                desired = command.get("desired_force")
                if not isinstance(desired, list) or len(desired) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in desired):
                    raise ValueError("invalid desired force")
            elif command is not None or event.get("estimated_position") is not None or event.get("estimated_velocity") is not None:
                raise ValueError("oracle command unexpectedly labeled estimated")
            residual = event.get("cbf_constraint_residual")
            if residual is None:
                missing += 1
            elif type(residual) not in (int, float) or not math.isfinite(residual):
                raise ValueError("invalid residual")
            else:
                violations += int(residual > 1e-8)
            applied += 1
            positive += int(values[2] > 0)
            safety |= event["safety_violation"]
            final_speed = values[1]
        if applied != row["steps_applied"] or no_command != row["no_command"] or (not no_command and applied != a["max_steps"]):
            raise ValueError("incomplete or inconsistent micro-episode")
        group["completed"] += 1
        group["no_command"] += int(no_command)
        group["steps_applied"] += applied
        group["positive_force_dot_steps"] += positive
        group["episodes_with_safety_violation"] += int(safety)
        group["cbf_residual_missing_steps"] += missing
        group["cbf_residual_violation_steps"] += violations
        group["final_speeds"].append(final_speed)
    return {"input_sha256": digest, "ledger_state": ledger["state"], "integrity": ledger["integrity"],
            "summary": [{"case": k[0], "controller": k[1], **v} for k, v in groups.items()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = analyze(args.input)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
