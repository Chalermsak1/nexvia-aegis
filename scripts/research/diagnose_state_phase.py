#!/usr/bin/env python3
"""Characterize post-integration position timing in development-only fixtures.

Forward a copied MjData to observe current kinematics without changing the
legacy environment, its controller inputs, or historical experimental evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment, PhysicalWorld3DConfig


def compare_position_phase(env, reported):
    """Read an independent data copy; never forward or modify the live data."""
    shadow = mujoco.MjData(env.model)
    mujoco.mj_copyData(shadow, env.model, env.data)
    mujoco.mj_forward(env.model, shadow)
    current = shadow.xpos[env.robot_body_id].copy()
    cached = np.asarray(reported['robot_pos'], dtype=float)
    return {
        'simulation_time_seconds': float(env.data.time),
        'runtime_timestep_seconds': float(env.model.opt.timestep),
        'reported_position': cached.tolist(),
        'integrated_translation_qpos': env.data.qpos[:3].tolist(),
        'copied_forward_position': current.tolist(),
        'reported_velocity': np.asarray(reported['robot_velocity']).tolist(),
        'reported_distance': float(reported['distance']),
        'copied_forward_distance': float(np.linalg.norm(env.target_pos - current)),
        'position_phase_offset_m': float(np.linalg.norm(current - cached)),
    }


def measure_case(timestep, speed, steps=3):
    env = AegisMuJoCo3DEnvironment(PhysicalWorld3DConfig(timestep=timestep))
    # Known synthetic development setup, not a reserved/confirmatory seed.
    env.reset(np.random.default_rng(9201001))
    env.target_pos = np.array([2., 2., .5])
    env.data.qvel[:3] = [speed, 0., 0.]
    mujoco.mj_forward(env.model, env.data)
    observations = []
    for _ in range(steps):
        reported = env.step(np.zeros(3))
        observations.append(compare_position_phase(env, reported))
    return {'timestep_seconds': timestep, 'initial_speed_m_s': speed,
            'command': [0., 0., 0.], 'steps': observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = ['src/aegis/env/mujoco_3d_cbf.py', 'scripts/research/diagnose_state_phase.py',
             'tests/test_state_phase_diagnostic.py']
    before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files}
    cases = [measure_case(dt, speed) for dt in (.01, .02) for speed in (0., .1, .5)]
    after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files}
    if before != after:
        raise RuntimeError('source changed during diagnostic')
    result = {
        'classification': 'EXPLORATORY_STATE_PHASE_REPRODUCTION',
        'parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'mujoco': mujoco.__version__},
        'source_sha256_before': before, 'source_sha256_after': after,
        'cases': cases, 'fixture_cases': 6, 'total_fixture_steps': 18,
        'limitations': [
            'Synthetic open-loop simulation fixtures; not policy evaluation or independent reliability trials.',
            'Copied-data forward pass is diagnostic only and never changes live controller inputs.',
            'No claim about exact corrections to historical summaries or their outcome classifications.',
            'Source hashes are selected-file consistency checks, not authenticated provenance.',
            'No Holdout, reserved seeds/outcomes, production tickets or real robot involved.'],
        'governance': 'GATE_B_NOT_AUTHORIZED',
    }
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
