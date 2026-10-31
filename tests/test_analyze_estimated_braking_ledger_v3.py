import copy
import os
import subprocess
import sys
import pytest
from scripts.research.development_ledger import DevelopmentLedger, inspect
from scripts.research.study_estimated_braking_v3 import run
from scripts.research.analyze_estimated_braking_ledger_v3 import analyze


def make(path, defect=None):
    case = {"name": "nominal", "velocity_scale": 1., "missing_velocity": False}
    arms = ("ORACLE_STATE_CBF_BRAKE", "ESTIMATED_STATE_CBF_BRAKE")
    assignments = [{"id": arm, "arm": arm, "seed": 2248000, "case": case, "max_steps": 2,
                    "source_sha256": {"source.py": "a" * 64}} for arm in arms]
    with DevelopmentLedger.create(path, study="V9-M5 exploratory estimated braking v3", assignments=assignments, record_events=True) as writer:
        for a in assignments:
            writer.start(a["id"])
            row = run(a["seed"], a["arm"], case, 2, on_event=lambda event: writer.event(a["id"], details=event))
            if a["arm"] == "ESTIMATED_STATE_CBF_BRAKE" and defect == "terminal_mismatch":
                row = copy.deepcopy(row); row["events"][0]["force"][0] += 1
            writer.complete(a["id"], status="COMPLETED", details={"episode": row, "source_sha256_after": a["source_sha256"]})
        writer.finalize()


def test_v3_event_records_match_terminal_snapshot(tmp_path):
    path = tmp_path / "good.jsonl"
    make(path)
    assert analyze(path)["ledger_state"] == "FINALIZED"


def test_v3_rejects_terminal_disagreement_with_incremental_events(tmp_path):
    path = tmp_path / "bad.jsonl"
    make(path, "terminal_mismatch")
    with pytest.raises(ValueError): analyze(path)


def test_real_simulation_process_exit_preserves_completed_step_events(tmp_path):
    path = tmp_path / "interrupted.jsonl"
    code = '''import os,sys
from scripts.research.development_ledger import DevelopmentLedger
from scripts.research.study_estimated_braking_v3 import run
w=DevelopmentLedger.create(sys.argv[1],study="test",assignments=[{"id":"a"}],record_events=True)
w.start("a")
def callback(event):
    w.event("a",details=event)
    if event["step"] == 2: os._exit(73)
run(2248000,"ESTIMATED_STATE_CBF_BRAKE",{"name":"test","velocity_scale":1.,"missing_velocity":False},10,on_event=callback)
'''
    completed = subprocess.run([sys.executable, "-c", code, str(path)], env=os.environ.copy(), check=False)
    assert completed.returncode == 73
    evidence = inspect(path)
    assert evidence["state"] == "INCOMPLETE" and evidence["event_counts"] == {"a": 3}
    assert evidence["assignments"]["a"] == "STARTED"
