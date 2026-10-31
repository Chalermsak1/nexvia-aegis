import math
import pytest
from scripts.research.dwell_diagnostics import classify


def row():
    return {"execution_status": "COMPLETED", "true_success": 1, "false_arrival": 0, "abstained": 0, "timeout": 0, "collision_occurred": 0,
            "post_stop": {"decision_distance": 0.2, "decision_speed": 0.04,
                          "steps": [{"distance": 0.2, "speed": 0.04, "collision": False} for _ in range(50)]}}


def evaluate(x):
    return classify(x, 0.25, 0.05, 0.02, 1.0)


def test_includes_stop_and_all_50_following_samples():
    x = row()
    assert evaluate(x) == "MET_SAMPLED_DWELL"
    x["post_stop"]["steps"][10]["speed"] = 0.051
    assert evaluate(x) == "NOT_MET"
    x = row()
    x["post_stop"]["decision_speed"] = 0.051
    assert evaluate(x) == "NOT_MET"


@pytest.mark.parametrize("defect", ["short", "nan", "collision", "prior_collision"])
def test_incomplete_and_bad_evidence_is_not_silently_accepted(defect):
    x = row()
    if defect == "short": x["post_stop"]["steps"].pop()
    if defect == "nan": x["post_stop"]["steps"][1]["speed"] = math.nan
    if defect == "collision": x["post_stop"]["steps"][1]["collision"] = True
    if defect == "prior_collision": x["collision_occurred"] = 1
    assert evaluate(x) == ("UNEVALUABLE" if defect in ("short", "nan") else "NOT_MET")


def test_no_stop_and_execution_errors_are_distinct():
    x = row()
    x["true_success"] = 0
    x["timeout"] = 1
    x["post_stop"] = None
    assert evaluate(x) == "NO_STOP"
    x["execution_status"] = "ERROR"
    assert evaluate(x) == "UNEVALUABLE"


def test_missing_or_contradictory_outcome_is_unevaluable():
    x = row()
    del x["abstained"]
    assert evaluate(x) == "UNEVALUABLE"


def test_post_stop_data_on_abstention_and_bad_step_are_unevaluable():
    x = row()
    x["true_success"] = 0
    x["abstained"] = 1
    assert evaluate(x) == "UNEVALUABLE"
    x = row()
    x["post_stop"]["steps"][1] = None
    assert evaluate(x) == "UNEVALUABLE"
    x = row()
    x["false_arrival"] = 1
    assert evaluate(x) == "UNEVALUABLE"


@pytest.mark.parametrize("label,distance,expected", [("true_success", 0.251, "UNEVALUABLE"),
    ("false_arrival", 0.2, "UNEVALUABLE"), ("true_success", 0.25, "MET_SAMPLED_DWELL"),
    ("false_arrival", 0.251, "NOT_MET")])
def test_outcome_must_match_unrounded_decision_distance(label, distance, expected):
    x = row()
    x["true_success"] = int(label == "true_success")
    x["false_arrival"] = int(label == "false_arrival")
    x["post_stop"]["decision_distance"] = distance
    assert evaluate(x) == expected
