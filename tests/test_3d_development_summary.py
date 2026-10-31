"""Regression tests for the exploratory benchmark evidence boundary."""

import copy
import json
import pytest

from scripts.research.summarize_3d_development import main, paired_counts, summarize


def fixture_payload():
    rows = []
    for controller in ("candidate", "baseline"):
        for seed in (100, 101):
            is_success = controller == "candidate" and seed == 100
            rows.append({
                "controller": controller, "seed": seed, "bias_xyz": [0, 0, 0],
                "steps": 5, "true_success": int(is_success), "false_arrival": 0,
                "abstained": int(not is_success), "timeout": 0, "collision_occurred": 0,
                "cbf_constraint_violation_occurred": 0, "cbf_unchecked_steps": 0,
                "cbf_exact_fallback_steps": 0, "cbf_infeasible_steps": 0,
                "range_bias_m": 0.0, "range_dropout_probability": 0.0, "range_latency_steps": 0,
            })
    summary = {}
    for name in ("candidate", "baseline"):
        success = int(name == "candidate")
        summary[name] = {
            "episodes": 2, "true_success": success, "false_arrival": 0,
            "accepted": success, "abstained": 2 - success, "timeout": 0, "collision": 0,
            "cbf_constraint_violation_episodes": 0, "cbf_unchecked_steps": 0,
            "cbf_exact_fallback_steps": 0, "cbf_infeasible_steps": 0,
        }
    return {
        "schema_version": "v9-m5-3d-development-benchmark/1.7",
        "classification": "EXPLORATORY_SIMULATION", "seed_start": 100,
        "n_seeds_per_bias": 2, "bias_vectors_xyz": [[0, 0, 0]], "max_steps": 10,
        "range_fault": {"bias_m": 0.0, "dropout_probability": 0.0, "latency_steps": 0},
        "summary": summary, "episodes": rows,
    }


def test_counts_and_undefined_selective_risk():
    candidate, baseline = summarize(fixture_payload())
    assert candidate["coverage"] == 0.5
    assert candidate["false_arrival_given_accepted"] == 0.0
    assert baseline["accepted"] == 0
    assert baseline["false_arrival_given_accepted"] is None


def test_paired_comparison_counts_and_missing_baseline():
    payload = fixture_payload()
    summarize(payload)
    success, false_arrival = paired_counts(payload, "baseline")
    assert success["matched_pairs"] == 2
    assert success["candidate_only"] == 1
    assert success["baseline_only"] == 0
    assert success["neither"] == 1
    assert false_arrival["neither"] == 2
    with pytest.raises(ValueError, match="baseline is missing"):
        paired_counts(payload, "missing")


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "summary", "terminal", "fault", "classification", "step_count"])
def test_invalid_evidence_is_rejected_before_creating_output(tmp_path, mutation):
    payload = copy.deepcopy(fixture_payload())
    if mutation == "duplicate":
        payload["episodes"][1] = copy.deepcopy(payload["episodes"][0])
    elif mutation == "missing":
        payload["episodes"].pop()
    elif mutation == "summary":
        payload["summary"]["candidate"]["true_success"] = 2
    elif mutation == "terminal":
        payload["episodes"][0]["timeout"] = 1
    elif mutation == "fault":
        payload["episodes"][0]["range_latency_steps"] = 3
    elif mutation == "classification":
        payload["classification"] = "PRODUCTION"
    else:
        payload["episodes"][0]["cbf_infeasible_steps"] = 6
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload))
    out = tmp_path / "output"
    with pytest.raises(ValueError):
        main([str(source), "--output-dir", str(out)])
    assert not out.exists()


def test_missing_requested_baseline_creates_no_output(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(fixture_payload()))
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="baseline is missing"):
        main([str(source), "--baseline", "missing", "--output-dir", str(output)])
    assert not output.exists()


def test_output_is_complete_and_existing_directory_is_preserved(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(fixture_payload()))
    out = tmp_path / "output"
    main([str(source), "--output-dir", str(out)])
    assert {p.name for p in out.iterdir()} == {"report.md", "summary.json", "summary.csv", "scenario_summary.csv"}
    assert "UNDEFINED (0 accepted)" in (out / "report.md").read_text()
    before = (out / "summary.json").read_bytes()
    with pytest.raises(FileExistsError):
        main([str(source), "--output-dir", str(out)])
    assert (out / "summary.json").read_bytes() == before
