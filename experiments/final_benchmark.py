from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import (
    AegisInspectionEnv,
    STOP,
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
    stop_probability: float | None
    stop_label: int | None


@dataclass
class AggregateResult:
    success_rate: float
    false_stop_rate: float
    abstain_rate: float
    anomaly_rate: float
    recovery_rate: float
    mismatch_rate: float
    avg_steps: float
    avg_inspections: float
    avg_verifications: float
    avg_reward: float
    stop_count: int
    false_stop_count: int
    brier: float
    ece: float


def make_env(scenario: str) -> AegisInspectionEnv:
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
        max_inspections=2,
        max_verifications=2,
        scenario=scenario,
    )


def make_policy(name: str):
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
            progress_weight=0.08,
            stop_probability_threshold=0.90,
            max_stop_sigma=0.045,
            mismatch_threshold=0.35,
            low_primary_trust=0.55,
            num_samples=1024,
        )
    raise ValueError(f"Unknown policy: {name}")


def run_episode(policy_name: str, scenario: str, seed: int) -> EpisodeResult:
    env = make_env(scenario)
    policy = make_policy(policy_name)

    observation, info = env.reset(seed=seed)
    policy.reset(seed=seed)

    total_reward = 0.0
    stop_count = 0
    false_stops = 0
    anomaly_detected = False
    cross_mismatch = False
    stop_probability = None
    stop_label = None

    for _ in range(env.max_steps):
        context = AgentContext(
            inspection_count=info["inspection_count"],
            max_inspections=env.max_inspections,
            verification_count=info["verification_count"],
            max_verifications=env.max_verifications,
            step_count=info["step_count"],
        )

        action = policy.act(observation, context)

        if policy_name == "aegis" and action == STOP:
            stop_probability = float(
                policy.last_diagnostics["effective_probability"]
            )

        observation, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)

        anomaly_detected = anomaly_detected or info["anomaly_this_step"]
        cross_mismatch = (
            cross_mismatch or info["cross_mismatch_this_step"]
        )

        if action == STOP:
            stop_count += 1
            stop_label = 1 if info["success"] else 0
            if not info["success"]:
                false_stops += 1

        if terminated or truncated:
            break

    env.close()

    return EpisodeResult(
        success=bool(info["success"]),
        abstained=bool(info["abstained"]),
        steps=int(info["step_count"]),
        inspections=int(info["inspection_count"]),
        verifications=int(info["verification_count"]),
        reward=total_reward,
        stop_count=stop_count,
        false_stops=false_stops,
        anomaly_detected=anomaly_detected,
        cross_mismatch=cross_mismatch,
        stop_probability=stop_probability,
        stop_label=stop_label,
    )


def brier(probabilities: list[float], labels: list[int]) -> float:
    if not probabilities:
        return float("nan")
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    return float(np.mean((p - y) ** 2))


def ece(
    probabilities: list[float],
    labels: list[int],
    bins: int = 10,
) -> float:
    if not probabilities:
        return float("nan")

    p = np.clip(
        np.asarray(probabilities, dtype=np.float64),
        0.0,
        1.0,
    )
    y = np.asarray(labels, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, bins + 1)
    score = 0.0

    for index in range(bins):
        low = edges[index]
        high = edges[index + 1]
        if index == bins - 1:
            mask = (p >= low) & (p <= high)
        else:
            mask = (p >= low) & (p < high)
        if not np.any(mask):
            continue
        score += (
            np.mean(mask)
            * abs(
                np.mean(p[mask])
                - np.mean(y[mask])
            )
        )

    return float(score)


def aggregate(
    episodes: list[EpisodeResult],
) -> AggregateResult:
    total = len(episodes)

    success = sum(e.success for e in episodes)
    abstain = sum(e.abstained for e in episodes)
    anomalies = sum(e.anomaly_detected for e in episodes)
    mismatches = sum(e.cross_mismatch for e in episodes)
    stops = sum(e.stop_count for e in episodes)
    false_stops = sum(e.false_stops for e in episodes)

    anomaly_episodes = [
        e for e in episodes
        if e.anomaly_detected
    ]

    recovery = (
        sum(e.success for e in anomaly_episodes)
        / len(anomaly_episodes)
        if anomaly_episodes
        else float("nan")
    )

    probabilities = [
        e.stop_probability
        for e in episodes
        if e.stop_probability is not None
        and e.stop_label is not None
    ]
    labels = [
        e.stop_label
        for e in episodes
        if e.stop_probability is not None
        and e.stop_label is not None
    ]

    return AggregateResult(
        success_rate=success / total,
        false_stop_rate=false_stops / stops if stops else 0.0,
        abstain_rate=abstain / total,
        anomaly_rate=anomalies / total,
        recovery_rate=recovery,
        mismatch_rate=mismatches / total,
        avg_steps=float(np.mean([e.steps for e in episodes])),
        avg_inspections=float(
            np.mean([e.inspections for e in episodes])
        ),
        avg_verifications=float(
            np.mean([e.verifications for e in episodes])
        ),
        avg_reward=float(
            np.mean([e.reward for e in episodes])
        ),
        stop_count=stops,
        false_stop_count=false_stops,
        brier=brier(probabilities, labels),
        ece=ece(probabilities, labels),
    )


