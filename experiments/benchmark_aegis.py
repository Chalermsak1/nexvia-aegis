from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import (
    ABSTAIN,
    INSPECT,
    MOVE,
    STOP,
    AegisInspectionEnv,
)
from aegis.policies import (
    AegisPolicy,
    AgentContext,
    AlwaysActPolicy,
    InspectOncePolicy,
    ThresholdReobservePolicy,
)


@dataclass
class StopEvent:
    probability: float
    success: bool


@dataclass
class EpisodeResult:
    success: bool
    abstained: bool
    steps: int
    inspections: int
    reward: float
    stop_count: int
    false_stops: int
    anomaly_detected: bool
    stop_events: list[StopEvent]


@dataclass
class AggregateResult:
    success_rate: float
    false_stop_rate: float
    abstain_rate: float
    anomaly_rate: float
    recovery_rate: float
    avg_steps: float
    avg_inspections: float
    avg_reward: float
    stop_count: int
    false_stop_count: int
    mean_stop_probability: float
    actual_stop_success: float
    brier_score: float
    ece: float


def create_environment(
    scenario: str,
) -> AegisInspectionEnv:
    return AegisInspectionEnv(
        observation_noise=0.08,
        inspection_noise=0.02,
        inspection_cost=0.03,
        movement_cost=0.01,
        abstain_cost=0.20,
        stop_failure_penalty=1.0,
        success_radius=0.06,
        max_steps=100,
        max_inspections=3,
        scenario=scenario,
    )


def create_policy(
    name: str,
):
    if name == "always_act":
        return AlwaysActPolicy()

    if name == "inspect_once":
        return InspectOncePolicy()

    if name == "threshold_reobserve":
        return ThresholdReobservePolicy(
            sigma_threshold=0.05,
        )

    if name == "aegis":
        return AegisPolicy(
            move_step=0.05,
            success_radius=0.06,
            move_cost=0.01,
            inspect_cost=0.03,
            stop_failure_penalty=1.0,
            abstain_penalty=0.20,
            inspection_noise=0.02,
            information_weight=0.15,
            progress_weight=0.08,
            verification_weight=0.20,
            stop_probability_threshold=0.90,
            max_stop_sigma=0.045,
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
    env = create_environment(
        scenario
    )

    policy = create_policy(
        policy_name
    )

    observation, info = env.reset(
        seed=seed
    )

    policy.reset(
        seed=seed
    )

    total_reward = 0.0
    stop_count = 0
    false_stops = 0

    anomaly_detected = False
    stop_events: list[StopEvent] = []

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
            step_count=(
                info["step_count"]
            ),
        )

        action = policy.act(
            observation,
            context,
        )

        predicted_probability = None

        if (
            policy_name == "aegis"
            and action == STOP
        ):
            predicted_probability = float(
                policy.last_diagnostics[
                    "current_probability"
                ]
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

        if info[
            "anomaly_this_step"
        ]:
            anomaly_detected = True

        if action == STOP:
            stop_count += 1

            successful_stop = bool(
                info["success"]
            )

            if not successful_stop:
                false_stops += 1

            if predicted_probability is not None:
                stop_events.append(
                    StopEvent(
                        probability=(
                            predicted_probability
                        ),
                        success=(
                            successful_stop
                        ),
                    )
                )

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
        reward=total_reward,
        stop_count=stop_count,
        false_stops=false_stops,
        anomaly_detected=anomaly_detected,
        stop_events=stop_events,
    )


def brier_score(
    probabilities: list[float],
    labels: list[int],
) -> float:
    if not probabilities:
        return float("nan")

    p = np.asarray(
        probabilities,
        dtype=np.float64,
    )

    y = np.asarray(
        labels,
        dtype=np.float64,
    )

    return float(
        np.mean(
            (p - y) ** 2
        )
    )


