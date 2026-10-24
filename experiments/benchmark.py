from __future__ import annotations

import csv
import os
from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import AegisInspectionEnv


SUCCESS_DISTANCE = 0.06
NUM_EPISODES = 1000


@dataclass
class EpisodeResult:
    episode: int
    seed: int
    success: bool
    steps: int
    inspections: int
    total_reward: float
    final_true_distance: float
    final_estimated_distance: float


def estimated_distance(observation: np.ndarray) -> float:
    robot = observation[0:2]
    target_estimate = observation[2:4]

    return float(np.linalg.norm(robot - target_estimate))


def run_episode(
    policy_name: str,
    seed: int,
) -> EpisodeResult:
    env = AegisInspectionEnv()

    observation, _ = env.reset(seed=seed)

    total_reward = 0.0
    step_count = 0

    # Baseline A: move immediately.
    if policy_name == "always_act":
        pass

    # Baseline B: inspect once before acting.
    elif policy_name == "inspect_once":
        observation, reward, terminated, truncated, info = env.step(1)

        total_reward += reward
        step_count += 1

    else:
        raise ValueError(f"Unknown policy: {policy_name}")

    terminated = False
    truncated = False
    info = {}

    while not terminated and not truncated:
        estimated_dist = estimated_distance(observation)

        if estimated_dist <= SUCCESS_DISTANCE:
            action = 2  # STOP
        else:
            action = 0  # MOVE

        observation, reward, terminated, truncated, info = env.step(action)

        total_reward += reward
        step_count += 1

    result = EpisodeResult(
        episode=0,
        seed=seed,
        success=bool(info["success"]),
        steps=step_count,
        inspections=info["inspection_count"],
        total_reward=total_reward,
        final_true_distance=float(info["distance_to_target"]),
        final_estimated_distance=estimated_distance(observation),
    )

    env.close()

    return result


def run_benchmark(policy_name: str) -> list[EpisodeResult]:
    results: list[EpisodeResult] = []

    for episode in range(NUM_EPISODES):
        seed = episode

        result = run_episode(
            policy_name=policy_name,
            seed=seed,
        )

        result.episode = episode + 1
        results.append(result)

    return results


def save_results(
    policy_name: str,
    results: list[EpisodeResult],
) -> str:
    os.makedirs("results", exist_ok=True)

    path = f"results/{policy_name}_1000.csv"

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "episode",
                "seed",
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
    policy_name: str,
    results: list[EpisodeResult],
) -> None:
    success_rate = np.mean(
        [result.success for result in results]
    )

    average_steps = np.mean(
        [result.steps for result in results]
    )

    average_inspections = np.mean(
        [result.inspections for result in results]
    )

    average_reward = np.mean(
        [result.total_reward for result in results]
    )

    average_true_distance = np.mean(
        [result.final_true_distance for result in results]
    )

    print(f"\n=== {policy_name.upper()} ===")
    print(f"Episodes:              {len(results)}")
    print(f"Success rate:          {success_rate:.3%}")
    print(f"Average steps:         {average_steps:.3f}")
    print(f"Average inspections:   {average_inspections:.3f}")
    print(f"Average reward:        {average_reward:.4f}")
    print(f"Average true distance: {average_true_distance:.4f}")


def main() -> None:
    print("\n=== NEXVIA AEGIS BENCHMARK ===")
    print(f"Episodes per policy: {NUM_EPISODES}")

    for policy_name in [
        "always_act",
        "inspect_once",
    ]:
        print(f"\nRunning: {policy_name}")

        results = run_benchmark(policy_name)

        path = save_results(
            policy_name,
            results,
        )

        print_summary(
            policy_name,
            results,
        )

        print("Saved:", path)


if __name__ == "__main__":
    main()
