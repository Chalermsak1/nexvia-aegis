"""Development budget hook preserves default behavior and strict scope."""
import numpy as np
import pytest
from experiments import benchmark_physical_3d_cbf as benchmark
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment


@pytest.mark.parametrize('budget', [0, -1, True, False, 1.5, float('nan'), '100', None])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError, match='positive integer'):
        benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), 'AEGIS_3D_ANCHOR_RECOVERY',
            2254000, np.zeros(3), recovery_steps=budget)


@pytest.mark.parametrize('arm', ['CBF_ONLY', 'AEGIS_3D_AWARE_CBF', 'AEGIS_3D_STABILIZED'])
def test_nondefault_budget_rejected_for_unrelated_arms(arm):
    with pytest.raises(ValueError, match='only exploratory recovery arms'):
        benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), arm, 2254000, np.zeros(3), recovery_steps=400)


@pytest.mark.parametrize('arm,attribute', [
    ('AEGIS_3D_ANCHOR_RECOVERY', 'AnchorRecoveryCandidate'),
    ('AEGIS_3D_RECOVERY_MONITOR', 'RecoveryMonitorCandidate')])
def test_selected_budget_reaches_constructor(monkeypatch, arm, attribute):
    original = getattr(benchmark, attribute)
    created = []

    def factory(**kwargs):
        controller = original(**kwargs)
        created.append(controller)
        return controller

    monkeypatch.setattr(benchmark, attribute, factory)
    result = benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), arm, 2254000, np.zeros(3),
        max_steps=3, recovery_steps=400)
    assert created[0].recovery_limit == 400
    assert result['recovery_steps_limit'] == 400


@pytest.mark.parametrize('arm', ['AEGIS_3D_ANCHOR_RECOVERY', 'AEGIS_3D_RECOVERY_MONITOR'])
def test_explicit_default_matches_omitted_default(arm):
    traces = [[], []]
    results = [benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), arm, 2254000, np.zeros(3),
        max_steps=5, trace=trace, **options)
        for trace, options in zip(traces, ({}, {'recovery_steps': 100}))]
    assert results[0] == results[1]
    assert traces[0] == traces[1]
    assert results[0]['recovery_steps_limit'] == 100
