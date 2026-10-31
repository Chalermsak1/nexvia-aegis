#!/usr/bin/env python3
"""Validate and summarize an exploratory stabilized-arrival study."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


def summarize(data, radius):
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("success radius must be finite and positive")
    if data.get("classification") != "EXPLORATORY_SIMULATION" or not data.get("sources_unchanged"):
        raise ValueError("missing exploratory classification or changed sources")
    n, start, horizon = data["n_seeds"], data["seed_start"], data["post_stop_steps"]
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (n, start, horizon)) or n <= 0 or horizon <= 0:
        raise ValueError("invalid design")
    names = [c["name"] for c in data["cases"]]
    if len(names) != len(set(names)) or not names:
        raise ValueError("missing or duplicate cases")
    biases = ((0., 0., 0.), (0.8, 0.8, -0.3))
    arms = ("AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD", "AEGIS_3D_STABILIZED")
    expected = set(itertools.product(names, range(start, start + n), biases, arms))
    seen, groups = set(), {}
    for row in data["episodes"]:
        key = (row["case"], row["seed"], tuple(row["bias_xyz"]), row["controller"])
        if key not in expected or key in seen:
            raise ValueError("duplicate or unplanned episode")
        seen.add(key)
        group = groups.setdefault((key[0], key[2], key[3]), {"assigned": 0, "errors": 0,
            "true_success": 0, "false_arrival": 0, "abstained": 0, "timeout": 0,
            "true_success_post_stops": 0, "left_radius": 0, "outside_at_end": 0,
            "speed_over_005_at_end": 0, "post_collision": 0, "post_cbf_missing": 0,
            "post_cbf_violation": 0, "anchor_rejected_inside": 0, "anchor_rejected_total": 0,
            "exploratory_stabilized_proxy": 0, "anchor_queries": 0})
        group["assigned"] += 1
        if row["execution_status"] == "ERROR":
            group["errors"] += 1
            continue
        outcomes = ("true_success", "false_arrival", "abstained", "timeout")
        if row["execution_status"] != "COMPLETED" or any(row[k] not in (0, 1) for k in outcomes) or sum(row[k] for k in outcomes) != 1:
            raise ValueError("invalid outcome")
        for k in outcomes:
            group[k] += row[k]
        group["anchor_queries"] += row["anchor_queries"]
        post = row["post_stop"]
        if bool(post) != bool(row["true_success"] or row["false_arrival"]):
            raise ValueError("STOP outcome and diagnostic disagree")
        if post:
            steps = post["steps"]
            if len(steps) != horizon:
                raise ValueError("incomplete post-STOP observations")
            group["post_collision"] += int(any(s["collision"] for s in steps))
            group["post_cbf_missing"] += int(any(s["cbf_residual"] is None for s in steps))
            group["post_cbf_violation"] += int(any(s["cbf_residual"] is not None and s["cbf_residual"] > 1e-8 for s in steps))
            if row["true_success"]:
                group["true_success_post_stops"] += 1
                group["left_radius"] += int(any(s["distance"] > radius for s in steps))
                group["outside_at_end"] += int(steps[-1]["distance"] > radius)
                group["speed_over_005_at_end"] += int(steps[-1]["speed"] > 0.05)
                # A descriptive one-second proxy, not a validated dwell rule.
                group["exploratory_stabilized_proxy"] += int(
                    all(s["distance"] <= radius and not s["collision"] for s in steps)
                    and steps[-1]["speed"] <= 0.05)
        if row["abstained"] and row["last_events"][-1]["terminal_reason"] == "ANCHOR_OUTSIDE_CONFIRMATION_MARGIN":
            group["anchor_rejected_total"] += 1
            group["anchor_rejected_inside"] += int(row["last_events"][-1]["true_distance"] <= radius)
    if seen != expected:
        raise ValueError("missing assigned episodes")
    return [{"case": k[0], "bias_xyz": list(k[1]), "controller": k[2], **v} for k, v in groups.items()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--success-radius", required=True, type=float, help="Radius from the simulation configuration, in metres")
    a = p.parse_args()
    raw = a.input.read_bytes()
    summary = summarize(json.loads(raw), a.success_radius)
    with a.output.open("x", encoding="utf-8") as out:
        json.dump({"input_sha256": hashlib.sha256(raw).hexdigest(), "success_radius": a.success_radius,
                   "speed_threshold_m_per_s": 0.05, "summary": summary}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
