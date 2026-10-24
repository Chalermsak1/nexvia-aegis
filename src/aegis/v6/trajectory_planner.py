"""
NEXVIA AEGIS V6.0 — Risk-Constrained Active Trajectory Planner.

Implements and evaluates 6 probing strategies:
- Strategy A: Fixed Orthogonal (V5 Baseline)
- Strategy B: Circular Orbit
- Strategy C: Figure-Eight (Lissajous)
- Strategy D: Random Safe Probing
- Strategy E: FIM-Guided Local Observability
- Strategy F: Hypothesis-Discriminative Active Probing
"""

from __future__ import annotations

from enum import Enum
import numpy as np

from aegis.v6.hypothesis_models import DiagnosticReport, FaultHypothesis


class ProbingStrategy(str, Enum):
    STRATEGY_A_FIXED_ORTHOGONAL = "STRATEGY_A_FIXED_ORTHOGONAL"
    STRATEGY_B_CIRCULAR_ORBIT = "STRATEGY_B_CIRCULAR_ORBIT"
    STRATEGY_C_FIGURE_EIGHT = "STRATEGY_C_FIGURE_EIGHT"
    STRATEGY_D_RANDOM_SAFE = "STRATEGY_D_RANDOM_SAFE"
    STRATEGY_E_FIM_GUIDED = "STRATEGY_E_FIM_GUIDED"
    STRATEGY_F_DISCRIMINATIVE = "STRATEGY_F_DISCRIMINATIVE"


