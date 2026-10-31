import pytest
from scripts.research.development_ledger import DevelopmentLedger
from scripts.research.analyze_recovery_monitor_ledger import analyze


def assignment(identifier, seed, arm="AEGIS_3D_RECOVERY_MONITOR"):
    return {"id": identifier, "seed": seed, "bias_xyz": [0., 0., 0.], "controller": arm, "post_stop_steps": 1, "max_steps": 3,
            "case": {"name": "nominal", "range_bias_m": 0., "range_dropout_probability": 0.},
            "source_sha256": {"source": "a" * 64}}


def episode(seed=1):
    return {"controller": "AEGIS_3D_RECOVERY_MONITOR", "seed": seed, "true_success": 0, "false_arrival": 0,
            "abstained": 1, "timeout": 0, "collision_occurred": 0, "range_bias_m": 0.,
            "range_dropout_probability": 0., "steps": 3, "postproposal_monitor_steps": 2,
            "postproposal_monitor_reason": "POSTPROPOSAL_MONITOR_ALARM", "post_stop": None}


def test_analyzer_preserves_incomplete_assignments(tmp_path):
    path = tmp_path / "evidence.jsonl"
    assignments = [assignment("a", 1), assignment("b", 2), assignment("c", 1, "AEGIS_3D_ANCHOR_RECOVERY"), assignment("d", 2, "AEGIS_3D_ANCHOR_RECOVERY")]
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=assignments) as w:
        w.start("a")
        w.complete("a", status="COMPLETED", details={"episode": episode(), "source_sha256_after": {"source": "a" * 64}})
    result = analyze(path)
    assert result["ledger_state"] == "INCOMPLETE"
    assert result["summary"][0]["assigned"] == 2
    assert result["summary"][0]["incomplete"] == 1
    assert result["summary"][0]["monitor_alarm_episodes"] == 1


@pytest.mark.parametrize("defect", ["outcome", "source", "identity", "fault", "monitor", "premature_timeout", "bad_hash", "malformed_post_stop", "missing_fault_count"])
def test_analyzer_rejects_contradictory_evidence(tmp_path, defect):
    path = tmp_path / "evidence.jsonl"
    a = assignment("a", 1)
    b = assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")
    e = episode()
    source_after = dict(a["source_sha256"])
    if defect == "outcome": e["true_success"] = 1
    if defect == "source": source_after["source"] = "b" * 64
    if defect == "identity": e["seed"] = 2
    if defect == "fault": e["range_bias_m"] = 0.1
    if defect == "monitor": e["postproposal_monitor_steps"] = 4
    if defect == "premature_timeout": e["abstained"] = 0; e["timeout"] = 1; e["steps"] = 1
    if defect == "bad_hash": a["source_sha256"] = {"source": "bad"}; source_after = dict(a["source_sha256"])
    if defect == "malformed_post_stop":
        e["abstained"] = 0; e["true_success"] = 1; e["post_stop"] = {"steps": [{"wrong": 1}]}
    if defect == "missing_fault_count":
        a["case"]["fail_vectors_after_stop_proposal"] = True
        b["case"]["fail_vectors_after_stop_proposal"] = True
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=[a, b]) as w:
        w.start("a")
        w.complete("a", status="COMPLETED", details={"episode": e, "source_sha256_after": source_after})
        w.start("b")
        w.complete("b", status="ERROR", details={"reason": "synthetic"})
        w.finalize()
    with pytest.raises(ValueError): analyze(path)


@pytest.mark.parametrize("defect", ["unpaired", "case_config"])
def test_unpaired_or_inconsistent_declared_grid_rejected(tmp_path, defect):
    path = tmp_path / "evidence.jsonl"
    items = [assignment("a", 1)]
    if defect == "case_config":
        other = assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")
        other["case"]["range_bias_m"] = .2
        items.append(other)
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=items):
        pass
    with pytest.raises(ValueError): analyze(path)


