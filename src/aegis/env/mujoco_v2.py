from __future__ import annotations

import numpy as np

from aegis.env.mujoco_world import AegisMuJoCoEnv
from aegis.sensing import NoisyPositionSensor, SensorArbitrator


class AegisMuJoCoV2(AegisMuJoCoEnv):
    """
    Nexvia Aegis v2.0.

    Extends the working MuJoCo environment with:
    - primary sensor
    - independent verification sensor
    - cross-sensor arbitration
    - uncertainty-aware confidence
    """

    def __init__(
        self,
        primary_noise: float = 0.05,
        verifier_noise: float = 0.08,
        primary_bias: tuple[float, float] = (0.0, 0.0),
        verifier_bias: tuple[float, float] = (0.0, 0.0),
        disagreement_threshold: float = 0.35,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.primary_sensor = NoisyPositionSensor(
            noise_sigma=primary_noise,
            bias=primary_bias,
        )

        self.verifier_sensor = NoisyPositionSensor(
            noise_sigma=verifier_noise,
            bias=verifier_bias,
        )

        self.arbitrator = SensorArbitrator(
            disagreement_threshold=disagreement_threshold,
        )

        self.last_sensing_info = {}

    def _get_observation(self):
        robot_pos, robot_vel = self._get_robot_state()

        true_delta = self.target_pos - robot_pos

        primary = self.primary_sensor.measure(
            true_delta,
            self.np_random,
        )

        verifier = self.verifier_sensor.measure(
            true_delta,
            self.np_random,
        )

        arbitration = self.arbitrator.compare(
            primary,
            verifier,
        )

        fused_delta = arbitration["estimate"]
        fused_sigma = arbitration["sigma"]
        disagreement = arbitration["disagreement"]

        confidence = float(
            np.exp(
                -fused_sigma * 2.0
                -disagreement * 0.5
            )
        )

        observation = np.array(
            [
                robot_pos[0],
                robot_pos[1],
                robot_vel[0],
                robot_vel[1],
                fused_delta[0],
                fused_delta[1],
                confidence,
            ],
            dtype=np.float32,
        )

        self.last_sensing_info = {
            "primary_estimate": primary.estimate.copy(),
            "verifier_estimate": verifier.estimate.copy(),
            "fused_estimate": fused_delta.copy(),
            "fused_sigma": fused_sigma,
            "sensor_disagreement": disagreement,
            "normalized_disagreement": arbitration[
                "normalized_disagreement"
            ],
            "cross_mismatch": arbitration[
                "cross_mismatch"
            ],
            "sensor_anomaly": arbitration[
                "anomaly"
            ],
            "confidence": confidence,
        }

        return observation

    def reset(self, *, seed=None, options=None):
        observation, info = super().reset(
            seed=seed,
            options=options,
        )

        info["sensing"] = self.last_sensing_info.copy()

        return observation, info

    def step(self, action):
        observation, reward, terminated, truncated, info = (
            super().step(action)
        )

        info["sensing"] = self.last_sensing_info.copy()

        return (
            observation,
            reward,
            terminated,
            truncated,
            info,
        )
