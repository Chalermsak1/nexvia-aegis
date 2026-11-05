"""
NEXVIA AEGIS — Unit Tests for Local 3D ESDF & Safe Flight Corridor Polytopes.

Verifies:
1. Local3DESDF distance and unit gradient computation against 3D point cloud surfaces.
2. Narrow aperture / doorway bottleneck detection.
3. ConvexPolytope containment and clearance calculations.
4. SafeFlightCorridorGenerator separating hyperplanes isolating obstacles from trajectory.
5. Export to C-ABI AegisNmpcCorridorPlane format for C++20 RTI-SQP NMPC engine.
6. Unified EpistemicPassagePOMDP active camera/body yaw gaze alignment and proactive air braking.
"""

import math
import numpy as np
import pytest

from aegis.vision.active_pomdp_gaze import (
    ActiveVisionConfig,
    EpistemicPassagePOMDP,
)
from aegis.vision.flight_corridor import (
    ConvexPolytope,
    SafeFlightCorridor,
    SafeFlightCorridorGenerator,
)
from aegis.vision.local_esdf import (
    ESDFConfig,
    Local3DESDF,
)


def test_local_3d_esdf_distance_and_gradient():
    """Validates 3D ESDF distance query and surface normal gradient direction."""
    esdf = Local3DESDF(ESDFConfig())

    # Wall at X = 2.0 spanning Y in [-1, 1], Z in [0, 2]
    ys = np.linspace(-1.0, 1.0, 21)
    zs = np.linspace(0.0, 2.0, 21)
    yy, zz = np.meshgrid(ys, zs)
    xx = np.full_like(yy, 2.0)
    wall_points = np.stack([xx.flatten(), yy.flatten(), zz.flatten()], axis=-1)

    esdf.update_from_point_cloud(wall_points)

    # Query point in front of wall at (1.5, 0.0, 1.0)
    dist, grad = esdf.get_distance_and_gradient(np.array([1.5, 0.0, 1.0]))

    # Distance should be ~0.5m
    assert abs(dist - 0.5) < 0.05, f"Expected dist ~0.5m, got {dist}"
    # Gradient should point AWAY from the wall (along -X direction)
    assert grad[0] < -0.9, f"Gradient should point in -X direction away from wall, got {grad}"
    assert np.linalg.norm(grad) > 0.95, "Gradient should be approximately unit length"


def test_esdf_narrow_doorway_bottleneck_detection():
    """Validates detection of narrow passages / doorways."""
    esdf = Local3DESDF(ESDFConfig())

    # Create a doorway at X = 1.0, width = 0.6m (aperture between Y = -0.3 and Y = +0.3)
    # Left wall: Y in [-2.0, -0.3]
    # Right wall: Y in [+0.3, +2.0]
    points = []
    for z in np.linspace(0.5, 2.0, 8):
        for y in np.linspace(-2.0, -0.3, 10):
            points.append([1.0, y, z])
        for y in np.linspace(0.3, 2.0, 10):
            points.append([1.0, y, z])

    esdf.update_from_point_cloud(np.array(points))

    # Path passing straight through doorway from (0.0, 0.0, 1.0) to (2.0, 0.0, 1.0)
    info = esdf.extract_passage_corridor(
        waypoint_a=np.array([0.0, 0.0, 1.0]),
        waypoint_b=np.array([2.0, 0.0, 1.0]),
        nominal_width=1.0,
    )

    assert info["is_narrow_passage"], "Should identify narrow doorway passage"
    assert info["min_clearance"] <= 0.35, f"Clearance should be ~0.30m, got {info['min_clearance']}"
    assert abs(info["bottleneck_point"][0] - 1.0) < 0.15, "Bottleneck should be centered at X=1.0"


