from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aegis.decision import AegisDecisionPolicy
from aegis.env.mujoco_v2 import AegisMuJoCoV2


@dataclass(frozen=True)
class Scenario:
    name: str
    primary_noise: float = 0.05
    verifier_noise: float = 0.08
    primary_bias: tuple[float, float] = (0.0, 0.0)
    verifier_bias: tuple[float, float] = (0.0, 0.0)
    heavy_tail_probability: float = 0.0
    outlier_scale: float = 1.0
    drift_rate: tuple[float, float] = (0.0, 0.0)


SCENARIOS = [
    Scenario(
        name="NORMAL",
    ),
    Scenario(
        name="BIASED",
        verifier_bias=(1.0, 1.0),
    ),
    Scenario(
        name="HEAVY_TAIL",
        heavy_tail_probability=0.10,
        outlier_scale=4.0,
    ),
    Scenario(
        name="OUTLIER",
        heavy_tail_probability=0.15,
        outlier_scale=8.0,
    ),
    Scenario(
        name="DRIFT",
        drift_rate=(0.0025, 0.0015),
    ),
    Scenario(
        name="CORRELATED_BIAS",
        primary_bias=(0.7, 0.7),
        verifier_bias=(0.7, 0.7),
    ),
]


def build_env(scenario: Scenario) -> AegisMuJoCoV2:
    env = AegisMuJoCoV2(
        primary_noise=scenario.primary_noise,
        verifier_noise=scenario.verifier_noise,
        primary_bias=scenario.primary_bias,
        verifier_bias=scenario.verifier_bias,
    )

    env.primary_sensor.heavy_tail_probability = (
        scenario.heavy_tail_probability
    )
    env.primary_sensor.outlier_scale = (
        scenario.outlier_scale
    )

    env.verifier_sensor.heavy_tail_probability = (
        scenario.heavy_tail_probability
    )
    env.verifier_sensor.outlier_scale = (
        scenario.outlier_scale
    )

    return env


def apply_drift(
    env: AegisMuJoCoV2,
    scenario: Scenario,
    step_index: int,
) -> None:
    dx, dy = scenario.drift_rate

    if dx == 0.0 and dy == 0.0:
        return

    env.verifier_sensor.bias = np.asarray(
        [
            dx * step_index,
            dy * step_index,
        ],
        dtype=np.float64,
    )


def move_toward(delta: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(delta))

    if norm <= 1e-8:
        return np.zeros(2, dtype=np.float32)

    return np.asarray(
        delta / norm,
        dtype=np.float32,
    )


