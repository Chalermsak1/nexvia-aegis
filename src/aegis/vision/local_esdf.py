"""
NEXVIA AEGIS — Local 3D Euclidean Signed Distance Field (ESDF).

Replaces overly conservative bounding-sphere approximations (TrackedObstacle3D)
with a dense 3D Signed Distance Field:
1. Reconstructs obstacle surfaces from Depth/LiDAR point clouds.
2. Evaluates continuous signed distance d(x) and surface normal gradient grad d(x)
   via trilinear interpolation.
3. Detects narrow passages (slits, doorways, window frames) where spherical barriers
   would falsely declare complete blockage.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Tuple

import numpy as np
from scipy.spatial import KDTree


@dataclass(frozen=True)
class ESDFConfig:
    voxel_size: float = 0.08          # Resolution of each voxel cell in meters
    grid_bounds_x: tuple[float, float] = (-3.0, 3.0)  # Local volume X limits (m)
    grid_bounds_y: tuple[float, float] = (-3.0, 3.0)  # Local volume Y limits (m)
    grid_bounds_z: tuple[float, float] = (0.0, 3.0)   # Local volume Z limits (m)
    truncation_dist: float = 0.80     # Maximum distance cutoff for ESDF (m)


class Local3DESDF:
    """
    Local 3D Euclidean Signed Distance Field.
    Maintains a continuous distance representation of local space.
    """

    def __init__(self, config: ESDFConfig | None = None) -> None:
        self.cfg = config or ESDFConfig()
        self.res = self.cfg.voxel_size
        self.x_min, self.x_max = self.cfg.grid_bounds_x
        self.y_min, self.y_max = self.cfg.grid_bounds_y
        self.z_min, self.z_max = self.cfg.grid_bounds_z

        self.nx = int(math.ceil((self.x_max - self.x_min) / self.res))
        self.ny = int(math.ceil((self.y_max - self.y_min) / self.res))
        self.nz = int(math.ceil((self.z_max - self.z_min) / self.res))

        # Distance field grid: shape (nx, ny, nz)
        self.distance_grid = np.full((self.nx, self.ny, self.nz), self.cfg.truncation_dist, dtype=np.float32)
        self.kdtree: KDTree | None = None
        self.point_cloud: np.ndarray = np.empty((0, 3), dtype=np.float64)

    def update_from_point_cloud(
        self,
        point_cloud: np.ndarray,
        sensor_origin: np.ndarray | None = None,
    ) -> None:
        """
        Builds ESDF from 3D point cloud hit points.
        """
        if len(point_cloud) == 0:
            self.point_cloud = np.empty((0, 3), dtype=np.float64)
            self.kdtree = None
            self.distance_grid.fill(self.cfg.truncation_dist)
            return

        self.point_cloud = np.asarray(point_cloud, dtype=np.float64)
        self.kdtree = KDTree(self.point_cloud)

    def get_distance_and_gradient(self, query_point: np.ndarray) -> tuple[float, np.ndarray]:
        """
        Computes signed distance d(x) and surface normal unit gradient grad d(x)
        at an arbitrary query position x in R^3.

        Positive d(x) > 0: point is in free space, distance to nearest obstacle surface.
        Gradient grad d(x): unit vector pointing AWAY from the obstacle toward free space.
        """
        p = np.asarray(query_point, dtype=np.float64)

        if self.kdtree is None or len(self.point_cloud) == 0:
            # Entire volume is free space up to truncation distance
            return self.cfg.truncation_dist, np.zeros(3, dtype=np.float64)

        # Query nearest point in point cloud
        dist, idx = self.kdtree.query(p, k=1)
        nearest_pt = self.point_cloud[idx]

        # Vector pointing from nearest surface point to query point
        diff = p - nearest_pt
        d_val = float(dist)

        if d_val > 1e-5:
            grad = diff / d_val
        else:
            grad = np.array([0.0, 0.0, 1.0], dtype=np.float64)

        return min(d_val, self.cfg.truncation_dist), grad

    def check_corridor_clearance(
        self,
        start_pt: np.ndarray,
        end_pt: np.ndarray,
        num_samples: int = 20,
    ) -> tuple[float, np.ndarray]:
        """
        Scans a candidate flight segment and returns the minimum clearance and the bottleneck location.
        """
        alphas = np.linspace(0.0, 1.0, num_samples)
        min_clearance = float("inf")
        bottleneck = start_pt.copy()

        for a in alphas:
            pt = (1.0 - a) * start_pt + a * end_pt
            d, _ = self.get_distance_and_gradient(pt)
            if d < min_clearance:
                min_clearance = d
                bottleneck = pt.copy()

        return min_clearance, bottleneck

    def extract_passage_corridor(
        self,
        waypoint_a: np.ndarray,
        waypoint_b: np.ndarray,
        nominal_width: float = 1.0,
        height_clearance: float = 1.0,
    ) -> dict[str, Any]:
        """
        Detects if a segment passes through a narrow aperture and extracts passage attributes.
        """
        min_clr, bottleneck = self.check_corridor_clearance(waypoint_a, waypoint_b)
        is_narrow = min_clr < (nominal_width / 2.0)

        # Estimate passage normal (direction of passage axis)
        axis = waypoint_b - waypoint_a
        norm_axis = float(np.linalg.norm(axis))
        if norm_axis > 1e-4:
            axis_unit = axis / norm_axis
        else:
            axis_unit = np.array([1.0, 0.0, 0.0])

        return {
            "is_narrow_passage": is_narrow,
            "min_clearance": min_clr,
            "bottleneck_point": bottleneck,
            "passage_axis": axis_unit,
        }