def test_convex_polytope_containment_and_c_abi_export():
    """Validates ConvexPolytope halfspace evaluation and C-ABI export."""
    # Box: X in [-1, 1], Y in [-1, 1], Z in [0, 2]
    A = np.array([
        [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ], dtype=np.float64)
    b = np.array([1.0, 1.0, 1.0, 1.0, 2.0, 0.0], dtype=np.float64)
    center = np.array([0.0, 0.0, 1.0])

    poly = ConvexPolytope(A=A, b=b, center=center)

    assert poly.contains(np.array([0.0, 0.0, 1.0])), "Center must be inside"
    assert poly.contains(np.array([0.8, -0.5, 1.5])), "Interior point must be inside"
    assert not poly.contains(np.array([1.5, 0.0, 1.0])), "Point outside X=+1 must not be inside"

    # Export to C-ABI planes
    planes = poly.to_c_abi_planes()
    assert len(planes) == 6
    for normal, d in planes:
        assert isinstance(normal, np.ndarray)
        assert isinstance(d, float)
        assert normal.shape == (3,)


def test_safe_flight_corridor_generation_separating_hyperplanes():
    """Validates that Safe Flight Corridor polytopes separate obstacles from the flight path."""
    gen = SafeFlightCorridorGenerator(default_box_radius=1.0, z_min=0.2, z_max=2.5)

    # Flight path along X from (0.0, 0.0, 1.0) to (2.0, 0.0, 1.0)
    wps = [np.array([0.0, 0.0, 1.0]), np.array([2.0, 0.0, 1.0])]

    # Obstacle cluster at (1.0, 0.4, 1.0)
    obs_cloud = np.array([
        [1.0, 0.40, 1.0],
        [1.0, 0.45, 1.0],
        [1.0, 0.50, 1.0],
    ])

    corridor = gen.generate_corridor(wps, obs_cloud)
    assert len(corridor.polytopes) == 1

    poly = corridor.polytopes[0]
    # Center of path must be inside
    assert poly.contains(np.array([1.0, 0.0, 1.0])), "Flight path center must be inside corridor"
    # All obstacle points must be strictly outside the corridor
    for obs in obs_cloud:
        assert not poly.contains(obs, margin=0.01), f"Obstacle {obs} must be outside corridor"


def test_epistemic_passage_pomdp_active_gaze_and_braking():
    """
    Validates that approaching a narrow passage triggers:
    1. Direct camera pan/tilt and body yaw alignment with the aperture.
    2. Proactive air braking to slow vehicle before entry.
    3. Safe Flight Corridor boundary force projection.
    """
    controller = EpistemicPassagePOMDP(
        ActiveVisionConfig(robot_mass=1.2, gravity=9.81),
        passage_threshold_m=0.8,
    )

    # Setup narrow passage in ESDF
    esdf = Local3DESDF(ESDFConfig())
    doorway_pts = []
    for y in [-0.35, 0.35]:
        for z in np.linspace(0.5, 1.8, 5):
            doorway_pts.append([1.5, y, z])
    esdf.update_from_point_cloud(np.array(doorway_pts))

    # Fast drone approaching doorway: pos = (0.5, 0.0, 1.0), vel = (1.2, 0.0, 0.0)
    drone_pos = np.array([0.5, 0.0, 1.0])
    drone_vel = np.array([1.2, 0.0, 0.0])
    drone_yaw = 45.0  # Currently yawed at 45 deg
    target_pos = np.array([2.5, 0.0, 1.0])

    decision = controller.plan_passage_step(
        drone_pos=drone_pos,
        drone_vel=drone_vel,
        drone_yaw_deg=drone_yaw,
        target_pos=target_pos,
        esdf=esdf,
    )

    assert decision.is_passing_narrow_corridor, "Should detect narrow doorway"
    assert decision.is_actively_probing, "High-speed approach to narrow opening must trigger active probing"
    # Yaw must re-orient toward the aperture (which is along X-axis, yaw ~ 0 deg)
    assert abs(decision.desired_yaw_deg) < 15.0, f"Body yaw should align with doorway, got {decision.desired_yaw_deg}"
    # Forward force must brake due to proactive air braking (safe_force[0] < nominal_force[0])
    assert decision.safe_force[0] < decision.nominal_force[0], "Proactive air brake must decelerate forward force"


def test_esdf_lidar_drift_and_degraded_observability():
    """Validates that LiDAR odometry drift and degraded observability trigger conservative clearance expansion."""
    from aegis.vision.ukf_obstacle_tracker import TrackedObstacle3D

    controller = EpistemicPassagePOMDP(
        ActiveVisionConfig(kappa_safety=3.0, uncertainty_safe_thresh=0.08),
        passage_threshold_m=1.0,
    )

    esdf = Local3DESDF(ESDFConfig())
    # Doorway at X=1.5
    doorway_pts = [[1.5, y, 1.0] for y in [-0.4, 0.4]]
    esdf.update_from_point_cloud(np.array(doorway_pts))

    # Case A: Nominal tracking with low covariance (sigma = 0.03 m)
    state_nom = np.array([1.5, 0.4, 1.0, 0.0, 0.0, 0.0, 0.20], dtype=np.float64)
    cov_nom = np.eye(7, dtype=np.float64) * (0.03**2)
    low_cov_obs = TrackedObstacle3D(
        track_id=1,
        state=state_nom,
        covariance=cov_nom,
        is_confirmed=True,
    )
    dec_nominal = controller.plan_passage_step(
        drone_pos=np.array([0.5, 0.0, 1.0]),
        drone_vel=np.array([0.3, 0.0, 0.0]),
        drone_yaw_deg=0.0,
        target_pos=np.array([2.5, 0.0, 1.0]),
        tracked_obstacles=[low_cov_obs],
        esdf=esdf,
    )

    # Case B: High odometry drift / covariance explosion (sigma = 0.22 m)
    state_drift = np.array([1.5, 0.4, 1.0, 0.0, 0.0, 0.0, 0.20], dtype=np.float64)
    cov_drift = np.eye(7, dtype=np.float64) * (0.22**2)
    high_cov_obs = TrackedObstacle3D(
        track_id=1,
        state=state_drift,
        covariance=cov_drift,
        is_confirmed=True,
    )
    dec_drift = controller.plan_passage_step(
        drone_pos=np.array([0.5, 0.0, 1.0]),
        drone_vel=np.array([0.3, 0.0, 0.0]),
        drone_yaw_deg=0.0,
        target_pos=np.array([2.5, 0.0, 1.0]),
        tracked_obstacles=[high_cov_obs],
        esdf=esdf,
    )

    assert dec_drift.is_actively_probing, "Odometry drift / high covariance must trigger active probing"
    assert dec_drift.information_entropy_bits > dec_nominal.information_entropy_bits
    # Forward thrust must be reduced under degraded observability
    assert dec_drift.safe_force[0] <= dec_nominal.safe_force[0]

