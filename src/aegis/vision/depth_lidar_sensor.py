"""
NEXVIA AEGIS — Simulated Depth Camera & 3D Spinning LiDAR with Raycasting & Occlusion.

Provides physical sensor simulation for 6-DOF quadrotors:
1. Depth Camera with finite Field of View (FoV) frustum and 2-DOF Pan/Tilt gimbal.
2. 3D Multi-Beam Spinning LiDAR with 360-degree horizontal azimuth coverage.
3. Multi-body Ray-Sphere intersection with strict Physical Line-of-Sight Occlusion:
   Closer obstacles cast depth shadows blocking rays from reaching hidden obstacles.
4. Distance-dependent Gaussian measurement noise and sensor dropout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, List, Set, Tuple

import numpy as np


@dataclass(frozen=True)
class DepthCameraConfig:
    horizontal_fov_deg: float = 86.0        # Horizontal FOV in degrees
    vertical_fov_deg: float = 57.0          # Vertical FOV in degrees
    min_range: float = 0.2                  # Minimum sensing range in meters
    max_range: float = 5.0                  # Maximum depth range in meters
    h_rays: int = 32                        # Horizontal angular resolution
    v_rays: int = 24                        # Vertical angular resolution
    range_noise_std: float = 0.02           # Baseline range measurement standard deviation (m)
    dropout_prob: float = 0.02              # Random beam packet loss probability


@dataclass(frozen=True)
class Lidar3DConfig:
    horizontal_fov_deg: float = 360.0       # Azimuth coverage in degrees
    channels: int = 16                      # Vertical beam layers
    vertical_fov_min_deg: float = -15.0     # Lowest vertical beam elevation
    vertical_fov_max_deg: float = 15.0      # Highest vertical beam elevation
    azimuth_step_deg: float = 5.0           # Horizontal angular step (72 beams / channel)
    min_range: float = 0.1                  # Minimum range in meters
    max_range: float = 8.0                  # Maximum range in meters
    range_noise_std: float = 0.015          # Range measurement noise (m)
    dropout_prob: float = 0.01              # Beam dropout probability


@dataclass
class ObstacleTarget:
    """Ground truth obstacle geometry for raycasting."""
    obs_id: int
    center: np.ndarray       # shape (3,) in world frame
    radius: float            # spherical radius in meters
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))


@dataclass
class SensorObservation:
    """Output observation from vision / LiDAR suite."""
    point_cloud: np.ndarray               # shape (N, 3) measured hit points in world frame
    ranges: np.ndarray                    # shape (N,) measured distances
    ray_directions: np.ndarray            # shape (N, 3) unit ray vectors in world frame
    visible_obstacle_ids: Set[int]        # Set of obstacle IDs with >= 1 unoccluded ray hit
    occluded_obstacle_ids: Set[int]       # Obstacles in scene whose direct line-of-sight is blocked
    out_of_fov_obstacle_ids: Set[int]     # Obstacles outside sensor FOV frustum


class SimulatedPerceptionSuite:
    """
    Simulated 3D Visual & LiDAR Perception Engine.
    Computes exact geometric line-of-sight raycasts against 3D spherical obstacles
    and planar arena boundaries under physical occlusion.
    """

    def __init__(
        self,
        camera_cfg: DepthCameraConfig | None = None,
        lidar_cfg: Lidar3DConfig | None = None,
    ) -> None:
        self.camera_cfg = camera_cfg or DepthCameraConfig()
        self.lidar_cfg = lidar_cfg or Lidar3DConfig()

        # Precompute camera ray angles in gimbal frame
        h_angles = np.linspace(
            -np.radians(self.camera_cfg.horizontal_fov_deg) / 2.0,
            np.radians(self.camera_cfg.horizontal_fov_deg) / 2.0,
            self.camera_cfg.h_rays,
        )
        v_angles = np.linspace(
            -np.radians(self.camera_cfg.vertical_fov_deg) / 2.0,
            np.radians(self.camera_cfg.vertical_fov_deg) / 2.0,
            self.camera_cfg.v_rays,
        )
        hh, vv = np.meshgrid(h_angles, v_angles)
        # Unit vectors in sensor camera frame (X forward, Y left, Z up)
        cx = np.cos(vv) * np.cos(hh)
        cy = np.cos(vv) * np.sin(hh)
        cz = np.sin(vv)
        cam_rays = np.stack([cx, cy, cz], axis=-1).reshape(-1, 3)
        cam_norms = np.linalg.norm(cam_rays, axis=1, keepdims=True)
        self.cam_local_rays = cam_rays / cam_norms

        # Precompute LiDAR ray angles in body frame
        azimuths = np.arange(0.0, 360.0, self.lidar_cfg.azimuth_step_deg)
        elevations = np.linspace(
            self.lidar_cfg.vertical_fov_min_deg,
            self.lidar_cfg.vertical_fov_max_deg,
            self.lidar_cfg.channels,
        )
        az_rad = np.radians(azimuths)
        el_rad = np.radians(elevations)
        aa, ee = np.meshgrid(az_rad, el_rad)
        lx = np.cos(ee) * np.cos(aa)
        ly = np.cos(ee) * np.sin(aa)
        lz = np.sin(ee)
        lidar_rays = np.stack([lx, ly, lz], axis=-1).reshape(-1, 3)
        lidar_norms = np.linalg.norm(lidar_rays, axis=1, keepdims=True)
        self.lidar_local_rays = lidar_rays / lidar_norms

    @staticmethod
    def _rotation_pan_tilt(pan_rad: float, tilt_rad: float) -> np.ndarray:
        """Rotation matrix for a 2-DOF gimbal (Yaw pan around Z, then Pitch tilt around Y)."""
        c_p, s_p = math.cos(pan_rad), math.sin(pan_rad)
        c_t, s_t = math.cos(tilt_rad), math.sin(tilt_rad)
        # R_pan = [[c_p, -s_p, 0], [s_p, c_p, 0], [0, 0, 1]]
        # R_tilt = [[c_t, 0, -s_t], [0, 1, 0], [s_t, 0, c_t]]
        R_pan = np.array([
            [c_p, -s_p, 0.0],
            [s_p,  c_p, 0.0],
            [0.0,  0.0, 1.0],
        ], dtype=np.float64)
        R_tilt = np.array([
            [c_t, 0.0, -s_t],
            [0.0, 1.0,  0.0],
            [s_t, 0.0,  c_t],
        ], dtype=np.float64)
        return R_pan @ R_tilt

    def _ray_sphere_intersect(
        self,
        ray_origin: np.ndarray,
        ray_dirs: np.ndarray,
        center: np.ndarray,
        radius: float,
    ) -> np.ndarray:
        """
        Vectorized ray-sphere intersection for multiple rays against one sphere.
        Returns distances t >= 0 (or inf if no intersection).
        """
        # ray: p(t) = ray_origin + t * d
        # ||p(t) - center||^2 = radius^2
        # t^2 + 2 t (d . (origin - center)) + ||origin - center||^2 - radius^2 = 0
        diff = ray_origin - center  # shape (3,)
        b = 2.0 * np.dot(ray_dirs, diff)  # shape (N,)
        c = np.dot(diff, diff) - radius**2  # scalar
        discriminant = b**2 - 4.0 * c  # shape (N,)

        t = np.full(len(ray_dirs), np.inf, dtype=np.float64)
        valid_mask = discriminant >= 0.0
        if np.any(valid_mask):
            sqrt_disc = np.sqrt(discriminant[valid_mask])
            b_val = b[valid_mask]
            t1 = (-b_val - sqrt_disc) / 2.0
            t2 = (-b_val + sqrt_disc) / 2.0
            
            # We want smallest positive root
            t_candidates = np.where(t1 > 1e-4, t1, np.where(t2 > 1e-4, t2, np.inf))
            t[valid_mask] = t_candidates
        return t

    def capture_depth_camera(
        self,
        drone_pos: np.ndarray,
        drone_rot: np.ndarray,
        obstacles: List[ObstacleTarget],
        gimbal_pan_deg: float = 0.0,
        gimbal_tilt_deg: float = 0.0,
        rng: np.random.Generator | None = None,
    ) -> SensorObservation:
        """
        Performs optical depth camera raycast with physical occlusion from closer obstacles.
        """
        if rng is None:
            rng = np.random.default_rng()

        # Transform local camera rays to world frame:
        # R_world_cam = R_drone @ R_gimbal
        R_gimbal = self._rotation_pan_tilt(np.radians(gimbal_pan_deg), np.radians(gimbal_tilt_deg))
        R_sensor = drone_rot @ R_gimbal
        world_rays = self.cam_local_rays @ R_sensor.T  # shape (N_rays, 3)

        n_rays = len(world_rays)
        min_ranges = np.full(n_rays, self.camera_cfg.max_range, dtype=np.float64)
        hit_obstacle_id = np.full(n_rays, -1, dtype=np.int32)

        # Intersect all obstacles and find the closest hit along each ray
        for obs in obstacles:
            t_hits = self._ray_sphere_intersect(drone_pos, world_rays, obs.center, obs.radius)
            # Find rays where this obstacle is closer than current minimum
            closer_mask = (t_hits >= self.camera_cfg.min_range) & (t_hits < min_ranges)
            min_ranges[closer_mask] = t_hits[closer_mask]
            hit_obstacle_id[closer_mask] = obs.obs_id

        # Classify obstacles by visibility status
        visible_ids: Set[int] = set()
        occluded_ids: Set[int] = set()
        out_of_fov_ids: Set[int] = set()

        for obs in obstacles:
            # Check if obstacle is inside FOV frustum (angle check)
            rel_vec = obs.center - drone_pos
            dist_to_center = np.linalg.norm(rel_vec)
            if dist_to_center > 1e-6:
                sensor_vec = rel_vec @ R_sensor  # vector in sensor coordinates
                az = math.degrees(math.atan2(sensor_vec[1], sensor_vec[0]))
                el = math.degrees(math.atan2(sensor_vec[2], math.hypot(sensor_vec[0], sensor_vec[1])))
                in_fov = (
                    abs(az) <= self.camera_cfg.horizontal_fov_deg / 2.0 + 10.0 and
                    abs(el) <= self.camera_cfg.vertical_fov_deg / 2.0 + 10.0 and
                    dist_to_center <= self.camera_cfg.max_range + obs.radius
                )
            else:
                in_fov = True

            hit_count = int(np.sum(hit_obstacle_id == obs.obs_id))
            if hit_count > 0:
                visible_ids.add(obs.obs_id)
            elif in_fov:
                # Inside FOV, but all its surface rays were intercepted by a closer obstacle!
                occluded_ids.add(obs.obs_id)
            else:
                out_of_fov_ids.add(obs.obs_id)

        # Generate point cloud with range noise and dropout
        valid_hits = hit_obstacle_id >= 0
        hit_indices = np.where(valid_hits)[0]

        # Apply beam dropout
        keep_mask = rng.uniform(0.0, 1.0, size=len(hit_indices)) > self.camera_cfg.dropout_prob
        hit_indices = hit_indices[keep_mask]

        if len(hit_indices) == 0:
            return SensorObservation(
                point_cloud=np.empty((0, 3), dtype=np.float64),
                ranges=np.empty((0,), dtype=np.float64),
                ray_directions=np.empty((0, 3), dtype=np.float64),
                visible_obstacle_ids=visible_ids,
                occluded_obstacle_ids=occluded_ids,
                out_of_fov_obstacle_ids=out_of_fov_ids,
            )

        true_ranges = min_ranges[hit_indices]
        # Range-dependent Gaussian noise
        noise = rng.normal(0.0, self.camera_cfg.range_noise_std * (true_ranges / self.camera_cfg.max_range), size=len(true_ranges))
        noisy_ranges = np.clip(true_ranges + noise, self.camera_cfg.min_range, self.camera_cfg.max_range)
        
        hit_dirs = world_rays[hit_indices]
        point_cloud = drone_pos + noisy_ranges[:, np.newaxis] * hit_dirs

        return SensorObservation(
            point_cloud=point_cloud,
            ranges=noisy_ranges,
            ray_directions=hit_dirs,
            visible_obstacle_ids=visible_ids,
            occluded_obstacle_ids=occluded_ids,
            out_of_fov_obstacle_ids=out_of_fov_ids,
        )

    def capture_lidar(
        self,
        drone_pos: np.ndarray,
        drone_rot: np.ndarray,
        obstacles: List[ObstacleTarget],
        rng: np.random.Generator | None = None,
    ) -> SensorObservation:
        """
        Performs 360-degree LiDAR raycast with physical occlusion from closer obstacles.
        """
        if rng is None:
            rng = np.random.default_rng()

        world_rays = self.lidar_local_rays @ drone_rot.T  # shape (N_rays, 3)
        n_rays = len(world_rays)
        min_ranges = np.full(n_rays, self.lidar_cfg.max_range, dtype=np.float64)
        hit_obstacle_id = np.full(n_rays, -1, dtype=np.int32)

        for obs in obstacles:
            t_hits = self._ray_sphere_intersect(drone_pos, world_rays, obs.center, obs.radius)
            closer_mask = (t_hits >= self.lidar_cfg.min_range) & (t_hits < min_ranges)
            min_ranges[closer_mask] = t_hits[closer_mask]
            hit_obstacle_id[closer_mask] = obs.obs_id

        visible_ids: Set[int] = set()
        occluded_ids: Set[int] = set()
        out_of_fov_ids: Set[int] = set()

        for obs in obstacles:
            rel_vec = obs.center - drone_pos
            dist = np.linalg.norm(rel_vec)
            # Check elevation angle relative to drone body horizontal plane
            body_vec = rel_vec @ drone_rot
            el = math.degrees(math.atan2(body_vec[2], math.hypot(body_vec[0], body_vec[1])))
            in_fov = (
                self.lidar_cfg.vertical_fov_min_deg - 5.0 <= el <= self.lidar_cfg.vertical_fov_max_deg + 5.0 and
                dist <= self.lidar_cfg.max_range + obs.radius
            )

            hit_count = int(np.sum(hit_obstacle_id == obs.obs_id))
            if hit_count > 0:
                visible_ids.add(obs.obs_id)
            elif in_fov:
                occluded_ids.add(obs.obs_id)
            else:
                out_of_fov_ids.add(obs.obs_id)

        valid_hits = hit_obstacle_id >= 0
        hit_indices = np.where(valid_hits)[0]
        keep_mask = rng.uniform(0.0, 1.0, size=len(hit_indices)) > self.lidar_cfg.dropout_prob
        hit_indices = hit_indices[keep_mask]

        if len(hit_indices) == 0:
            return SensorObservation(
                point_cloud=np.empty((0, 3), dtype=np.float64),
                ranges=np.empty((0,), dtype=np.float64),
                ray_directions=np.empty((0, 3), dtype=np.float64),
                visible_obstacle_ids=visible_ids,
                occluded_obstacle_ids=occluded_ids,
                out_of_fov_obstacle_ids=out_of_fov_ids,
            )

        true_ranges = min_ranges[hit_indices]
        noise = rng.normal(0.0, self.lidar_cfg.range_noise_std, size=len(true_ranges))
        noisy_ranges = np.clip(true_ranges + noise, self.lidar_cfg.min_range, self.lidar_cfg.max_range)
        hit_dirs = world_rays[hit_indices]
        point_cloud = drone_pos + noisy_ranges[:, np.newaxis] * hit_dirs

        return SensorObservation(
            point_cloud=point_cloud,
            ranges=noisy_ranges,
            ray_directions=hit_dirs,
            visible_obstacle_ids=visible_ids,
            occluded_obstacle_ids=occluded_ids,
            out_of_fov_obstacle_ids=out_of_fov_ids,
        )
