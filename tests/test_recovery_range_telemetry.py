"""Recorded transport validity must not hide physically invalid range values."""
import numpy as np
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode


def test_negative_range_is_logged_without_relaxing_abstention():
    trace = []
    result = run_3d_episode(AegisMuJoCo3DEnvironment(), 'AEGIS_3D_RECOVERY_MONITOR',
        2254000, np.zeros(3), max_steps=130, trace=trace,
        navigation_force_method='DIRECTION_PRESERVING_PEAK')
    last = trace[-1]
    assert last['range_valid'] and last['range_fresh']
    assert last['range_raw_transport_valid']
    assert last['range_controller_distance'] < 0
    assert last['range_semantically_valid'] is False
    assert last['range_validation_status'] == 'NEGATIVE_DISTANCE'
    assert last['terminal_reason'] == 'POSTPROPOSAL_RANGE_UNAVAILABLE'
    assert last['effective_decision'] == 'ABSTAIN'
    assert result['abstained'] == 1 and result['true_success'] == 0
