from __future__ import annotations

import numpy as np

from aegis.env.inspection import AegisInspectionEnv


ACTION_NAMES = {
    0: "MOVE",
    1: "INSPECT",
    2: "STOP",
}


def estimated_distance(observation: np.ndarray) -> float:
    robot = observation[0:2]
    target_estimate = observation[2:4]

    return float(np.linalg.norm(robot - target_estimate))


def main() -> None:
    env = AegisInspectionEnv()

    observation, info = env.reset(seed=42)

    print("\n=== NEXVIA AEGIS — BASELINE 1 ===")
    print("Policy: INSPECT → MOVE → STOP")
    print()
    print("Initial observation:", observation)
    print("Initial confidence:", observation[5])

    # ---------------------------------------------------------
    # Step 1: INSPECT
    # ---------------------------------------------------------

    observation, reward, terminated, truncated, info = env.step(1)

    print("\nStep 01")
    print("Action: INSPECT")
    print("Estimated distance:",
          round(estimated_distance(observation), 4))
    print("Confidence:",
          round(float(observation[5]), 4))
    print("Reward:",
          round(reward, 4))

    step = 1

    # ---------------------------------------------------------
    # Step 2+: MOVE using ONLY observation
    # ---------------------------------------------------------

    while not terminated and not truncated:
        estimated_dist = estimated_distance(observation)

        if estimated_dist <= 0.06:
            action = 2  # STOP
        else:
            action = 0  # MOVE

        observation, reward, terminated, truncated, info = env.step(action)

        step += 1

        print(
            f"Step {step:02d} | "
            f"Action: {ACTION_NAMES[action]:<7} | "
            f"Estimated distance: "
            f"{estimated_distance(observation):.4f} | "
            f"Confidence: {observation[5]:.2f} | "
            f"Reward: {reward:.3f}"
        )

    print("\n=== RESULT ===")
    print("Success:", info["success"])
    print("Final true distance:",
          round(info["distance_to_target"], 4))
    print("Final estimated distance:",
          round(estimated_distance(observation), 4))
    print("Total steps:", info["step_count"])
    print("Inspections:", info["inspection_count"])
    print("Terminated:", terminated)
    print("Truncated:", truncated)

    env.close()


if __name__ == "__main__":
    main()
