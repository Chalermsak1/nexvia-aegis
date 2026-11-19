"""Opt-in, versioned development environment with synchronized step observations.

Legacy AegisMuJoCo3DEnvironment and benchmark defaults remain unchanged. A
forward refresh can alter derived solver state; this is a distinct simulation
arm, not a drop-in reinterpretation of old trajectories or evidence. Extra
forward passes may invoke installed MuJoCo callbacks; fixtures validate a
callback-free setup only. Identity/timing stamps describe step() outputs;
assignment metadata must separately record ENVIRONMENT_ID, including reset.
"""
from __future__ import annotations
from typing import Any
import mujoco
import numpy as np
from .mujoco_3d_cbf import AegisMuJoCo3DEnvironment


class SynchronizedAegisMuJoCo3DEnvironment(AegisMuJoCo3DEnvironment):
    ENVIRONMENT_ID = 'AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT'

    def step(
        self,
        desired_control: np.ndarray,
        force_braking: bool = False,
        *,
        measured_pos: np.ndarray | None = None,
        measured_vel: np.ndarray | None = None,
        require_measured_feedback: bool = False,
    ) -> dict[str, Any]:
        # Refresh before CBF construction, including after an explicit external
        # state edit. mj_forward computes derived state without integrating.
        mujoco.mj_forward(self.model, self.data)
        interval_start = float(self.data.time)
        transition = super().step(
            desired_control,
            force_braking=force_braking,
            measured_pos=measured_pos,
            measured_vel=measured_vel,
            require_measured_feedback=require_measured_feedback,
        )
        # super().step's cached-position observation is deliberately replaced;
        # preserve its pre-integration control/CBF diagnostics separately.
        mujoco.mj_forward(self.model, self.data)
        transition.update(super().get_state())
        transition.update(
            environment_id=self.ENVIRONMENT_ID,
            state_phase='POST_INTEGRATION_FORWARD_REFRESH',
            control_diagnostics_phase='PRE_INTEGRATION_CBF',
            control_interval_start_seconds=interval_start,
            simulation_time_seconds=float(self.data.time),
            runtime_timestep_seconds=float(self.model.opt.timestep),
        )
        return transition
