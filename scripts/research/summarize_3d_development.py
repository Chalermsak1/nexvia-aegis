"""Validate and summarize exploratory 3D benchmark JSON without re-running episodes.

This tool produces descriptive counts, never a confirmatory decision. It accepts
only the development benchmark schema and creates a new output directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "v9-m5-3d-development-benchmark/1.7"
OUTCOMES = ("true_success", "false_arrival", "abstained", "timeout")
FLAGS = (*OUTCOMES, "collision_occurred", "cbf_constraint_violation_occurred")
COUNTS = ("cbf_unchecked_steps", "cbf_exact_fallback_steps", "cbf_infeasible_steps")
SUMMARY_MAP = {
    "true_success": "true_success", "false_arrival": "false_arrival",
    "collision": "collision_occurred", "abstained": "abstained", "timeout": "timeout",
    "cbf_constraint_violation_episodes": "cbf_constraint_violation_occurred",
    "cbf_unchecked_steps": "cbf_unchecked_steps", "cbf_exact_fallback_steps": "cbf_exact_fallback_steps",
    "cbf_infeasible_steps": "cbf_infeasible_steps",
}


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _bias(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three numeric values")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(f"{label} must contain finite numeric values")
    return tuple(float(v) for v in value)  # type: ignore[return-value]


def _metrics(name: str, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    success = sum(r["true_success"] for r in episodes)
    false = sum(r["false_arrival"] for r in episodes)
    accepted = success + false
    n = len(episodes)
    return {
        "controller": name, "episodes": n, "true_success": success,
        "false_arrival": false, "accepted": accepted,
        "abstained": sum(r["abstained"] for r in episodes),
        "timeout": sum(r["timeout"] for r in episodes),
        "collision": sum(r["collision_occurred"] for r in episodes),
        "cbf_infeasible_episodes": sum(r["cbf_infeasible_steps"] > 0 for r in episodes),
        "coverage": accepted / n, "true_success_rate": success / n,
        "false_arrival_incidence": false / n,
        "false_arrival_given_accepted": false / accepted if accepted else None,
    }


def summarize(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the declared design and return descriptive per-arm summaries."""
    if payload.get("schema_version") != SCHEMA or payload.get("classification") != "EXPLORATORY_SIMULATION":
        raise ValueError("Only exploratory 3D development benchmark schema 1.7 is supported")
    start = _integer(payload.get("seed_start"), "seed_start")
    count = _integer(payload.get("n_seeds_per_bias"), "n_seeds_per_bias", minimum=1)
    max_steps = _integer(payload.get("max_steps"), "max_steps", minimum=1)
    biases = [_bias(b, "bias_vectors_xyz") for b in payload.get("bias_vectors_xyz", [])]
    if not biases or len(set(biases)) != len(biases):
        raise ValueError("Bias design must be nonempty and contain no duplicates")
    expected = {(seed, bias) for seed in range(start, start + count) for bias in biases}
    summaries = payload.get("summary")
    rows = payload.get("episodes")
    if not isinstance(summaries, dict) or not summaries or not isinstance(rows, list):
        raise ValueError("Benchmark summary and episode records are required")
    if any(not isinstance(name, str) or not name or not name.replace("_", "").isalnum() for name in summaries):
        raise ValueError("Controller names must be nonempty letters, numbers, and underscores")
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in summaries}
    keys: set[tuple[str, int, tuple[float, float, float]]] = set()
    fault = payload.get("range_fault")
    if not isinstance(fault, dict) or set(fault) != {"bias_m", "dropout_probability", "latency_steps"}:
        raise ValueError("A complete range fault configuration is required")
    for field in ("bias_m", "dropout_probability"):
        value = fault[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"range_fault {field} must be finite")
    if not 0.0 <= fault["dropout_probability"] <= 1.0:
        raise ValueError("range_fault dropout_probability must be in [0, 1]")
    _integer(fault["latency_steps"], "range_fault latency_steps")
    for row in rows:
        if not isinstance(row, dict) or row.get("controller") not in groups:
            raise ValueError("Episode has an unknown or missing controller")
        name = row["controller"]
        seed = _integer(row.get("seed"), "episode seed")
        bias = _bias(row.get("bias_xyz"), "episode bias_xyz")
        key = (name, seed, bias)
        if key in keys or (seed, bias) not in expected:
            raise ValueError(f"Duplicate or unplanned episode: {key}")
        keys.add(key)
        steps = _integer(row.get("steps"), "episode steps", minimum=1)
        if steps > max_steps:
            raise ValueError("Episode steps exceed the declared limit")
        for field in FLAGS:
            if _integer(row.get(field), field) not in (0, 1):
                raise ValueError(f"{field} must be 0 or 1")
        for field in COUNTS:
            if _integer(row.get(field), field) > steps:
                raise ValueError(f"{field} cannot exceed episode steps")
        if sum(row[field] for field in OUTCOMES) != 1:
            raise ValueError("Each episode must have exactly one terminal outcome")
        for row_field, fault_field in (("range_bias_m", "bias_m"), ("range_dropout_probability", "dropout_probability"), ("range_latency_steps", "latency_steps")):
            if row.get(row_field) != fault[fault_field]:
                raise ValueError(f"Episode {row_field} conflicts with the declared fault")
        groups[name].append(row)

    results = []
    for name, episodes in groups.items():
        if {(r["seed"], _bias(r["bias_xyz"], "episode bias")) for r in episodes} != expected:
            raise ValueError(f"Missing planned episodes for {name}")
        reported = summaries[name]
        if not isinstance(reported, dict) or reported.get("episodes") != len(episodes):
            raise ValueError(f"Episode count mismatch for {name}")
        for summary_field, row_field in SUMMARY_MAP.items():
            if reported.get(summary_field) != sum(r[row_field] for r in episodes):
                raise ValueError(f"Summary mismatch for {name}: {summary_field}")
        metrics = _metrics(name, episodes)
        if reported.get("accepted") != metrics["accepted"]:
            raise ValueError(f"Accepted count mismatch for {name}")
        results.append(metrics)
    return results