@pytest.mark.parametrize("defect", ["missing_event", "wrong_tail", "wrong_step", "wrong_type"])
def test_incremental_evidence_contradictions_are_rejected(tmp_path, defect):
    path = tmp_path / "evidence.jsonl"
    a = assignment("a", 1)
    b = assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")
    records = [{"step": 0}, {"step": 1}, {"step": 2}]
    if defect == "wrong_step":
        records[1]["step"] = 4
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=[a, b], record_events=True) as w:
        w.start("a")
        for item in records[:2] if defect == "missing_event" else records:
            w.event("a", details={"type": "OTHER" if defect == "wrong_type" else "PRE_PHYSICS_DECISION", "record": item})
        tail = [{"step": 99}] if defect == "wrong_tail" else records
        w.complete("a", status="COMPLETED", details={"episode": episode(), "last_events": tail,
            "source_sha256_after": a["source_sha256"]})
        w.start("b")
        w.complete("b", status="ERROR", details={"reason": "synthetic"})
        w.finalize()
    with pytest.raises(ValueError):
        analyze(path)


@pytest.mark.parametrize("defect", ["horizon", "runtime", "source", "method", "missing_method", "null_method", "seed_bool", "bias_bool", "fault_bool"])
def test_assignment_pair_and_method_metadata_rejected(tmp_path, defect):
    path = tmp_path / "metadata.jsonl"
    items = [assignment("a", 1), assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")]
    for item in items:
        item["navigation_force_method"] = "AXIS_CLIP"
    if defect == "horizon": items[1]["max_steps"] += 1
    if defect == "runtime": items[1]["runtime"] = {"python": "different"}
    if defect == "source": items[1]["source_sha256"] = {"source": "b" * 64}
    if defect == "method": items[1]["navigation_force_method"] = "DIRECTION_PRESERVING_PEAK"
    if defect == "missing_method": del items[1]["navigation_force_method"]
    if defect == "null_method":
        for item in items: item["navigation_force_method"] = None
    if defect == "seed_bool": items[1]["seed"] = True
    if defect == "bias_bool": items[1]["bias_xyz"][0] = False
    if defect == "fault_bool": items[1]["case"]["range_bias_m"] = False
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=items):
        pass
    with pytest.raises(ValueError):
        analyze(path)


@pytest.mark.parametrize("defect", [None, "missing_mode", "missing_flag", "bad_flag", "bad_method", "bad_phase", "verify_transform", "eligible_untransformed", "nonfinite", "bool_vector", "untransformed_action", "bool_step", "wrong_direction", "zero_action"])
def test_force_event_scope_and_identity(tmp_path, defect):
    path = tmp_path / "force.jsonl"
    items = [assignment("a", 1), assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")]
    for item in items:
        item["navigation_force_method"] = "DIRECTION_PRESERVING_PEAK"
    events = [{"step": step, "navigation_force_method": "DIRECTION_PRESERVING_PEAK",
               "navigation_force_transformed": True, "phase_before": "BASE", "phase_after": "BASE",
               "mode": "NOMINAL", "decision": "NAVIGATE", "effective_decision": "NAVIGATE",
               "action": [1., 2., 0.], "original_action": [1., 2., 0.], "nav_vector": [1., 2., 0.]}
              for step in range(3)]
    event = events[0]
    if defect == "missing_mode": del event["mode"]
    if defect == "missing_flag": del event["navigation_force_transformed"]
    if defect == "bad_flag": event["navigation_force_transformed"] = 1
    if defect == "bad_method": event["navigation_force_method"] = "AXIS_CLIP"
    if defect == "bad_phase": event["phase_after"] = "RECOVERY"
    if defect == "verify_transform": event["decision"] = "VERIFY"
    if defect == "eligible_untransformed": event["navigation_force_transformed"] = False
    if defect == "nonfinite": event["action"][0] = float("nan")
    if defect == "bool_vector": event["action"][0] = True
    if defect == "bool_step": event["step"] = False
    if defect == "wrong_direction": event["action"][0] = -.5
    if defect == "zero_action": event["action"] = [0., 0., 0.]
    if defect == "untransformed_action":
        event["phase_before"] = event["phase_after"] = "RECOVERY"
        event["navigation_force_transformed"] = False
        event["action"][0] = .5
    e = episode()
    e["navigation_force_method"] = "DIRECTION_PRESERVING_PEAK"
    # NaN is rejected by the ledger writer itself, so use infinity-free
    # corruption for analyzer tests; finite validation is tested directly.
    if defect == "nonfinite":
        from scripts.research.analyze_recovery_monitor_ledger import validate_force_event
        with pytest.raises(ValueError):
            validate_force_event(event, "DIRECTION_PRESERVING_PEAK")
        return
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=items, record_events=True) as ledger:
        ledger.start("a")
        for event in events:
            ledger.event("a", details={"type": "PRE_PHYSICS_DECISION", "record": event})
        ledger.complete("a", status="COMPLETED", details={"episode": e, "last_events": events,
            "source_sha256_after": items[0]["source_sha256"]})
        ledger.start("b")
        ledger.complete("b", status="ERROR", details={"reason": "synthetic"})
        ledger.finalize()
    if defect is None:
        assert analyze(path)["ledger_state"] == "FINALIZED_WITH_ERRORS"
    else:
        with pytest.raises(ValueError):
            analyze(path)


