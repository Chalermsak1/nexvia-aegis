#!/usr/bin/env python3
"""Validate assigned dual-velocity episodes and summarize diagnostics."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path


def analyze(data):
    if data.get("classification") != "EXPLORATORY_SIMULATION" or data.get("sources_unchanged") is not True:
        raise ValueError("invalid experimental identity")
    n, start = data["n_seeds"], data["seed_start"]
    names = [c["name"] for c in data["cases"]]
    if type(n) is not int or n <= 0 or type(start) is not int or not names or len(set(names)) != len(names):
        raise ValueError("invalid self-declared design")
    expected = set(itertools.product(names, range(start, start + n), ((0., 0., 0.), (0.8, 0.8, -0.3)),
                                     ("AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_DUAL_VELOCITY")))
    seen, groups = set(), {}
    for row in data["episodes"]:
        key = (row["case"], row["seed"], tuple(row["bias_xyz"]), row["controller"])
        if key not in expected or key in seen:
            raise ValueError("duplicate or unplanned episode")
        seen.add(key)
        group = groups.setdefault((key[0], key[2], key[3]), {"assigned": 0, "errors": 0,
            "true_success": 0, "false_arrival": 0, "abstained": 0, "timeout": 0,
            "comparisons": 0, "disagreements": 0, "hazard_counts": Counter()})
        group["assigned"] += 1
        if row.get("execution_status") == "ERROR":
            group["errors"] += 1
            continue
        outcomes = [row.get(k) for k in ("true_success", "false_arrival", "abstained", "timeout")]
        if row.get("execution_status") != "COMPLETED" or any(type(x) is not int or x not in (0, 1) for x in outcomes) or sum(outcomes) != 1:
            raise ValueError("invalid outcome")
        for k, value in zip(("true_success", "false_arrival", "abstained", "timeout"), outcomes):
            group[k] += value
        counts = row.get("hazard_counts")
        if not isinstance(counts, dict) or any(k not in {"VELOCITY_DISAGREEMENT", "VELOCITIES_CONSISTENT", "SOURCE_UNAVAILABLE"}
            or type(v) is not int or v < 0 for k, v in counts.items()) or sum(counts.values()) > row["steps"]:
            raise ValueError("invalid hazard counts")
        examples = row.get("hazard_examples")
        if not isinstance(examples, list) or len(examples) > sum(counts.values()):
            raise ValueError("invalid hazard examples")
        for event in examples:
            actual, primary = event.get("velocity"), event.get("velocity_observation")
            if (not isinstance(actual, list) or not isinstance(primary, list) or len(actual) != 3 or len(primary) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in actual + primary)
                or math.sqrt(sum(v*v for v in actual)) <= 0.05 or math.sqrt(sum(v*v for v in primary)) > 0.05
                or event.get("velocity_crosscheck_reason") not in counts):
                raise ValueError("invalid hazard example")
        if key[3] == "AEGIS_3D_DUAL_VELOCITY":
            comparisons, disagreements = row["velocity_comparisons"], row["velocity_disagreements"]
            if type(comparisons) is not int or type(disagreements) is not int or not 0 <= disagreements <= comparisons <= row["steps"]:
                raise ValueError("invalid crosscheck counts")
            group["comparisons"] += comparisons
            group["disagreements"] += disagreements
        elif counts or examples:
            raise ValueError("unexpected crosscheck data in comparator")
        group["hazard_counts"].update(counts)
    if seen != expected:
        raise ValueError("missing assigned episode")
    return [{"case": k[0], "bias_xyz": list(k[1]), "controller": k[2], **{**v, "hazard_counts": dict(v["hazard_counts"])}} for k, v in groups.items()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raw = a.input.read_bytes()
    summary = analyze(json.loads(raw))
    with a.output.open("x", encoding="utf-8") as out:
        json.dump({"input_sha256": hashlib.sha256(raw).hexdigest(), "summary": summary}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
