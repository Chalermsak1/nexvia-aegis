from __future__ import annotations

import numpy as np

from aegis.v3.control.post_action import PostActionVerifier
from aegis.v3.control.bounded_recovery import (
    BoundedRecoveryManager,
)
from aegis.v3.control.fault_aware_controller import (
    FaultAwareVerificationController,
)
from aegis.v3.env.world import (
    AegisPhysicalWorld,
    WorldConfig,
)
from aegis.v3.policies.policy_v31 import AegisDecisionV31, AegisPolicyV31
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import (
    FaultInjectableSensor,
    SensorConfig,
)


class AegisAgentV31PostAction:
    """
    Nexvia Aegis 3.1 fault-tolerant + bounded fail-safe agent.

    Behavior:
        - normal verified operation -> ACT
        - isolated sensor fault -> degraded ACT
        - unresolved multi-sensor fault -> ABSTAIN
        - persistent unresolved fault -> bounded recovery
        - recovery exhaustion -> FAIL_SAFE and terminate episode

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
            FaultAwareVerificationController()
        )

        policy = AegisPolicyV31()
        recovery = BoundedRecoveryManager()
        post_action = PostActionVerifier()

        post_action_checks = 0
        post_action_confirmed = 0
        post_action_contradictions = 0
        post_action_status_counts: dict[str, int] = {}
        forced_recovery = False
        post_action_contradiction_streak = 0

        state = world.reset(rng)

        verification.reset()
        policy.reset()
        recovery.reset()

        previous_action = np.zeros(
            2,
            dtype=np.float64,
        )

        initial_distance = float(
            state["distance"]
        )

        total_reward = 0.0
        success = False
        fail_safe = False

        decisions = {
            "ACT": 0,
            "VERIFY": 0,
            "ABSTAIN": 0,
            "RECOVER": 0,
        }

        recovery_modes = {
            "HOLD": 0,
            "SAFE_PROBE": 0,
            "FAIL_SAFE": 0,
        }

        status_counts: dict[str, int] = {}
        decision_reasons: dict[str, int] = {}

        trusted_sensor_counts: dict[str, int] = {
            "0": 0,
            "1": 0,
            "NONE": 0,
        }

        isolated_sensor_counts: dict[str, int] = {
            "0": 0,
            "1": 0,
            "NONE": 0,
        }

        unsafe_actions = 0
        temporal_failures = 0
        degraded_steps = 0
        isolated_fault_steps = 0
        multi_sensor_fault_steps = 0

        termination_reason = "MAX_STEPS"

        if verbose:
            print("=== NEXVIA AEGIS 3.1 POST-ACTION ===")
            print("target:", state["target_pos"])
            print(
                "initial distance:",
                initial_distance,
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

            if evidence.degraded:
                degraded_steps += 1

            if evidence.status == "ISOLATED_SENSOR_FAULT":
                isolated_fault_steps += 1

            if evidence.status == "MULTI_SENSOR_FAULT":
                multi_sensor_fault_steps += 1

            trusted_key = (
                "NONE"
                if evidence.trusted_sensor is None
                else str(evidence.trusted_sensor)
            )

            isolated_key = (
                "NONE"
                if evidence.isolated_sensor is None
                else str(evidence.isolated_sensor)
            )

            trusted_sensor_counts[trusted_key] = (
                trusted_sensor_counts.get(
                    trusted_key,
                    0,
                )
                + 1
            )

            isolated_sensor_counts[isolated_key] = (
                isolated_sensor_counts.get(
                    isolated_key,
                    0,
                )
                + 1
            )

            decision = policy.decide(
                evidence
            )

            # Once a physical contradiction is observed,
            # do not permit another normal ACT decision.
            # Enter bounded recovery until evidence is
            # reacquired or the system reaches FAIL_SAFE.
            if forced_recovery:
                decision = AegisDecisionV31(
                    action="RECOVER",
                    reason="post_action_contradiction_recovery",
                    confidence=float(
                        evidence.confidence
                    ),
                    recovery_level=(
                        recovery.failure_streak + 1
                    ),
                )

            decisions[decision.action] += 1

            decision_reasons[decision.reason] = (
                decision_reasons.get(
                    decision.reason,
                    0,
                )
                + 1
            )

            # --------------------------------------------------
            # Normal / degraded verified operation.
            # --------------------------------------------------

            if decision.action == "ACT":
                action = self._move_toward(
                    evidence.estimate
                )

                recovery.reset()

            # --------------------------------------------------
            # No movement while obtaining evidence.
            # --------------------------------------------------

            elif decision.action in {
                "VERIFY",
                "ABSTAIN",
            }:
                action = np.zeros(
                    2,
                    dtype=np.float64,
                )

            # --------------------------------------------------
            # Bounded recovery.
            # --------------------------------------------------

            else:
                recovery_action = recovery.update(
                    fault_status=evidence.status,
                )

                recovery_modes[
                    recovery_action.mode
                ] += 1

                action = recovery_action.action

                if verbose:
                    print(
                        f"step={state['step'] + 1:03d} "
                        f"status={evidence.status:<25} "
                        f"confidence="
                        f"{evidence.confidence:.3f} "
                        f"decision=RECOVER "
                        f"mode="
                        f"{recovery_action.mode:<10} "
                        f"level="
                        f"{recovery_action.level}"
                    )

                if recovery_action.terminal:
                    fail_safe = True
                    termination_reason = (
                        "FAIL_SAFE_PERSISTENT_FAULT"
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

            # --------------------------------------------------
            # A terminal fail-safe does not execute any further
            # world action. We hold position and terminate.
            # --------------------------------------------------

            if fail_safe:
                action = np.zeros(
                    2,
                    dtype=np.float64,
                )
                break

            state = world.step(
                action,
                rng,
            )

            # Verify only genuine ACT actions. Recovery motions
            # are not interpreted as target-directed actions.
            if decision.action == "ACT":
                post_range_reading = range_sensor.measure(
                    state["distance"],
                    rng,
                )

                post_result = post_action.verify(
                    previous_range=range_reading,
                    current_range=post_range_reading,
                    previous_action=action,
                )

                post_action_checks += 1
                post_action_status_counts[
                    post_result.status
                ] = post_action_status_counts.get(
                    post_result.status,
                    0,
                ) + 1

                if post_result.status == (
                    "PROGRESS_CONFIRMED"
                ):
                    post_action_confirmed += 1
                    post_action_contradiction_streak = 0

                elif post_result.status == (
                    "POST_ACTION_CONTRADICTION"
                ):
                    post_action_contradictions += 1
                    post_action_contradiction_streak += 1

                    if post_action_contradiction_streak >= 2:
                        forced_recovery = True

                    if verbose:
                        print(
                            f"step={state['step']:03d} "
                            f"POST_ACTION_CONTRADICTION "
                            f"delta="
                            f"{post_result.distance_change:.3f} "
                            f"confidence="
                            f"{post_result.confidence:.3f}"
                        )

            previous_action = action.copy()

            total_reward += -0.01 * float(
                np.linalg.norm(action)
            )

            if state["terminated"]:
                total_reward += 1.0
                success = True
                termination_reason = "SUCCESS"
                break

            if state["truncated"]:
                termination_reason = "TIME_LIMIT"
                break

        final_state = world.state()

        result = {
            "success": success,
            "fail_safe": fail_safe,
            "termination_reason": termination_reason,
            "steps": int(
                final_state["step"]
            ),
            "initial_distance": initial_distance,
            "final_distance": float(
                final_state["distance"]
            ),
            "reward": float(
                total_reward
            ),
            "decisions": decisions,
            "recovery_modes": recovery_modes,
            "status_counts": status_counts,
            "decision_reasons": decision_reasons,
            "trusted_sensor_counts": (
                trusted_sensor_counts
            ),
            "isolated_sensor_counts": (
                isolated_sensor_counts
            ),
            "degraded_steps": degraded_steps,
            "isolated_fault_steps": (
                isolated_fault_steps
            ),
            "multi_sensor_fault_steps": (
                multi_sensor_fault_steps
            ),
            "temporal_failures": (
                temporal_failures
            ),
            "unsafe_actions": unsafe_actions,
            "post_action_checks": post_action_checks,
            "post_action_confirmed": post_action_confirmed,
            "post_action_contradictions": post_action_contradictions,
            "post_action_status_counts": post_action_status_counts,
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
                "fail-safe:",
                result["fail_safe"],
            )
            print(
                "termination:",
                result["termination_reason"],
            )
            print(
                "steps:",
                result["steps"],
            )
            print(
                "initial distance:",
                result["initial_distance"],
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
                "decision reasons:",
                result["decision_reasons"],
            )
            print(
                "unsafe actions:",
                result["unsafe_actions"],
            )

        return result

