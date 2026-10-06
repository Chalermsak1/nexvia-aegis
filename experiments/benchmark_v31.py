from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aegis.v3.control.bounded_recovery import (
    BoundedRecoveryManager,
)
from aegis.v3.control.fault_aware_controller import (
    FaultAwareVerificationController,
)
from aegis.v3.control.recovery import RecoveryManager
from aegis.v3.control.verification_controller import (
    VerificationController,
)
from aegis.v3.env.world import (
    AegisPhysicalWorld,
    WorldConfig,
)
from aegis.v3.policies.policy import AegisPolicyV3
from aegis.v3.policies.policy_v31 import AegisPolicyV31
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import (
    FaultInjectableSensor,
    SensorConfig,
)


@dataclass(frozen=True)
class Scenario:
    name: str

    primary_noise: float = 0.05
    verifier_noise: float = 0.05

    primary_bias: tuple[float, float] = (0.0, 0.0)
    verifier_bias: tuple[float, float] = (0.0, 0.0)

    primary_drift: tuple[float, float] = (0.0, 0.0)
    verifier_drift: tuple[float, float] = (0.0, 0.0)

    outlier_probability: float = 0.0
    outlier_scale: float = 1.0

    primary_dropout: float = 0.0
    verifier_dropout: float = 0.0
    range_dropout: float = 0.0

    actuator_noise: float = 0.0

    external_force_probability: float = 0.0
    external_force_scale: float = 0.0

    moving_target: bool = False
    target_velocity: tuple[float, float] = (0.0, 0.0)

    max_steps: int = 300


TARGET_SCENARIOS = [
    Scenario(
        name="NORMAL",
    ),
    Scenario(
        name="BIASED",
        verifier_bias=(1.0, 1.0),
    ),
    Scenario(
        name="HEAVY_TAIL",
        outlier_probability=0.10,
        outlier_scale=4.0,
    ),
    Scenario(
        name="DROPOUT",
        verifier_dropout=0.25,
    ),
    Scenario(
        name="DRIFT",
        verifier_drift=(0.01, 0.005),
    ),
    Scenario(
        name="CORRELATED_BIAS",
        primary_bias=(0.8, 0.8),
        verifier_bias=(0.8, 0.8),
    ),
]


def make_world(
    scenario: Scenario,
) -> AegisPhysicalWorld:
    config = WorldConfig(
        actuator_noise=scenario.actuator_noise,
        external_force_probability=(
            scenario.external_force_probability
        ),
        external_force_scale=(
            scenario.external_force_scale
        ),
        moving_target=scenario.moving_target,
        target_velocity=scenario.target_velocity,
        max_steps=scenario.max_steps,
    )

    return AegisPhysicalWorld(config)


def make_sensors(
    scenario: Scenario,
):
    primary = FaultInjectableSensor(
        SensorConfig(
            name="primary",
            noise_sigma=scenario.primary_noise,
            bias=scenario.primary_bias,
            drift_rate=scenario.primary_drift,
            outlier_probability=(
                scenario.outlier_probability
            ),
            outlier_scale=scenario.outlier_scale,
            dropout_probability=(
                scenario.primary_dropout
            ),
        )
    )

    verifier = FaultInjectableSensor(
        SensorConfig(
            name="verifier",
            noise_sigma=scenario.verifier_noise,
            bias=scenario.verifier_bias,
            drift_rate=scenario.verifier_drift,
            outlier_probability=(
                scenario.outlier_probability
            ),
            outlier_scale=scenario.outlier_scale,
            dropout_probability=(
                scenario.verifier_dropout
            ),
        )
    )

    range_sensor = RangeSensor(
        noise_sigma=0.05,
        dropout_probability=scenario.range_dropout,
    )

    return primary, verifier, range_sensor


