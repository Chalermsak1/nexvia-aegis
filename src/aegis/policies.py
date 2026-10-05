from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.env.inspection import (
    ABSTAIN,
    INSPECT,
    MOVE,
    STOP,
    VERIFY,
)


@dataclass
class AgentContext:
    inspection_count: int
    max_inspections: int
    verification_count: int
    max_verifications: int
    step_count: int


class BasePolicy:
    name = "base"

    def reset(self, seed: int | None = None) -> None:
        pass

    def act(self, observation: np.ndarray, context: AgentContext) -> int:
        raise NotImplementedError


class AlwaysActPolicy(BasePolicy):
    name = "always_act"

    def act(self, observation: np.ndarray, context: AgentContext) -> int:
        robot = observation[0:2]
        belief = observation[2:4]
        distance = float(np.linalg.norm(robot - belief))
        return STOP if distance <= 0.06 else MOVE


class InspectOncePolicy(BasePolicy):
    name = "inspect_once"

    def act(self, observation: np.ndarray, context: AgentContext) -> int:
        if context.inspection_count == 0:
            return INSPECT
        robot = observation[0:2]
        belief = observation[2:4]
        distance = float(np.linalg.norm(robot - belief))
        return STOP if distance <= 0.06 else MOVE


class AegisPolicy(BasePolicy):
    """
    Nexvia Aegis v1.0.

    Belief estimation
        -> uncertainty estimation
        -> active sensing
        -> independent verification
        -> sensor arbitration
        -> risk-aware STOP
        -> abstention when evidence remains unresolved

    The policy never accesses ground truth.
    """

    name = "aegis"

    def __init__(
        self,
        move_step: float = 0.05,
        success_radius: float = 0.06,
        move_cost: float = 0.01,
        inspect_cost: float = 0.03,
        verify_cost: float = 0.04,
        abstain_penalty: float = 0.20,
        inspection_noise: float = 0.02,
        verification_noise: float = 0.035,
        information_weight: float = 0.12,
        progress_weight: float = 0.08,
        stop_probability_threshold: float = 0.90,
        max_stop_sigma: float = 0.045,
        mismatch_threshold: float = 0.35,
        low_primary_trust: float = 0.55,
        num_samples: int = 1024,
    ) -> None:
        if not 0.0 < stop_probability_threshold <= 1.0:
            raise ValueError(
                "stop_probability_threshold must be in (0, 1]"
            )
        if move_step <= 0:
            raise ValueError("move_step must be > 0")
        if success_radius <= 0:
            raise ValueError("success_radius must be > 0")
        if inspection_noise <= 0:
            raise ValueError("inspection_noise must be > 0")
        if verification_noise <= 0:
            raise ValueError("verification_noise must be > 0")
        if num_samples < 64:
            raise ValueError("num_samples must be >= 64")

        self.move_step = move_step
        self.success_radius = success_radius
        self.move_cost = move_cost
        self.inspect_cost = inspect_cost
        self.verify_cost = verify_cost
        self.abstain_penalty = abstain_penalty
        self.inspection_noise = inspection_noise
        self.verification_noise = verification_noise
        self.information_weight = information_weight
        self.progress_weight = progress_weight
        self.stop_probability_threshold = stop_probability_threshold
        self.max_stop_sigma = max_stop_sigma
        self.mismatch_threshold = mismatch_threshold
        self.low_primary_trust = low_primary_trust
        self.num_samples = num_samples

        self.rng = np.random.default_rng(0)
        self.standard_samples = np.zeros(
            (num_samples, 2),
            dtype=np.float64,
        )
        self.last_utilities: dict[str, float] = {}
        self.last_diagnostics: dict[str, float] = {}

    def reset(self, seed: int | None = None) -> None:
        self.rng = np.random.default_rng(seed)
        self.standard_samples = self.rng.normal(
            0.0,
            1.0,
            size=(self.num_samples, 2),
        )
        self.last_utilities = {}
        self.last_diagnostics = {}

    def act(self, observation: np.ndarray, context: AgentContext) -> int:
        robot = observation[0:2]
        belief = observation[2:4]
        sigma = max(float(observation[4]), 1e-6)
        primary_trust = float(observation[5])
        verifier_trust = float(observation[6])
        verifier_available = bool(observation[7] >= 0.5)
        cross_disagreement = float(observation[8])
        residual = float(observation[9]) * 8.0
        verification_score = float(observation[10])

        distance = float(np.linalg.norm(robot - belief))
        probability = self._success_probability(robot, belief, sigma)

        trust_factor = 0.90 + 0.10 * (
            (primary_trust + verifier_trust) / 2.0
        )
        effective_probability = probability * trust_factor

        recent_anomaly = residual >= 3.0
        unresolved_mismatch = (
            cross_disagreement > self.mismatch_threshold
        )
        primary_untrusted = primary_trust < self.low_primary_trust

        verification_resolved = (
            verifier_available
            and not unresolved_mismatch
            and verifier_trust >= 0.65
        )

        safe_stop = (
            verifier_available
            and verification_resolved
            and not recent_anomaly
            and effective_probability >= self.stop_probability_threshold
            and sigma <= self.max_stop_sigma
        )

        stop_utility = (
            effective_probability - (1.0 - effective_probability)
            if safe_stop
            else -np.inf
        )

        # MOVE utility
        move_utility = -np.inf
        if distance > 1e-8:
            direction = (belief - robot) / distance
            next_robot = np.clip(
                robot + direction * self.move_step,
                0.0,
                1.0,
            )
            next_probability = self._success_probability(
                next_robot,
                belief,
                sigma,
            )
            progress_fraction = min(
                max(
                    distance
                    - float(np.linalg.norm(next_robot - belief)),
                    0.0,
                )
                / self.move_step,
                1.0,
            )
            move_utility = (
                next_probability * trust_factor
                - effective_probability
                + self.progress_weight * progress_fraction
                - self.move_cost
            )

        # INSPECT utility: use only when the primary sensor is still trusted.
        inspect_utility = -np.inf
        can_inspect = (
            context.inspection_count < context.max_inspections
        )
        if can_inspect and primary_trust >= self.low_primary_trust:
            posterior_sigma = self._posterior_sigma(
                sigma,
                self.inspection_noise,
            )
            post_probability = self._success_probability(
                robot,
                belief,
                posterior_sigma,
            )
            information_gain = max(
                (sigma - posterior_sigma) / sigma,
                0.0,
            )
            inspect_utility = (
                post_probability * trust_factor
                - effective_probability
                + self.information_weight * information_gain
                - self.inspect_cost
            )

        # VERIFY utility: independent evidence gets priority when risk is high.
        verify_utility = -np.inf
        can_verify = (
            context.verification_count < context.max_verifications
        )
        if can_verify:
            urgency = 0.0
            if not verifier_available:
                urgency += 0.30
            if recent_anomaly:
                urgency += 0.40
            if unresolved_mismatch or primary_untrusted:
                urgency += 0.50
            if distance <= 0.20:
                urgency += 0.20
            if sigma >= 0.05:
                urgency += 0.15

            posterior_sigma = self._posterior_sigma(
                sigma,
                self.verification_noise,
            )
            post_probability = self._success_probability(
                robot,
                belief,
                posterior_sigma,
            )
            information_gain = max(
                (sigma - posterior_sigma) / sigma,
                0.0,
            )
            verify_utility = (
                post_probability * trust_factor
                - effective_probability
                + self.information_weight * information_gain
                + urgency
                - self.verify_cost
            )

        abstain_utility = -self.abstain_penalty

        self.last_utilities = {
            "MOVE": float(move_utility),
            "INSPECT": float(inspect_utility),
            "STOP": float(stop_utility),
            "ABSTAIN": float(abstain_utility),
            "VERIFY": float(verify_utility),
        }

        self.last_diagnostics = {
            "distance": distance,
            "probability": probability,
            "effective_probability": effective_probability,
            "sigma": sigma,
            "primary_trust": primary_trust,
            "verifier_trust": verifier_trust,
            "cross_disagreement": cross_disagreement,
            "residual": residual,
            "verification_score": verification_score,
            "safe_stop": float(safe_stop),
        }

        # Recent anomaly -> independent verification first.
        if recent_anomaly:
            if can_verify:
                return VERIFY
            return ABSTAIN

        # Persistent cross-sensor disagreement -> arbitrate again.
        if unresolved_mismatch or primary_untrusted:
            if can_verify:
                return VERIFY
            if distance <= 0.20:
                return ABSTAIN

        # Require independent verification before high-risk STOP.
        if not verifier_available and can_verify:
            return VERIFY

        # Safe STOP.
        if safe_stop:
            return STOP

        # Near target without resolved verification.
        if (
            distance <= 0.18
            and can_verify
            and not verification_resolved
        ):
            return VERIFY

        # Active primary sensing when it has marginal value.
        if (
            can_inspect
            and inspect_utility > move_utility + 0.04
        ):
            return INSPECT

        # Continue acting when movement remains worthwhile.
        if move_utility > abstain_utility:
            return MOVE

        # Last attempt at independent evidence.
        if can_verify:
            return VERIFY
        if can_inspect:
            return INSPECT
        return ABSTAIN

    def _success_probability(
        self,
        center: np.ndarray,
        belief: np.ndarray,
        sigma: float,
    ) -> float:
        samples = belief + sigma * self.standard_samples
        distances = np.linalg.norm(
            samples - center,
            axis=1,
        )
        return float(
            np.mean(
                distances <= self.success_radius
            )
        )

    @staticmethod
    def _posterior_sigma(
        prior_sigma: float,
        measurement_sigma: float,
    ) -> float:
        prior_variance = max(prior_sigma**2, 1e-12)
        measurement_variance = max(measurement_sigma**2, 1e-12)
        posterior_variance = 1.0 / (
            1.0 / prior_variance
            + 1.0 / measurement_variance
        )
        return float(
            np.sqrt(
                max(
                    posterior_variance,
                    1e-12,
                )
            )
        )
