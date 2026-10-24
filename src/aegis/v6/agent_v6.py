"""
NEXVIA AEGIS V6.0 — Closed-Loop Physical AI Agent.

Integrates:
- MuJoCo physical simulation world
- Dual vector sensors and independent scalar range sensor
- Multi-hypothesis diagnosis engine
- Active risk-constrained trajectory planning
- Certified recalibration and safe recovery controller
"""

from __future__ import annotations

import numpy as np

from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld, WorldConfig
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v6.recovery_controller import AegisV6RecoveryController
from aegis.v6.trajectory_planner import ProbingStrategy


class AegisAgentV6:
    """
    Closed-Loop Physical AI Agent for AEGIS V6.0.
    """

    def __init__(
        self,
        world_config: WorldConfig | None = None,
        strategy: ProbingStrategy = ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
        enable_multi_hypothesis: bool = True,
        enforce_observability_gate: bool = True,
        enforce_validation_gate: bool = True,
        enforce_risk_constraints: bool = True,
        probing_steps: int = 32,
        probing_force: float = 0.85,
        target_tolerance: float = 0.18,
    ):
        self.world = AegisPhysicalWorld(world_config)
        self.verifier = VerificationController()
        self.recovery_controller = AegisV6RecoveryController(
            strategy=strategy,
            enable_multi_hypothesis=enable_multi_hypothesis,
            enforce_observability_gate=enforce_observability_gate,
            enforce_validation_gate=enforce_validation_gate,
            enforce_risk_constraints=enforce_risk_constraints,
            probing_steps=probing_steps,
            probing_force=probing_force,
            target_tolerance=target_tolerance,
        )

        self.sensor_a = FaultInjectableSensor(
            SensorConfig(name="vector_a", noise_sigma=0.05)
        )
        self.sensor_b = FaultInjectableSensor(
            SensorConfig(name="vector_b", noise_sigma=0.05)
        )
        self.range_sensor = RangeSensor(noise_sigma=0.05)

    def run_episode(self, seed: int = 42) -> dict:
        rng = np.random.default_rng(seed)
        self.recovery_controller.reset()
        initial = self.world.reset(rng)

        decisions: dict[str, int] = {}
        calibrated_occurred = False
        final_cal_bias = None
        probing_actions_count = 0
        last_report = None
        prev_pos = self.world.state()["robot_pos"].copy()
        distance_traveled = 0.0

        for _ in range(self.world.config.max_steps):
            state = self.world.state()
            true_delta = state["target_pos"] - state["robot_pos"]

            read_a = self.sensor_a.measure(true_delta, rng, step=state["step"])
            read_b = self.sensor_b.measure(true_delta, rng, step=state["step"])
            read_r = self.range_sensor.measure(state["distance"], rng)

            verification = self.verifier.verify([read_a, read_b], read_r)

            force_action, decision_type, diag_report, cal_vector = (
                self.recovery_controller.update(
                    reading_a=read_a,
                    reading_b=read_b,
                    range_reading=read_r,
                    verification_status=verification.status,
                    step=state["step"],
                    rng=rng,
                )
            )

            if diag_report is not None:
                last_report = diag_report

            if decision_type == "PROBE":
                probing_actions_count += 1

            decisions[decision_type] = decisions.get(decision_type, 0) + 1
            if self.recovery_controller.state.last_calibration and self.recovery_controller.state.last_calibration.status == "CALIBRATED":
                calibrated_occurred = True
                final_cal_bias = self.recovery_controller.state.active_bias.copy()

            if decision_type in ("STOP", "ABSTAIN"):
                break

            world_state = self.world.step(force_action, rng)
            new_pos = world_state["robot_pos"].copy()
            distance_traveled += float(np.linalg.norm(new_pos - prev_pos))
            prev_pos = new_pos

            if world_state["terminated"] or world_state["truncated"]:
                break

        final_state = self.world.state()
        final_dist = float(final_state["distance"])
        success = final_dist <= self.world.config.success_radius
        self.world.close()

        lead_h = last_report.leading_hypothesis.value if last_report else "H0_NOMINAL"
        entropy = last_report.entropy if last_report else 0.0
        reason = last_report.reason_code if last_report else "NO_DIAGNOSIS"

        return {
            "success": success,
            "final_distance": final_dist,
            "steps": final_state["step"],
            "decisions": decisions,
            "calibrated": calibrated_occurred,
            "estimated_bias": final_cal_bias,
            "probing_actions_count": probing_actions_count,
            "distance_traveled": distance_traveled,
            "leading_hypothesis": lead_h,
            "diagnostic_entropy": entropy,
            "reason_code": reason,
        }
