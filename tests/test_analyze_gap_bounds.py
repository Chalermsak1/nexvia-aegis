import copy
import pytest
from scripts.research.analyze_gap_bounds import analyze


def sample():
    rows = []
    for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
        for arm in ("AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP"):
            gap = [{"gap_bridged": True, "velocity_observation": None,
                    "velocity": [0.06, 0, 0], "gap_speed_bound": 0.04}] if arm.endswith("BOUNDED_GAP") else []
            rows.append({"case": "test", "seed": 1, "bias_xyz": bias, "controller": arm,
                         "execution_status": "COMPLETED", "gap_events": gap, "bridged_velocity_steps": len(gap)})
    return {"classification": "EXPLORATORY_SIMULATION", "sources_unchanged": True,
            "n_seeds": 1, "seed_start": 1, "cases": [{"name": "test"}], "episodes": rows}


def test_finds_bound_violation():
    result = analyze(sample())
    assert result[1]["bound_violations"] == 1 and result[1]["truth_over_speed_limit"] == 1


@pytest.mark.parametrize("defect", ["missing", "duplicate", "wrong_count", "false_gap", "changed_source"])
def test_invalid_records_rejected(defect):
    data = sample()
    if defect == "missing": data["episodes"].pop()
    if defect == "duplicate": data["episodes"].append(copy.deepcopy(data["episodes"][0]))
    if defect == "wrong_count": data["episodes"][1]["bridged_velocity_steps"] = 2
    if defect == "false_gap": data["episodes"][1]["gap_events"][0]["velocity_observation"] = [0, 0, 0]
    if defect == "changed_source": data["sources_unchanged"] = False
    with pytest.raises(ValueError): analyze(data)
