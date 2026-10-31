import copy
import pytest
from scripts.research.development_ledger import DevelopmentLedger
from scripts.research.study_estimated_braking import run
from scripts.research.analyze_estimated_braking_ledger_v2 import analyze


def make_ledger(path, defect=None):
    case = {"name": "nominal", "velocity_scale": 1., "missing_velocity": False}
    arms = ("ORACLE_STATE_CBF_BRAKE", "ESTIMATED_STATE_CBF_BRAKE")
    assignments = [{"id": arm, "arm": arm, "seed": 2248000, "case": case, "max_steps": 2,
                    "source_sha256": {"source.py": "a" * 64}} for arm in arms]
    with DevelopmentLedger.create(path, study="V9-M5 exploratory estimated braking v2", assignments=assignments) as w:
        for a in assignments:
            w.start(a["id"])
            row = run(a["seed"], a["arm"], case, 2)
            if a["arm"] == "ESTIMATED_STATE_CBF_BRAKE":
                if defect == "force": row["events"][0]["force"][0] += 0.5
                if defect == "velocity": row["events"][0]["true_velocity_before"][0] += 1
                if defect == "estimate": row["events"][0]["estimated_velocity"] = None
                if defect == "desired": row["events"][0]["command"]["desired_force"] = None
                if defect == "sequence": row["events"][0]["measurement_sequence"] = 9
            w.complete(a["id"], status="COMPLETED", details={"episode": row, "source_sha256_after": copy.deepcopy(a["source_sha256"])})
        w.finalize()


def test_valid_estimated_and_oracle_records(tmp_path):
    path = tmp_path / "valid.jsonl"
    make_ledger(path)
    assert analyze(path)["ledger_state"] == "FINALIZED"


@pytest.mark.parametrize("defect", ["force", "velocity", "estimate", "desired", "sequence"])
def test_invalid_step_evidence_rejected(tmp_path, defect):
    path = tmp_path / "bad.jsonl"
    make_ledger(path, defect)
    with pytest.raises(ValueError): analyze(path)
