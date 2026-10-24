from __future__ import annotations

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
)


ACTION_NAMES = {
    MOVE: "MOVE",
    INSPECT: "INSPECT",
    STOP: "STOP",
    ABSTAIN: "ABSTAIN",
    VERIFY: "VERIFY",
}


def run_case(
    name: str,
    observation_noise: float,
    seed: int = 42,
) -> None:
    print()
    print("=" * 70)
    print(
        f"{name} "
        f"(observation_noise={observation_noise})"
    )
    print("=" * 70)

    env = AegisInspectionEnv(
        observation_noise=observation_noise,
        inspection_noise=0.02,
        verification_noise=0.035,
        inspection_cost=0.03,
        verification_cost=0.04,
        movement_cost=0.01,
        abstain_cost=0.20,
        success_radius=0.06,
        max_steps=100,
        max_inspections=3,
        max_verifications=3,
    )

    policy = AegisPolicy(
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
        num_samples=512,
    )

    observation, info = env.reset(
        seed=seed
    )

    policy.reset(seed=seed)

    print(
        "Initial belief:",
        observation[2:4],
    )

    print(
        "Initial sigma:",
        round(float(observation[6]), 4),
    )

    print(
        "Initial confidence:",
        round(float(observation[5]), 4),
    )

    for step in range(1, 101):
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
            step_count=info["step_count"],
        )

        action = policy.act(
            observation,
            context,
        )

        previous_observation = observation.copy()

        (
            observation,
            reward,
            terminated,
            truncated,
            info,
        ) = env.step(action)

        print(
            f"Step {step:02d} | "
            f"Action: {ACTION_NAMES[action]:<8} | "
            f"Distance(est): "
            f"{policy.last_diagnostics['distance']:.4f} | "
            f"Probability: "
            f"{policy.last_diagnostics['probability']:.4f} | "
            f"Sigma: "
            f"{observation[6]:.4f} | "
            f"Reward: {reward:.3f}"
        )

        print(
            "            Utilities:",
            {
                key: (
                    round(value, 4)
                    if value != float("-inf")
                    else "-inf"
                )
                for key, value
                in policy.last_utilities.items()
            },
        )

        if terminated or truncated:
            if info["success"]:
                result = "SUCCESS"
            elif info["abstained"]:
                result = "ABSTAINED"
            else:
                result = "FAILED"

            print()
            print("RESULT:", result)
            print(
                "True distance:",
                round(
                    info["distance_to_target"],
                    4,
                ),
            )
            print(
                "Estimated distance:",
                round(
                    policy.last_diagnostics[
                        "distance"
                    ],
                    4,
                ),
            )
            print(
                "Inspections:",
                info["inspection_count"],
            )
            print(
                "Steps:",
                info["step_count"],
            )

            break

    env.close()


def main() -> None:
    print(
        "=== NEXVIA AEGIS v0.3 "
        "DECISION CHECK ==="
    )

    cases = [
        ("LOW", 0.02),
        ("MEDIUM", 0.08),
        ("HIGH", 0.15),
        ("SEVERE", 0.25),
    ]

    for name, noise in cases:
        run_case(
            name=name,
            observation_noise=noise,
        )


if __name__ == "__main__":
    main()
