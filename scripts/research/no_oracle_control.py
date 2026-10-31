#!/usr/bin/env python3
"""Experimental estimate-only force calculation; not integrated or safety-rated.

This module does not call AegisMuJoCo3DEnvironment.step: that method currently
passes simulator ground-truth position/velocity into its CBF. A consumer must
not treat this command generator as an actuator driver or certified controller.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from aegis.v9.velocity_freshness_candidate import TimedVelocity, VelocityFreshness


@dataclass(frozen=True)
class EstimatedState:
    """Position and velocity from the same simulated measurement timestamp.

    Caller-supplied metadata is neither authenticated nor evidence of physical
    accuracy. The caller must put position and velocity in the same frame.
    """

    position: object
    velocity: object
    sequence: int
    acquired_seconds: float


def _vector(value):
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return None
    if vector.shape != (3,) or not np.isfinite(vector).all():
        return None
    return vector.copy()


class EstimateOnlyControl:
    """Compute desired and projected forces using only an estimated state.

    The provided projector is an injected simulator component. Both its CBF
    state and our damping/braking use the supplied estimate. There is no claim
    that the estimate, CBF projection, or resulting command is safe.
    """

    def __init__(self, *, mass=1.0, force_limit=2.0, damping=0.5, max_age_seconds=0.01):
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
               for v in (mass, force_limit, damping)) or mass <= 0 or force_limit <= 0 or damping < 0:
            raise ValueError("invalid mass, force limit, or damping")
        self.mass = float(mass)
        self.force_limit = float(force_limit)
        self.damping = float(damping)
        self.gate = VelocityFreshness(max_age_seconds)

    def reset(self):
        self.gate.reset()

    def command(self, estimate, *, now_seconds, mode, projector, obstacles=(), action=None):
        """Return a proposed force or NO_COMMAND; never take a truth parameter.

        NAVIGATE uses ``action - damping * velocity``; BRAKE uses a dissipative
        desired force based on estimated velocity. Missing, stale or malformed
        evidence causes NO_COMMAND. NO_COMMAND is not itself a braking action.
        A downstream operational system would require an independent fallback.
        """
        if mode not in ("NAVIGATE", "BRAKE"):
            return {"status": "NO_COMMAND", "reason": "INVALID_MODE"}
        if not isinstance(estimate, EstimatedState):
            return {"status": "NO_COMMAND", "reason": "MISSING_STATE"}
        position = _vector(estimate.position)
        desired_action = _vector(action) if mode == "NAVIGATE" else None
        if position is None or (mode == "NAVIGATE" and desired_action is None):
            return {"status": "NO_COMMAND", "reason": "INVALID_INPUT"}
        velocity = self.gate.accept(TimedVelocity(estimate.velocity, estimate.sequence, estimate.acquired_seconds), now_seconds)
        if velocity is None:
            return {"status": "NO_COMMAND", "reason": self.gate.reason}

        if mode == "BRAKE":
            speed = float(np.linalg.norm(velocity))
            desired = (-velocity / speed * min(self.force_limit, 2.0 * self.mass * speed)
                       if speed > 1e-4 else np.zeros(3, dtype=float))
        else:
            desired = np.clip(desired_action - self.damping * velocity, -self.force_limit, self.force_limit)
        try:
            projected, active = projector.compute_safe_control(
                pos=position.copy(), vel=velocity.copy(), desired_u=desired.copy(),
                obstacles=list(obstacles), force_braking=False,
            )
        except Exception as exc:
            return {"status": "NO_COMMAND", "reason": "PROJECTOR_ERROR", "error_type": type(exc).__name__}
        projected = _vector(projected)
        if projected is None or np.any(np.abs(projected) > self.force_limit + 1e-8):
            return {"status": "NO_COMMAND", "reason": "INVALID_PROJECTED_FORCE"}
        return {"status": "COMMAND_PROPOSED", "desired_force": desired.tolist(),
                "projected_force": projected.tolist(), "barrier_active": bool(active),
                "velocity_source": "ESTIMATED", "projection_safety": "UNVERIFIED"}


class _IdentityProjector:
    """Synthetic no-obstacle projector for demonstrating inputs only."""

    def compute_safe_control(self, *, pos, vel, desired_u, obstacles, force_braking):
        if force_braking:
            raise AssertionError("the projector must not replace braking with truth")
        return desired_u.copy(), False


def demonstration():
    """Four analytic one-step fixtures; simulator truth is scoring only."""
    true_velocity = np.array([1.0, 0.0, 0.0])
    fixtures = (("accurate", [1., 0., 0.]), ("underreported", [.25, 0., 0.]),
                ("reversed", [-1., 0., 0.]), ("missing", None))
    rows = []
    for name, measured in fixtures:
        ctrl = EstimateOnlyControl()
        state = EstimatedState([0., 0., 1.], measured, 0, 0.) if measured is not None else None
        result = ctrl.command(state, now_seconds=0., mode="BRAKE", projector=_IdentityProjector())
        # Ground truth is evaluated after command selection, never used in it.
        force = result.get("projected_force")
        work = float(np.dot(force, true_velocity)) if force is not None else None
        rows.append({"fixture": name, "true_velocity_for_scoring": true_velocity.tolist(),
                     "measured_velocity": measured, "result": result,
                     "instantaneous_force_dot_true_velocity": work})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True, help="New development JSON; never overwrites")
    args = p.parse_args()
    payload = {"classification": "SYNTHETIC_ANALYTIC_FIXTURES", "not_a_holdout": True,
               "dt_seconds": None, "simulator_used": False, "fixtures": demonstration(),
               "source_sha256": {"scripts/research/no_oracle_control.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                 "src/aegis/v9/velocity_freshness_candidate.py": hashlib.sha256((ROOT / "src/aegis/v9/velocity_freshness_candidate.py").read_bytes()).hexdigest()}}
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