def expected_calibration_error(
    probabilities: list[float],
    labels: list[int],
    bins: int = 10,
) -> float:
    if not probabilities:
        return float("nan")

    p = np.asarray(
        probabilities,
        dtype=np.float64,
    )

    y = np.asarray(
        labels,
        dtype=np.float64,
    )

    p = np.clip(
        p,
        0.0,
        1.0,
    )

    edges = np.linspace(
        0.0,
        1.0,
        bins + 1,
    )

    ece = 0.0

    for i in range(bins):
        low = edges[i]
        high = edges[i + 1]

        if i == bins - 1:
            mask = (
                (p >= low)
                & (p <= high)
            )
        else:
            mask = (
                (p >= low)
                & (p < high)
            )

        if not np.any(mask):
            continue

        confidence = float(
            np.mean(
                p[mask]
            )
        )

        accuracy = float(
            np.mean(
                y[mask]
            )
        )

        weight = (
            np.sum(mask)
            / len(p)
        )

        ece += (
            weight
            * abs(
                confidence
                - accuracy
            )
        )

    return float(ece)


def aggregate(
    episodes: list[EpisodeResult],
    policy_name: str,
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

    stop_count = sum(
        episode.stop_count
        for episode in episodes
    )

    false_stop_count = sum(
        episode.false_stops
        for episode in episodes
    )

    success_rate = (
        successes / total
    )

    abstain_rate = (
        abstentions / total
    )

    anomaly_rate = (
        anomalies / total
    )

    false_stop_rate = (
        false_stop_count
        / stop_count
        if stop_count > 0
        else 0.0
    )

    # Recovery means:
    # anomaly occurred, but the episode still
    # ended successfully.
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

    avg_steps = float(
        np.mean(
            [
                episode.steps
                for episode in episodes
            ]
        )
    )

    avg_inspections = float(
        np.mean(
            [
                episode.inspections
                for episode in episodes
            ]
        )
    )

    avg_reward = float(
        np.mean(
            [
                episode.reward
                for episode in episodes
            ]
        )
    )

    probabilities: list[float] = []
    labels: list[int] = []

    if policy_name == "aegis":
        for episode in episodes:
            for event in (
                episode.stop_events
            ):
                probabilities.append(
                    event.probability
                )

                labels.append(
                    1
                    if event.success
                    else 0
                )

    if probabilities:
        mean_stop_probability = float(
            np.mean(
                probabilities
            )
        )

        actual_stop_success = float(
            np.mean(labels)
        )

        score_brier = brier_score(
            probabilities,
            labels,
        )

        score_ece = (
            expected_calibration_error(
                probabilities,
                labels,
            )
        )
    else:
        mean_stop_probability = float(
            "nan"
        )

        actual_stop_success = float(
            "nan"
        )

        score_brier = float(
            "nan"
        )

        score_ece = float(
            "nan"
        )

    return AggregateResult(
        success_rate=success_rate,
        false_stop_rate=false_stop_rate,
        abstain_rate=abstain_rate,
        anomaly_rate=anomaly_rate,
        recovery_rate=recovery_rate,
        avg_steps=avg_steps,
        avg_inspections=avg_inspections,
        avg_reward=avg_reward,
        stop_count=stop_count,
        false_stop_count=(
            false_stop_count
        ),
        mean_stop_probability=(
            mean_stop_probability
        ),
        actual_stop_success=(
            actual_stop_success
        ),
        brier_score=score_brier,
        ece=score_ece,
    )


def print_result(
    policy_name: str,
    result: AggregateResult,
) -> None:
    names = {
        "always_act": "Always Act",
        "inspect_once": "Inspect Once",
        "threshold_reobserve": (
            "Threshold Reobserve"
        ),
        "aegis": "Nexvia Aegis",
    }

    print()
    print(
        names[policy_name]
    )

    print("-" * 70)

    print(
        f"Success Rate           : "
        f"{result.success_rate * 100:7.2f}%"
    )

    print(
        f"False Stop Rate        : "
        f"{result.false_stop_rate * 100:7.2f}%"
    )

    print(
        f"Abstain Rate           : "
        f"{result.abstain_rate * 100:7.2f}%"
    )

    print(
        f"Anomaly Rate           : "
        f"{result.anomaly_rate * 100:7.2f}%"
    )

    if np.isfinite(
        result.recovery_rate
    ):
        print(
            f"Recovery Rate          : "
            f"{result.recovery_rate * 100:7.2f}%"
        )
    else:
        print(
            "Recovery Rate          : N/A"
        )

    print(
        f"Average Steps          : "
        f"{result.avg_steps:7.2f}"
    )

    print(
        f"Average Inspections    : "
        f"{result.avg_inspections:7.2f}"
    )

    print(
        f"Average Reward         : "
        f"{result.avg_reward:7.4f}"
    )

    print(
        f"Stop Decisions         : "
        f"{result.stop_count}"
    )

    print(
        f"False Stops            : "
        f"{result.false_stop_count}"
    )

    if policy_name == "aegis":
        if np.isfinite(
            result.mean_stop_probability
        ):
            print(
                f"Mean STOP Probability : "
                f"{result.mean_stop_probability:7.4f}"
            )

            print(
                f"Actual STOP Success   : "
                f"{result.actual_stop_success:7.4f}"
            )

            print(
                f"Brier Score           : "
                f"{result.brier_score:7.4f}"
            )

            print(
                f"ECE                   : "
                f"{result.ece:7.4f}"
            )
        else:
            print(
                "Calibration            : N/A"
            )


def run_scenario(
    scenario: str,
    episodes_per_policy: int,
    base_seed: int,
) -> None:
    print()
    print("=" * 80)
    print(
        f"SCENARIO: {scenario.upper()}"
    )
    print(
        f"Episodes per policy: "
        f"{episodes_per_policy}"
    )
    print("=" * 80)

    policies = [
        "always_act",
        "inspect_once",
        "threshold_reobserve",
        "aegis",
    ]

    results: dict[
        str,
        AggregateResult,
    ] = {}

    for policy_name in policies:
        episodes: list[
            EpisodeResult
        ] = []

        for i in range(
            episodes_per_policy
        ):
            episode = run_episode(
                policy_name=policy_name,
                scenario=scenario,
                seed=(
                    base_seed + i
                ),
            )

            episodes.append(
                episode
            )

        result = aggregate(
            episodes,
            policy_name,
        )

        results[
            policy_name
        ] = result

        print_result(
            policy_name,
            result,
        )

    print()
    print("-" * 80)
    print("AEGIS VS ALWAYS ACT")
    print("-" * 80)

    success_delta = (
        results["aegis"].success_rate
        - results["always_act"].success_rate
    )

    false_stop_delta = (
        results["aegis"].false_stop_rate
        - results["always_act"].false_stop_rate
    )

    abstain_delta = (
        results["aegis"].abstain_rate
        - results["always_act"].abstain_rate
    )

    reward_delta = (
        results["aegis"].avg_reward
        - results["always_act"].avg_reward
    )

    print(
        f"Success Δ     : "
        f"{success_delta * 100:+.2f} pp"
    )

    print(
        f"False Stop Δ  : "
        f"{false_stop_delta * 100:+.2f} pp"
    )

    print(
        f"Abstain Δ     : "
        f"{abstain_delta * 100:+.2f} pp"
    )

    print(
        f"Reward Δ      : "
        f"{reward_delta:+.4f}"
    )


def main() -> None:
    print(
        "=== NEXVIA AEGIS v0.4.2 ==="
    )

    print(
        "Distribution Shift + "
        "Verification + Abstention"
    )

    scenarios = [
        "normal",
        "biased",
        "heavy_tail",
        "outlier",
        "drift",
    ]

    episodes_per_policy = 20

    base_seed = 20_000

    for scenario in scenarios:
        run_scenario(
            scenario=scenario,
            episodes_per_policy=(
                episodes_per_policy
            ),
            base_seed=base_seed,
        )

        base_seed += (
            episodes_per_policy
        )


if __name__ == "__main__":
    main()
