from __future__ import annotations

import numpy as np

from aegis.decision import AegisDecisionPolicy
from aegis.env.mujoco_v2 import AegisMuJoCoV2


def run_episode(
    env: AegisMuJoCoV2,
    policy: AegisDecisionPolicy,
    seed: int,
):
    observation, info = env.reset(seed=seed)

    decisions = {
        "ACT": 0,
        "VERIFY": 0,
        "ABSTAIN": 0,
    }

    print("\n=== Episode ===")
    print("target:", info["target_pos"])
    print("initial distance:", info["ground_truth_distance"])

    for step in range(100):
        sensing = info["sensing"]

        fused_delta = np.asarray(
            sensing["fused_estimate"],
            dtype=np.float64,
        )

        estimated_distance = float(
            np.linalg.norm(fused_delta)
        )

        decision = policy.decide(
            estimated_distance=estimated_distance,
            confidence=sensing["confidence"],
            sensor_disagreement=sensing[
                "sensor_disagreement"
            ],
            cross_mismatch=sensing[
                "cross_mismatch"
            ],
        )

        decisions[decision.action] += 1

        print(
            f"step={step + 1:03d} "
            f"decision={decision.action:<7} "
            f"confidence={decision.confidence:.3f} "
            f"estimated_distance={estimated_distance:.3f} "
            f"disagreement="
            f"{sensing['sensor_disagreement']:.3f}"
        )

        # ACT:
        # move toward the fused target estimate.
        if decision.action == "ACT":
            direction = fused_delta

            norm = float(np.linalg.norm(direction))

            if norm > 1e-8:
                action = direction / norm
            else:
                action = np.zeros(2)

        # VERIFY:
        # remain still and acquire a fresh sensor observation.
        elif decision.action == "VERIFY":
            action = np.zeros(2)

        # ABSTAIN:
        # safe hold.
        else:
            action = np.zeros(2)

        observation, reward, terminated, truncated, info = (
            env.step(action)
        )

        if terminated or truncated:
            break

    print("\nFinal state")
    print("robot:", info["robot_pos"])
    print("distance:", info["ground_truth_distance"])
    print("steps:", info["step_count"])
    print("decisions:", decisions)


def main():
    env = AegisMuJoCoV2()

    policy = AegisDecisionPolicy(
        act_confidence=0.75,
        verify_confidence=0.50,
        max_disagreement=0.35,
        target_tolerance=0.25,
    )

    run_episode(
        env=env,
        policy=policy,
        seed=42,
    )

    env.close()


if __name__ == "__main__":
    main()

