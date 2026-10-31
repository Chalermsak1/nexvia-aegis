import pytest
from scripts.research.development_ledger import DevelopmentLedger
from scripts.research.analyze_estimated_braking_ledger import analyze


def item(name="a", seed=1, arm="ESTIMATED_STATE_CBF_BRAKE"):
    return {"id": name, "seed": seed, "arm": arm, "case": {"name": "nominal"},
            "source_sha256": {"source.py": "a" * 64}, "max_steps": 1}


def episode():
    return {"controller": "ESTIMATED_STATE_CBF_BRAKE", "seed": 1, "case": "nominal", "no_command": False,
            "steps_applied": 1, "events": [{"step": 0, "status": "STEP", "true_speed_before": 0.4,
                "true_speed_after": 0.5, "force_dot_true_velocity_before": 0.1, "safety_violation": False,
                "cbf_constraint_residual": 0.0}]}


def test_summary_and_incomplete_record(tmp_path):
    path = tmp_path / "a.jsonl"
    assignments = [item(), item("b", 2), item("c", 1, "ORACLE_STATE_CBF_BRAKE"), item("d", 2, "ORACLE_STATE_CBF_BRAKE")]
    with DevelopmentLedger.create(path, study="V9-M5 exploratory estimated braking", assignments=assignments) as w:
        w.start("a")
        w.complete("a", status="COMPLETED", details={"episode": episode(), "source_sha256_after": {"source.py": "a" * 64}})
    result = analyze(path)
    assert result["ledger_state"] == "INCOMPLETE"
    assert result["summary"][0]["incomplete"] == 1
    assert result["summary"][0]["positive_force_dot_steps"] == 1


@pytest.mark.parametrize("defect", ["identity", "step", "source", "no_command", "partial"])
def test_contradictions_are_rejected(tmp_path, defect):
    path = tmp_path / "a.jsonl"
    row, source = episode(), {"source.py": "a" * 64}
    if defect == "identity": row["seed"] = 2
    if defect == "step": row["events"][0]["step"] = 1
    if defect == "source": source["source.py"] = "b" * 64
    if defect == "no_command": row["no_command"] = True
    if defect == "partial": row["events"] = []; row["steps_applied"] = 0
    with DevelopmentLedger.create(path, study="V9-M5 exploratory estimated braking", assignments=[item(), item("b", 1, "ORACLE_STATE_CBF_BRAKE")]) as w:
        w.start("a")
        w.complete("a", status="COMPLETED", details={"episode": row, "source_sha256_after": source})
        w.start("b")
        w.complete("b", status="ERROR", details={"reason": "synthetic"})
        w.finalize()
    with pytest.raises(ValueError): analyze(path)


def test_no_command_without_reason_is_rejected(tmp_path):
    path = tmp_path / "bad.jsonl"
    assignments = [item(), item("b", 1, "ORACLE_STATE_CBF_BRAKE")]
    row = episode()
    row.update(no_command=True, steps_applied=0, events=[{"step": 0, "status": "NO_COMMAND"}])
    with DevelopmentLedger.create(path, study="V9-M5 exploratory estimated braking", assignments=assignments) as w:
        w.start("a"); w.complete("a", status="COMPLETED", details={"episode": row, "source_sha256_after": assignments[0]["source_sha256"]})
        w.start("b"); w.complete("b", status="ERROR", details={"reason": "synthetic"})
        w.finalize()
    with pytest.raises(ValueError): analyze(path)
