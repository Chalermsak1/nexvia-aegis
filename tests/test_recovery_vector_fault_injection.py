"""Synthetic check that the paired arms receive the same targeted vector loss."""
import numpy as np
import pytest
from experiments import benchmark_physical_3d_cbf as benchmark
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment


@pytest.mark.parametrize("arm,attribute", [("AEGIS_3D_ANCHOR_RECOVERY", "AnchorRecoveryCandidate"),
    ("AEGIS_3D_RECOVERY_MONITOR", "RecoveryMonitorCandidate")])
def test_targeted_loss_starts_only_after_stop_proposal(monkeypatch, arm, attribute):
    class Observer:
        def __init__(self, **kwargs):
            self.phase = "BASE"
            self.received = []
            self.postproposal_monitor_steps = 0
            self.postproposal_monitor_reason = "NOT_STARTED"
        def reset(self): pass
        def update(self, a, b, r, **kwargs):
            self.received.append((a.valid, a.dropped, b.valid, b.dropped))
            if self.phase == "BASE":
                self.phase = "BRAKING"
                return np.zeros(3), "VERIFY", np.zeros(3), False
            return np.zeros(3), "ABSTAIN", np.zeros(3), False
    controller = Observer()
    monkeypatch.setattr(benchmark, attribute, lambda **kwargs: controller)
    row = benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), arm, 2247000, np.zeros(3),
                                   max_steps=5, fail_vectors_after_stop_proposal=True)
    assert controller.received == [(True, False, True, False), (False, True, False, True)]
    assert row["injected_vector_loss_steps"] == 1 and row["abstained"] == 1


def test_vector_loss_not_accepted_for_unrelated_arm():
    with pytest.raises(ValueError):
        benchmark.run_3d_episode(AegisMuJoCo3DEnvironment(), "CBF_ONLY", 2247000, np.zeros(3),
                                 fail_vectors_after_stop_proposal=True)