def run_episode(
    scenario: Scenario,
    policy_name: str,
    seed: int,
    max_steps: int = 300,
) -> dict:
    env = build_env(scenario)

    if policy_name == "AEGIS":
        policy = AegisDecisionPolicy()

    observation, info = env.reset(seed=seed)

    success = False
    total_reward = 0.0
    mismatch_steps = 0
    mismatch_act_steps = 0
    act_steps = 0
    verify_steps = 0
    abstain_steps = 0

    for step_index in range(1, max_steps + 1):
        apply_drift(
            env,
            scenario,
            step_index,
        )

        sensing = info["sensing"]

        fused_delta = np.asarray(
            sensing["fused_estimate"],
            dtype=np.float64,
        )

        estimated_distance = float(
            np.linalg.norm(fused_delta)
        )

        mismatch = bool(
            sensing["cross_mismatch"]
        )

        if mismatch:
            mismatch_steps += 1

        if policy_name == "ALWAYS_ACT":
            decision_action = "ACT"

        else:
            decision = policy.decide(
                estimated_distance=estimated_distance,
                confidence=sensing["confidence"],
                sensor_disagreement=sensing[
                    "sensor_disagreement"
                ],
                cross_mismatch=mismatch,
            )

            decision_action = decision.action

        if decision_action == "ACT":
            act_steps += 1
            action = move_toward(fused_delta)

            if mismatch:
                mismatch_act_steps += 1

        elif decision_action == "VERIFY":
            verify_steps += 1
            action = np.zeros(
                2,
                dtype=np.float32,
            )

        else:
            abstain_steps += 1
            action = np.zeros(
                2,
                dtype=np.float32,
            )

        (
            observation,
            reward,
            terminated,
            truncated,
            info,
        ) = env.step(action)

        total_reward += float(reward)

        if terminated:
            success = True
            break

        if truncated:
            break

    final_distance = float(
        info["ground_truth_distance"]
    )

    steps = int(info["step_count"])

    env.close()

    return {
        "scenario": scenario.name,
        "policy": policy_name,
        "success": int(success),
        "steps": steps,
        "final_distance": final_distance,
        "reward": total_reward,
        "act_steps": act_steps,
        "verify_steps": verify_steps,
        "abstain_steps": abstain_steps,
        "mismatch_steps": mismatch_steps,
        "mismatch_act_steps": mismatch_act_steps,
    }


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)

    return {
        "scenario": rows[0]["scenario"],
        "policy": rows[0]["policy"],
        "episodes": n,
        "success_rate": (
            sum(r["success"] for r in rows)
            / n
        ),
        "avg_steps": (
            sum(r["steps"] for r in rows)
            / n
        ),
        "avg_final_distance": (
            sum(r["final_distance"] for r in rows)
            / n
        ),
        "avg_reward": (
            sum(r["reward"] for r in rows)
            / n
        ),
        "act_rate": (
            sum(r["act_steps"] for r in rows)
            / sum(r["steps"] for r in rows)
        ),
        "verify_rate": (
            sum(r["verify_steps"] for r in rows)
            / sum(r["steps"] for r in rows)
        ),
        "abstain_rate": (
            sum(r["abstain_steps"] for r in rows)
            / sum(r["steps"] for r in rows)
        ),
        "mismatch_rate": (
            sum(r["mismatch_steps"] for r in rows)
            / sum(r["steps"] for r in rows)
        ),
        "mismatch_act_rate": (
            sum(r["mismatch_act_steps"] for r in rows)
            / max(
                sum(r["mismatch_steps"] for r in rows),
                1,
            )
        ),
    }


def main():
    episodes = 100
    base_seed = 200_000

    policies = [
        "ALWAYS_ACT",
        "AEGIS",
    ]

    result_rows = []
    summary_rows = []

    print("=== NEXVIA AEGIS v2.0 BENCHMARK ===")
    print(f"Episodes per scenario/policy: {episodes}")
    print(f"Base seed: {base_seed}")

    for scenario in SCENARIOS:
        for policy_name in policies:
            print(
                f"\nRunning "
                f"{scenario.name:<16} "
                f"{policy_name}"
            )

            rows = []

            for episode_index in range(episodes):
                seed = (
                    base_seed
                    + episode_index
                )

                row = run_episode(
                    scenario=scenario,
                    policy_name=policy_name,
                    seed=seed,
                )

                rows.append(row)
                result_rows.append(row)

            summary = aggregate(rows)
            summary_rows.append(summary)

            print(
                f"success={summary['success_rate']:.3f} "
                f"abstain={summary['abstain_rate']:.3f} "
                f"mismatch="
                f"{summary['mismatch_rate']:.3f} "
                f"mismatch_act="
                f"{summary['mismatch_act_rate']:.3f} "
                f"reward="
                f"{summary['avg_reward']:.3f}"
            )

    results_dir = Path("results")
    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_path = (
        results_dir
        / "v2_benchmark_episodes.csv"
    )

    summary_path = (
        results_dir
        / "v2_benchmark_summary.csv"
    )

    with raw_path.open(
        "w",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=result_rows[0].keys(),
        )
        writer.writeheader()
        writer.writerows(result_rows)

    with summary_path.open(
        "w",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=summary_rows[0].keys(),
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\n=== SUMMARY ===")

    for row in summary_rows:
        print(
            f"{row['scenario']:<16} "
            f"{row['policy']:<11} "
            f"success={row['success_rate']:.3f} "
            f"abstain={row['abstain_rate']:.3f} "
            f"mismatch_act="
            f"{row['mismatch_act_rate']:.3f} "
            f"reward={row['avg_reward']:.3f}"
        )

    print("\nWritten:")
    print(raw_path)
    print(summary_path)


if __name__ == "__main__":
    main()
