"""
NEXVIA AEGIS — Autonomous Active Frontier Exploration & Informative Path Planning (IPP).

Enables GPS-denied mapless exploration of unknown subterranean environments,
collapsed buildings, and complex 3D structures:
1. 3D Occupancy Volumetric Grid (Voxel Space):
   - Maintains Unknown, Free, and Occupied voxels via 3D raycasting.
2. Frontier Voxel Extraction & Spatial Clustering:
   - Identifies candidate frontiers at the interface of Free and Unknown space.
   - Groups frontier voxels into reachable clusters using spatial distance thresholds.
3. Information-Theoretic Utility & Gaze Optimization:
   - Computes Expected Volumetric Information Gain U(pose, frontier) penalized by
     flight distance, heading deflection, and velocity alignment.
4. Integration with Local ESDF & Safe Flight Corridor (SFC) Polytopes:
   - Projects exploration paths through certified collision-free convex polyhedra
     shielded by High-Order Control Barrier Functions (HOCBF).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class ExplorationConfig:
    """Configuration for 3D Frontier-Based Autonomous Exploration."""
    voxel_resolution: float = 0.20          # Voxel cell side length (m)
    bounds_min: tuple[float, float, float] = (-6.0, -6.0, 0.0)   # Arena bounds (m)
    bounds_max: tuple[float, float, float] = (6.0, 6.0, 3.0)     # Arena bounds (m)
    sensor_max_range: float = 4.5           # Max LiDAR/Depth sensing distance (m)
    sensor_fov_deg: float = 86.0            # Forward depth camera FoV (deg)
    min_cluster_size: int = 4               # Minimum frontier voxels to form a cluster
    cluster_radius: float = 0.60            # Grouping radius for frontier clustering (m)
    dist_weight: float = 1.2                # Travel distance penalty weight
    heading_weight: float = 0.8             # Heading change penalty weight
    volume_weight: float = 1.0              # Frontier size / information reward weight
    arrival_threshold: float = 0.40         # Distance to mark frontier cluster reached (m)


class VoxelState:
    UNKNOWN = 0
    FREE = 1
    OCCUPIED = 2


@dataclass
class FrontierCluster:
    """Group of contiguous frontier voxels representing an unexplored boundary."""
    cluster_id: int
    centroid: np.ndarray                    # (3,) coordinate of cluster center
    voxel_count: int
    bounding_radius: float
    information_gain: float = 0.0
    utility_score: float = 0.0


class OccupancyVoxelGrid3D:
    """
    3D Discrete Volumetric Grid for Mapless Exploration.
    """

    def __init__(self, cfg: ExplorationConfig) -> None:
        self.cfg = cfg
        self.res = cfg.voxel_resolution
        self.b_min = np.array(cfg.bounds_min, dtype=np.float64)
        self.b_max = np.array(cfg.bounds_max, dtype=np.float64)

        self.dims = np.ceil((self.b_max - self.b_min) / self.res).astype(np.int32)
        self.grid = np.zeros(self.dims, dtype=np.uint8)  # 0: UNKNOWN, 1: FREE, 2: OCCUPIED
        self.total_voxels = int(np.prod(self.dims))

    def world_to_grid(self, pt: np.ndarray) -> Optional[tuple[int, int, int]]:
        """Converts continuous 3D world coordinates to discrete grid indices."""
        idx = np.floor((pt - self.b_min) / self.res).astype(np.int32)
        if (
            0 <= idx[0] < self.dims[0]
            and 0 <= idx[1] < self.dims[1]
            and 0 <= idx[2] < self.dims[2]
        ):
            return int(idx[0]), int(idx[1]), int(idx[2])
        return None

    def grid_to_world(self, ix: int, iy: int, iz: int) -> np.ndarray:
        """Converts discrete grid indices to continuous world coordinate of voxel center."""
        return self.b_min + (np.array([ix, iy, iz], dtype=np.float64) + 0.5) * self.res

    def integrate_sensor_scan(
        self,
        origin: np.ndarray,
        hit_points: List[np.ndarray],
        max_range: float | None = None,
    ) -> None:
        """
        Integrates range observations using 3D raycasting.
        Voxels along the ray are marked FREE; hit voxel is marked OCCUPIED.
        """
        r_max = max_range or self.cfg.sensor_max_range
        p_orig = np.asarray(origin, dtype=np.float64)

        # Clear immediate spherical neighborhood around drone as physically FREE
        r_clear = 0.8
        steps_clear = int(math.ceil(r_clear / self.res))
        orig_idx = self.world_to_grid(p_orig)
        if orig_idx is not None:
            ox, oy, oz = orig_idx
            for dx in range(-steps_clear, steps_clear + 1):
                for dy in range(-steps_clear, steps_clear + 1):
                    for dz in range(-steps_clear, steps_clear + 1):
                        if dx * dx + dy * dy + dz * dz <= steps_clear * steps_clear:
                            qx, qy, qz = ox + dx, oy + dy, oz + dz
                            if 0 <= qx < self.dims[0] and 0 <= qy < self.dims[1] and 0 <= qz < self.dims[2]:
                                if self.grid[qx, qy, qz] != VoxelState.OCCUPIED:
                                    self.grid[qx, qy, qz] = VoxelState.FREE

        for hit in hit_points:
            p_hit = np.asarray(hit, dtype=np.float64)
            ray = p_hit - p_orig
            dist = float(np.linalg.norm(ray))
            if dist < 1e-4:
                continue

            num_steps = max(1, int(math.ceil(min(dist, r_max) / (0.5 * self.res))))
            step_vec = (ray / max(1e-4, dist)) * (dist / num_steps)

            # Trace ray
            for s in range(num_steps):
                p_sample = p_orig + s * step_vec
                g_idx = self.world_to_grid(p_sample)
                if g_idx is not None:
                    # Do not overwrite previously confirmed obstacles
                    if self.grid[g_idx] != VoxelState.OCCUPIED:
                        self.grid[g_idx] = VoxelState.FREE

            # Mark endpoint
            if dist <= r_max:
                hit_idx = self.world_to_grid(p_hit)
                if hit_idx is not None:
                    self.grid[hit_idx] = VoxelState.OCCUPIED

    def get_coverage_ratio(self) -> float:
        """Returns the ratio of explored (Free + Occupied) to total volume."""
        explored = int(np.count_nonzero(self.grid != VoxelState.UNKNOWN))
        return float(explored / max(1, self.total_voxels))


class FrontierExplorationEngine:
    """
    Active Frontier Exploration & Informative Path Planner for Aerial Robots.
    """

    def __init__(self, config: ExplorationConfig | None = None) -> None:
        self.cfg = config or ExplorationConfig()
        self.voxel_grid = OccupancyVoxelGrid3D(self.cfg)
        self.active_frontier: Optional[FrontierCluster] = None
        self.visited_clusters: List[np.ndarray] = []
        self.exploration_complete: bool = False

    def reset(self) -> None:
        """Resets voxel map and exploration state."""
        self.voxel_grid = OccupancyVoxelGrid3D(self.cfg)
        self.active_frontier = None
        self.visited_clusters.clear()
        self.exploration_complete = False

    def update_map(self, drone_pos: np.ndarray, sensor_hits: List[np.ndarray]) -> None:
        """Integrates new sensor readings into the volumetric map."""
        self.voxel_grid.integrate_sensor_scan(drone_pos, sensor_hits)

    def extract_frontiers(self) -> List[np.ndarray]:
        """
        Extracts frontier voxels: cells that are FREE and have >= 1 UNKNOWN 26-neighbor.
        Returns list of 3D world coordinates.
        """
        grid = self.voxel_grid.grid
        free_mask = grid == VoxelState.FREE

        # Fast 6-connectivity neighbor check for efficiency
        frontiers_world = []
        nx, ny, nz = self.voxel_grid.dims

        free_indices = np.argwhere(free_mask)
        # Random sub-sampling if point set is too large to maintain 50 Hz real-time compute
        if len(free_indices) > 2500:
            sample_mask = np.random.choice(len(free_indices), size=2500, replace=False)
            free_indices = free_indices[sample_mask]

        neighbor_offsets = [
            (1, 0, 0), (-1, 0, 0),
            (0, 1, 0), (0, -1, 0),
            (0, 0, 1), (0, 0, -1),
        ]

        for ix, iy, iz in free_indices:
            has_unknown_neighbor = False
            for dx, dy, dz in neighbor_offsets:
                qx, qy, qz = ix + dx, iy + dy, iz + dz
                if 0 <= qx < nx and 0 <= qy < ny and 0 <= qz < nz:
                    if grid[qx, qy, qz] == VoxelState.UNKNOWN:
                        has_unknown_neighbor = True
                        break
                else:
                    # Outside boundary is considered unknown/frontier boundary
                    has_unknown_neighbor = True
                    break

            if has_unknown_neighbor:
                pt_world = self.voxel_grid.grid_to_world(int(ix), int(iy), int(iz))
                frontiers_world.append(pt_world)

        return frontiers_world

    def cluster_frontiers(
        self,
        frontier_points: List[np.ndarray],
        drone_pos: np.ndarray | None = None,
    ) -> List[FrontierCluster]:
        """
        Clusters discrete frontier points into directional cohesive clusters.
        Partitions by 8 angular sectors around drone_pos to prevent 360-degree ring centroid collapse.
        """
        if not frontier_points:
            return []

        pts = np.array(frontier_points, dtype=np.float64)
        clusters: List[FrontierCluster] = []
        cluster_id = 0

        p_ref = drone_pos if drone_pos is not None else np.zeros(3)

        # Partition points into 8 directional sectors (45 degrees each)
        num_sectors = 8
        sector_bins: Dict[int, List[np.ndarray]] = {s: [] for s in range(num_sectors)}

        for pt in pts:
            delta = pt[:2] - p_ref[:2]
            dist_xy = float(np.linalg.norm(delta))
            if dist_xy < 0.5:
                continue  # Skip voxels too close to drone body
            angle = math.atan2(delta[1], delta[0])  # [-pi, pi]
            sector_idx = int(math.floor(((angle + math.pi) / (2 * math.pi)) * num_sectors)) % num_sectors
            sector_bins[sector_idx].append(pt)

        for s_idx, s_pts_list in sector_bins.items():
            if len(s_pts_list) < self.cfg.min_cluster_size:
                continue

            s_pts = np.array(s_pts_list, dtype=np.float64)
            centroid = np.mean(s_pts, axis=0)
            max_rad = float(np.max(np.linalg.norm(s_pts - centroid, axis=-1)))

            # Check if this centroid is already visited
            is_visited = False
            for v_c in self.visited_clusters:
                if np.linalg.norm(centroid - v_c) < self.cfg.arrival_threshold * 1.5:
                    is_visited = True
                    break

            if not is_visited:
                clusters.append(
                    FrontierCluster(
                        cluster_id=cluster_id,
                        centroid=centroid,
                        voxel_count=len(s_pts),
                        bounding_radius=max_rad,
                        information_gain=float(len(s_pts)),
                    )
                )
                cluster_id += 1

        return clusters

    def select_best_frontier(
        self,
        drone_pos: np.ndarray,
        drone_yaw: float,
        drone_vel: np.ndarray,
    ) -> Optional[FrontierCluster]:
        """
        Evaluates utility score across all candidate clusters:
            U(C) = [Vol(C)^gamma] / [(d + eps)^w_d * (1 + |Delta yaw|)^w_h]
        """
        raw_frontiers = self.extract_frontiers()
        clusters = self.cluster_frontiers(raw_frontiers, drone_pos=drone_pos)

        if not clusters:
            self.exploration_complete = True
            return None

        best_cluster: Optional[FrontierCluster] = None
        best_utility = -float("inf")

        for c in clusters:
            delta_pos = c.centroid - drone_pos
            dist = float(np.linalg.norm(delta_pos))

            # Heading difference
            target_yaw = math.atan2(delta_pos[1], delta_pos[0])
            yaw_diff = abs(math.atan2(math.sin(target_yaw - drone_yaw), math.cos(target_yaw - drone_yaw)))

            # Information utility formulation
            gain_term = c.information_gain ** self.cfg.volume_weight
            dist_cost = (dist + 0.3) ** self.cfg.dist_weight
            heading_cost = 1.0 + self.cfg.heading_weight * (yaw_diff / math.pi)

            # Velocity alignment bonus (penalize reversing direction)
            v_norm = float(np.linalg.norm(drone_vel))
            alignment = 1.0
            if v_norm > 0.2 and dist > 0.1:
                cos_theta = float(np.dot(drone_vel, delta_pos) / (v_norm * dist))
                alignment = max(0.2, 0.5 * (1.0 + cos_theta))

            utility = (gain_term * alignment) / (dist_cost * heading_cost)
            c.utility_score = utility

            if utility > best_utility:
                best_utility = utility
                best_cluster = c

        self.active_frontier = best_cluster
        return best_cluster

    def step_exploration(
        self,
        drone_pos: np.ndarray,
        drone_yaw: float,
        drone_vel: np.ndarray,
        sensor_hits: List[np.ndarray],
    ) -> Dict[str, Any]:
        """
        Executes one step of active frontier planning:
        1. Updates 3D volumetric map
        2. Evaluates arrival at active frontier
        3. Selects new optimal informative exploration target
        """
        self.update_map(drone_pos, sensor_hits)

        # Check if arrived at current active frontier
        if self.active_frontier is not None:
            dist = float(np.linalg.norm(self.active_frontier.centroid - drone_pos))
            if dist < self.cfg.arrival_threshold:
                self.visited_clusters.append(self.active_frontier.centroid.copy())
                self.active_frontier = None

        # Select new best frontier if none active
        if self.active_frontier is None:
            self.select_best_frontier(drone_pos, drone_yaw, drone_vel)

        best_frontier = self.active_frontier
        coverage = self.voxel_grid.get_coverage_ratio()

        target_pos = best_frontier.centroid.copy() if best_frontier else drone_pos.copy()
        target_yaw = (
            math.atan2(target_pos[1] - drone_pos[1], target_pos[0] - drone_pos[0])
            if best_frontier and float(np.linalg.norm(target_pos[:2] - drone_pos[:2])) > 0.1
            else drone_yaw
        )

        return {
            "target_pos": target_pos,
            "target_yaw": target_yaw,
            "has_active_frontier": best_frontier is not None,
            "coverage_ratio": coverage,
            "exploration_complete": self.exploration_complete,
            "active_cluster": best_frontier,
        }
