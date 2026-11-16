"""
NEXVIA AEGIS — Convex Safe Flight Corridor (SFC) Polytopes.

Generates convex polyhedral safe flight corridors along candidate flight paths:
    P_k = { x in R^3 : A_poly x <= b_poly }

Bypasses spherical obstacle conservatism (TrackedObstacle3D) by constructing
tight separating hyperplanes around doorframes, window slits, and right-angle walls.
Integrates directly with:
- C++20 RTI-SQP NMPC-HOCBF engine (AegisNmpcCorridorPlane)
- Robust Tube-CLBF controller (tube-expanded linear halfspaces)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, List, Tuple

import numpy as np


@dataclass
class ConvexPolytope:
    """
    3D Convex Polytope defined by the intersection of halfspaces:
        A x <= b  <=>  n_m^T x <= d_m
    """
    A: np.ndarray             # shape (M, 3) plane outward normals
    b: np.ndarray             # shape (M,) plane offsets
    center: np.ndarray        # shape (3,) interior reference point

    def contains(self, point: np.ndarray, margin: float = 0.0) -> bool:
        """Checks if a 3D point lies strictly inside the polytope with given margin."""
        p = np.asarray(point, dtype=np.float64)
        viol = self.A @ p - (self.b - margin)
        return bool(np.all(viol <= 1e-5))

    def compute_clearance(self, point: np.ndarray) -> float:
        """
        Computes minimum distance from point to all polytope bounding facets.
        Positive if inside, negative if outside.
        """
        p = np.asarray(point, dtype=np.float64)
        margins = self.b - self.A @ p
        return float(np.min(margins))

    def to_c_abi_planes(self) -> list[tuple[np.ndarray, float]]:
        """
        Exports plane constraints in (normal, d) format compatible with
        AegisNmpcCorridorPlane (n^T x <= d).
        """
        planes = []
        for i in range(len(self.b)):
            planes.append((self.A[i].copy(), float(self.b[i])))
        return planes


@dataclass
class SafeFlightCorridor:
    """Sequence of overlapping convex polytopes connecting flight waypoints."""
    polytopes: list[ConvexPolytope] = field(default_factory=list)

    def get_active_polytope(self, drone_pos: np.ndarray) -> ConvexPolytope | None:
        """Returns the polytope containing the drone, or closest polytope if outside."""
        if not self.polytopes:
            return None

        # Check if drone is inside any polytope
        for poly in self.polytopes:
            if poly.contains(drone_pos):
                return poly

        # Fallback to polytope with maximum clearance (least negative)
        best_poly = self.polytopes[0]
        best_clr = self.polytopes[0].compute_clearance(drone_pos)
        for poly in self.polytopes[1:]:
            clr = poly.compute_clearance(drone_pos)
            if clr > best_clr:
                best_clr = clr
                best_poly = poly
        return best_poly


class SafeFlightCorridorGenerator:
    """
    Iterative Separating Hyperplane Safe Flight Corridor (SFC) Generator.
    Extracts convex bounding polytopes from 3D point cloud or geometric obstacles.
    """

    def __init__(
        self,
        default_box_radius: float = 1.2,
        z_min: float = 0.2,
        z_max: float = 2.8,
        min_plane_distance: float = 0.20,
    ) -> None:
        self.default_box_radius = default_box_radius
        self.z_min = z_min
        self.z_max = z_max
        self.min_plane_distance = min_plane_distance

    def generate_polytope_for_segment(
        self,
        pt_a: np.ndarray,
        pt_b: np.ndarray,
        point_cloud: np.ndarray,
    ) -> ConvexPolytope:
        """
        Generates a convex polytope enclosing the line segment [pt_a, pt_b]
        without colliding with any point in the point cloud.
        """
        center = 0.5 * (pt_a + pt_b)
        seg_vec = pt_b - pt_a
        seg_len = float(np.linalg.norm(seg_vec))

        A_list: list[np.ndarray] = []
        b_list: list[float] = []

        # 1. Base bounding box around segment
        r = self.default_box_radius + 0.5 * seg_len
        # +/- X
        A_list.append(np.array([1.0, 0.0, 0.0]))
        b_list.append(center[0] + r)
        A_list.append(np.array([-1.0, 0.0, 0.0]))
        b_list.append(-center[0] + r)
        # +/- Y
        A_list.append(np.array([0.0, 1.0, 0.0]))
        b_list.append(center[1] + r)
        A_list.append(np.array([0.0, -1.0, 0.0]))
        b_list.append(-center[1] + r)
        # Floor & Ceiling
        A_list.append(np.array([0.0, 0.0, 1.0]))
        b_list.append(self.z_max)
        A_list.append(np.array([0.0, 0.0, -1.0]))
        b_list.append(-self.z_min)

        if len(point_cloud) == 0:
            return ConvexPolytope(
                A=np.array(A_list, dtype=np.float64),
                b=np.array(b_list, dtype=np.float64),
                center=center,
            )

        # 2. Filter points within local bounding sphere of radius 1.5 * r
        dists_to_center = np.linalg.norm(point_cloud - center, axis=1)
        nearby_mask = dists_to_center < (1.5 * r)
        nearby_points = point_cloud[nearby_mask]

        if len(nearby_points) == 0:
            return ConvexPolytope(
                A=np.array(A_list, dtype=np.float64),
                b=np.array(b_list, dtype=np.float64),
                center=center,
            )

        # 3. Iterative separating hyperplanes
        # For obstacle points inside the initial box, add tangent planes
        cur_A = np.array(A_list, dtype=np.float64)
        cur_b = np.array(b_list, dtype=np.float64)

        # Check which points are inside
        for obs_pt in nearby_points:
            # Check if obs_pt is currently inside the polytope
            if np.all(cur_A @ obs_pt <= cur_b):
                # Find closest point on line segment [pt_a, pt_b] to obs_pt
                if seg_len > 1e-4:
                    t = float(np.clip(np.dot(obs_pt - pt_a, seg_vec) / (seg_len**2), 0.0, 1.0))
                    closest_on_seg = pt_a + t * seg_vec
                else:
                    closest_on_seg = center

                normal = obs_pt - closest_on_seg
                dist_norm = float(np.linalg.norm(normal))
                if dist_norm < 1e-4:
                    normal = np.array([1.0, 0.0, 0.0])
                    dist_norm = 1.0
                normal = normal / dist_norm

                # Plane passes through obs_pt: normal^T x <= normal^T obs_pt
                plane_d = float(np.dot(normal, obs_pt))

                # Ensure segment points remain strictly inside
                d_a = float(np.dot(normal, pt_a))
                d_b = float(np.dot(normal, pt_b))
                if max(d_a, d_b) <= plane_d:
                    A_list.append(normal)
                    b_list.append(plane_d)
                    cur_A = np.array(A_list, dtype=np.float64)
                    cur_b = np.array(b_list, dtype=np.float64)

        return ConvexPolytope(
            A=np.array(A_list, dtype=np.float64),
            b=np.array(b_list, dtype=np.float64),
            center=center,
        )

    def generate_corridor(
        self,
        waypoints: list[np.ndarray],
        point_cloud: np.ndarray,
    ) -> SafeFlightCorridor:
        """
        Builds a connected sequence of convex polytopes covering the trajectory waypoints.
        """
        if len(waypoints) < 2:
            center = waypoints[0] if waypoints else np.zeros(3)
            return SafeFlightCorridor([
                self.generate_polytope_for_segment(center, center, point_cloud)
            ])

        polytopes = []
        for i in range(len(waypoints) - 1):
            poly = self.generate_polytope_for_segment(waypoints[i], waypoints[i + 1], point_cloud)
            polytopes.append(poly)

        return SafeFlightCorridor(polytopes)