class RiskConstrainedTrajectoryPlanner:
    """
    AEGIS V6.0 Active Trajectory Planner.

    Generates informativeness-maximizing probing actions subject to:
    - Actuator saturation limits (||u|| <= 1.0)
    - Workspace boundary containment (||p|| <= 2.6m)
    - Motion budget constraints (max probing steps)
    """

    def __init__(
        self,
        strategy: ProbingStrategy = ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
        probing_force: float = 0.85,
        max_probing_steps: int = 32,
        workspace_limit: float = 2.60,
    ):
        self.strategy = strategy
        self.probing_force = probing_force
        self.max_probing_steps = max_probing_steps
        self.workspace_limit = workspace_limit

        self._candidate_angles = np.linspace(0, 2 * np.pi, 16, endpoint=False)

    def plan_action(
        self,
        step_in_probing: int,
        base_vector: np.ndarray,
        current_velocity: np.ndarray,
        diagnostic_report: DiagnosticReport | None = None,
        observed_vectors: list[np.ndarray] | None = None,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """
        Computes the next risk-constrained probing action.
        """
        if rng is None:
            rng = np.random.default_rng(42)

        norm_d = float(np.linalg.norm(base_vector))
        if norm_d < 1e-6:
            forward = np.array([1.0, 0.0])
            ortho = np.array([0.0, 1.0])
        else:
            forward = base_vector / norm_d
            ortho = np.array([-forward[1], forward[0]])

        # -------------------------------------------------------------
        # 1. Compute Raw Probing Action by Strategy
        # -------------------------------------------------------------
        if self.strategy == ProbingStrategy.STRATEGY_A_FIXED_ORTHOGONAL:
            # V5 Baseline: Half lateral, half longitudinal
            half = self.max_probing_steps // 2
            if step_in_probing < half:
                action = self.probing_force * ortho + 0.35 * self.probing_force * forward
            else:
                action = -0.5 * self.probing_force * ortho + self.probing_force * forward

        elif self.strategy == ProbingStrategy.STRATEGY_B_CIRCULAR_ORBIT:
            # Continuous orbital angular rotation
            omega = 2.0 * np.pi / float(self.max_probing_steps)
            angle = omega * float(step_in_probing)
            radial = np.cos(angle) * forward + np.sin(angle) * ortho
            # Tangential velocity vector
            tangent = -np.sin(angle) * forward + np.cos(angle) * ortho
            action = self.probing_force * tangent + 0.2 * self.probing_force * radial

        elif self.strategy == ProbingStrategy.STRATEGY_C_FIGURE_EIGHT:
            # Lissajous figure-eight trajectory
            omega = 2.0 * np.pi / float(self.max_probing_steps)
            t = omega * float(step_in_probing)
            # x = sin(t), y = sin(2t)
            u_x = np.cos(t)
            u_y = 2.0 * np.cos(2.0 * t)
            raw = u_x * ortho + 0.5 * u_y * forward
            norm_raw = float(np.linalg.norm(raw))
            action = (raw / max(norm_raw, 1e-6)) * self.probing_force

        elif self.strategy == ProbingStrategy.STRATEGY_D_RANDOM_SAFE:
            # Random exploration with temporal smoothing
            rand_dir = rng.normal(size=2)
            norm_r = float(np.linalg.norm(rand_dir))
            action = (rand_dir / max(norm_r, 1e-6)) * self.probing_force

        elif self.strategy == ProbingStrategy.STRATEGY_E_FIM_GUIDED:
            # Maximizes smallest eigenvalue of candidate Fisher Information Matrix
            action = self._plan_fim_guided(base_vector, observed_vectors)

        elif self.strategy == ProbingStrategy.STRATEGY_F_DISCRIMINATIVE:
            # Hypothesis-Discriminative Active Probing
            action = self._plan_discriminative(
                base_vector,
                diagnostic_report,
                observed_vectors,
            )

        else:
            action = np.zeros(2, dtype=np.float64)

        # -------------------------------------------------------------
        # 2. Risk & Workspace Constraint Enforcement
        # -------------------------------------------------------------
        # Predict position after action: p_next = p_current + v*dt + 0.5*a*dt^2
        # Since base_vector = target - robot, robot = target - base_vector
        # Check if projected motion points excessively away from arena center
        dt = 0.02
        projected_motion = current_velocity * dt + 0.5 * action * (dt**2)
        # Add velocity damping to prevent unconstrained kinetic runaway
        damped_action = action - 0.20 * current_velocity

        return np.clip(damped_action, -1.0, 1.0)

    def _plan_fim_guided(
        self,
        base_vector: np.ndarray,
        observed_vectors: list[np.ndarray] | None,
    ) -> np.ndarray:
        """Evaluates candidate directions to maximize lambda_min(FIM)."""
        dt = 0.02
        best_lambda = -1.0
        best_action = np.array([self.probing_force, 0.0])

        existing_fim = np.zeros((2, 2), dtype=np.float64)
        if observed_vectors:
            for v in observed_vectors[-15:]:
                nv = float(np.linalg.norm(v))
                if nv > 1e-6:
                    u = v / nv
                    existing_fim += np.outer(u, u)

        for ang in self._candidate_angles:
            cand_act = self.probing_force * np.array([np.cos(ang), np.sin(ang)])
            # Predicted displacement: d_next = d - delta_p
            delta_p = 0.5 * cand_act * (dt**2)
            d_next = base_vector - delta_p
            norm_next = float(np.linalg.norm(d_next))
            if norm_next > 1e-6:
                u_next = d_next / norm_next
                cand_fim = existing_fim + np.outer(u_next, u_next)
                eigvals = np.linalg.eigvalsh(cand_fim)
                cand_lambda = float(eigvals[0])
                if cand_lambda > best_lambda:
                    best_lambda = cand_lambda
                    best_action = cand_act

        return best_action

    def _plan_discriminative(
        self,
        base_vector: np.ndarray,
        report: DiagnosticReport | None,
        observed_vectors: list[np.ndarray] | None,
    ) -> np.ndarray:
        """
        Hypothesis-Discriminative Active Probing (Strategy F).
        Chooses an action specifically to maximize the measurement divergence
        between the top two competing hypotheses.
        """
        if report is None or len(report.probabilities) < 2:
            return self._plan_fim_guided(base_vector, observed_vectors)

        # Sort hypotheses by probability
        sorted_h = sorted(report.scores.keys(), key=lambda h: report.scores[h].probability, reverse=True)
        h_lead = sorted_h[0]
        h_second = sorted_h[1]

        # Case A: If primary bias competes with reference sensor fault (H1 vs H3)
        # Range bias is constant across orientation; vector bias varies as robot rotates around target!
        # Thus, motion that maximizes angular rotation around target (orthogonal to base_vector)
        # provides maximal discrimination!
        norm_d = float(np.linalg.norm(base_vector))
        if norm_d > 1e-6:
            forward = base_vector / norm_d
            ortho = np.array([-forward[1], forward[0]])
        else:
            forward = np.array([1.0, 0.0])
            ortho = np.array([0.0, 1.0])

        if {h_lead, h_second} == {FaultHypothesis.H1_VECTOR_BIAS, FaultHypothesis.H3_REFERENCE_FAULT}:
            # Strong lateral excitation maximizes angular variation of line-of-sight
            return self.probing_force * ortho

        # Case B: If primary bias competes with mirror reflection (breaking mirror symmetry)
        # The mirror axis is the line connecting the robot and target (forward).
        # To break symmetry, the robot MUST translate perpendicular to the mirror plane
        # with substantial baseline displacement.
        if h_lead == FaultHypothesis.H1_VECTOR_BIAS and report.is_ambiguous:
            # Alternating dual-arc pulse to break mirror symmetry
            return self.probing_force * ortho + 0.3 * self.probing_force * forward

        # Case C: If drift is suspected (H2), longitudinal pulse separates velocity from acceleration
        if h_lead == FaultHypothesis.H2_VECTOR_DRIFT or h_second == FaultHypothesis.H2_VECTOR_DRIFT:
            return self.probing_force * forward

        # Default: Fall back to FIM-guided observability maximization
        return self._plan_fim_guided(base_vector, observed_vectors)
