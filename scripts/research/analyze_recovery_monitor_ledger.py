#!/usr/bin/env python3
"""Validate a development ledger and summarize assigned recovery outcomes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import itertools

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.development_ledger import inspect
from scripts.research.evidence_integrity import validate_source_maps


FORCE_METHODS = ("AXIS_CLIP", "DIRECTION_PRESERVING_PEAK")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_transition_counters(event, budget):
    names = ("recovery_steps", "stabilization_wait_steps", "missing_velocity_count")
    if budget is None and not any(name in event for name in names):
        return  # Historical counters remain unknown, not inferred as zero.
    if any(type(event.get(name)) is not int or event[name] < 0 for name in names):
        raise ValueError("missing or invalid transition counters")
    if budget is not None and event["recovery_steps"] > budget + 1:
        raise ValueError("recovery counter exceeds registered timeout transition")


def validate_force_event(event, method):
    fields = {"navigation_force_method", "navigation_force_transformed", "phase_before", "phase_after", "original_action"}
    if method is None and not fields.intersection(event):
        return  # Historical traces predate this opt-in instrumentation.
    if method not in FORCE_METHODS:
        raise ValueError("force event method was not assigned")
    if not fields.issubset(event) or event["navigation_force_method"] != method:
        raise ValueError("missing or inconsistent navigation force instrumentation")
    if type(event["navigation_force_transformed"]) is not bool:
        raise ValueError("invalid navigation force transformation flag")
    for label in ("mode", "decision", "effective_decision", "phase_before", "phase_after"):
        if not isinstance(event.get(label), str) or not event[label]:
            raise ValueError("missing navigation decision scope")
    eligible = (method == "DIRECTION_PRESERVING_PEAK" and event["phase_before"] == "BASE"
                and event["phase_after"] == "BASE" and event["decision"] in ("NAVIGATE", "PROBE"))
    if event["navigation_force_transformed"] != eligible:
        raise ValueError("navigation force transformation outside declared scope")
    vectors = {}
    for name in ("action", "original_action", "nav_vector"):
        vector = event.get(name)
        if not isinstance(vector, list) or len(vector) != 3 or not all(finite(x) for x in vector):
            raise ValueError("invalid navigation force vector")
        vectors[name] = vector
    if not eligible and vectors["action"] != vectors["original_action"]:
        raise ValueError("untransformed action differs from original")
    if eligible:
        action_norm, nav_norm = math.hypot(*vectors["action"]), math.hypot(*vectors["nav_vector"])
        if not math.isfinite(action_norm) or not math.isfinite(nav_norm):
            raise ValueError("invalid navigation vector magnitude")
        if (action_norm == 0) != (nav_norm == 0):
            raise ValueError("transformed direction vanished or appeared")
        if nav_norm and any(not math.isclose(a / action_norm, n / nav_norm, rel_tol=1e-10, abs_tol=1e-10)
                            for a, n in zip(vectors["action"], vectors["nav_vector"])):
            raise ValueError("transformed action does not preserve direction")


def analyze(path):
    path = Path(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    ledger = inspect(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError("ledger changed during inspection")
    header = ledger["records"][0]
    if header["study"] != "V9-M5 exploratory recovery monitor":
        raise ValueError("unexpected development study")
    assignments = {}
    scientific_keys = set()
    groups = {}
    case_configs = {}
    paired_metadata = {}
    budget_presence = {"recovery_steps_limit" in a for a in header["assignments"]}
    if len(budget_presence) != 1:
        raise ValueError("mixed legacy and explicit recovery budgets")
    budgets = {a.get("recovery_steps_limit") for a in header["assignments"]}
    if len(budgets) != 1 or (budget_presence == {True} and any(type(b) is not int or b <= 0 for b in budgets)):
        raise ValueError("mixed or invalid recovery budgets")
    method_presence = {"navigation_force_method" in a for a in header["assignments"]}
    if len(method_presence) != 1:
        raise ValueError("mixed legacy and explicit force assignments")
    methods = {a.get("navigation_force_method") for a in header["assignments"]}
    if len(methods) != 1 or (method_presence == {True} and not methods.issubset(FORCE_METHODS)):
        raise ValueError("mixed or unsupported navigation force methods")
    for a in header["assignments"]:
        case, arm, seed, bias = a["case"]["name"], a["controller"], a["seed"], tuple(a["bias_xyz"])
        if type(seed) is not int or seed < 0 or len(bias) != 3 or not all(finite(x) for x in bias):
            raise ValueError("invalid assignment seed or bias")
        if any(type(a.get(name)) is not int or a[name] <= 0 for name in ("max_steps", "post_stop_steps")):
            raise ValueError("invalid assignment horizon")
        fault = a["case"]
        if (not finite(fault.get("range_bias_m")) or not finite(fault.get("range_dropout_probability"))
                or not 0 <= fault["range_dropout_probability"] <= 1
                or ("fail_vectors_after_stop_proposal" in fault and type(fault["fail_vectors_after_stop_proposal"]) is not bool)):
            raise ValueError("invalid assigned fault configuration")
        pair = (case, seed, bias)
        metadata = {name: a.get(name) for name in ("max_steps", "post_stop_steps", "runtime", "source_sha256", "navigation_force_method", "recovery_steps_limit")}
        if pair in paired_metadata and paired_metadata[pair] != metadata:
            raise ValueError("paired source, runtime, horizon or force method differs")
        paired_metadata[pair] = metadata
        key = (case, seed, bias, arm)
        if case in case_configs and case_configs[case] != a["case"]:
            raise ValueError("inconsistent configuration for case")
        case_configs[case] = a["case"]
        if key in scientific_keys or arm not in ("AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR"):
            raise ValueError("duplicate or unexpected assignment")
        scientific_keys.add(key)
        assignments[a["id"]] = a
        group = groups.setdefault((case, bias, arm), {"assigned": 0, "completed": 0, "error": 0, "incomplete": 0,
            "true_success": 0, "false_arrival": 0, "abstained": 0, "timeout": 0,
            "collision_occurred": 0, "monitor_steps": 0, "monitor_alarm_episodes": 0,
            "vector_fault_triggered_episodes": 0, "vector_fault_then_stop": 0, "vector_fault_then_abstain": 0})
        group["assigned"] += 1
    seeds = {a["seed"] for a in assignments.values()}
    biases = {tuple(a["bias_xyz"]) for a in assignments.values()}
    expected = set(itertools.product(case_configs, seeds, biases, ("AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR")))
    if scientific_keys != expected:
        raise ValueError("assignment grid is incomplete or unpaired")
    terminal = {r["id"]: r for r in ledger["records"] if r["kind"] == "TERMINAL"}
    events = {assignment_id: [] for assignment_id in assignments}
    for record in ledger["records"]:
        if record["kind"] == "EVENT":
            details = record["details"]
            if set(details) != {"type", "record"} or details["type"] != "PRE_PHYSICS_DECISION" or not isinstance(details["record"], dict):
                raise ValueError("invalid incremental decision event")
            events[record["id"]].append(details["record"])
            validate_force_event(details["record"], assignments[record["id"]].get("navigation_force_method"))
            validate_transition_counters(details["record"], assignments[record["id"]].get("recovery_steps_limit"))
    for assignment_id, a in assignments.items():
        group = groups[(a["case"]["name"], tuple(a["bias_xyz"]), a["controller"])]
        record = terminal.get(assignment_id)
        if record is None:
            group["incomplete"] += 1
            continue
        if record["status"] == "ERROR":
            group["error"] += 1
            continue
        details = record["details"]
        validate_source_maps(a.get("source_sha256"), details.get("source_sha256_after"))
        episode = details["episode"]
        if type(episode.get("seed")) is not int:
            raise ValueError("invalid episode seed type")
        if "recovery_steps_limit" in a:
            if type(episode.get("recovery_steps_limit")) is not int or episode["recovery_steps_limit"] != a["recovery_steps_limit"]:
                raise ValueError("recovery budget differs from assignment")
            if not isinstance(details.get("last_events"), list) or not details["last_events"]:
                raise ValueError("missing recovery transition evidence")
            for event in details["last_events"]:
                validate_transition_counters(event, a["recovery_steps_limit"])
        elif "recovery_steps_limit" in episode:
            raise ValueError("episode recovery budget was not assigned")
        if "navigation_force_method" in a:
            if episode.get("navigation_force_method") != a["navigation_force_method"]:
                raise ValueError("navigation force method differs from assignment")
        elif "navigation_force_method" in episode:
            raise ValueError("episode force method was not assigned")
        if "navigation_force_method" in a:
            if not isinstance(details.get("last_events"), list) or not details["last_events"]:
                raise ValueError("missing force decision evidence")
            for event in details["last_events"]:
                validate_force_event(event, a["navigation_force_method"])
        if ledger["schema"].endswith("/2"):
            recorded = events[assignment_id]
            if len(recorded) != episode.get("steps") or recorded[-4:] != details.get("last_events"):
                raise ValueError("incremental decision events differ from terminal evidence")
            if any(type(event.get("step")) is not int or event.get("step") != index for index, event in enumerate(recorded)):
                raise ValueError("incremental decision steps are not consecutive")
        if episode["controller"] != a["controller"] or episode["seed"] != a["seed"]:
            raise ValueError("episode identity differs from assignment")
        if (type(a.get("max_steps")) is not int or a["max_steps"] <= 0
                or type(episode.get("steps")) is not int or not 1 <= episode["steps"] <= a["max_steps"]):
            raise ValueError("invalid episode step count")
        outcome_names = ("true_success", "false_arrival", "abstained", "timeout")
        outcomes = [episode.get(name) for name in outcome_names]
        if any(type(x) is not int or x not in (0, 1) for x in outcomes) or sum(outcomes) != 1:
            raise ValueError("invalid episode outcome")
        if episode["timeout"] and episode["steps"] != a["max_steps"]:
            raise ValueError("timeout before assigned horizon")
        if type(episode.get("collision_occurred")) is not int or episode["collision_occurred"] not in (0, 1):
            raise ValueError("invalid collision flag")
        if not finite(episode.get("range_bias_m")) or not finite(episode.get("range_dropout_probability")) or episode.get("range_bias_m") != a["case"]["range_bias_m"] or episode.get("range_dropout_probability") != a["case"]["range_dropout_probability"]:
            raise ValueError("episode fault does not match assignment")
        if a["case"].get("fail_vectors_after_stop_proposal", False):
            loss_steps = episode.get("injected_vector_loss_steps")
            if type(loss_steps) is not int or not 0 <= loss_steps <= episode["steps"]:
                raise ValueError("missing or invalid vector-loss accounting")
            if loss_steps:
                group["vector_fault_triggered_episodes"] += 1
                group["vector_fault_then_stop"] += episode["true_success"] + episode["false_arrival"]
                group["vector_fault_then_abstain"] += episode["abstained"]
        post = episode.get("post_stop")
        if bool(post) != bool(episode["true_success"] or episode["false_arrival"]):
            raise ValueError("post-stop evidence contradicts outcome")
        if post and (not isinstance(post, dict) or not isinstance(post.get("steps"), list) or len(post["steps"]) != a["post_stop_steps"]):
            raise ValueError("incomplete post-stop evidence")
        if post:
            for value in (post.get("decision_distance"), post.get("decision_speed")):
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("invalid post-stop decision state")
            for sample in post["steps"]:
                if not isinstance(sample, dict) or type(sample.get("collision")) is not bool:
                    raise ValueError("invalid post-stop sample")
                for value in (sample.get("distance"), sample.get("speed")):
                    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                        raise ValueError("invalid post-stop position or speed")
                residual = sample.get("cbf_residual")
                if residual is not None and (type(residual) not in (int, float) or not math.isfinite(residual)):
                    raise ValueError("invalid post-stop residual")
        group["completed"] += 1
        for name, value in zip(outcome_names, outcomes):
            group[name] += value
        group["collision_occurred"] += episode["collision_occurred"]
        if a["controller"] == "AEGIS_3D_RECOVERY_MONITOR":
            steps = episode.get("postproposal_monitor_steps")
            if type(steps) is not int or steps < 0 or steps > episode["steps"]:
                raise ValueError("invalid monitoring step count")
            group["monitor_steps"] += steps
            group["monitor_alarm_episodes"] += int(episode.get("postproposal_monitor_reason") == "POSTPROPOSAL_MONITOR_ALARM")
    return {"input_sha256": before, "ledger_state": ledger["state"], "integrity": ledger["integrity"],
            "summary": [{"case": k[0], "bias_xyz": list(k[1]), "controller": k[2], **v} for k, v in groups.items()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = analyze(args.input)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
