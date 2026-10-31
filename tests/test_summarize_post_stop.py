import copy
import pytest
from scripts.research.summarize_post_stop import summarize


def fixture():
    rows = []
    for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
        for arm in ("AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD"):
            rows.append({"case": "nominal", "seed": 1, "bias_xyz": bias, "controller": arm,
                         "execution_status": "COMPLETED", "true_success": 1, "false_arrival": 0,
                         "abstained": 0, "timeout": 0, "last_events": [],
                         "post_stop": {"steps": [{"distance": 0.3, "speed": 0.1,
                                                   "collision": False, "cbf_residual": 0.0}]}})
    return {"classification": "EXPLORATORY_SIMULATION", "sources_unchanged": True,
            "source_sha256_before": {"source.py": "a" * 64}, "source_sha256_after": {"source.py": "a" * 64},
            "n_seeds": 1, "seed_start": 1, "post_stop_steps": 1,
            "cases": [{"name": "nominal"}], "episodes": rows}


def test_summary_counts_left_radius_and_speed():
    assert all(x["left_radius"] == x["speed_over_005_at_end"] == 1 for x in summarize(fixture(), 0.25))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "incomplete", "changed_source", "invalid_outcome"])
def test_summary_rejects_invalid_evidence(mutation):
    data = fixture()
    if mutation == "missing": data["episodes"].pop()
    if mutation == "duplicate": data["episodes"].append(copy.deepcopy(data["episodes"][0]))
    if mutation == "incomplete": data["episodes"][0]["post_stop"]["steps"] = []
    if mutation == "changed_source": data["sources_unchanged"] = False
    if mutation == "invalid_outcome": data["episodes"][0]["timeout"] = 1
    with pytest.raises(ValueError): summarize(data, 0.25)


def test_error_is_counted_and_not_success():
    data = fixture()
    data["episodes"][0]["execution_status"] = "ERROR"
    result = summarize(data, 0.25)
    assert result[0]["errors"] == 1 and result[0]["true_success"] == 0
