#!/usr/bin/env python3
"""Sampled simulation dwell diagnostics; not a registered success criterion."""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
if __package__:
    from .evidence_integrity import validate_source_metadata
else:
    from evidence_integrity import validate_source_metadata


def classify(row, radius, speed_limit, timestep, dwell_seconds):
    """Classify sampled post-STOP dwell without imputing absent observations."""
    for v in (radius, speed_limit, timestep, dwell_seconds):
        if not math.isfinite(v) or v <= 0:
            raise ValueError("parameters must be finite and positive")
    if row.get("execution_status") != "COMPLETED":
        return "UNEVALUABLE"
    outcomes = [row.get(k) for k in ("true_success", "false_arrival", "abstained", "timeout")]
    if any(type(x) is not int or x not in (0, 1) for x in outcomes) or sum(outcomes) != 1:
        return "UNEVALUABLE"
    if not (row.get("true_success") or row.get("false_arrival")):
        return "NO_STOP" if row.get("post_stop") is None else "UNEVALUABLE"
    post = row.get("post_stop")
    if not isinstance(post, dict) or not isinstance(post.get("steps"), list):
        return "UNEVALUABLE"
    # Include STOP and each following sample; N steps provide N time intervals.
    intervals = math.ceil(dwell_seconds / timestep - 1e-12)
    if len(post["steps"]) < intervals:
        return "UNEVALUABLE"
    prior_collision = row.get("collision_occurred")
    if prior_collision not in (0, 1, False, True):
        return "UNEVALUABLE"
    # Conservatively treat any observed pre-STOP collision as a failure.
    samples = [{"distance": post.get("decision_distance"), "speed": post.get("decision_speed"),
                "collision": bool(prior_collision)}] + post["steps"][:intervals]
    for sample in samples:
        if not isinstance(sample, dict):
            return "UNEVALUABLE"
        distance, speed = sample.get("distance"), sample.get("speed")
        if (not isinstance(distance, (int, float)) or isinstance(distance, bool) or not math.isfinite(distance)
                or distance < 0 or not isinstance(speed, (int, float)) or isinstance(speed, bool)
                or not math.isfinite(speed) or speed < 0 or not isinstance(sample.get("collision"), bool)):
            return "UNEVALUABLE"
    decision_in_radius = samples[0]["distance"] <= radius
    if bool(row["true_success"]) != decision_in_radius:
        return "UNEVALUABLE"
    return "MET_SAMPLED_DWELL" if all(s["distance"] <= radius and s["speed"] <= speed_limit and not s["collision"] for s in samples) else "NOT_MET"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--success-radius", type=float, required=True)
    p.add_argument("--speed-limit", type=float, required=True)
    p.add_argument("--dwell-seconds", type=float, required=True)
    p.add_argument("--arms", nargs="+", default=["AEGIS_3D_STRICT_RANGE", "AEGIS_3D_STABILIZED", "AEGIS_3D_STABILIZED_RETRY"])
    a = p.parse_args()
    raw = a.input.read_bytes()
    data = json.loads(raw)
    validate_source_metadata(data)
    timestep = data["runtime"]["timestep_seconds"]
    counts = defaultdict(lambda: defaultdict(int))
    assignments = set()
    rows = []
    for row in data["episodes"]:
        key = (row["case"], row["seed"], tuple(row["bias_xyz"]), row["controller"])
        if key in assignments:
            raise ValueError("duplicate episode")
        assignments.add(key)
        result = classify(row, a.success_radius, a.speed_limit, timestep, a.dwell_seconds)
        counts[(key[0], key[2], key[3])][result] += 1
        rows.append({"case": key[0], "seed": key[1], "bias_xyz": list(key[2]), "controller": key[3], "dwell": result})
    from itertools import product
    names = [c["name"] for c in data["cases"]]
    if len(names) != len(set(names)) or len(a.arms) != len(set(a.arms)):
        raise ValueError("duplicate cases or arms")
    expected = set(product(names, range(data["seed_start"], data["seed_start"] + data["n_seeds"]),
                           ((0., 0., 0.), (0.8, 0.8, -0.3)),
                           a.arms))
    if assignments != expected:
        raise ValueError("incomplete or unexpected assignment count")
    summary = [{"case": k[0], "bias_xyz": list(k[1]), "controller": k[2], "counts": dict(v)} for k, v in counts.items()]
    with a.output.open("x", encoding="utf-8") as out:
        json.dump({"input_sha256": hashlib.sha256(raw).hexdigest(), "radius": a.success_radius,
                   "speed_limit": a.speed_limit, "dwell_seconds": a.dwell_seconds,
                   "timestep_seconds": timestep, "summary": summary, "episodes": rows}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
