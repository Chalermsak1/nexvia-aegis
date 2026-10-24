from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import (
    ABSTAIN,
    INSPECT,
    MOVE,
    STOP,
    VERIFY,
    AegisInspectionEnv,
)
from aegis.policies import (
    AegisPolicy,
    AgentContext,
    AlwaysActPolicy,
    InspectOncePolicy,
)


@dataclass
class EpisodeResult:
    success: bool
    abstained: bool
    steps: int
    inspections: int
    verifications: int
    reward: float
    stop_count: int
    false_stops: int
    anomaly_detected: bool
    cross_mismatch: bool


@dataclass
class AggregateResult:
    success_rate: float
    false_stop_rate: float
    abstain_rate: float
    anomaly_rate: float
    recovery_rate: float
    cross_mismatch_rate: float
    avg_steps: float
    avg_inspections: float
    avg_verifications: float
    avg_reward: float
    stop_count: int
    false_stop_count: int


def make_env(
    scenario: str,
) -> AegisInspectionEnv:
    return AegisInspectionEnv(
        observation_noise=0.08,
        inspection_noise=0.02,
        verification_noise=0.035,
        inspection_cost=0.03,
        verification_cost=0.04,
        movement_cost=0.01,
        abstain_cost=0.20,
        stop_failure_penalty=1.0,
        success_radius=0.06,
        max_steps=100,
        max_inspections=3,
        max_verifications=2,
        scenario=scenario,
    )


def make_policy(
    name: str,
):
    if name == "always_act":
        return AlwaysActPolicy()

    if name == "inspect_once":
        return InspectOncePolicy()

    if name == "aegis":
        return AegisPolicy(
            move_step=0.05,
            success_radius=0.06,
            move_cost=0.01,
            inspect_cost=0.03,
            verify_cost=0.04,
            abstain_penalty=0.20,
            inspection_noise=0.02,
            verification_noise=0.035,
            information_weight=0.12,
            verification_weight=0.20,
            progress_weight=0.08,
            stop_probability_threshold=0.90,
            max_stop_sigma=0.045,
            min_sensor_trust=0.55,
            max_cross_disagreement=0.35,
            anomaly_residual_threshold=3.0,
            num_samples=1024,
        )

    raise ValueError(
        f"Unknown policy: {name}"
    )


def run_episode(
    policy_name: str,
    scenario: str,
    seed: int,
) -> EpisodeResult:
    env = make_env(
        scenario
    )

    policy = make_policy(
        policy_name
    )

    observation, info = (
        env.reset(
            seed=seed
        )
    )

    policy.reset(
        seed=seed
    )

    total_reward = 0.0
    stop_count = 0
    false_stops = 0

    anomaly_detected = False
    cross_mismatch = False

    for _ in range(
        env.max_steps
    ):
        context = AgentContext(
            inspection_count=(
                info["inspection_count"]
            ),
            max_inspections=(
                env.max_inspections
            ),
            verification_count=(
                info["verification_count"]
            ),
            max_verifications=(
                env.max_verifications
            ),
            step_count=(
                info["step_count"]
            ),
        )

        action = policy.act(
            observation,
            context,
        )

        (
            observation,
            reward,
            terminated,
            truncated,
            info,
        ) = env.step(action)

        total_reward += float(
            reward
        )

        anomaly_detected = (
            anomaly_detected
            or info[
                "anomaly_this_step"
            ]
        )

        cross_mismatch = (
            cross_mismatch
            or info[
                "cross_mismatch_this_step"
            ]
        )

        if action == STOP:
            stop_count += 1

            if not info["success"]:
                false_stops += 1

        if terminated or truncated:
            break

    env.close()

    return EpisodeResult(
        success=bool(
            info["success"]
        ),
        abstained=bool(
            info["abstained"]
        ),
        steps=int(
            info["step_count"]
        ),
        inspections=int(
            info["inspection_count"]
        ),
        verifications=int(
            info["verification_count"]
        ),
        reward=total_reward,
        stop_count=stop_count,
        false_stops=false_stops,
        anomaly_detected=anomaly_detected,
        cross_mismatch=cross_mismatch,
    )


