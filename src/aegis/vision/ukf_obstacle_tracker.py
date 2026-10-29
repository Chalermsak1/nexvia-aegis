"""
NEXVIA AEGIS — Unscented Kalman Filter (UKF) for 3D Dynamic Obstacle Tracking under Occlusion.

Features:
1. 7-State Unscented Kalman Filter per obstacle: [x, y, z, vx, vy, vz, radius].
2. Scaled Unscented Transform (Van der Merwe) for non-linear spherical surface geometry.
3. Occlusion-Aware Variance Propagation:
   Under occlusion (line-of-sight blockage or out-of-FOV), track enters pure prediction mode;
   covariance ellipsoid P_pos expands exponentially reflecting information degradation.
4. Mahalanobis distance gating (chi-squared test) for robust point-cloud cluster association.
5. Principal axis decomposition of the 3D position uncertainty ellipsoid: lambda_max(P_pos).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import linalg


@dataclass
class TrackedObstacle3D:
    """State and uncertainty belief of a single tracked obstacle."""
    track_id: int
    state: np.ndarray             # shape (7,) [px, py, pz, vx, vy, vz, r]
    covariance: np.ndarray        # shape (7, 7) error covariance matrix
    consecutive_occlusions: int = 0
    total_detections: int = 0
    is_confirmed: bool = False
    is_currently_occluded: bool = False

    @property
    def position(self) -> np.ndarray:
        return self.state[0:3]

    @property
    def velocity(self) -> np.ndarray:
        return self.state[3:6]

    @property
    def radius(self) -> float:
        return float(self.state[6])

    @property
    def position_covariance(self) -> np.ndarray:
        return self.covariance[0:3, 0:3]

    @property
    def max_position_std(self) -> float:
        """Square root of maximum eigenvalue of position covariance ellipsoid."""
        eigvals = linalg.eigvalsh(self.position_covariance)
        return float(math.sqrt(max(1e-9, np.max(eigvals))))

    @property
    def uncertainty_volume(self) -> float:
        """Volume of 3-sigma position uncertainty ellipsoid in m^3."""
        det_p = max(1e-18, linalg.det(self.position_covariance))
        # Volume = (4/3) * pi * a * b * c = (4/3) * pi * (3^3) * sqrt(det(P))
        return float((4.0 / 3.0) * math.pi * (3.0**3) * math.sqrt(det_p))


@dataclass(frozen=True)
class UKFTrackerConfig:
    dt: float = 0.02                          # Outer loop sample time (50 Hz)
    alpha: float = 0.05                       # UKF spread parameter (0.0001 < alpha <= 1)
    beta: float = 2.0                         # Optimal for Gaussian distributions
    kappa: float = 0.0                        # Secondary scaling parameter
    pos_process_noise: float = 0.005          # Position process noise variance (m^2)
    vel_process_noise: float = 0.08           # Velocity random walk variance (m^2/s^2)
    radius_process_noise: float = 0.0001      # Radius stability variance
    meas_pos_noise: float = 0.02              # Sensor position noise (m)
    meas_radius_noise: float = 0.03           # Sensor radius noise (m)
    mahalanobis_gate_threshold: float = 13.28 # Chi-square gate for 4-DOF at 99% confidence
    confirmation_hits: int = 3                # Hits required to confirm track
    max_occlusion_steps: int = 80             # Steps before pruning lost track (~1.6s)


class MultiObstacleUKFTracker:
    """
    Decentralized Multi-Target Unscented Kalman Filter Tracker.
    Maintains rigorous spatial uncertainty ellipsoids for active collision avoidance.
    """

    def __init__(self, cfg: UKFTrackerConfig | None = None) -> None:
        self.cfg = cfg or UKFTrackerConfig()
        self.tracks: Dict[int, TrackedObstacle3D] = {}
        self.next_track_id = 0

        # State dimension: 7, Measurement dimension: 4 [px, py, pz, r]
        self.n_x = 7
        self.n_z = 4

        # Compute Van der Merwe UKF weights
        self.lambda_ = self.cfg.alpha**2 * (self.n_x + self.cfg.kappa) - self.n_x
        self.c = self.n_x + self.lambda_

        self.w_m = np.full(2 * self.n_x + 1, 0.5 / self.c, dtype=np.float64)
        self.w_c = np.full(2 * self.n_x + 1, 0.5 / self.c, dtype=np.float64)
        self.w_m[0] = self.lambda_ / self.c
        self.w_c[0] = self.lambda_ / self.c + (1.0 - self.cfg.alpha**2 + self.cfg.beta)

        # Process noise matrix Q (7x7)
        self.Q = np.diag([
            self.cfg.pos_process_noise,
            self.cfg.pos_process_noise,
            self.cfg.pos_process_noise,
            self.cfg.vel_process_noise,
            self.cfg.vel_process_noise,
            self.cfg.vel_process_noise,
            self.cfg.radius_process_noise,
        ]).astype(np.float64)

        # Measurement noise matrix R (4x4)
        self.R = np.diag([
            self.cfg.meas_pos_noise**2,
            self.cfg.meas_pos_noise**2,
            self.cfg.meas_pos_noise**2,
            self.cfg.meas_radius_noise**2,
        ]).astype(np.float64)

    def _generate_sigma_points(self, x: np.ndarray, P: np.ndarray) -> np.ndarray:
        """Generates 2*n_x + 1 scaled sigma points."""
        sigma_points = np.zeros((2 * self.n_x + 1, self.n_x), dtype=np.float64)
        sigma_points[0] = x

        # Ensure P is strictly symmetric positive-definite
        P_sym = 0.5 * (P + P.T) + 1e-8 * np.eye(self.n_x)
        try:
            sqrt_P = linalg.cholesky(self.c * P_sym, lower=True)
        except linalg.LinAlgError:
            # Fallback to eigenvalue clipping if Cholesky encounters numerical precision limits
            vals, vecs = linalg.eigh(P_sym)
            vals = np.maximum(vals, 1e-8)
            sqrt_P = vecs @ np.diag(np.sqrt(self.c * vals))

        for i in range(self.n_x):
            sigma_points[1 + i] = x + sqrt_P[:, i]
            sigma_points[1 + self.n_x + i] = x - sqrt_P[:, i]
        return sigma_points

    def _state_transition(self, x: np.ndarray, dt: float) -> np.ndarray:
        """Constant velocity state transition: p_{t+dt} = p_t + v_t * dt."""
        x_next = np.copy(x)
        x_next[0:3] = x[0:3] + x[3:6] * dt
        return x_next

    @staticmethod
    def _measurement_function(x: np.ndarray) -> np.ndarray:
        """Extracts measurement vector [px, py, pz, r] from state."""
        return np.array([x[0], x[1], x[2], x[6]], dtype=np.float64)

    def predict(self, dt: float | None = None) -> None:
        """
        Executes UKF prediction step for all active tracks.
        Uncertainty expands according to process noise Q.
        """
        dt_val = dt if dt is not None else self.cfg.dt

        for track in self.tracks.values():
            sigmas = self._generate_sigma_points(track.state, track.covariance)
            propagated_sigmas = np.array([self._state_transition(s, dt_val) for s in sigmas], dtype=np.float64)

            # Reconstruct predicted mean
            x_pred = np.sum(self.w_m[:, np.newaxis] * propagated_sigmas, axis=0)

            # Reconstruct predicted covariance
            diff = propagated_sigmas - x_pred
            P_pred = np.zeros((self.n_x, self.n_x), dtype=np.float64)
            for i in range(2 * self.n_x + 1):
                P_pred += self.w_c[i] * np.outer(diff[i], diff[i])
            P_pred += self.Q

            track.state = x_pred
            track.covariance = 0.5 * (P_pred + P_pred.T)
            track.consecutive_occlusions += 1
            track.is_currently_occluded = True

    def update_from_clusters(
        self,
        clusters: List[Tuple[np.ndarray, float]],  # List of (centroid_xyz, estimated_radius)
        dt: float | None = None,
    ) -> None:
        """
        Associates detected 3D point cloud clusters to tracks via Mahalanobis distance gating,
        performing UKF measurement updates on matched tracks and spawning new tracks for unassociated clusters.
        """
        self.predict(dt)

        if not clusters:
            self._prune_stale_tracks()
            return

        unmatched_clusters = list(range(len(clusters)))
        matched_tracks: Set[int] = set()

        for track_id, track in self.tracks.items():
            sigmas = self._generate_sigma_points(track.state, track.covariance)
            meas_sigmas = np.array([self._measurement_function(s) for s in sigmas], dtype=np.float64)

            # Predicted measurement mean
            z_pred = np.sum(self.w_m[:, np.newaxis] * meas_sigmas, axis=0)

            # Innovation covariance S and Cross-covariance P_xz
            diff_z = meas_sigmas - z_pred
            diff_x = sigmas - track.state
            S = np.zeros((self.n_z, self.n_z), dtype=np.float64)
            P_xz = np.zeros((self.n_x, self.n_z), dtype=np.float64)

            for i in range(2 * self.n_x + 1):
                S += self.w_c[i] * np.outer(diff_z[i], diff_z[i])
                P_xz += self.w_c[i] * np.outer(diff_x[i], diff_z[i])
            S += self.R
            S = 0.5 * (S + S.T)

            # Find best matching cluster within Mahalanobis gate
            best_cluster_idx = -1
            best_mahalanobis = float("inf")

            try:
                S_inv = linalg.inv(S)
            except linalg.LinAlgError:
                S_inv = linalg.pinv(S)

            for c_idx in unmatched_clusters:
                centroid, r_est = clusters[c_idx]
                z_meas = np.array([centroid[0], centroid[1], centroid[2], r_est], dtype=np.float64)
                y_innov = z_meas - z_pred
                d_m_sq = float(y_innov.T @ S_inv @ y_innov)

                if d_m_sq <= self.cfg.mahalanobis_gate_threshold and d_m_sq < best_mahalanobis:
                    best_mahalanobis = d_m_sq
                    best_cluster_idx = c_idx

            if best_cluster_idx >= 0:
                # Apply UKF measurement update
                centroid, r_est = clusters[best_cluster_idx]
                z_meas = np.array([centroid[0], centroid[1], centroid[2], r_est], dtype=np.float64)
                y_innov = z_meas - z_pred

                K = P_xz @ S_inv  # Kalman Gain (7x4)
                track.state = track.state + K @ y_innov
                P_up = track.covariance - K @ S @ K.T
                track.covariance = 0.5 * (P_up + P_up.T)

                track.consecutive_occlusions = 0
                track.is_currently_occluded = False
                track.total_detections += 1
                if track.total_detections >= self.cfg.confirmation_hits:
                    track.is_confirmed = True

                matched_tracks.add(track_id)
                unmatched_clusters.remove(best_cluster_idx)

        # Initialize new tracks for unmatched clusters
        for c_idx in unmatched_clusters:
            centroid, r_est = clusters[c_idx]
            new_id = self.next_track_id
            self.next_track_id += 1

            init_state = np.zeros(7, dtype=np.float64)
            init_state[0:3] = centroid
            init_state[6] = r_est

            init_cov = np.diag([
                0.04, 0.04, 0.04,    # pos var: 0.2m std
                0.50, 0.50, 0.50,    # vel var: 0.7m/s std
                0.01,                # radius var: 0.1m std
            ]).astype(np.float64)

            self.tracks[new_id] = TrackedObstacle3D(
                track_id=new_id,
                state=init_state,
                covariance=init_cov,
                consecutive_occlusions=0,
                total_detections=1,
                is_confirmed=(self.cfg.confirmation_hits <= 1),
                is_currently_occluded=False,
            )

        self._prune_stale_tracks()

    def _prune_stale_tracks(self) -> None:
        """Prunes tracks that have been occluded for longer than max_occlusion_steps."""
        to_delete = [
            tid for tid, track in self.tracks.items()
            if track.consecutive_occlusions > self.cfg.max_occlusion_steps
        ]
        for tid in to_delete:
            del self.tracks[tid]

    def get_confirmed_tracks(self) -> List[TrackedObstacle3D]:
        """Returns all validated and confirmed obstacle tracks."""
        return [t for t in self.tracks.values() if t.is_confirmed or t.total_detections >= 2]
