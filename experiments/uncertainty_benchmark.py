from __future__ import annotations

import csv
import os
from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import AegisInspectionEnv


NUM_EPISODES = 1000
SUCCESS_DISTANCE = 0.06


UNCERTAINTY_LEVELS = {
    "low": {
        "observation_noise": 0.02,
        "inspection_noise": 0.005,
    },
    "medium": {
        "observation_noise": 0.08,
        "inspection_noise": 0.015,
    },
    "high": {
        "observation_noise": 0.15,
        "inspection_noise": 0.03,
    },
    "severe": {
        "observation_noise": 0.25,
        "inspection_noise": 0.05,
    },
}


POLICIES = [
    "always_act",
    "inspect_once",
]


@dataclass
class EpisodeResult:
    episode: int
    seed: int
    uncertainty: str
    policy: str
    success: bool
    steps: int
    inspections: int
    total_reward: float
    final_true_distance: float
    final_estimated_distance: float


def estimated_distance(
    observation: np.ndarray,
) -> float:
    robot = observation[0:2]
    target_estimate = observation[2:4]

    return float(
        np.linalg.norm(
            robot - target_estimate
        )
    )


def run_episode(
    policy: str,
    uncertainty: str,
    seed: int,
) -> EpisodeResult:
    config = UNCERTAINTY_LEVELS[uncertainty]

    env = AegisInspectionEnv(
        observation_noise=config["observation_noise"],
        inspection_noise=config["inspection_noise"],
    )

    observation, _ = env.reset(seed=seed)

    total_reward = 0.0
    step_count = 0
    terminated = False
    truncated = False
    info = {}

    # ---------------------------------------------------------
    # Optional initial inspection
    # ---------------------------------------------------------

    if policy == "inspect_once":
        (
            observation,
            reward,
            terminated,
            truncated,
            info,
        ) = env.step(1)

        total_reward += reward
        step_count += 1

    elif policy != "always_act":
        raise ValueError(
            f"Unknown policy: {policy}"
        )

    # ---------------------------------------------------------
    # Main loop
    # ---------------------------------------------------------

    while not terminated and not truncated:
        distance = estimated_distance(observation)

        if distance <= SUCCESS_DISTANCE:
            action = 2  # STOP
        else:
            action = 0  # MOVE

        (
            observation,
            reward,
            terminated,
            truncated,
            info,
        ) = env.step(action)

        total_reward += reward
        step_count += 1

    result = EpisodeResult(
        episode=0,
        seed=seed,
        uncertainty=uncertainty,
        policy=policy,
        success=bool(info["success"]),
        steps=step_count,
        inspections=info["inspection_count"],
        total_reward=total_reward,
        final_true_distance=float(
            info["distance_to_target"]
        ),
        final_estimated_distance=estimated_distance(
            observation
        ),
    )

    env.close()

    return result


def save_results(
    results: list[EpisodeResult],
) -> str:
    os.makedirs("results", exist_ok=True)

    path = "results/uncertainty_benchmark.csv"

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
                "steps",
                "inspections",
                "total_reward",
                "final_true_distance",
                "final_estimated_distance",
            ]
        )

        for result in results:
            writer.writerow(
                [
                    result.episode,
                    result.seed,
                    result.uncertainty,
                    result.policy,
                    result.success,
                    result.steps,
                    result.inspections,
                    result.total_reward,
                    result.final_true_distance,
                    result.final_estimated_distance,
                ]
            )

    return path


def print_summary(
    results: list[EpisodeResult],
) -> None:
    print("\n=== SUMMARY ===")

    for uncertainty in UNCERTAINTY_LEVELS:
        for policy in POLICIES:
            subset = [
                result
                for result in results
                if result.uncertainty == uncertainty
                and result.policy == policy
            ]

            success_rate = np.mean(
                [result.success for result in subset]
            )

            average_steps = np.mean(
                [result.steps for result in subset]
            )

            average_inspections = np.mean(
                [result.inspections for result in subset]
            )

            average_reward = np.mean(
                [result.total_reward for result in subset]
            )

            average_true_distance = np.mean(
                [
                    result.final_true_distance
                    for result in subset
                ]
            )

            print(
                f"{uncertainty:>7} | "
                f"{policy:<12} | "
                f"success={success_rate:7.2%} | "
                f"steps={average_steps:6.2f} | "
                f"inspect={average_inspections:5.2f} | "
                f"reward={average_reward:8.4f} | "
                f"error={average_true_distance:7.4f}"
            )


def main() -> None:
    print("=== NEXVIA AEGIS — UNCERTAINTY BENCHMARK ===")
    print(f"Episodes per condition: {NUM_EPISODES}")

    results: list[EpisodeResult] = []

    for uncertainty in UNCERTAINTY_LEVELS:
        for policy in POLICIES:
            print(
                f"\nRunning "
                f"{uncertainty.upper()} / "
                f"{policy}"
            )

            for episode in range(NUM_EPISODES):
                result = run_episode(
                    policy=policy,
                    uncertainty=uncertainty,
                    seed=episode,
                )

                result.episode = episode + 1

                results.append(result)

    path = save_results(results)

    print_summary(results)

    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