def aggregate(
    episodes: list[EpisodeResult],
) -> AggregateResult:
    total = len(episodes)

    successes = sum(
        episode.success
        for episode in episodes
    )

    abstentions = sum(
        episode.abstained
        for episode in episodes
    )

    anomalies = sum(
        episode.anomaly_detected
        for episode in episodes
    )

    mismatches = sum(
        episode.cross_mismatch
        for episode in episodes
    )

    stops = sum(
        episode.stop_count
        for episode in episodes
    )

    false_stops = sum(
        episode.false_stops
        for episode in episodes
    )

    anomaly_episodes = [
        episode
        for episode in episodes
        if episode.anomaly_detected
    ]

    if anomaly_episodes:
        recovery_rate = (
            sum(
                episode.success
                for episode in anomaly_episodes
            )
            / len(anomaly_episodes)
        )
    else:
        recovery_rate = float("nan")

    return AggregateResult(
        success_rate=(
            successes / total
        ),
        false_stop_rate=(
            false_stops / stops
            if stops
            else 0.0
        ),
        abstain_rate=(
            abstentions / total
        ),
        anomaly_rate=(
            anomalies / total
        ),
        recovery_rate=recovery_rate,
        cross_mismatch_rate=(
            mismatches / total
        ),
        avg_steps=float(
            np.mean(
                [
                    episode.steps
                    for episode in episodes
                ]
            )
        ),
        avg_inspections=float(
            np.mean(
                [
                    episode.inspections
                    for episode in episodes
                ]
            )
        ),
        avg_verifications=float(
            np.mean(
                [
                    episode.verifications
                    for episode in episodes
                ]
            )
        ),
        avg_reward=float(
            np.mean(
                [
                    episode.reward
                    for episode in episodes
                ]
            )
        ),
        stop_count=stops,
        false_stop_count=false_stops,
    )


def print_result(
    name: str,
    result: AggregateResult,
) -> None:
    titles = {
        "always_act": "Always Act",
        "inspect_once": "Inspect Once",
        "aegis": "Nexvia Aegis v0.5",
    }

    print()
    print(
        titles[name]
    )
    print("-" * 70)

    print(
        f"Success Rate             : "
        f"{result.success_rate * 100:7.2f}%"
    )

    print(
        f"False Stop Rate          : "
        f"{result.false_stop_rate * 100:7.2f}%"
    )

    print(
        f"Abstain Rate             : "
        f"{result.abstain_rate * 100:7.2f}%"
    )

    print(
        f"Anomaly Rate             : "
        f"{result.anomaly_rate * 100:7.2f}%"
    )

    if np.isfinite(
        result.recovery_rate
    ):
        print(
            f"Recovery Rate            : "
            f"{result.recovery_rate * 100:7.2f}%"
        )
    else:
        print(
            "Recovery Rate            : N/A"
        )

    print(
        f"Cross-Sensor Mismatch    : "
        f"{result.cross_mismatch_rate * 100:7.2f}%"
    )

    print(
        f"Average Steps            : "
        f"{result.avg_steps:7.2f}"
    )

    print(
        f"Average Inspections      : "
        f"{result.avg_inspections:7.2f}"
    )

    print(
        f"Average Verifications    : "
        f"{result.avg_verifications:7.2f}"
    )

    print(
        f"Average Reward           : "
        f"{result.avg_reward:7.4f}"
    )

    print(
        f"Stop Decisions           : "
        f"{result.stop_count}"
    )

    print(
        f"False Stops              : "
        f"{result.false_stop_count}"
    )


def run_scenario(
    scenario: str,
    episodes: int,
    base_seed: int,
) -> None:
    print()
    print("=" * 80)
    print(
        f"SCENARIO: {scenario.upper()}"
    )
    print(
        f"Episodes per policy: {episodes}"
    )
    print("=" * 80)

    policies = [
        "always_act",
        "inspect_once",
        "aegis",
    ]

    results = {}

    for policy_name in policies:
        episodes_result = []

        for index in range(
            episodes
        ):
            result = run_episode(
                policy_name=policy_name,
                scenario=scenario,
                seed=(
                    base_seed + index
                ),
            )

            episodes_result.append(
                result
            )

        aggregate_result = aggregate(
            episodes_result
        )

        results[
            policy_name
        ] = aggregate_result

        print_result(
            policy_name,
            aggregate_result,
        )

    print()
    print("-" * 80)
    print("AEGIS VS ALWAYS ACT")
    print("-" * 80)

    aegis = results["aegis"]
    baseline = results["always_act"]

    print(
        f"Success Δ     : "
        f"{(
            aegis.success_rate
            - baseline.success_rate
        ) * 100:+.2f} pp"
    )

    print(
        f"False Stop Δ  : "
        f"{(
            aegis.false_stop_rate
            - baseline.false_stop_rate
        ) * 100:+.2f} pp"
    )

    print(
        f"Reward Δ      : "
        f"{(
            aegis.avg_reward
            - baseline.avg_reward
        ):+.4f}"
    )


def main() -> None:
    print(
        "=== NEXVIA AEGIS v0.5 ==="
    )

    print(
        "Cross-Sensor Verification"
    )

    scenarios = [
        "normal",
        "biased",
        "heavy_tail",
        "outlier",
        "drift",
    ]

    episodes = 20
    base_seed = 30_000

    for scenario in scenarios:
        run_scenario(
            scenario=scenario,
            episodes=episodes,
            base_seed=base_seed,
        )

        base_seed += episodes


if __name__ == "__main__":
    main()