def print_result(
    title: str,
    result: AggregateResult,
) -> None:
    print(f"\n{title}")
    print("-" * 72)
    print(
        f"Success Rate          : "
        f"{result.success_rate * 100:7.2f}%"
    )
    print(
        f"False Stop Rate       : "
        f"{result.false_stop_rate * 100:7.2f}%"
    )
    print(
        f"Abstain Rate          : "
        f"{result.abstain_rate * 100:7.2f}%"
    )
    print(
        f"Anomaly Rate          : "
        f"{result.anomaly_rate * 100:7.2f}%"
    )

    if np.isfinite(result.recovery_rate):
        print(
            f"Recovery Rate         : "
            f"{result.recovery_rate * 100:7.2f}%"
        )
    else:
        print("Recovery Rate         : N/A")

    print(
        f"Cross-Mismatch Rate   : "
        f"{result.mismatch_rate * 100:7.2f}%"
    )
    print(
        f"Average Steps         : "
        f"{result.avg_steps:7.2f}"
    )
    print(
        f"Average Inspections   : "
        f"{result.avg_inspections:7.2f}"
    )
    print(
        f"Average Verifications : "
        f"{result.avg_verifications:7.2f}"
    )
    print(
        f"Average Reward        : "
        f"{result.avg_reward:7.4f}"
    )
    print(
        f"Stop Decisions        : "
        f"{result.stop_count}"
    )
    print(
        f"False Stops           : "
        f"{result.false_stop_count}"
    )

    if np.isfinite(result.brier):
        print(
            f"Brier Score           : "
            f"{result.brier:7.4f}"
        )
        print(
            f"ECE                   : "
            f"{result.ece:7.4f}"
        )


def run_scenario(
    scenario: str,
    episodes: int,
    base_seed: int,
) -> None:
    print("\n" + "=" * 82)
    print(
        f"SCENARIO: {scenario.upper()} | "
        f"EPISODES: {episodes}"
    )
    print("=" * 82)

    policies = [
        "always_act",
        "inspect_once",
        "aegis",
    ]

    results: dict[str, AggregateResult] = {}

    for policy_name in policies:
        runs = [
            run_episode(
                policy_name=policy_name,
                scenario=scenario,
                seed=base_seed + index,
            )
            for index in range(episodes)
        ]

        result = aggregate(runs)
        results[policy_name] = result

        titles = {
            "always_act": "Always Act",
            "inspect_once": "Inspect Once",
            "aegis": "Nexvia Aegis v1.0",
        }

        print_result(
            titles[policy_name],
            result,
        )

    aegis = results["aegis"]
    baseline = results["always_act"]

    print("\nAegis vs Always Act")
    print("-" * 72)
    print(
        f"Success Δ     : "
        f"{(aegis.success_rate - baseline.success_rate) * 100:+.2f} pp"
    )
    print(
        f"False Stop Δ  : "
        f"{(aegis.false_stop_rate - baseline.false_stop_rate) * 100:+.2f} pp"
    )
    print(
        f"Reward Δ      : "
        f"{aegis.avg_reward - baseline.avg_reward:+.4f}"
    )


def main() -> None:
    print("=== NEXVIA AEGIS v1.0 FINAL BENCHMARK ===")
    print(
        "Uncertainty + Active Sensing + "
        "Cross-Sensor Arbitration + Abstention"
    )

    scenarios = [
        "normal",
        "biased",
        "heavy_tail",
        "outlier",
        "drift",
        "correlated_bias",
    ]

    episodes = 1000
    base_seed = 40_000

    for scenario in scenarios:
        run_scenario(
            scenario,
            episodes,
            base_seed,
        )
        base_seed += episodes


if __name__ == "__main__":
    main()