@pytest.mark.parametrize("defect", ["mixed", "missing", "zero", "negative", "bool", "null"])
def test_invalid_or_mixed_explicit_recovery_budgets(tmp_path, defect):
    path = tmp_path / "budget.jsonl"
    items = [assignment("a", 1), assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")]
    for item in items: item["recovery_steps_limit"] = 100
    if defect == "mixed": items[1]["recovery_steps_limit"] = 300
    if defect == "missing": del items[1]["recovery_steps_limit"]
    if defect in ("zero", "negative", "bool", "null"):
        for item in items: item["recovery_steps_limit"] = {"zero": 0, "negative": -1, "bool": True, "null": None}[defect]
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=items):
        pass
    with pytest.raises(ValueError):
        analyze(path)


@pytest.mark.parametrize("defect", [None, "wrong_result", "missing_result", "bool_result", "missing_counter", "bool_counter", "negative_counter", "exceeded_counter"])
def test_recovery_budget_results_and_transition_counters(tmp_path, defect):
    path = tmp_path / "transition.jsonl"
    items = [assignment("a", 1), assignment("b", 1, "AEGIS_3D_ANCHOR_RECOVERY")]
    for item in items: item["recovery_steps_limit"] = 100
    e = episode()
    e["recovery_steps_limit"] = 100
    events = [{"step": step, "recovery_steps": step, "stabilization_wait_steps": 0, "missing_velocity_count": 0} for step in range(3)]
    if defect == "wrong_result": e["recovery_steps_limit"] = 300
    if defect == "missing_result": del e["recovery_steps_limit"]
    if defect == "bool_result": e["recovery_steps_limit"] = True
    if defect == "missing_counter": del events[0]["recovery_steps"]
    if defect == "bool_counter": events[0]["missing_velocity_count"] = False
    if defect == "negative_counter": events[0]["stabilization_wait_steps"] = -1
    if defect == "exceeded_counter": events[-1]["recovery_steps"] = 102
    with DevelopmentLedger.create(path, study="V9-M5 exploratory recovery monitor", assignments=items, record_events=True) as ledger:
        ledger.start("a")
        for event in events:
            ledger.event("a", details={"type": "PRE_PHYSICS_DECISION", "record": event})
        ledger.complete("a", status="COMPLETED", details={"episode": e, "last_events": events,
            "source_sha256_after": items[0]["source_sha256"]})
        ledger.start("b")
        ledger.complete("b", status="ERROR", details={"reason": "synthetic"})
        ledger.finalize()
    if defect is None:
        assert analyze(path)["ledger_state"] == "FINALIZED_WITH_ERRORS"
    else:
        with pytest.raises(ValueError):
            analyze(path)
