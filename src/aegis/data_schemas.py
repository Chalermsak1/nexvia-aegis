"""
NEXVIA-AEGIS: Robot Telemetry, Perception & Multi-Agent Data Schemas.

Standard data classes for:
1. Robot Kinematics & Physical Telemetry
2. Obstacle & Corridor Geometry
3. Multi-Agent Swarm Packets (Byzantine Resilience)
4. AI / Safe RL Observation Vector (20 Dimensions)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np


@dataclass
class DroneKinematicState:
    """Single-agent full physical state."""
    timestamp_s: float
    position: np.ndarray             # [x, y, z] in world frame (m)
    velocity: np.ndarray             # [vx, vy, vz] in world frame (m/s)
    rotation_matrix: np.ndarray      # 3x3 SO(3) attitude rotation matrix
    angular_velocity: np.ndarray     # [wx, wy, wz] body frame angular rates (rad/s)
    tilt_angle_rad: float            # Body tilt angle relative to gravity vector
    sigma_pos: float = 0.05          # Position estimation uncertainty std (m)
    sigma_vel: float = 0.08          # Velocity estimation uncertainty std (m/s)
    battery_soc: float = 1.0         # Battery State of Charge [0.0, 1.0]


@dataclass
class ObstacleTarget:
    """3D Obstacle representation."""
    obstacle_id: int
    center: np.ndarray               # [cx, cy, cz] world position (m)
    radius: float                    # Collision boundary radius (m)
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))


@dataclass
class CorridorPlane:
    """Convex Safe Flight Corridor hyperplane boundary."""
    normal: np.ndarray               # Unit normal pointing outward [nx, ny, nz]
    distance: float                  # Halfspace constant: normal . p <= distance


@dataclass
class SwarmAgentPacket:
    """Inter-robot communication payload for Byzantine-resilient consensus."""
    agent_id: int
    step: int
    pos_estimate: np.ndarray         # Shape (3,) position estimate
    sigma: float                     # Reported sensor standard deviation
    martingale_wealth: float         # Ville e-process test martingale wealth
    valid: bool = True


@dataclass
class SafeRLObservation:
    """Normalized 20-dimensional feature vector for Actor-Critic policy."""
    position_error: np.ndarray       # Shape (3,) [p_target - p]
    velocity: np.ndarray             # Shape (3,)
    z_body_axis: np.ndarray          # Shape (3,) R[:, 2] (indicates tilt direction)
    angular_velocity: np.ndarray     # Shape (3,)
    obstacle_relative_pos: np.ndarray # Shape (3,) vector to closest obstacle
    obstacle_relative_vel: np.ndarray # Shape (3,) relative velocity
    battery_soc: float               # Float in [0, 1]
    tilt_angle_norm: float           # Normalized tilt angle [0, 1]

    def to_vector(self) -> np.ndarray:
        """Flattens into a single 20-dimensional NumPy array."""
        return np.concatenate([
            self.position_error,
            self.velocity,
            self.z_body_axis,
            self.angular_velocity,
            self.obstacle_relative_pos,
            self.obstacle_relative_vel,
            [self.battery_soc],
            [self.tilt_angle_norm],
        ], dtype=np.float32)

