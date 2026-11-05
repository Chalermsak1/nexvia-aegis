"""
Unit tests for DownwashWakeModel and WakeAwareHOCBF.
"""

import math
import numpy as np
import pytest

from aegis.env.downwash_wake_model import (
    DownwashWakeConfig,
    DownwashWakeModel,
    WakeAwareHOCBF,
)


def test_downwash_directional_asymmetry():
    """Follower above leader receives zero wake; follower below receives downward jet."""
    model = DownwashWakeModel()
    pos_leader = np.array([0.0, 0.0, 1.5])
    thrust_leader = 12.0  # ~Hover thrust

    # Case A: Follower above leader at (0, 0, 2.0) -> No wake
    pos_above = np.array([0.0, 0.0, 2.0])
    v_w, f_w, tau_w, sev = model.evaluate_pairwise_wake(pos_leader, thrust_leader, pos_above)
    assert np.allclose(v_w, 0.0)
    assert np.allclose(f_w, 0.0)
    assert sev == 0.0

    # Case B: Follower below leader at (0, 0, 0.8) -> Strong downwash
    pos_below = np.array([0.0, 0.0, 0.8])
    v_w, f_w, tau_w, sev = model.evaluate_pairwise_wake(pos_leader, thrust_leader, pos_below)
    assert v_w[2] < -3.0, f"Expected strong downward velocity, got {v_w[2]:.2f} m/s"
    assert f_w[2] < 0.0, f"Expected downward drag force, got {f_w[2]:.2f} N"
    assert sev > 0.3


def test_shear_torque_on_wake_boundary():
    """Follower on radial wake boundary experiences outward tipping torque."""
    model = DownwashWakeModel()
    pos_leader = np.array([0.0, 0.0, 1.8])
    thrust_leader = 11.8

    # Follower displaced in +X by 0.15m at z = 1.2m (under leader, near shear gradient)
    pos_edge = np.array([0.15, 0.0, 1.2])
    v_w, f_w, tau_w, sev = model.evaluate_pairwise_wake(pos_leader, thrust_leader, pos_edge)

    assert v_w[2] < 0.0
    # Positive displacement in X should induce pitch/roll moment away from center
    assert abs(tau_w[1]) > 1e-4, f"Expected non-zero shear tipping moment, got {tau_w}"


def test_swarm_wake_superposition():
    """Superposition of multiple wake sources computes aggregate forces across swarm."""
    model = DownwashWakeModel()
    positions = [
        np.array([0.0, 0.0, 2.0]),   # Leader 0 (High)
        np.array([0.0, 0.0, 1.2]),   # Follower 1 (Directly beneath 0)
        np.array([1.5, 1.5, 1.2]),   # Distant drone 2
    ]
    thrusts = [12.0, 12.0, 12.0]

    states = model.compute_swarm_wake_disturbances(positions, thrusts)
    assert len(states) == 3

    # Leader 0 has no one above it -> not in wake
    assert states[0].in_wake_cone is False
    assert states[0].wake_force[2] == 0.0

    # Follower 1 is directly beneath Leader 0 -> in wake
    assert states[1].in_wake_cone is True
    assert states[1].wake_force[2] < 0.0

    # Distant drone 2 is far away laterally -> zero wake
    assert states[2].in_wake_cone is False


def test_wake_aware_hocbf_barrier():
    """Wake-aware HOCBF expands safety buffer vertically to prevent vertical stacking."""
    cbf = WakeAwareHOCBF(r_safe=0.44, kappa_wake=2.5)

    pos_leader = np.array([0.0, 0.0, 1.8])
    vel_leader = np.zeros(3)

    # Follower directly beneath at (0, 0, 1.0) -> dz = -0.8m
    pos_follower_below = np.array([0.0, 0.0, 1.0])
    vel_follower_upward = np.array([0.0, 0.0, 0.5])  # Flying toward leader from below

    a_vec, b_val, h_val = cbf.compute_barrier_constraint(
        pos_i=pos_follower_below,
        vel_i=vel_follower_upward,
        pos_j=pos_leader,
        vel_j=vel_leader,
        mu_responsibility=1.0,
    )

    # Barrier constraint must decelerate upward velocity to prevent entering wake
    # a_vec = -grad_p / m. Since grad_z = -2 * z_under / k^2 < 0, a_vec[2] > 0
    assert a_vec[2] > 0.0, "Upward motion must be bounded by wake barrier"
    assert math.isfinite(b_val)
    assert math.isfinite(h_val)
