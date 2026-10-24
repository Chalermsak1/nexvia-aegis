from __future__ import annotations

import numpy as np

from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld, WorldConfig
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v5.recovery_controller import SafeRecoveryController


class AegisAgentV5:
    """
    Closed-Loop Physical AI Agent with Online Cross-Modal Recalibration (AEGIS V5.0).
    """

    def __init__(
        self,
        world_config: WorldConfig | None = None,
        estimation_method: str = "HUBER",
        enforce_observability: bool = True,
        enforce_validation: bool = True,
        target_tolerance: float = 0.18,
    ):
        self.world = AegisPhysicalWorld(world_config)
        self.verifier = VerificationController()
        self.recovery_controller = SafeRecoveryController(
            estimation_method=estimation_method,
            enforce_observability=enforce_observability,
            enforce_validation=enforce_validation,
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

        decisions = {}
        calibrated_occurred = False
        final_cal_bias = None

        for _ in range(self.world.config.max_steps):
            state = self.world.state()
            true_delta = state["target_pos"] - state["robot_pos"]

            read_a = self.sensor_a.measure(true_delta, rng, step=state["step"])
            read_b = self.sensor_b.measure(true_delta, rng, step=state["step"])
            read_r = self.range_sensor.measure(state["distance"], rng)

            verification = self.verifier.verify([read_a, read_b], read_r)

            force_action, decision_type, cal_res, cal_vector = (
                self.recovery_controller.update(
                    reading_a=read_a,
                    reading_b=read_b,
                    range_reading=read_r,
                    verification_status=verification.status,
                    step=state["step"],
                )
            )

            decisions[decision_type] = decisions.get(decision_type, 0) + 1
            if cal_res and cal_res.status == "CALIBRATED":
                calibrated_occurred = True
                final_cal_bias = cal_res.bias.copy()

            if decision_type == "STOP":
                break
            elif decision_type == "ABSTAIN":
                break

            world_state = self.world.step(force_action, rng)
            if world_state["terminated"] or world_state["truncated"]:
                break

        final_state = self.world.state()
        final_dist = float(final_state["distance"])
        success = final_dist <= self.world.config.success_radius
        self.world.close()

        return {
            "success": success,
            "final_distance": final_dist,
            "steps": final_state["step"],
            "decisions": decisions,
            "calibrated": calibrated_occurred,
            "estimated_bias": final_cal_bias,
        }
