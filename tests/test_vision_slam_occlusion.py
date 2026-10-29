"""
Unit and integration tests for Active Vision & LiDAR SLAM under Occlusion.
"""

import math
import numpy as np
import pytest

from aegis.vision.depth_lidar_sensor import (
    DepthCameraConfig,
    Lidar3DConfig,
    ObstacleTarget,
    SimulatedPerceptionSuite,
)
from aegis.vision.ukf_obstacle_tracker import (
    MultiObstacleUKFTracker,
    UKFTrackerConfig,
)
from aegis.vision.active_pomdp_gaze import (
    ActiveVisionConfig,
    ActiveVisionPOMDPController,
)


def test_depth_camera_physical_occlusion():
    """Verify that a foreground obstacle physically blocks rays to a background obstacle."""
    suite = SimulatedPerceptionSuite()
    drone_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    drone_rot = np.eye(3, dtype=np.float64)  # looking along +X

    # Obstacle 1 directly in front at X=1.5, Obstacle 2 directly behind it at X=3.0
    obs1 = ObstacleTarget(obs_id=1, center=np.array([1.5, 0.0, 1.0]), radius=0.4)
    obs2 = ObstacleTarget(obs_id=2, center=np.array([3.0, 0.0, 1.0]), radius=0.3)

    obs_result = suite.capture_depth_camera(drone_pos, drone_rot, [obs1, obs2])

    assert 1 in obs_result.visible_obstacle_ids, "Foreground obstacle must be visible"
    assert 2 in obs_result.occluded_obstacle_ids, "Background obstacle must be physically occluded"
    assert len(obs_result.point_cloud) > 0, "Depth camera must return hit points on foreground obstacle"

    # Now move Obstacle 2 sideways outside Obstacle 1's shadow
    obs2_side = ObstacleTarget(obs_id=2, center=np.array([2.5, 0.8, 1.0]), radius=0.3)
    obs_result_unblocked = suite.capture_depth_camera(drone_pos, drone_rot, [obs1, obs2_side])

    assert 1 in obs_result_unblocked.visible_obstacle_ids
    assert 2 in obs_result_unblocked.visible_obstacle_ids, "Unblocked obstacle must now be visible"


def test_lidar_360_degree_coverage():
    """Verify 360-degree LiDAR coverage detects obstacles surrounding the vehicle."""
    suite = SimulatedPerceptionSuite()
    drone_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    drone_rot = np.eye(3, dtype=np.float64)

    # 4 obstacles in North (+X), West (+Y), South (-X), East (-Y)
    obstacles = [
        ObstacleTarget(obs_id=10, center=np.array([2.0, 0.0, 1.0]), radius=0.3),
        ObstacleTarget(obs_id=11, center=np.array([0.0, 2.0, 1.0]), radius=0.3),
        ObstacleTarget(obs_id=12, center=np.array([-2.0, 0.0, 1.0]), radius=0.3),
        ObstacleTarget(obs_id=13, center=np.array([0.0, -2.0, 1.0]), radius=0.3),
    ]

    lidar_obs = suite.capture_lidar(drone_pos, drone_rot, obstacles)
    assert len(lidar_obs.visible_obstacle_ids) == 4, "LiDAR should detect all 4 surround obstacles"
    assert len(lidar_obs.point_cloud) >= 20, "LiDAR should generate dense surface points"


def test_ukf_tracker_occlusion_variance_growth():
    """Verify UKF covariance contracts with measurements and expands under occlusion."""
    tracker = MultiObstacleUKFTracker(UKFTrackerConfig(dt=0.02))

    # Initialize track with 3 consecutive detections
    true_pos = np.array([1.5, 0.5, 1.0])
    for _ in range(5):
        tracker.update_from_clusters([(true_pos, 0.35)])

    tracks = tracker.get_confirmed_tracks()
    assert len(tracks) == 1
    t = tracks[0]
    assert t.is_confirmed
    cov_detected = t.max_position_std
    vol_detected = t.uncertainty_volume

    # Simulate 20 steps of complete occlusion (no cluster measurements)
    for _ in range(20):
        tracker.update_from_clusters([])

    tracks_after = tracker.get_confirmed_tracks()
    assert len(tracks_after) == 1
    t_after = tracks_after[0]
    assert t_after.is_currently_occluded
    cov_occluded = t_after.max_position_std

    assert cov_occluded > cov_detected, "Covariance must expand under occlusion"
    assert t_after.uncertainty_volume > vol_detected, "Uncertainty volume must expand"


def test_active_pomdp_gaze_and_robust_hocbf():
    """Verify Active POMDP triggers gaze saccade and expands robust HOCBF envelope."""
    controller = ActiveVisionPOMDPController(ActiveVisionConfig(
        kappa_safety=3.0,
        uncertainty_safe_thresh=0.10,
    ))

    drone_pos = np.array([0.0, 0.0, 1.0])
    drone_vel = np.array([0.8, 0.0, 0.0])
    drone_yaw = 0.0
    target_pos = np.array([3.0, 0.0, 1.0])

    # Case A: Low uncertainty obstacle along path
    tracker = MultiObstacleUKFTracker()
    for _ in range(10):
        tracker.update_from_clusters([(np.array([1.5, 0.1, 1.0]), 0.3)])
    confirmed = tracker.get_confirmed_tracks()

    decision_low = controller.plan_step(drone_pos, drone_vel, drone_yaw, target_pos, confirmed)
    assert not decision_low.is_actively_probing, "Low uncertainty should not trigger active probing"

    # Case B: High uncertainty obstacle due to 25 steps of occlusion
    for _ in range(25):
        tracker.update_from_clusters([])
    confirmed_high = tracker.get_confirmed_tracks()

    decision_high = controller.plan_step(drone_pos, drone_vel, drone_yaw, target_pos, confirmed_high)
    assert decision_high.is_actively_probing, "High uncertainty must trigger active probing"
    assert decision_high.critical_track_id is not None
    # Nominal speed must decelerate compared to unhindered flight
    assert np.linalg.norm(decision_high.nominal_force) != np.linalg.norm(decision_low.nominal_force)
    # Robust clearance margin must expand by 3-sigma
    assert decision_high.effective_clearance_margins[0] > decision_low.effective_clearance_margins[0]
