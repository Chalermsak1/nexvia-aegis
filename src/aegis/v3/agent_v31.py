from __future__ import annotations

import numpy as np

from aegis.v3.control.recovery import RecoveryManager
from aegis.v3.control.temporal_controller import (
    TemporalAwareVerificationController,
)
from aegis.v3.env.world import (
    AegisPhysicalWorld,
    WorldConfig,
)
from aegis.v3.policies.policy import AegisPolicyV3
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import (
    FaultInjectableSensor,
    SensorConfig,
)


class AegisAgentV31:
    """
    Nexvia Aegis 3.1 exploratory agent.

    Adds to v3.0:
        - temporal consistency
        - active recovery
        - hold / probe / retreat / escalate

    Ground truth is used only by the simulation world
    to generate synthetic sensor measurements.
    """

    def __init__(
        self,
        world_config: WorldConfig | None = None,
        primary_config: SensorConfig | None = None,
        verifier_config: SensorConfig | None = None,
        range_noise: float = 0.05,
        range_dropout: float = 0.0,
    ):
        self.world_config = (
            world_config or WorldConfig()
        )

        self.primary_config = (
            primary_config
            or SensorConfig(
                name="primary",
                noise_sigma=0.05,
            )
        )

        self.verifier_config = (
            verifier_config
            or SensorConfig(
                name="verifier",
                noise_sigma=0.05,
            )
        )

        self.range_noise = float(range_noise)
        self.range_dropout = float(range_dropout)

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

    def run_episode(
        self,
        seed: int = 42,
        verbose: bool = True,
    ) -> dict:

        rng = np.random.default_rng(seed)

        world = AegisPhysicalWorld(
            self.world_config
        )

        primary = FaultInjectableSensor(
            self.primary_config
        )

        verifier = FaultInjectableSensor(
            self.verifier_config
        )

        range_sensor = RangeSensor(
            noise_sigma=self.range_noise,
            dropout_probability=self.range_dropout,
        )

        verification = (
            TemporalAwareVerificationController()
        )

        policy = AegisPolicyV3()

        recovery = RecoveryManager()

        state = world.reset(rng)

        verification.reset()
        policy.reset()
        recovery.reset()

        previous_action = np.zeros(
            2,
            dtype=np.float64,
        )

        total_reward = 0.0
        success = False

        decisions = {
            "ACT": 0,
            "VERIFY": 0,
            "ABSTAIN": 0,
            "RECOVER": 0,
        }

        recovery_modes = {
            "HOLD": 0,
            "PROBE": 0,
            "RETREAT": 0,
            "ESCALATE": 0,
        }

        status_counts: dict[str, int] = {}

        unsafe_actions = 0
        temporal_failures = 0

        if verbose:
            print("=== NEXVIA AEGIS 3.1 ===")
            print("target:", state["target_pos"])
            print(
                "initial distance:",
                state["distance"],
            )

        for _ in range(
            self.world_config.max_steps
        ):
            state = world.state()

            true_delta = (
                state["target_pos"]
                - state["robot_pos"]
            )

            primary_reading = primary.measure(
                true_delta,
                rng,
                step=state["step"],
            )

            verifier_reading = verifier.measure(
                true_delta,
                rng,
                step=state["step"],
            )

            range_reading = range_sensor.measure(
                state["distance"],
                rng,
            )

            evidence = verification.verify(
                vector_readings=[
                    primary_reading,
                    verifier_reading,
                ],
                range_reading=range_reading,
                previous_action=previous_action,
            )

            status_counts[evidence.status] = (
                status_counts.get(
                    evidence.status,
                    0,
                )
                + 1
            )

            if not evidence.temporal_consistent:
                temporal_failures += 1

            decision = policy.decide(
                evidence
            )

            decisions[decision.action] += 1

            if decision.action == "ACT":
                action = self._move_toward(
                    evidence.estimate
                )

                # Successful return to verified operation
                # resets active recovery escalation.
                recovery.reset()

            elif decision.action in {
                "VERIFY",
                "ABSTAIN",
            }:
                action = np.zeros(
                    2,
                    dtype=np.float64,
                )

            else:
                recovery_action = recovery.update(
                    fault_detected=True,
                    estimate=evidence.estimate,
                )

                action = recovery_action.action

                recovery_modes[
                    recovery_action.mode
                ] += 1

                if verbose:
                    print(
                        f"step={state['step'] + 1:03d} "
                        f"status={evidence.status:<25} "
                        f"confidence="
                        f"{evidence.confidence:.3f} "
                        f"decision=RECOVER "
                        f"mode="
                        f"{recovery_action.mode:<8} "
                        f"level="
                        f"{recovery_action.level}"
                    )

            if (
                decision.action == "ACT"
                and not evidence.safe_to_act
            ):
                unsafe_actions += 1

            if verbose and (
                decision.action
                in {"VERIFY", "ABSTAIN"}
            ):
                print(
                    f"step={state['step'] + 1:03d} "
                    f"status={evidence.status:<25} "
                    f"confidence="
                    f"{evidence.confidence:.3f} "
                    f"decision="
                    f"{decision.action:<8}"
                )

            state = world.step(
                action,
                rng,
            )

            previous_action = action.copy()

            total_reward += -0.01 * float(
                np.linalg.norm(action)
            )

            if state["terminated"]:
                total_reward += 1.0
                success = True
                break

            if state["truncated"]:
                break

        final_state = world.state()

        result = {
            "success": success,
            "steps": int(
                final_state["step"]
            ),
            "initial_distance": float(
                state["distance"]
                if False
                else np.linalg.norm(
                    final_state["target_pos"]
                    - np.array(
                        [-2.0, -2.0]
                    )
                )
            ),
            "final_distance": float(
                final_state["distance"]
            ),
            "reward": float(
                total_reward
            ),
            "decisions": decisions,
            "recovery_modes": recovery_modes,
            "status_counts": status_counts,
            "temporal_failures": (
                temporal_failures
            ),
            "unsafe_actions": unsafe_actions,
        }

        world.close()

        if verbose:
            print()
            print("=== FINAL ===")
            print(
                "success:",
                result["success"],
            )
            print(
                "steps:",
                result["steps"],
            )
            print(
                "final distance:",
                result["final_distance"],
            )
            print(
                "decisions:",
                result["decisions"],
            )
            print(
                "recovery:",
                result["recovery_modes"],
            )
            print(
                "statuses:",
                result["status_counts"],
            )
            print(
                "temporal failures:",
                result["temporal_failures"],
            )
            print(
                "unsafe actions:",
                result["unsafe_actions"],
            )

        return result
