from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

MOVE = 0
INSPECT = 1
STOP = 2
ABSTAIN = 3
VERIFY = 4


class AegisInspectionEnv(gym.Env):
    """
    Nexvia Aegis v1.0 environment.

    The primary sensor can experience distribution shift.
    A separate verification sensor provides an independent
    observation stream. The policy receives only observable
    belief/uncertainty/trust state; ground truth is evaluation-only.

    Scenarios:
        normal
        biased
        heavy_tail
        outlier
        drift
        correlated_bias
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        observation_noise: float = 0.08,
        inspection_noise: float = 0.02,
        verification_noise: float = 0.035,
        inspection_cost: float = 0.03,
        verification_cost: float = 0.04,
        movement_cost: float = 0.01,
        abstain_cost: float = 0.20,
        stop_failure_penalty: float = 1.0,
        success_radius: float = 0.06,
        max_steps: int = 100,
        max_inspections: int = 2,
        max_verifications: int = 2,
        scenario: str = "normal",
    ) -> None:
        super().__init__()

        if observation_noise <= 0:
            raise ValueError("observation_noise must be > 0")
        if inspection_noise <= 0:
            raise ValueError("inspection_noise must be > 0")
        if verification_noise <= 0:
            raise ValueError("verification_noise must be > 0")
        if success_radius <= 0:
            raise ValueError("success_radius must be > 0")
        if max_steps <= 0:
            raise ValueError("max_steps must be > 0")
        if max_inspections < 0:
            raise ValueError("max_inspections must be >= 0")
        if max_verifications < 0:
            raise ValueError("max_verifications must be >= 0")

        valid_scenarios = {
            "normal",
            "biased",
            "heavy_tail",
            "outlier",
            "drift",
            "correlated_bias",
        }
        if scenario not in valid_scenarios:
            raise ValueError(
                f"Unknown scenario: {scenario}; expected {sorted(valid_scenarios)}"
            )

        self.observation_noise = float(observation_noise)
        self.inspection_noise = float(inspection_noise)
        self.verification_noise = float(verification_noise)
        self.inspection_cost = float(inspection_cost)
        self.verification_cost = float(verification_cost)
        self.movement_cost = float(movement_cost)
        self.abstain_cost = float(abstain_cost)
        self.stop_failure_penalty = float(stop_failure_penalty)
        self.success_radius = float(success_radius)
        self.max_steps = int(max_steps)
        self.max_inspections = int(max_inspections)
        self.max_verifications = int(max_verifications)
        self.scenario = scenario

        self.action_space = spaces.Discrete(5)

        # Observation vector:
        # 0-1  robot position
        # 2-3  fused belief position
        # 4    fused sigma
        # 5    primary sensor trust
        # 6    verifier sensor trust
        # 7    verifier available flag
        # 8    cross-sensor disagreement, scaled to [0, 1]
        # 9    recent primary residual, scaled to [0, 1]
        # 10   verification quality
        # 11   visibility of fused belief
        self.observation_space = spaces.Box(
            low=np.zeros(12, dtype=np.float32),
            high=np.ones(12, dtype=np.float32),
            dtype=np.float32,
        )

        self.robot = np.zeros(2, dtype=np.float64)
        self.true_target = np.zeros(2, dtype=np.float64)

        self.primary_belief = np.zeros(2, dtype=np.float64)
        self.primary_sigma = self.observation_noise

        self.verifier_belief = np.zeros(2, dtype=np.float64)
        self.verifier_sigma = self.verification_noise
        self.verifier_available = False

        self.fused_belief = np.zeros(2, dtype=np.float64)
        self.fused_sigma = self.observation_noise

        self.primary_trust = 1.0
        self.verifier_trust = 1.0
        self.cross_sensor_disagreement = 0.0
        self.last_residual = 0.0
        self.verification_score = 1.0

        self.last_primary_measurement: np.ndarray | None = None
        self.last_verifier_measurement: np.ndarray | None = None

        self.inspection_count = 0
        self.verification_count = 0
        self.step_count = 0

        self.success = False
        self.abstained = False
        self.terminated_by_stop = False
        self.anomaly_detected = False
        self.cross_sensor_mismatch = False

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ):
        super().reset(seed=seed)

        self.robot = np.array([0.05, 0.05], dtype=np.float64)
        self.true_target = self.np_random.uniform(0.20, 0.80, size=2)

        primary = self._generate_primary_measurement(
            noise_std=self.observation_noise
        )

        self.primary_belief = primary.copy()
        self.primary_sigma = self.observation_noise

        self.verifier_belief = np.zeros(2, dtype=np.float64)
        self.verifier_sigma = self.verification_noise
        self.verifier_available = False

        self.fused_belief = primary.copy()
        self.fused_sigma = self.observation_noise

        self.primary_trust = 1.0
        self.verifier_trust = 1.0
        self.cross_sensor_disagreement = 0.0
        self.last_residual = 0.0
        self.verification_score = 1.0

        self.last_primary_measurement = primary.copy()
        self.last_verifier_measurement = None

        self.inspection_count = 0
        self.verification_count = 0
        self.step_count = 0

        self.success = False
        self.abstained = False
        self.terminated_by_stop = False
        self.anomaly_detected = False
        self.cross_sensor_mismatch = False

        self._recompute_fused_belief()

        return self._get_observation(), self._build_info()

    def step(self, action: int):
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action: {action}")

        if self.success or self.abstained or self.terminated_by_stop:
            raise RuntimeError("step() called after episode termination")

        self.step_count += 1
        reward = 0.0
        terminated = False
        truncated = False
        anomaly_this_step = False
        cross_mismatch_this_step = False

        if action == MOVE:
            self._move_toward_fused_belief()
            measurement = self._generate_primary_measurement(
                noise_std=self.observation_noise
            )
            anomaly_this_step, cross_mismatch_this_step = self._update_primary(
                measurement,
                measurement_noise=self.observation_noise,
            )
            reward = -self.movement_cost

        elif action == INSPECT:
            anomaly_this_step, cross_mismatch_this_step = self._inspect()
            reward = -self.inspection_cost

        elif action == VERIFY:
            cross_mismatch_this_step = self._verify()
            reward = -self.verification_cost

        elif action == STOP:
            distance = float(np.linalg.norm(self.robot - self.true_target))
            terminated = True
            self.terminated_by_stop = True
            if distance <= self.success_radius:
                self.success = True
                reward = 1.0
            else:
                reward = -self.stop_failure_penalty

        elif action == ABSTAIN:
            terminated = True
            self.abstained = True
            reward = -self.abstain_cost

        if not terminated and self.step_count >= self.max_steps:
            truncated = True

        self.anomaly_detected = self.anomaly_detected or anomaly_this_step
        self.cross_sensor_mismatch = (
            self.cross_sensor_mismatch or cross_mismatch_this_step
        )

        return (
            self._get_observation(),
            reward,
            terminated,
            truncated,
            self._build_info(
                action=action,
                anomaly_this_step=anomaly_this_step,
                cross_mismatch_this_step=cross_mismatch_this_step,
            ),
        )

    def _move_toward_fused_belief(self) -> None:
        direction = self.fused_belief - self.robot
        distance = float(np.linalg.norm(direction))
        if distance <= 1e-12:
            return
        direction /= distance
        self.robot = np.clip(self.robot + direction * 0.05, 0.0, 1.0)

    def _inspect(self) -> tuple[bool, bool]:
        if self.inspection_count >= self.max_inspections:
            return False, False

        measurement = self._generate_primary_measurement(
            noise_std=self.inspection_noise
        )
        anomaly, mismatch = self._update_primary(
            measurement,
            measurement_noise=self.inspection_noise,
        )
        self.inspection_count += 1
        return anomaly, mismatch

    def _verify(self) -> bool:
        if self.verification_count >= self.max_verifications:
            return False

        measurement = self._generate_verification_measurement()

        if not self.verifier_available:
            self.verifier_belief = measurement.copy()
            self.verifier_sigma = self.verification_noise
            self.verifier_available = True
        else:
            self.verifier_belief, self.verifier_sigma = self._kalman_update(
                self.verifier_belief,
                self.verifier_sigma,
                measurement,
                self.verification_noise,
            )

        self.last_verifier_measurement = measurement.copy()
        mismatch = self._recompute_cross_sensor_state(update_trust=True)
        self.verification_count += 1

        return mismatch

    def _update_primary(
        self,
        measurement: np.ndarray,
        measurement_noise: float,
    ) -> tuple[bool, bool]:
        prior_belief = self.primary_belief.copy()
        prior_sigma = max(float(self.primary_sigma), 1e-6)

        denominator = np.sqrt(
            max(prior_sigma**2 + measurement_noise**2, 1e-12)
        )
        residual = float(
            np.linalg.norm(measurement - prior_belief)
            / denominator
        )

        anomaly = residual >= 3.0
        self.last_residual = residual
        self.last_primary_measurement = measurement.copy()

        self.primary_belief, self.primary_sigma = self._kalman_update(
            prior_belief,
            prior_sigma,
            measurement,
            measurement_noise,
        )

        consistency = float(
            np.exp(-0.5 * min(residual, 8.0) ** 2)
        )
        self.verification_score = min(
            1.0,
            0.85 * self.verification_score + 0.15 * consistency,
        )

        mismatch = False
        if self.verifier_available:
            mismatch = self._recompute_cross_sensor_state(update_trust=False)
        else:
            self._recompute_fused_belief()

        return anomaly, mismatch

    def _recompute_cross_sensor_state(
        self,
        *,
        update_trust: bool,
    ) -> bool:
        if not self.verifier_available:
            self.cross_sensor_disagreement = 0.0
            self._recompute_fused_belief()
            return False

        combined_sigma = np.sqrt(
            max(self.primary_sigma**2 + self.verifier_sigma**2, 1e-12)
        )
        disagreement = float(
            np.linalg.norm(self.primary_belief - self.verifier_belief)
            / combined_sigma
        )

        self.cross_sensor_disagreement = min(
            disagreement / 6.0,
            1.0,
        )

        mismatch = disagreement >= 2.5

        if update_trust:
            if mismatch:
                self.primary_trust = max(
                    0.15,
                    self.primary_trust * 0.55,
                )
                self.verifier_trust = min(
                    1.0,
                    self.verifier_trust + 0.03,
                )
                self.verification_score *= 0.60
            else:
                self.primary_trust = min(
                    1.0,
                    self.primary_trust + 0.04,
                )
                self.verifier_trust = min(
                    1.0,
                    self.verifier_trust + 0.02,
                )
                self.verification_score = min(
                    1.0,
                    0.80 * self.verification_score
                    + 0.20 * np.exp(-0.5 * disagreement**2),
                )

        self._recompute_fused_belief()
        return mismatch

    @staticmethod
    def _kalman_update(
        belief: np.ndarray,
        sigma: float,
        measurement: np.ndarray,
        measurement_sigma: float,
    ) -> tuple[np.ndarray, float]:
        prior_variance = max(sigma**2, 1e-12)
        measurement_variance = max(measurement_sigma**2, 1e-12)
        gain = prior_variance / (prior_variance + measurement_variance)
        posterior = belief + gain * (measurement - belief)
        posterior_variance = (1.0 - gain) * prior_variance
        return (
            np.clip(posterior, 0.0, 1.0),
            float(np.sqrt(max(posterior_variance, 1e-12))),
        )

    def _recompute_fused_belief(self) -> None:
        if not self.verifier_available:
            self.fused_belief = self.primary_belief.copy()
            self.fused_sigma = float(self.primary_sigma)
            return

        primary_var = max(self.primary_sigma**2, 1e-8)
        verifier_var = max(self.verifier_sigma**2, 1e-8)

        wp = self.primary_trust / primary_var
        wv = self.verifier_trust / verifier_var
        total = max(wp + wv, 1e-12)

        self.fused_belief = np.clip(
            (wp * self.primary_belief + wv * self.verifier_belief) / total,
            0.0,
            1.0,
        )
        self.fused_sigma = float(np.sqrt(1.0 / total))

    def _generate_primary_measurement(
        self,
        noise_std: float,
    ) -> np.ndarray:
        if self.scenario in {
            "normal",
            "biased",
            "outlier",
            "drift",
            "correlated_bias",
        }:
            noise = self.np_random.normal(
                0.0,
                noise_std,
                size=2,
            )
        elif self.scenario == "heavy_tail":
            noise = (
                self.np_random.standard_t(
                    df=3,
                    size=2,
                )
                * (noise_std / np.sqrt(3.0))
            )
        else:
            raise RuntimeError("Unknown scenario")

        bias = np.zeros(2, dtype=np.float64)

        if self.scenario in {"biased", "correlated_bias"}:
            bias = np.array([0.10, -0.08], dtype=np.float64)
        elif self.scenario == "drift":
            drift = min(
                0.18,
                0.025 + 0.007 * self.step_count,
            )
            bias = np.array(
                [drift, -0.70 * drift],
                dtype=np.float64,
            )
        elif self.scenario == "outlier":
            if self.np_random.random() < 0.12:
                noise += self.np_random.normal(
                    0.0,
                    max(4.0 * noise_std, 0.15),
                    size=2,
                )

        return np.clip(
            self.true_target + bias + noise,
            0.0,
            1.0,
        )

    def _generate_verification_measurement(self) -> np.ndarray:
        noise = self.np_random.normal(
            0.0,
            self.verification_noise,
            size=2,
        )

        bias = np.zeros(2, dtype=np.float64)
        if self.scenario == "correlated_bias":
            bias = np.array([0.10, -0.08], dtype=np.float64)

        return np.clip(
            self.true_target + bias + noise,
            0.0,
            1.0,
        )

    def _get_observation(self) -> np.ndarray:
        distance = float(
            np.linalg.norm(
                self.robot - self.fused_belief
            )
        )
        visibility = float(
            np.exp(-distance / 0.5)
        )

        observation = np.array(
            [
                self.robot[0],
                self.robot[1],
                self.fused_belief[0],
                self.fused_belief[1],
                min(self.fused_sigma, 1.0),
                self.primary_trust,
                self.verifier_trust,
                float(self.verifier_available),
                self.cross_sensor_disagreement,
                min(self.last_residual / 8.0, 1.0),
                self.verification_score,
                visibility,
            ],
            dtype=np.float32,
        )

        return np.clip(observation, 0.0, 1.0)

    def _build_info(
        self,
        action: int | None = None,
        anomaly_this_step: bool = False,
        cross_mismatch_this_step: bool = False,
    ) -> dict[str, Any]:
        true_distance = float(
            np.linalg.norm(
                self.robot - self.true_target
            )
        )
        estimated_distance = float(
            np.linalg.norm(
                self.robot - self.fused_belief
            )
        )

        return {
            "success": bool(self.success),
            "abstained": bool(self.abstained),
            "terminated_by_stop": bool(self.terminated_by_stop),
            "step_count": self.step_count,
            "inspection_count": self.inspection_count,
            "verification_count": self.verification_count,
            "distance_to_target": true_distance,
            "estimated_distance": estimated_distance,
            "true_target": self.true_target.copy(),
            "primary_belief": self.primary_belief.copy(),
            "verifier_belief": self.verifier_belief.copy(),
            "fused_belief": self.fused_belief.copy(),
            "primary_sigma": float(self.primary_sigma),
            "verifier_sigma": float(self.verifier_sigma),
            "fused_sigma": float(self.fused_sigma),
            "primary_trust": float(self.primary_trust),
            "verifier_trust": float(self.verifier_trust),
            "verifier_available": bool(self.verifier_available),
            "cross_sensor_disagreement": float(self.cross_sensor_disagreement),
            "verification_residual": float(self.last_residual),
            "verification_score": float(self.verification_score),
            "anomaly_this_step": bool(anomaly_this_step),
            "anomaly_detected": bool(self.anomaly_detected),
            "cross_mismatch_this_step": bool(cross_mismatch_this_step),
            "cross_sensor_mismatch": bool(self.cross_sensor_mismatch),
            "scenario": self.scenario,
            "action": action,
        }

    def render(self):
        return None
