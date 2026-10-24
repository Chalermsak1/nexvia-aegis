from __future__ import annotations

import csv
import os
from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import AegisInspectionEnv
from aegis.policies import (
    AegisPolicy,
    AgentContext,
    AlwaysActPolicy,
    BasePolicy,
    InspectOncePolicy,
    ThresholdReobservePolicy,
)


NUM_EPISODES = 1000

UNCERTAINTY_LEVELS = {
    "low": {
        "observation_noise": 0.02,
    },
    "medium": {
        "observation_noise": 0.08,
    },
    "high": {
        "observation_noise": 0.15,
    },
    "severe": {
        "observation_noise": 0.25,
    },
}


POLICY_FACTORIES = {
    "always_act": AlwaysActPolicy,
    "inspect_once": InspectOncePolicy,
    "threshold_reobserve": lambda: ThresholdReobservePolicy(
        sigma_threshold=0.05,
    ),
    "aegis": lambda: AegisPolicy(
        num_samples=128,
    ),
}


@dataclass
class EpisodeResult:
    episode: int
    seed: int
    uncertainty: str
    policy: str

    success: bool
    abstained: bool

    steps: int
    inspections: int

    total_reward: float

    final_true_distance: float
    final_estimated_distance: float

    stop_confidence: float | None
    stop_success: bool | None


def estimated_distance(
    observation: np.ndarray,
) -> float:
    robot = observation[0:2]
    belief = observation[2:4]

    return float(
        np.linalg.norm(
            robot - belief
        )
    )


def build_policy(
    policy_name: str,
) -> BasePolicy:
    factory = POLICY_FACTORIES[policy_name]

    return factory()


