from __future__ import annotations

import numpy as np

from aegis.v3.control.verification_controller import (
    VerificationController,
)
from aegis.v3.env.world import (
    AegisPhysicalWorld,
    WorldConfig,
)
from aegis.v3.policies.policy import (
    AegisPolicyV3,
)
from aegis.v3.sensors.cross_modal import (
    RangeSensor,
)
from aegis.v3.sensors.sensors import (
    FaultInjectableSensor,
    SensorConfig,
)


class AegisAgentV3:
    """
    Closed-loop Nexvia Aegis 3.0 agent.

    Ground truth is used only by the simulation world
    to generate sensor measurements.

    The decision layer receives sensor evidence only.
    """

    def __init__(
        self,
        world_config: WorldConfig | None = None,
    ):
        self.world = AegisPhysicalWorld(
            world_config
        )

        self.sensor_a = FaultInjectableSensor(
            SensorConfig(
                name="vector_a",
                noise_sigma=0.05,
            )
        )

        self.sensor_b = FaultInjectableSensor(
            SensorConfig(
                name="vector_b",
                noise_sigma=0.05,
            )
        )

        self.range_sensor = RangeSensor(
            noise_sigma=0.05
        )

        self.verifier = VerificationController()

        self.policy = AegisPolicyV3()

    def _sense(
        self,
        rng: np.random.Generator,
    ):
        state = self.world.state()

        true_delta = (
            state["target_pos"]
            - state["robot_pos"]
        )

        readings = [
            self.sensor_a.measure(
                true_delta,
                rng,
                step=state["step"],
            ),
            self.sensor_b.measure(
                true_delta,
                rng,
                step=state["step"],
            ),
        ]

        range_reading = self.range_sensor.measure(
            state["distance"],
            rng,
        )

        verification = self.verifier.verify(
            readings,
            range_reading,
        )

        return verification

    @staticmethod
    def _move_toward(
        estimate: np.ndarray,
    ) -> np.ndarray:

        norm = float(
            np.linalg.norm(estimate)
        )

        if norm <= 1e-8:
            return np.zeros(
                2,
                dtype=np.float64,
            )

        return estimate / norm

    @staticmethod
    def _recovery_action(
        estimate: np.ndarray,
    ) -> np.ndarray:

        direction = AegisAgentV3._move_toward(
            estimate
        )

        # Small retreat / probing action.
        return -0.35 * direction

    def run_episode(
        self,
        seed: int = 42,
    ) -> dict:

        rng = np.random.default_rng(seed)

        self.policy.reset()

        initial = self.world.reset(rng)

        total_reward = 0.0

        decisions = {
            "ACT": 0,
            "VERIFY": 0,
            "ABSTAIN": 0,
            "RECOVER": 0,
        }

        recovery_count = 0
        post_action_checks = 0
        progress_failures = 0

        previous_estimated_distance = None

        print("=== NEXVIA AEGIS 3.0 ===")
        print("target:", initial["target_pos"])
        print(
            "initial distance:",
            initial["distance"],
        )

        for _ in range(
            self.world.config.max_steps
        ):

            verification = self._sense(rng)

            estimated_distance = float(
                np.linalg.norm(
                    verification.estimate
                )
            )

            decision = self.policy.decide(
                verification
            )

            decisions[decision.action] += 1

            print(
                f"step="
                f"{self.world.step_count + 1:03d} "
                f"status="
                f"{verification.status:<22} "
                f"confidence="
                f"{verification.confidence:.3f} "
                f"decision="
                f"{decision.action:<7} "
                f"estimate="
                f"{estimated_distance:.3f}"
            )

            if decision.action == "ACT":
                action = self._move_toward(
                    verification.estimate
                )

                if (
                    previous_estimated_distance
                    is not None
                ):
                    post_action_checks += 1

                    if (
                        estimated_distance
                        > previous_estimated_distance
                        + 0.05
                    ):
                        progress_failures += 1

                previous_estimated_distance = (
                    estimated_distance
                )

            elif decision.action == "VERIFY":
                # Hold position and acquire
                # fresh evidence on the next cycle.
                action = np.zeros(
                    2,
                    dtype=np.float64,
                )

            elif decision.action == "ABSTAIN":
                # Safe hold.
                action = np.zeros(
                    2,
                    dtype=np.float64,
                )

            else:
                recovery_count += 1

                action = self._recovery_action(
                    verification.estimate
                )

                previous_estimated_distance = None

            state = self.world.step(
                action,
                rng,
            )

            total_reward += -0.01 * float(
                np.linalg.norm(action)
            )

            if state["terminated"]:
                total_reward += 1.0
                break

            if state["truncated"]:
                break

        final_state = self.world.state()

        result = {
            "success": bool(
                final_state["distance"]
                <= self.world.config.success_radius
            ),
            "steps": int(
                final_state["step"]
            ),
            "initial_distance": float(
                initial["distance"]
            ),
            "final_distance": float(
                final_state["distance"]
            ),
            "reward": total_reward,
            "decisions": decisions,
            "recovery_count": recovery_count,
            "post_action_checks": post_action_checks,
            "progress_failures": progress_failures,
        }

        self.world.close()

        print("\n=== FINAL ===")
        print("success:", result["success"])
        print("steps:", result["steps"])
        print(
            "final distance:",
            result["final_distance"],
        )
        print("decisions:", result["decisions"])
        print(
            "recoveries:",
            result["recovery_count"],
        )
        print(
            "progress failures:",
            result["progress_failures"],
        )

        return result