def scenario_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Split validated episode records by declared vector-bias scenario."""
    result = []
    for name in payload["summary"]:
        for bias in payload["bias_vectors_xyz"]:
            rows = [r for r in payload["episodes"] if r["controller"] == name and _bias(r["bias_xyz"], "episode bias") == _bias(bias, "bias")]
            result.append({"bias_xyz": list(bias), **_metrics(name, rows)})
    return result


def paired_counts(payload: dict[str, Any], baseline: str) -> list[dict[str, Any]]:
    """Pair validated episodes by seed and bias; report counts only."""
    if baseline not in payload["summary"]:
        raise ValueError(f"Requested baseline is missing: {baseline}")
    grouped = {name: {} for name in payload["summary"]}
    for row in payload["episodes"]:
        grouped[row["controller"]][(row["seed"], _bias(row["bias_xyz"], "episode bias"))] = row
    reference = grouped[baseline]
    output = []
    for name, rows in grouped.items():
        if name == baseline:
            continue
        for outcome in ("true_success", "false_arrival"):
            counts = {"both": 0, "candidate_only": 0, "baseline_only": 0, "neither": 0}
            for key, candidate in rows.items():
                c, b = candidate[outcome], reference[key][outcome]
                field = "both" if c and b else "candidate_only" if c else "baseline_only" if b else "neither"
                counts[field] += 1
            output.append({"candidate": name, "baseline": baseline, "outcome": outcome,
                           "matched_pairs": len(rows), **counts})
    return output


def render_markdown(results: list[dict[str, Any]], by_scenario: list[dict[str, Any]], paired: list[dict[str, Any]], source_sha: str, fault: dict[str, Any]) -> str:
    def percent(value: float | None) -> str:
        return "UNDEFINED (0 accepted)" if value is None else f"{100 * value:.1f}%"

    lines = [
        "# Exploratory 3D benchmark summary", "",
        "Development simulation only. These are descriptive observations, not a safety certificate or confirmatory test.",
        f"Input SHA-256: `{source_sha}`", f"Declared range fault: `{json.dumps(fault, sort_keys=True)}`", "",
        "| Controller | Episodes | True success | False arrival | Accepted | Coverage | False arrival / accepted | Abstain | Timeout | Collision | CBF infeasible episodes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        label = r["controller"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {label} | {r['episodes']} | {r['true_success']} | {r['false_arrival']} | {r['accepted']} | {percent(r['coverage'])} | {percent(r['false_arrival_given_accepted'])} | {r['abstained']} | {r['timeout']} | {r['collision']} | {r['cbf_infeasible_episodes']} |")
    lines.extend(["", "## Results by vector-bias scenario", "", "| Controller | Bias (x, y, z) | Episodes | True success | False arrival | Accepted | Coverage | False arrival / accepted |", "|---|---|---:|---:|---:|---:|---:|---:|"])
    for r in by_scenario:
        lines.append(f"| {r['controller']} | {r['bias_xyz']} | {r['episodes']} | {r['true_success']} | {r['false_arrival']} | {r['accepted']} | {percent(r['coverage'])} | {percent(r['false_arrival_given_accepted'])} |")
    if paired:
        lines.extend(["", "## Matched outcome counts", "", "| Candidate | Baseline | Outcome | Pairs | Both | Candidate only | Baseline only | Neither |", "|---|---|---|---:|---:|---:|---:|---:|"])
        for r in paired:
            lines.append(f"| {r['candidate']} | {r['baseline']} | {r['outcome']} | {r['matched_pairs']} | {r['both']} | {r['candidate_only']} | {r['baseline_only']} | {r['neither']} |")
    lines.extend(["", "Collision and CBF infeasibility can overlap terminal outcomes. Seeds are reused across arms and bias scenarios; do not treat these rows as independent confirmatory observations. Completeness is checked against the input's declared design, not an independent assignment manifest. Required scientific baselines and model provenance need separate review.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Exploratory 3D benchmark JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory; existing directories are never overwritten")
    parser.add_argument("--baseline", help="Optional controller name for descriptive matched counts")
    args = parser.parse_args(argv)
    raw = args.input.read_bytes()
    payload = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON value: {value}")))
    results = summarize(payload)
    by_scenario = scenario_metrics(payload)
    paired = paired_counts(payload, args.baseline) if args.baseline else []
    source_sha = hashlib.sha256(raw).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "summary.json").write_text(json.dumps({
        "schema_version": "aegis-exploratory-summary/1.0", "input_sha256": source_sha,
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "classification": "EXPLORATORY_SIMULATION",
        "input_metadata": {key: payload.get(key) for key in (
            "schema_version", "seed_start", "n_seeds_per_bias", "bias_vectors_xyz",
            "max_steps", "range_fault", "source_sha256", "runtime",
        )},
        "results": results, "by_scenario": by_scenario, "paired_counts": paired,
    }, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (args.output_dir / "summary.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    with (args.output_dir / "scenario_summary.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(by_scenario[0]))
        writer.writeheader()
        writer.writerows(by_scenario)
    if paired:
        with (args.output_dir / "paired_counts.csv").open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(paired[0]))
            writer.writeheader()
            writer.writerows(paired)
    (args.output_dir / "report.md").write_text(render_markdown(results, by_scenario, paired, source_sha, payload["range_fault"]), encoding="utf-8")
    print(f"Validated {len(payload['episodes'])} exploratory episodes; report: {args.output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
