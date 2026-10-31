import copy
import pytest
from scripts.research.analyze_dual_velocity import analyze


def sample():
    rows = []
    for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
        for arm in ("AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_DUAL_VELOCITY"):
            dual = arm == "AEGIS_3D_DUAL_VELOCITY"
            event = {"velocity": [0.2, 0, 0], "velocity_observation": [0.01, 0, 0],
                     "velocity_crosscheck_reason": "VELOCITIES_CONSISTENT"}
            row = {"case": "case", "seed": 1, "bias_xyz": bias, "controller": arm, "steps": 10,
                   "execution_status": "COMPLETED", "true_success": 1, "false_arrival": 0, "abstained": 0,
                   "timeout": 0, "hazard_counts": {"VELOCITIES_CONSISTENT": 1} if dual else {},
                   "hazard_examples": [event] if dual else []}
            if dual: row.update(velocity_comparisons=10, velocity_disagreements=0)
            rows.append(row)
    return {"classification": "EXPLORATORY_SIMULATION", "sources_unchanged": True,
            "n_seeds": 1, "seed_start": 1, "cases": [{"name": "case"}], "episodes": rows}


def test_summary_retains_common_fault_evidence():
    assert analyze(sample())[1]["hazard_counts"] == {"VELOCITIES_CONSISTENT": 1}


@pytest.mark.parametrize("defect", ["missing", "duplicate", "bad_example", "contradictory", "bad_counts"])
def test_invalid_evidence_is_rejected(defect):
    data = sample()
    if defect == "missing": data["episodes"].pop()
    if defect == "duplicate": data["episodes"].append(copy.deepcopy(data["episodes"][0]))
    if defect == "bad_example": data["episodes"][1]["hazard_examples"][0]["velocity"] = [0., 0., 0.]
    if defect == "contradictory": data["episodes"][1]["timeout"] = 1
    if defect == "bad_counts": data["episodes"][1]["velocity_disagreements"] = 11
    with pytest.raises(ValueError): analyze(data)
