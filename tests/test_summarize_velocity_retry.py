import pytest
from scripts.research.summarize_velocity_retry import summarize
from test_summarize_stabilized_arrival import sample


def test_retry_assignment_and_missing_arm_validation():
    data = sample()
    for row in data["episodes"]:
        if row["controller"] == "AEGIS_3D_ANCHOR_GUARD":
            row["controller"] = "AEGIS_3D_STABILIZED_RETRY"
    assert len(summarize(data, 0.25)) == 6
    data["episodes"].pop()
    with pytest.raises(ValueError):
        summarize(data, 0.25)
