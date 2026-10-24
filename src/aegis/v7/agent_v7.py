"""
NEXVIA AEGIS V7.0 — Closed-Loop Physical AI Agent.

Integrates:
- MuJoCo physical simulation world
- Dual vector sensors and independent range sensor
- Intermittent independent sensor anchoring (AEGIS-Anchor)
- Multi-hypothesis diagnosis engine (H0–H6)
- Risk-constrained Model Predictive Control (MPC)
- Safe recovery controller
"""

from __future__ import annotations

import numpy as np

from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld, WorldConfig
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v7.anchor_sensor import AnchorSensor, AnchorSensorConfig
from aegis.v7.recovery_controller import AegisV7RecoveryController


class AegisAgentV7:
    """
    Closed-Loop Physical AI Agent for AEGIS V7.0.
    """

    def __init__(
        self,
        world_config: WorldConfig | None = None,
        use_mpc: bool = True,
        use_anchor: bool = True,
        unconditional_anchor: bool = False,
        generic_fim_only: bool = False,
        fixed_probe_only: bool = False,
        enforce_observability_gate: bool = True,
        enforce_validation_gate: bool = True,
        enforce_terminal_braking: bool = True,
        probing_steps: int = 32,
        target_tolerance: float = 0.25,
        anchor_config: AnchorSensorConfig | None = None,
    ):
        self.world = AegisPhysicalWorld(world_config)
        self.verifier = VerificationController()
        self.recovery_controller = AegisV7RecoveryController(
            use_mpc=use_mpc,
            use_anchor=use_anchor,
            unconditional_anchor=unconditional_anchor,
            generic_fim_only=generic_fim_only,
            fixed_probe_only=fixed_probe_only,
            enforce_observability_gate=enforce_observability_gate,
            enforce_validation_gate=enforce_validation_gate,
            enforce_terminal_braking=enforce_terminal_braking,
            probing_steps=probing_steps,
            target_tolerance=target_tolerance,
        )

        self.sensor_a = FaultInjectableSensor(
            SensorConfig(name="vector_a", noise_sigma=0.05)
        )
        self.sensor_b = FaultInjectableSensor(
            SensorConfig(name="vector_b", noise_sigma=0.05)
        )
        self.range_sensor = RangeSensor(noise_sigma=0.05)
        self.anchor_sensor = AnchorSensor(anchor_config)

    def run_episode(self, seed: int = 42) -> dict:
        rng = np.random.default_rng(seed)
        self.recovery_controller.reset()
        self.anchor_sensor.reset()
        initial = self.world.reset(rng)

        decisions: dict[str, int] = {}
        calibrated_occurred = False
        final_cal_bias = None
        probing_actions_count = 0
        last_report = None
        prev_pos = self.world.state()["robot_pos"].copy()
        distance_traveled = 0.0
        max_overshoot = 0.0

        query_anchor = False

        for _ in range(self.world.config.max_steps):
            state = self.world.state()
            true_delta = state["target_pos"] - state["robot_pos"]

            read_a = self.sensor_a.measure(true_delta, rng, step=state["step"])
            read_b = self.sensor_b.measure(true_delta, rng, step=state["step"])
            read_r = self.range_sensor.measure(state["distance"], rng)

            # Query anchor if requested on previous step
            read_anchor = self.anchor_sensor.measure(true_delta, rng, query=query_anchor)

            verification = self.verifier.verify([read_a, read_b], read_r)

            force_action, decision_type, diag_report, cal_vector, query_anchor = (
                self.recovery_controller.update(
                    reading_a=read_a,
                    reading_b=read_b,
                    range_reading=read_r,
                    anchor_reading=read_anchor,
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
            if (
                self.recovery_controller.state.last_calibration
                and self.recovery_controller.state.last_calibration.status == "CALIBRATED"
            ):
                calibrated_occurred = True
                final_cal_bias = self.recovery_controller.state.active_bias.copy()

            if decision_type in ("STOP", "ABSTAIN"):
                break

            world_state = self.world.step(force_action, rng)
            new_pos = world_state["robot_pos"].copy()
            distance_traveled += float(np.linalg.norm(new_pos - prev_pos))
            prev_pos = new_pos

            # Track maximum overshoot if robot gets close
            cur_dist = float(world_state["distance"])
            if cur_dist > self.world.config.success_radius and decision_type == "ACT":
                overshoot = max(0.0, self.world.config.success_radius - cur_dist)
                max_overshoot = max(max_overshoot, overshoot)

            if world_state["terminated"] or world_state["truncated"]:
                break

        final_state = self.world.state()
        final_dist = float(final_state["distance"])
        stopped = "STOP" in decisions and decisions["STOP"] > 0
        success = stopped and (final_dist <= 0.45)
        false_success = stopped and (final_dist > 0.45)
        abstain = "ABSTAIN" in decisions and decisions["ABSTAIN"] > 0
        self.world.close()

        lead_h = last_report.leading_hypothesis.value if last_report else "H0_NOMINAL"
        entropy = last_report.entropy if last_report else 0.0
        reason = last_report.reason_code if last_report else "NO_DIAGNOSIS"

        return {
            "success": success,
            "false_success": false_success,
            "abstain": abstain,
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
            "anchor_queries": self.anchor_sensor.total_queries,
            "anchor_cost": self.anchor_sensor.total_cost,
        }