def move_toward(
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


def evaluate_ground_truth_alignment(
    action: np.ndarray,
    true_delta: np.ndarray,
) -> bool:
    """
    Independent evaluator-side safety proxy.

    Returns True when an executed ACT action points
    opposite to the simulator ground-truth target direction.

    This function is NEVER used to choose the action.
    """

    action_norm = float(
        np.linalg.norm(action)
    )

    delta_norm = float(
        np.linalg.norm(true_delta)
    )

    if action_norm <= 1e-8:
        return False

    if delta_norm <= 1e-8:
        return False

    cosine = float(
        np.dot(action, true_delta)
        / (action_norm * delta_norm)
    )

    return cosine < 0.0


def run_episode_v30(
    scenario: Scenario,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)

    world = make_world(scenario)

    primary, verifier, range_sensor = (
        make_sensors(scenario)
    )

    controller = VerificationController()
    policy = AegisPolicyV3()
    recovery = RecoveryManager()

    initial = world.reset(rng)

    total_reward = 0.0
    success = False

    act_steps = 0
    verify_steps = 0
    abstain_steps = 0
    recover_steps = 0

    unsafe_gate_steps = 0
    wrong_direction_act_steps = 0

    mismatch_steps = 0
    degraded_steps = 0

    for _ in range(
        scenario.max_steps
    ):
        state = world.state()

        true_delta = (
            state["target_pos"]
            - state["robot_pos"]
        )

        reading_a = primary.measure(
            true_delta,
            rng,
            step=state["step"],
        )

        reading_b = verifier.measure(
            true_delta,
            rng,
            step=state["step"],
        )

        range_reading = range_sensor.measure(
            state["distance"],
            rng,
        )

        verification = controller.verify(
            [reading_a, reading_b],
            range_reading,
        )

        if verification.status != "VERIFIED":
            degraded_steps += 1

        if "MISMATCH" in verification.status:
            mismatch_steps += 1

        decision = policy.decide(
            verification
        )

        if decision.action == "ACT":
            action = move_toward(
                verification.estimate
            )
            act_steps += 1

            if not verification.safe_to_act:
                unsafe_gate_steps += 1

            if evaluate_ground_truth_alignment(
                action,
                true_delta,
            ):
                wrong_direction_act_steps += 1

        elif decision.action == "RECOVER":
            action = -0.35 * move_toward(
                verification.estimate
            )
            recover_steps += 1

        elif decision.action == "VERIFY":
            action = np.zeros(
                2,
                dtype=np.float64,
            )
            verify_steps += 1

        else:
            action = np.zeros(
                2,
                dtype=np.float64,
            )
            abstain_steps += 1

        state = world.step(
            action,
            rng,
        )

        total_reward += (
            -0.01
            * float(np.linalg.norm(action))
        )

        if state["terminated"]:
            total_reward += 1.0
            success = True
            break

        if state["truncated"]:
            break

    final_state = world.state()

    result = {
        "scenario": scenario.name,
        "policy": "AEGIS_V3.0",
        "seed": seed,
        "success": int(success),
        "steps": int(final_state["step"]),
        "initial_distance": float(
            initial["distance"]
        ),
        "final_distance": float(
            final_state["distance"]
        ),
        "reward": float(total_reward),
        "act_steps": act_steps,
        "verify_steps": verify_steps,
        "abstain_steps": abstain_steps,
        "recover_steps": recover_steps,
        "unsafe_gate_steps": unsafe_gate_steps,
        "wrong_direction_act_steps": (
            wrong_direction_act_steps
        ),
        "mismatch_steps": mismatch_steps,
        "degraded_steps": degraded_steps,
        "fail_safe": 0,
        "isolated_fault_steps": 0,
        "multi_sensor_fault_steps": 0,
        "temporal_failures": 0,
    }

    world.close()

    return result


def run_episode_v31(
    scenario: Scenario,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)

    world = make_world(scenario)

    primary, verifier, range_sensor = (
        make_sensors(scenario)
    )

    controller = (
        FaultAwareVerificationController()
    )

    policy = AegisPolicyV31()
    recovery = BoundedRecoveryManager()

    initial = world.reset(rng)

    total_reward = 0.0
    success = False
    fail_safe = False

    act_steps = 0
    verify_steps = 0
    abstain_steps = 0
    recover_steps = 0

    unsafe_gate_steps = 0
    wrong_direction_act_steps = 0

    isolated_fault_steps = 0
    multi_sensor_fault_steps = 0
    degraded_steps = 0
    temporal_failures = 0

    previous_action = np.zeros(
        2,
        dtype=np.float64,
    )

    for _ in range(
        scenario.max_steps
    ):
        state = world.state()

        true_delta = (
            state["target_pos"]
            - state["robot_pos"]
        )

        reading_a = primary.measure(
            true_delta,
            rng,
            step=state["step"],
        )

        reading_b = verifier.measure(
            true_delta,
            rng,
            step=state["step"],
        )

        range_reading = range_sensor.measure(
            state["distance"],
            rng,
        )

        verification = controller.verify(
            vector_readings=[
                reading_a,
                reading_b,
            ],
            range_reading=range_reading,
            previous_action=previous_action,
        )

        if verification.degraded:
            degraded_steps += 1

        if verification.status == (
            "ISOLATED_SENSOR_FAULT"
        ):
            isolated_fault_steps += 1

        if verification.status == (
            "MULTI_SENSOR_FAULT"
        ):
            multi_sensor_fault_steps += 1

        if not verification.temporal_consistent:
            temporal_failures += 1

        decision = policy.decide(
            verification
        )

        if decision.action == "ACT":
            action = move_toward(
                verification.estimate
            )
            act_steps += 1

            if not verification.safe_to_act:
                unsafe_gate_steps += 1

            if evaluate_ground_truth_alignment(
                action,
                true_delta,
            ):
                wrong_direction_act_steps += 1

            recovery.reset()

        elif decision.action == "VERIFY":
            action = np.zeros(
                2,
                dtype=np.float64,
            )
            verify_steps += 1

        elif decision.action == "ABSTAIN":
            action = np.zeros(
                2,
                dtype=np.float64,
            )
            abstain_steps += 1

        else:
            recovery_action = recovery.update(
                fault_status=verification.status,
            )

            action = recovery_action.action
            recover_steps += 1

            if recovery_action.terminal:
                fail_safe = True
                break

        state = world.step(
            action,
            rng,
        )

        previous_action = action.copy()

        total_reward += (
            -0.01
            * float(np.linalg.norm(action))
        )

        if state["terminated"]:
            total_reward += 1.0
            success = True
            break

        if state["truncated"]:
            break

    final_state = world.state()

    result = {
        "scenario": scenario.name,
        "policy": "AEGIS_V3.1",
        "seed": seed,
        "success": int(success),
        "steps": int(final_state["step"]),
        "initial_distance": float(
            initial["distance"]
        ),
        "final_distance": float(
            final_state["distance"]
        ),
        "reward": float(total_reward),
        "act_steps": act_steps,
        "verify_steps": verify_steps,
        "abstain_steps": abstain_steps,
        "recover_steps": recover_steps,
        "unsafe_gate_steps": unsafe_gate_steps,
        "wrong_direction_act_steps": (
            wrong_direction_act_steps
        ),
        "mismatch_steps": (
            multi_sensor_fault_steps
        ),
        "degraded_steps": degraded_steps,
        "fail_safe": int(fail_safe),
        "isolated_fault_steps": (
            isolated_fault_steps
        ),
        "multi_sensor_fault_steps": (
            multi_sensor_fault_steps
        ),
        "temporal_failures": temporal_failures,
    }

    world.close()

    return result


def aggregate(
    rows: list[dict],
) -> dict:
    n = len(rows)

    total_steps = max(
        sum(r["steps"] for r in rows),
        1,
    )

    total_act = max(
        sum(r["act_steps"] for r in rows),
        1,
    )

    total_recover = max(
        sum(r["recover_steps"] for r in rows),
        1,
    )

    return {
        "evaluation": rows[0]["evaluation"],
        "scenario": rows[0]["scenario"],
        "policy": rows[0]["policy"],
        "episodes": n,
        "success_rate": (
            sum(r["success"] for r in rows) / n
        ),
        "failure_rate": (
            1.0
            - (
                sum(r["success"] for r in rows)
                / n
            )
        ),
        "fail_safe_rate": (
            sum(r["fail_safe"] for r in rows) / n
        ),
        "avg_steps": (
            sum(r["steps"] for r in rows) / n
        ),
        "avg_final_distance": (
            sum(
                r["final_distance"]
                for r in rows
            )
            / n
        ),
        "avg_reward": (
            sum(r["reward"] for r in rows) / n
        ),
        "act_rate": (
            sum(r["act_steps"] for r in rows)
            / total_steps
        ),
        "verify_rate": (
            sum(r["verify_steps"] for r in rows)
            / total_steps
        ),
        "abstain_rate": (
            sum(r["abstain_steps"] for r in rows)
            / total_steps
        ),
        "recover_rate": (
            sum(r["recover_steps"] for r in rows)
            / total_steps
        ),
        "unsafe_gate_rate": (
            sum(
                r["unsafe_gate_steps"]
                for r in rows
            )
            / total_act
        ),
        "ground_truth_wrong_direction_rate": (
            sum(
                r["wrong_direction_act_steps"]
                for r in rows
            )
            / total_act
        ),
        "isolated_fault_rate": (
            sum(
                r["isolated_fault_steps"]
                for r in rows
            )
            / total_steps
        ),
        "multi_sensor_fault_rate": (
            sum(
                r["multi_sensor_fault_steps"]
                for r in rows
            )
            / total_steps
        ),
        "degraded_rate": (
            sum(
                r["degraded_steps"]
                for r in rows
            )
            / total_steps
        ),
        "avg_recovery_steps": (
            sum(
                r["recover_steps"]
                for r in rows
            )
            / n
        ),
        "avg_temporal_failures": (
            sum(
                r.get("temporal_failures", 0)
                for r in rows
            )
            / n
        ),
    }


def run_benchmark(
    evaluation: str,
    base_seed: int,
    episodes: int,
):
    runners = [
        run_episode_v30,
        run_episode_v31,
    ]

    raw_rows = []
    summary_rows = []

    print()
    print(
        "================================================"
    )
    print(
        f"NEXVIA AEGIS V3.0 vs V3.1 "
        f"{evaluation.upper()}"
    )
    print(
        f"episodes={episodes} "
        f"base_seed={base_seed}"
    )
    print(
        "================================================"
    )

    for scenario_index, scenario in enumerate(
        TARGET_SCENARIOS
    ):
        for runner in runners:
            rows = []

            for episode_index in range(
                episodes
            ):
                seed = (
                    base_seed
                    + episode_index
                    + (
                        scenario_index
                        * 10_000
                    )
                )

                row = runner(
                    scenario,
                    seed,
                )

                row["evaluation"] = evaluation

                row.setdefault("temporal_failures", 0)
                rows.append(row)
                raw_rows.append(row)

            summary = aggregate(rows)
            summary_rows.append(summary)

            print(
                f"{evaluation:<11} "
                f"{scenario.name:<18} "
                f"{summary['policy']:<13} "
                f"success="
                f"{summary['success_rate']:.3f} "
                f"fail_safe="
                f"{summary['fail_safe_rate']:.3f} "
                f"unsafe_gate="
                f"{summary['unsafe_gate_rate']:.3f} "
                f"gt_wrong_dir="
                f"{summary['ground_truth_wrong_direction_rate']:.3f} "
                f"recover="
                f"{summary['recover_rate']:.3f}"
            )

    return raw_rows, summary_rows


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=rows[0].keys(),
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    development_rows, development_summary = (
        run_benchmark(
            evaluation="development",
            base_seed=300_000,
            episodes=100,
        )
    )

    holdout_rows, holdout_summary = (
        run_benchmark(
            evaluation="holdout",
            base_seed=400_000,
            episodes=100,
        )
    )

    raw_rows = (
        development_rows
        + holdout_rows
    )

    summary_rows = (
        development_summary
        + holdout_summary
    )

    write_csv(
        Path(
            "results/v31_targeted_episodes.csv"
        ),
        raw_rows,
    )

    write_csv(
        Path(
            "results/v31_targeted_summary.csv"
        ),
        summary_rows,
    )

    print()
    print(
        "================================================"
    )
    print("V3.1 TARGETED BENCHMARK COMPLETE")
    print(
        "================================================"
    )

    for row in summary_rows:
        print(
            f"{row['evaluation']:<11} "
            f"{row['scenario']:<18} "
            f"{row['policy']:<13} "
            f"success="
            f"{row['success_rate']:.3f} "
            f"fail_safe="
            f"{row['fail_safe_rate']:.3f} "
            f"gt_wrong_dir="
            f"{row['ground_truth_wrong_direction_rate']:.3f}"
        )

    print()
    print(
        "results/v31_targeted_episodes.csv"
    )
    print(
        "results/v31_targeted_summary.csv"
    )


if __name__ == "__main__":
    main()
