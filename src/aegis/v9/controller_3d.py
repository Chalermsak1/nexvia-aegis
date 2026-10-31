"""
NEXVIA AEGIS — Phase 2: Native 3D-Aware Autonomous Safety Controller (Aegis3DAwareController).

Addresses the 3D Reality Gap identified in V9-M5 development audits:
1. Native 3D Vector & Altitude Tracking:
   Maintains full (x, y, z) state vectors rather than 2D projection, preventing
   unobserved vertical misalignment false arrivals.
2. Disjoint 3D Sensor Bias Estimation:
   Calibrates 3D bias vectors b_a, b_b in R^3 using anchor corroboration and cross-modal range checks.
3. 3D Ville Anytime Martingale Monitor:
   Tracks 3D vector discrepancies and altitude drift channels under non-exchangeable drift.
4. Calibrated 3D Arrival Verification (Replaces flawed raw-measurement heuristics):
   Corroborates arrival against the CALIBRATED 3D state estimate rather than raw corrupted sensors,
   intended to reduce false arrivals; performance requires empirical evaluation.
5. Fail-Closed Actuator & Degradation Safeguards:
   Enforces fail-closed abstention under unresolvable common-mode failures or severe dropouts.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any
import numpy as np

from aegis.next.velocity_controller import KinematicVelocityController, VelocityProfileConfig
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.ville_monitor import MultiChannelVilleMonitor, VilleChannelSpec, VilleStepResult


@dataclass
class Sensor3DCalibration:
    """State of 3D bias estimate for a sensor."""
    bias_est: np.ndarray  # shape (3,)
    sample_count: int = 0
    is_calibrated: bool = False
    is_valid: bool = True

    def update(self, observed: np.ndarray, reference: np.ndarray) -> None:
        """Recursive Welford / exponential moving average update of 3D bias."""
        error = observed - reference
        alpha = 1.0 / (self.sample_count + 1) if self.sample_count < 20 else 0.05
        self.bias_est = (1.0 - alpha) * self.bias_est + alpha * error
        self.sample_count += 1
        if self.sample_count >= 10:
            self.is_calibrated = True


class Aegis3DAwareController:
    """
    Native 3D Autonomous Safety & Runtime-Assurance Controller.
    Full 3D observation signature:
        update(reading_a, reading_b, range_reading, anchor_reading=None, step=0)
            -> (force_action_3d, decision_type, calibrated_vector_3d, query_anchor_next)
    """

    def __init__(
        self,
        *,
        success_radius: float = 0.25,
        cbf_force_limit: float = 2.0,
        alpha_risk: float = 0.05,
        tau_diff_3d: float = 3.0,
        tau_range_3d: float = 0.35,
        arrival_margin_m: float = 0.03,
    ) -> None:
        if not math.isfinite(arrival_margin_m) or arrival_margin_m < 0:
            raise ValueError("arrival_margin_m must be finite and nonnegative")
        self.success_radius = float(success_radius)
        self.cbf_force_limit = float(cbf_force_limit)
        self.alpha_risk = float(alpha_risk)
        self.tau_diff_3d = float(tau_diff_3d)
        self.tau_range_3d = float(tau_range_3d)
        self.arrival_margin_m = float(arrival_margin_m)

        self.cal_a = Sensor3DCalibration(bias_est=np.zeros(3, dtype=np.float64))
        self.cal_b = Sensor3DCalibration(bias_est=np.zeros(3, dtype=np.float64))

        self.ville_monitor: MultiChannelVilleMonitor | None = None
        self.mode: str = "NOMINAL"  # "NOMINAL", "ACTIVE_PROBING", "CALIBRATED_APPROACH", "ABSTAIN", "STOP"
        self.terminal_reason: str = "ACTIVE"
        self.step_count: int = 0

        self.consecutive_disagreements: int = 0
        self.consecutive_range_dropouts: int = 0
        self.last_nav_vector_3d: np.ndarray = np.zeros(3, dtype=np.float64)
        self.prev_action_3d: np.ndarray = np.zeros(3, dtype=np.float64)

        # Arrival verification buffer (multi-sample corroboration)
        self.arrival_check_steps: int = 0
        self.arrival_range_samples: list[float] = []

    def reset(self) -> None:
        """Resets all internal episode state."""
        self.cal_a = Sensor3DCalibration(bias_est=np.zeros(3, dtype=np.float64))
        self.cal_b = Sensor3DCalibration(bias_est=np.zeros(3, dtype=np.float64))
        self.ville_monitor = None
        self.mode = "NOMINAL"
        self.terminal_reason = "ACTIVE"
        self.step_count = 0
        self.consecutive_disagreements = 0
        self.consecutive_range_dropouts = 0
        self.last_nav_vector_3d = np.zeros(3, dtype=np.float64)
        self.prev_action_3d = np.zeros(3, dtype=np.float64)
        self.arrival_check_steps = 0
        self.arrival_range_samples = []

    def _ensure_monitors(self, sig_a: float, sig_b: float, sig_r: float) -> None:
        if self.ville_monitor is not None:
            return
        # Under 3D isotropic Gaussian noise N(0, sigma^2 I_3), norm has mean 2 * sqrt(2/pi) * sigma
        mean_factor_3d = 2.0 * math.sqrt(2.0 / math.pi)
        mean_factor_1d = math.sqrt(2.0 / math.pi)

        mu0_diff = mean_factor_3d * math.sqrt(sig_a**2 + sig_b**2)
        mu0_vr_a = mean_factor_3d * sig_a + mean_factor_1d * sig_r
        mu0_vr_b = mean_factor_3d * sig_b + mean_factor_1d * sig_r

        specs = [
            VilleChannelSpec(
                name="diff_ab_3d",
                mu0=mu0_diff,
                vmax=0.40,
                x_max=3.50,
            ),
            VilleChannelSpec(
                name="range_vr_a_3d",
                mu0=mu0_vr_a,
                vmax=0.40,
                x_max=3.50,
            ),
            VilleChannelSpec(
                name="range_vr_b_3d",
                mu0=mu0_vr_b,
                vmax=0.40,
                x_max=3.50,
            ),
        ]
        self.ville_monitor = MultiChannelVilleMonitor(channels=specs, alpha=self.alpha_risk)

    def update(
        self,
        reading_a: SensorReading | np.ndarray,
        reading_b: SensorReading | np.ndarray,
        range_reading: RangeReading | float | None,
        anchor_reading: AnchorReading | np.ndarray | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        """
        Executes one 3D control update cycle.
        Returns: (force_action_3d, decision_type, calibrated_vector_3d, query_anchor_next)
        """
        self.step_count = step

        # Extract 3D numpy arrays
        vec_a: np.ndarray | None = None
        sig_a = 0.05
        if isinstance(reading_a, SensorReading):
            if reading_a.valid and not reading_a.dropped:
                vec_a = np.asarray(reading_a.estimate, dtype=np.float64)
                sig_a = float(reading_a.sigma)
        elif reading_a is not None:
            vec_a = np.asarray(reading_a, dtype=np.float64)

        vec_b: np.ndarray | None = None
        sig_b = 0.05
        if isinstance(reading_b, SensorReading):
            if reading_b.valid and not reading_b.dropped:
                vec_b = np.asarray(reading_b.estimate, dtype=np.float64)
                sig_b = float(reading_b.sigma)
        elif reading_b is not None:
            vec_b = np.asarray(reading_b, dtype=np.float64)

        for vec, sigma in ((vec_a, sig_a), (vec_b, sig_b)):
            if vec is not None and (
                vec.shape != (3,) or not np.all(np.isfinite(vec))
                or not math.isfinite(sigma) or sigma <= 0.0
            ):
                self.arrival_check_steps = 0
                self.arrival_range_samples = []
                self.terminal_reason = "INVALID_3D_VECTOR_OBSERVATION"
                return np.zeros(3), "ABSTAIN", np.zeros(3), False

        r_dist: float | None = None
        r_valid = False
        sig_r = 0.05
        if isinstance(range_reading, RangeReading):
            if range_reading.valid and not range_reading.dropped:
                candidate_range = float(range_reading.distance)
                candidate_sigma = float(range_reading.sigma)
                if math.isfinite(candidate_range) and candidate_range >= 0.0 and math.isfinite(candidate_sigma) and candidate_sigma > 0.0:
                    r_dist = candidate_range
                    r_valid = True
                    sig_r = candidate_sigma
        elif range_reading is not None and math.isfinite(float(range_reading)) and float(range_reading) >= 0.0:
            r_dist = float(range_reading)
            r_valid = True

        self._ensure_monitors(sig_a, sig_b, sig_r)

        # Handle range dropouts
        if not r_valid:
            self.consecutive_range_dropouts += 1
            self.arrival_check_steps = 0
            self.arrival_range_samples = []
            if self.consecutive_range_dropouts > 8 and self.mode == "ACTIVE_PROBING":
                self.terminal_reason = "PERSISTENT_RANGE_DROPOUT_UNDER_STRESS"
                return np.zeros(3), "ABSTAIN", self.last_nav_vector_3d, False
        else:
            self.consecutive_range_dropouts = 0

        # Anchor calibration update if available and valid
        query_anchor = False
        if anchor_reading is not None:
            is_valid = (anchor_reading.valid and anchor_reading.queried
                        and math.isfinite(anchor_reading.sigma) and anchor_reading.sigma > 0.0
                        if isinstance(anchor_reading, AnchorReading) else True)
            if is_valid:
                anc_val = (
                    np.asarray(anchor_reading.estimate, dtype=np.float64)
                    if isinstance(anchor_reading, AnchorReading)
                    else np.asarray(anchor_reading, dtype=np.float64)
                )
                if anc_val.shape == (3,) and np.all(np.isfinite(anc_val)):
                    if vec_a is not None:
                        self.cal_a.update(vec_a, anc_val)
                    if vec_b is not None:
                        self.cal_b.update(vec_b, anc_val)

        # Complete sensor failure check
        if vec_a is None and vec_b is None:
            self.terminal_reason = "TOTAL_3D_VECTOR_DROPOUT"
            return np.zeros(3), "ABSTAIN", self.last_nav_vector_3d, False

        # 3D Monitoring
        e_ab = float(np.linalg.norm(vec_a - vec_b)) if (vec_a is not None and vec_b is not None) else 0.0
        v_ab = vec_a is not None and vec_b is not None

        e_vr_a = abs(float(np.linalg.norm(vec_a)) - r_dist) if (vec_a is not None and r_dist is not None) else 0.0
        v_vr_a = vec_a is not None and r_dist is not None

        e_vr_b = abs(float(np.linalg.norm(vec_b)) - r_dist) if (vec_b is not None and r_dist is not None) else 0.0
        v_vr_b = vec_b is not None and r_dist is not None

        obs_map = {
            "diff_ab_3d": (e_ab, v_ab),
            "range_vr_a_3d": (e_vr_a, v_vr_a),
            "range_vr_b_3d": (e_vr_b, v_vr_b),
        }
        assert self.ville_monitor is not None
        ville_res = self.ville_monitor.update(obs_map)

        # Disagreement detection
        if e_ab > self.tau_diff_3d * math.sqrt(sig_a**2 + sig_b**2):
            self.consecutive_disagreements += 1
        else:
            self.consecutive_disagreements = max(0, self.consecutive_disagreements - 1)

        # Mode Transition Logic
        if self.mode == "NOMINAL":
            if ville_res.is_alarm or self.consecutive_disagreements >= 2:
                self.mode = "ACTIVE_PROBING"
                query_anchor = True
                brake = np.zeros(3, dtype=np.float64)
                return brake, "PROBE", self.last_nav_vector_3d, query_anchor

        elif self.mode == "ACTIVE_PROBING":
            # If anchor was queried and calibrated, transition to CALIBRATED_APPROACH
            if self.cal_a.is_calibrated or self.cal_b.is_calibrated:
                self.mode = "CALIBRATED_APPROACH"
            else:
                # Continue requesting anchor or probing
                query_anchor = True
                if step > 60 and not (self.cal_a.is_calibrated or self.cal_b.is_calibrated):
                    self.terminal_reason = "CALIBRATION_TIMEOUT_UNDER_FAULT"
                    return np.zeros(3), "ABSTAIN", self.last_nav_vector_3d, False

        # Compute Calibrated 3D Navigation Vector
        if self.mode in ("CALIBRATED_APPROACH", "ACTIVE_PROBING") and (self.cal_a.is_calibrated or self.cal_b.is_calibrated):
            # Use calibrated estimates!
            candidates: list[np.ndarray] = []
            if vec_a is not None and self.cal_a.is_calibrated:
                candidates.append(vec_a - self.cal_a.bias_est)
            if vec_b is not None and self.cal_b.is_calibrated:
                candidates.append(vec_b - self.cal_b.bias_est)
            if candidates:
                nav_3d = np.mean(candidates, axis=0)
            else:
                nav_3d = (vec_a - self.cal_a.bias_est) if vec_a is not None else (vec_b - self.cal_b.bias_est)  # type: ignore
        else:
            # Nominal navigation: fusion of A and B
            if vec_a is not None and vec_b is not None:
                nav_3d = 0.5 * (vec_a + vec_b)
            elif vec_a is not None:
                nav_3d = vec_a.copy()
            else:
                nav_3d = vec_b.copy()  # type: ignore

        self.last_nav_vector_3d = nav_3d
        est_dist_3d = float(np.linalg.norm(nav_3d))
        z_offset = abs(float(nav_3d[2]))

        # CALIBRATED 3D ARRIVAL VERIFICATION
        # Both full 3D distance, vertical axis, AND independent range must corroborate arrival zone
        max_allowable_range = self.success_radius + 1.645 * sig_r
        if est_dist_3d <= self.success_radius and z_offset <= self.success_radius:
            # Cross-modal range corroboration
            if r_valid and r_dist is not None:
                range_discrepancy = abs(est_dist_3d - r_dist)
                range_in_target_zone = (r_dist <= max_allowable_range)
                if range_discrepancy <= self.tau_range_3d and range_in_target_zone:
                    self.arrival_range_samples.append(r_dist)
                    self.arrival_check_steps += 1
                    # Require 3 consecutive steps of verified corroboration
                    if self.arrival_check_steps >= 3:
                        mean_r = float(np.mean(self.arrival_range_samples))
                        r_ucb = mean_r + 1.645 * sig_r / math.sqrt(len(self.arrival_range_samples))
                        if r_ucb <= self.success_radius + self.arrival_margin_m:
                            self.mode = "STOP"
                            self.terminal_reason = "3D_CALIBRATED_VERIFIED_ARRIVAL"
                            return np.zeros(3), "STOP", nav_3d, False
                        else:
                            # Distance borderline, brake and verify further
                            return np.zeros(3), "VERIFY", nav_3d, False
                    else:
                        # Braking verify step
                        return np.zeros(3), "VERIFY", nav_3d, False
                else:
                    # Contradiction between calibrated vector and range sensor!
                    self.arrival_check_steps = 0
                    self.arrival_range_samples = []
                    # Trigger active probe or fail-closed
                    if self.consecutive_disagreements > 5:
                        self.terminal_reason = "UNRESOLVED_3D_CROSS_MODAL_CONFLICT"
                        return np.zeros(3), "ABSTAIN", nav_3d, False
            else:
                # No fresh range reading at arrival boundary -> cannot certify, clear corroboration
                self.arrival_check_steps = 0
                self.arrival_range_samples = []
                return np.zeros(3), "VERIFY", nav_3d, False
        else:
            self.arrival_check_steps = 0
            self.arrival_range_samples = []

        # Proportional-Derivative 3D navigation guidance towards target
        kp = 1.2
        kd = 0.4
        desired_accel = kp * nav_3d
        action_3d = np.clip(desired_accel, -self.cbf_force_limit, self.cbf_force_limit)
        self.prev_action_3d = action_3d

        decision = "PROBE" if self.mode == "ACTIVE_PROBING" else "NAVIGATE"
        return action_3d, decision, nav_3d, query_anchor
