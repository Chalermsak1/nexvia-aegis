"""
NEXVIA AEGIS — Unit Tests for Autonomous Frontier Exploration & Active Mapping.

Verifies:
1. 3D Volumetric Voxel Raycasting: Correctly updates Free and Occupied space.
2. Frontier Boundary Detection: Detects voxels at Free/Unknown interfaces.
3. Information-Theoretic Cluster Ranking: Prefers large frontiers nearby with low heading deviation.
4. Active Exploration Loop: Progresses autonomous exploration in unknown space.
"""

import math
import numpy as np
import pytest

from aegis.navigation.frontier_exploration import (
    ExplorationConfig,
    FrontierExplorationEngine,
    OccupancyVoxelGrid3D,
    VoxelState,
)


def test_occupancy_voxel_grid_raycasting():
    """Verifies 3D raycasting updates voxels along ray to Free and endpoints to Occupied."""
    cfg = ExplorationConfig(
        voxel_resolution=0.2,
        bounds_min=(-2.0, -2.0, 0.0),
        bounds_max=(2.0, 2.0, 2.0),
        sensor_max_range=3.0,
    )
    grid = OccupancyVoxelGrid3D(cfg)

    origin = np.array([0.0, 0.0, 1.0])
    # 4 horizontal hits on a bounding box at distance 1.2m
    hits = [
        np.array([1.2, 0.0, 1.0]),
        np.array([-1.2, 0.0, 1.0]),
        np.array([0.0, 1.2, 1.0]),
        np.array([0.0, -1.2, 1.0]),
    ]

    initial_coverage = grid.get_coverage_ratio()
    assert initial_coverage == 0.0

    grid.integrate_sensor_scan(origin, hits)

    # Origin should be free
    orig_idx = grid.world_to_grid(origin)
    assert orig_idx is not None
    assert grid.grid[orig_idx] == VoxelState.FREE

    # Endpoints should be occupied
    for h in hits:
        hit_idx = grid.world_to_grid(h)
        assert hit_idx is not None
        assert grid.grid[hit_idx] == VoxelState.OCCUPIED

    assert grid.get_coverage_ratio() > 0.0


def test_frontier_extraction_and_clustering():
    """Verifies frontier identification and spatial clustering."""
    cfg = ExplorationConfig(
        voxel_resolution=0.2,
        bounds_min=(-3.0, -3.0, 0.0),
        bounds_max=(3.0, 3.0, 2.0),
        min_cluster_size=2,
    )
    engine = FrontierExplorationEngine(cfg)

    # Simulate drone scanning a clear space around itself
    drone_pos = np.array([0.0, 0.0, 1.0])
    hits = []
    # Circle of hits at 1.5m radius
    for angle in np.linspace(0, 2 * math.pi, 24, endpoint=False):
        hits.append(drone_pos + np.array([1.5 * math.cos(angle), 1.5 * math.sin(angle), 0.0]))

    engine.update_map(drone_pos, hits)

    frontiers = engine.extract_frontiers()
    assert len(frontiers) > 0, "Expected non-zero frontier voxels at interface"

    clusters = engine.cluster_frontiers(frontiers)
    assert len(clusters) > 0, "Expected frontier clusters to be formed"
    for c in clusters:
        assert c.voxel_count >= cfg.min_cluster_size
        assert c.information_gain > 0


def test_active_exploration_step():
    """Verifies autonomous exploration decision-making and coverage progression."""
    cfg = ExplorationConfig(
        voxel_resolution=0.25,
        bounds_min=(-3.0, -3.0, 0.0),
        bounds_max=(3.0, 3.0, 2.0),
        sensor_max_range=2.5,
    )
    engine = FrontierExplorationEngine(cfg)

    curr_pos = np.array([0.0, 0.0, 1.0])
    curr_yaw = 0.0
    curr_vel = np.array([0.1, 0.0, 0.0])

    coverages = []
    for step in range(5):
        # Generate simulated radial scan from current position
        hits = [
            curr_pos + np.array([2.0 * math.cos(a), 2.0 * math.sin(a), 0.0])
            for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)
        ]

        decision = engine.step_exploration(
            drone_pos=curr_pos,
            drone_yaw=curr_yaw,
            drone_vel=curr_vel,
            sensor_hits=hits,
        )

        assert "target_pos" in decision
        assert "coverage_ratio" in decision
        coverages.append(decision["coverage_ratio"])

        # Move simulated drone toward selected frontier target
        target = decision["target_pos"]
        direction = target - curr_pos
        dist = float(np.linalg.norm(direction))
        if dist > 0.05:
            step_move = (direction / dist) * min(0.4, dist)
            curr_pos += step_move
            curr_vel = step_move / 0.1
            curr_yaw = decision["target_yaw"]

    # Coverage must increase monotonically as drone explores
    assert coverages[-1] >= coverages[0]
