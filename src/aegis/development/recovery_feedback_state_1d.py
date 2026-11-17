"""Conditional DEVELOPMENT bounds from feedback; never an action authorizer.

Discrete, semi-implicit WORLD-X point-mass model in SI units, coherent integer
clock, static delay, post-cap actuator enqueue acknowledgements. Source labels
and boolean assumptions are assertions, not authentication or calibration.
"""
from copy import deepcopy
from fractions import Fraction
import re

from .recovery_envelope_1d import Interval, internal, point, spec
from .recovery_envelope_state_1d import assess_state, remaining_cut_window


class EvidenceConflict(ValueError):
    """No common state satisfies supplied observations and declared bounds."""


def _number(value):
    # Bound packet parsing BEFORE Fraction construction; scientific notation
    # is intentionally unsupported. The pre-existing model parser is unchanged.
    if type(value) is str:
        if not 0 < len(value) <= 80 or not re.fullmatch(
            r"[+-]?(?:[0-9]+/[0-9]+|[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", value
        ):
            raise ValueError("packet rational requires bounded decimal/fraction notation")
    elif type(value) is not int and not isinstance(value, Fraction):
        raise ValueError("packet rational rejects floats and booleans")
    return Interval(value, value).lo


def _bounds(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("two explicit packet bounds required")
    return Interval(_number(value[0]), _number(value[1]))


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError("exact record fields required: " + names)


def _tick(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError("nonnegative bounded integer epoch required")
    return value


def _label(value):
    if type(value) is not str or not value.strip() or len(value) > 128:
        raise ValueError("bounded nonempty source/clock label required")


def _record(row, fields, time_key, epoch, clock):
    _fields(row, fields)
    for key in (time_key, "received_tick"):
        _tick(row[key])
    if not row[time_key] <= row["received_tick"] <= epoch:
        raise ValueError("future observation, future receipt or receipt before event")
    _label(row["source_id"])
    if row["clock_id"] != clock or row["frame"] != "WORLD_X_SI":
        raise ValueError("unsupported clock or coordinate frame")


def _meet(left, right, label):
    if left is None:
        return right
    lo, hi = max(left.lo, right.lo), min(left.hi, right.hi)
    if lo > hi:
        raise EvidenceConflict(label)
    return internal(lo, hi)


def prepare_feedback(model, evidence, *, evidence_status,
                     measurement_bounds_asserted, actuator_model_asserted,
                     power_bounds_asserted, command_records_asserted,
                     clock_bounds_asserted):
    """Build current enclosure, FIFO bounds and remaining power budget.

    Old state bounds are transported under arbitrary per-step acceleration
    |a| <= (cap_max + disturbance)/mass_min. No assumption of zero force or
    ongoing braking is made. Old force packets are retained as unused evidence;
    only current force packets narrow [-cap_max, cap_max]. Missing FIFO slots
    keep that full bound. Contradiction never triggers a wider fallback.

    Flags assert the meaning/coverage of packet intervals, model, clock and
    acknowledged enqueue times. They do not supply an external trust anchor.
    max_state_age_ticks is an explicit resource limit, not a calibrated policy.
    """
    out = {
        "status": "UNKNOWN_INPUT", "model": None, "snapshot": None,
        "operational_authorization": False, "registered_criterion": False,
        "action": None, "future_position_containment": "NOT_ESTABLISHED",
        "trust": "CALLER_ASSERTIONS_NOT_AUTHENTICATED",
        "scope": "DEVELOPMENT_SAMPLED_1D_MODEL_ONLY",
    }
    try:
        flags = (measurement_bounds_asserted, actuator_model_asserted,
                 power_bounds_asserted, command_records_asserted, clock_bounds_asserted)
        if any(type(flag) is not bool for flag in flags):
            raise ValueError("explicit boolean assumptions required")
        if evidence_status not in ("COMPATIBLE_UNDER_ASSERTED_BOUNDS", "UNKNOWN", "CONTRADICTORY"):
            raise ValueError("invalid evidence status")
        if evidence_status != "COMPATIBLE_UNDER_ASSERTED_BOUNDS":
            out["status"] = "CONTRADICTORY_EVIDENCE" if evidence_status == "CONTRADICTORY" else "UNKNOWN_EVIDENCE"
            return out
        if not all(flags):
            out["status"] = "UNKNOWN_PHYSICAL_PREMISES"
            return out
        s = spec(model)
        _fields(evidence, "assessment_tick clock_id max_state_age_ticks state_observations force_observations commands power")
        epoch = _tick(evidence["assessment_tick"])
        clock = evidence["clock_id"]
        _label(clock)
        age_limit = evidence["max_state_age_ticks"]
        if type(age_limit) is not int or not 0 <= age_limit <= 64:
            raise ValueError("state transport resource limit must be integer 0..64")
        for key in ("state_observations", "force_observations", "commands"):
            if not isinstance(evidence[key], list) or len(evidence[key]) > 128:
                raise ValueError("bounded observation/command lists required")
        cap = internal(-s["cap"].hi, s["cap"].hi)
        accel = internal(-(s["cap"].hi + s["disturbance"]) / s["mass"].lo,
                         (s["cap"].hi + s["disturbance"]) / s["mass"].lo)
        position = velocity = None
        transported = []
        for row in evidence["state_observations"]:
            _record(row, "sample_tick received_tick clock_id frame source_id position velocity",
                    "sample_tick", epoch, clock)
            p, v = _bounds(row["position"]), _bounds(row["velocity"])
            age = epoch - row["sample_tick"]
            if age > age_limit:
                raise ValueError("state observation exceeds declared transport resource limit")
            # Sum the semi-implicit equations, allowing a different bounded
            # acceleration every tick. Both coefficients are nonnegative.
            elapsed = age * s["dt"]
            pn = p + point(elapsed) * v + point(s["dt"]**2 * age * (age + 1) / 2) * accel
            vn = v + point(elapsed) * accel
            position = _meet(position, pn, "transported position observations conflict")
            velocity = _meet(velocity, vn, "transported velocity observations conflict")
            transported.append({"source_id": row["source_id"], "sample_tick": row["sample_tick"],
                                "age_ticks": age, "position": pn.wire(), "velocity": vn.wire()})
        force = cap
        stale_force = []
        current_force_sources = []
        force_by_tick = {}
        for row in evidence["force_observations"]:
            _record(row, "sample_tick received_tick clock_id frame source_id force",
                    "sample_tick", epoch, clock)
            value = _bounds(row["force"])
            tick = row["sample_tick"]
            force_by_tick[tick] = _meet(force_by_tick.get(tick, cap), value,
                                        "force packets conflict at an epoch or with actuator cap")
            if row["sample_tick"] != epoch:
                stale_force.append({"source_id": row["source_id"], "sample_tick": row["sample_tick"],
                                    "reason": "STALE_FORCE_NOT_TRANSPORTED"})
                continue
            force = force_by_tick[tick]
            current_force_sources.append(row["source_id"])
        accepted = {}
        for row in evidence["commands"]:
            _record(row, "enqueue_tick received_tick clock_id frame source_id effective_target",
                    "enqueue_tick", epoch, clock)
            tick = row["enqueue_tick"]
            if tick >= epoch:
                raise ValueError("only previously enqueued commands belong to the starting FIFO")
            value = _bounds(row["effective_target"])
            if not value.inside(cap):
                raise ValueError("effective post-cap target interval exceeds declared cap domain")
            accepted[tick] = _meet(accepted.get(tick), value, "conflicting acknowledgements for one enqueue tick")
        queues, missing = {}, {}
        for delay in range(s["delay_ticks"][0], s["delay_ticks"][1] + 1):
            ticks = list(range(epoch - delay, epoch))
            queues[str(delay)] = [accepted.get(tick, cap).wire() for tick in ticks]
            missing[str(delay)] = [tick for tick in ticks if tick not in accepted]
        out["diagnostics"] = {
            "transported_state_observations": transported,
            "acceleration_transport_bound_m_s2": accel.wire(),
            "stale_force_observations_unused": stale_force,
            "current_force_sources": current_force_sources,
            "unknown_queue_ticks_by_delay": missing,
            "command_semantics": "EFFECTIVE_POST_CAP_TARGET_AT_ACTUATOR_ENQUEUE_ONE_TARGET_PER_TICK",
            "clock_semantics": "EXACT_SHARED_DISCRETE_EPOCH_ASSERTION_NO_JITTER_TRANSPORT",
            "force_bound": force.wire(),
        }
        if position is None:
            out.update(status="UNKNOWN_EVIDENCE", reason="no state observation; no reset state invented")
            return out
        power = evidence["power"]
        if power is None:
            out.update(status="UNKNOWN_EVIDENCE", reason="no absolute power cutoff bound")
            return out
        _fields(power, "absolute_cut_ticks received_tick clock_id source_id")
        _label(power["source_id"])
        if power["clock_id"] != clock or _tick(power["received_tick"]) > epoch:
            raise ValueError("power record has incompatible clock or future receipt")
        remaining = remaining_cut_window(power["absolute_cut_ticks"], epoch)
        out["diagnostics"]["remaining_power_cut_ticks"] = remaining
        absolute_lo, absolute_hi = power["absolute_cut_ticks"]
        # A force packet at endpoint t describes the previous delivered force.
        # Cut at t first affects the NEXT step. A cut strictly before t implies
        # that the last interval was unpowered (instant-zero model, no restore).
        zero = point(Fraction(0))
        for tick, value in force_by_tick.items():
            if absolute_hi < tick:
                _meet(value, zero, "force contradicts a certainly elapsed power cutoff")
        if absolute_hi < epoch:
            force = _meet(force, zero, "current force contradicts elapsed power cutoff")
            queues = {d: [zero.wire() for _ in queue] for d, queue in queues.items()}
            flush = "CERTAIN_PRIOR_UNPOWERED_STEP"
        elif absolute_lo < epoch:
            # Cut/window/queue correlation is intentionally lost by this hull.
            queues = {d: [[str(min(Fraction(x[0]), 0)), str(max(Fraction(x[1]), 0))]
                           for x in queue] for d, queue in queues.items()}
            flush = "POSSIBLE_PRIOR_UNPOWERED_STEP_ZERO_INCLUDED"
        else:
            flush = "NO_PRIOR_CUTOFF_IN_DECLARED_WINDOW"
        out["diagnostics"].update(power_flush_status=flush, force_bound=force.wire())
        prepared = deepcopy(model)
        # Beyond the finite horizon all cut times have the same dynamics.
        prepared.update(position=position.wire(), velocity=velocity.wire(),
                        power_cut_ticks=[min(tick, s["horizon"]) for tick in remaining])
        spec(prepared)
        out.update(status="READY_CONDITIONAL_INPUTS", model=prepared, snapshot={
            "mode": "EXPLICIT_INTERVALS", "assessment_tick": epoch,
            "state_bounds_tick": epoch, "actuator_bounds_tick": epoch,
            "force": force.wire(), "pending_by_delay": queues,
        })
    except EvidenceConflict as exc:
        out.update(status="CONTRADICTORY_EVIDENCE", reason=str(exc))
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        out.update(status="UNKNOWN_INPUT", reason=str(exc))
    return out


def assess_feedback(model, evidence, **assumptions):
    """Offline adapter; returns conditional analysis and never selects actions."""
    prepared = prepare_feedback(model, evidence, **assumptions)
    if prepared["status"] != "READY_CONDITIONAL_INPUTS":
        return {"preparation": prepared, "assessment": None,
                "conclusion": prepared["status"], "operational_authorization": False, "action": None}
    result = assess_state(prepared["model"], prepared["snapshot"],
                          evidence_status="COMPATIBLE_UNDER_ASSERTED_BOUNDS",
                          measurement_bounds_asserted=True, actuator_model_asserted=True,
                          power_bounds_asserted=True, actuator_state_bounds_asserted=True)
    return {"preparation": prepared, "assessment": result,
            "conclusion": result["conclusion"], "operational_authorization": False, "action": None}
