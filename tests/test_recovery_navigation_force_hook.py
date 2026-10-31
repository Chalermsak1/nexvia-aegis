"""Exploratory force transformation must not change recovery/terminal commands."""
import numpy as np
import pytest
from experiments import benchmark_physical_3d_cbf as benchmark
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.navigation_force_candidate import navigation_force


@pytest.mark.parametrize('arm,attribute', [
    ('AEGIS_3D_ANCHOR_RECOVERY', 'AnchorRecoveryCandidate'),
    ('AEGIS_3D_RECOVERY_MONITOR', 'RecoveryMonitorCandidate')])
@pytest.mark.parametrize('before,after,decision,transformed', [
    ('BASE', 'BASE', 'NAVIGATE', True),
    ('BASE', 'BASE', 'PROBE', True),
    ('BASE', 'RECOVERY', 'NAVIGATE', False),
    ('RECOVERY', 'RECOVERY', 'NAVIGATE', False),
    ('BASE', 'BRAKING', 'VERIFY', False),
    ('BRAKING', 'ANCHOR', 'VERIFY', False),
    ('ANCHOR', 'TERMINAL', 'STOP', False),
    ('BASE', 'TERMINAL', 'ABSTAIN', False),
])
def test_transform_only_inherited_base_guidance(monkeypatch, arm, attribute, before, after, decision, transformed):
    original_class = getattr(benchmark, attribute)
    original_action = np.array([.2, .3, .1])
    nav = np.array([4., 6., -1.])

    class Fixture(original_class):
        def reset(self):
            super().reset()
            self.phase = before

        def update(self, *args, **kwargs):
            self.phase = after
            return original_action.copy(), decision, nav.copy(), False

    monkeypatch.setattr(benchmark, attribute, Fixture)
    trace = []
    row = benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), arm, 2254000, np.zeros(3), max_steps=1,
        navigation_force_method='DIRECTION_PRESERVING_PEAK', trace=trace)
    assert row['navigation_force_method'] == 'DIRECTION_PRESERVING_PEAK'
    assert trace[0]['navigation_force_transformed'] is transformed
    assert trace[0]['original_action'] == original_action.tolist()
    expected = navigation_force(1.2 * nav, method='DIRECTION_PRESERVING_PEAK') if transformed else original_action
    assert np.allclose(trace[0]['action'], expected)
    assert trace[0]['phase_before'] == before and trace[0]['phase_after'] == after


def test_default_axis_mode_preserves_actual_short_episode():
    traces = [[], []]
    result = []
    for options, trace in zip(({}, {'navigation_force_method': 'AXIS_CLIP'}), traces):
        result.append(benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), 'AEGIS_3D_ANCHOR_RECOVERY',
            2254000, np.zeros(3), max_steps=5, trace=trace, **options))
    assert result[0] == result[1] and traces[0] == traces[1]
    assert not any(event['navigation_force_transformed'] for event in traces[0])


@pytest.mark.parametrize('arm,method', [('CBF_ONLY', 'DIRECTION_PRESERVING_PEAK'), ('AEGIS_3D_ANCHOR_RECOVERY', 'UNKNOWN')])
def test_invalid_or_out_of_scope_method_rejected(arm, method):
    with pytest.raises(ValueError):
        benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), arm, 2254000, np.zeros(3), navigation_force_method=method)