def run_episode(
    policy_name: str,
    uncertainty: str,
    seed: int,
) -> EpisodeResult:
    config = UNCERTAINTY_LEVELS[uncertainty]

    env = AegisInspectionEnv(
        observation_noise=config["observation_noise"],
        inspection_noise=0.02,
        inspection_cost=0.03,
        movement_cost=0.01,
        abstain_cost=0.05,
        success_radius=0.06,
        max_steps=100,
        max_inspections=3,
    )

    policy = build_policy(policy_name)

    if hasattr(policy, "reset"):
        policy.reset(seed=seed)

    observation, info = env.reset(
        seed=seed
    )

    terminated = False
    truncated = False

    total_reward = 0.0
    step_count = 0

    stop_confidence = None
    stop_success = None

    while not terminated and not truncated:
        context = AgentContext(
            inspection_count=info["inspection_count"],
            max_inspections=env.max_inspections,
            step_count=info["step_count"],
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

        total_reward += reward
        step_count += 1

        if action == 2:
            stop_confidence = float(
                observation[5]
            )
            stop_success = bool(
                info["success"]
            )

    result = EpisodeResult(
        episode=0,
        seed=seed,
        uncertainty=uncertainty,
        policy=policy_name,

        success=bool(info["success"]),
        abstained=bool(info["abstained"]),

        steps=step_count,
        inspections=info["inspection_count"],

        total_reward=float(total_reward),

        final_true_distance=float(
            info["distance_to_target"]
        ),
        final_estimated_distance=estimated_distance(
            observation
        ),

        stop_confidence=stop_confidence,
        stop_success=stop_success,
    )

    env.close()

    return result


def calculate_ece(
    confidences: list[float],
    outcomes: list[bool],
    bins: int = 10,
) -> float:
    if not confidences:
        return float("nan")

    confidences_np = np.asarray(
        confidences,
        dtype=float,
    )

    outcomes_np = np.asarray(
        outcomes,
        dtype=float,
    )

    total = len(confidences_np)
    ece = 0.0

    for lower in np.linspace(
        0.0,
        1.0,
        bins + 1,
    )[:-1]:
        upper = lower + 1.0 / bins

        if upper >= 1.0:
            mask = (
                (confidences_np >= lower)
                & (confidences_np <= upper)
            )
        else:
            mask = (
                (confidences_np >= lower)
                & (confidences_np < upper)
            )

        if not np.any(mask):
            continue

        bin_confidence = float(
            np.mean(
                confidences_np[mask]
            )
        )

        bin_accuracy = float(
            np.mean(
                outcomes_np[mask]
            )
        )

        weight = np.sum(mask) / total

        ece += weight * abs(
            bin_confidence - bin_accuracy
        )

    return float(ece)


def summarize(
    results: list[EpisodeResult],
) -> None:
    print("\n=== RESEARCH SUMMARY ===")

    for uncertainty in UNCERTAINTY_LEVELS:
        for policy_name in POLICY_FACTORIES:
            subset = [
                r
                for r in results
                if (
                    r.uncertainty == uncertainty
                    and r.policy == policy_name
                )
            ]

            success_rate = np.mean(
                [r.success for r in subset]
            )

            abstain_rate = np.mean(
                [r.abstained for r in subset]
            )

            average_steps = np.mean(
                [r.steps for r in subset]
            )

            average_inspections = np.mean(
                [r.inspections for r in subset]
            )

            average_reward = np.mean(
                [r.total_reward for r in subset]
            )

            average_true_distance = np.mean(
                [
                    r.final_true_distance
                    for r in subset
                ]
            )

            confidence_values = [
                r.stop_confidence
                for r in subset
                if r.stop_confidence is not None
            ]

            outcomes = [
                r.stop_success
                for r in subset
                if r.stop_success is not None
            ]

            ece = calculate_ece(
                confidence_values,
                outcomes,
            )

            brier = (
                np.mean(
                    [
                        (
                            confidence
                            - float(outcome)
                        )
                        ** 2
                        for confidence, outcome
                        in zip(
                            confidence_values,
                            outcomes,
                        )
                    ]
                )
                if confidence_values
                else float("nan")
            )

            stop_risk = (
                1.0
                - np.mean(outcomes)
                if outcomes
                else float("nan")
            )

            print(
                f"{uncertainty:>7} | "
                f"{policy_name:<18} | "
                f"success={success_rate:7.2%} | "
                f"abstain={abstain_rate:7.2%} | "
                f"steps={average_steps:6.2f} | "
                f"inspect={average_inspections:5.2f} | "
                f"reward={average_reward:8.4f} | "
                f"error={average_true_distance:7.4f} | "
                f"stopRisk={stop_risk:7.2%} | "
                f"ECE={ece:7.4f} | "
                f"Brier={brier:7.4f}"
            )


def save_results(
    results: list[EpisodeResult],
) -> str:
    os.makedirs(
        "results",
        exist_ok=True,
    )

    path = (
        "results/"
        "aegis_research_benchmark.csv"
    )

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "episode",
                "seed",
                "uncertainty",
                "policy",
                "success",
                "abstained",
                "steps",
                "inspections",
                "total_reward",
                "final_true_distance",
                "final_estimated_distance",
                "stop_confidence",
                "stop_success",
            ]
        )

        for r in results:
            writer.writerow(
                [
                    r.episode,
                    r.seed,
                    r.uncertainty,
                    r.policy,
                    r.success,
                    r.abstained,
                    r.steps,
                    r.inspections,
                    r.total_reward,
                    r.final_true_distance,
                    r.final_estimated_distance,
                    r.stop_confidence,
                    r.stop_success,
                ]
            )

    return path


def main() -> None:
    print(
        "=== NEXVIA AEGIS "
        "RESEARCH BENCHMARK ==="
    )

    print(
        f"Episodes per condition: "
        f"{NUM_EPISODES}"
    )

    results: list[EpisodeResult] = []

    total_conditions = (
        len(UNCERTAINTY_LEVELS)
        * len(POLICY_FACTORIES)
    )

    condition_index = 0

    for uncertainty in UNCERTAINTY_LEVELS:
        for policy_name in POLICY_FACTORIES:
            condition_index += 1

            print(
                f"\n[{condition_index}/"
                f"{total_conditions}] "
                f"{uncertainty.upper()} / "
                f"{policy_name}"
            )

            for episode in range(
                NUM_EPISODES
            ):
                result = run_episode(
                    policy_name=policy_name,
                    uncertainty=uncertainty,
                    seed=episode,
                )

                result.episode = (
                    episode + 1
                )

                results.append(result)

    path = save_results(results)

    summarize(results)

    print(
        f"\nSaved results: {path}"
    )


if __name__ == "__main__":
    main()
