#!/usr/bin/env python3
"""Assess assumed gap speed bounds against simulator truth, descriptively."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
if __package__:
    from .evidence_integrity import validate_source_metadata
else:
    from evidence_integrity import validate_source_metadata


def analyze(data):
    validate_source_metadata(data)
    names = [x["name"] for x in data["cases"]]
    if not names or len(names) != len(set(names)) or data["n_seeds"] <= 0:
        raise ValueError("invalid self-declared design")
    expected = set(itertools.product(names, range(data["seed_start"], data["seed_start"] + data["n_seeds"]),
                    ((0., 0., 0.), (0.8, 0.8, -0.3)), ("AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP")))
    seen, groups = set(), {}
    for row in data["episodes"]:
        key = (row["case"], row["seed"], tuple(row["bias_xyz"]), row["controller"])
        if key not in expected or key in seen:
            raise ValueError("duplicate or unplanned episode")
        seen.add(key)
        group = groups.setdefault((key[0], key[2], key[3]), {"assigned": 0, "errors": 0,
            "bridged_steps": 0, "bound_violations": 0, "truth_over_speed_limit": 0,
            "episodes_with_bound_violation": 0})
        group["assigned"] += 1
        if row.get("execution_status") == "ERROR":
            group["errors"] += 1
            continue
        if row.get("execution_status") != "COMPLETED" or not isinstance(row.get("gap_events"), list):
            raise ValueError("missing episode status or gap events")
        events = row["gap_events"]
        if key[3] == "AEGIS_3D_BOUNDED_GAP" and row.get("bridged_velocity_steps") != len(events):
            raise ValueError("bridged count and events disagree")
        if key[3] == "AEGIS_3D_FRESH_VELOCITY" and events:
            raise ValueError("unexpected gap events in comparator")
        violations = 0
        for e in events:
            v, bound = e.get("velocity"), e.get("gap_speed_bound")
            if (not e.get("gap_bridged") or e.get("velocity_observation") is not None
                    or not isinstance(v, list) or len(v) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v)
                    or type(bound) not in (int, float) or not math.isfinite(bound) or bound < 0):
                raise ValueError("invalid bridged event")
            speed = math.sqrt(sum(x*x for x in v))
            violations += int(speed > bound + 1e-12)
            group["truth_over_speed_limit"] += int(speed > 0.05)
        group["bridged_steps"] += len(events)
        group["bound_violations"] += violations
        group["episodes_with_bound_violation"] += int(violations > 0)
    if seen != expected:
        raise ValueError("missing assigned episodes")
    return [{"case": k[0], "bias_xyz": list(k[1]), "controller": k[2], **v} for k, v in groups.items()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raw = a.input.read_bytes()
    summary = analyze(json.loads(raw))
    with a.output.open("x", encoding="utf-8") as out:
        json.dump({"input_sha256": hashlib.sha256(raw).hexdigest(), "speed_limit_m_per_s": 0.05,
                   "summary": summary}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
