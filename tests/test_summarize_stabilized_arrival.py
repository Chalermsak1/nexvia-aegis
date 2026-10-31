import copy
import pytest
from scripts.research.summarize_stabilized_arrival import summarize
from test_summarize_post_stop import fixture


def sample():
    data = fixture()
    data["episodes"] = []
    for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
        for arm in ("AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD", "AEGIS_3D_STABILIZED"):
            data["episodes"].append({"case": "nominal", "seed": 1, "bias_xyz": bias, "controller": arm,
                "execution_status": "COMPLETED", "true_success": 1, "false_arrival": 0, "abstained": 0,
                "timeout": 0, "anchor_queries": 1, "last_events": [], "post_stop": {"steps": [
                    {"distance": 0.2, "speed": 0.04, "collision": False, "cbf_residual": 0.0}]}})
    return data


def test_proxy_is_not_counted_if_post_stop_leaves_target_or_speed_high():
    d = sample()
    d["episodes"][0]["post_stop"]["steps"][0]["distance"] = 0.26
    d["episodes"][1]["post_stop"]["steps"][0]["speed"] = 0.06
    result = summarize(d, 0.25)
    assert [x["exploratory_stabilized_proxy"] for x in result[:3]] == [0, 0, 1]


def test_missing_or_duplicate_assignments_rejected():
    d = sample()
    d["episodes"].pop()
    with pytest.raises(ValueError): summarize(d, 0.25)
    d = sample()
    d["episodes"].append(copy.deepcopy(d["episodes"][0]))
    with pytest.raises(ValueError): summarize(d, 0.25)
