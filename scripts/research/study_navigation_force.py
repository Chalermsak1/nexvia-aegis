#!/usr/bin/env python3
"""Ideal-state development force ablation. Not an arrival-policy evaluation."""
import argparse
import hashlib
import platform
from pathlib import Path
import sys
import mujoco
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError
from scripts.research.navigation_force_candidate import navigation_force

FILES = ['scripts/research/study_navigation_force.py', 'scripts/research/navigation_force_candidate.py',
         'scripts/research/development_ledger.py', 'src/aegis/env/mujoco_3d_cbf.py']
ARMS = ('AXIS_CLIP', 'DIRECTION_PRESERVING_PEAK')


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


def run(seed, arm, steps, emit):
    env = AegisMuJoCo3DEnvironment()
    state = env.reset(np.random.default_rng(np.random.SeedSequence(seed).spawn(10)[0]))
    initial = float(state['distance'])
    minimum = initial
    violations = 0
    collision = False
    for step in range(steps):
        position = state['robot_pos'].copy()
        velocity = state['robot_velocity'].copy()
        # Both arms deliberately use simulator truth: isolate force geometry.
        desired = navigation_force(1.2 * (state['target_pos'] - position), env.config.control_force_limit, method=arm) - .5 * velocity
        state = env.step(desired)
        residual = state['cbf_constraint_residual']
        violations += int(residual is not None and residual > 1e-8)
        collision |= bool(state['safety_violation'])
        minimum = min(minimum, float(state['distance']))
        emit({'step': step, 'type': 'POST_PHYSICS', 'position_before': position.tolist(),
              'velocity_before': velocity.tolist(), 'target': state['target_pos'].tolist(),
              'desired_force': desired.tolist(), 'projected_force': state['safe_action'].tolist(),
              'position_after': state['robot_pos'].tolist(), 'velocity_after': state['robot_velocity'].tolist(),
              'distance_after': float(state['distance']), 'safety_violation': bool(state['safety_violation']),
              'cbf_residual': residual, 'cbf_feasible': state['cbf_qp_feasible']})
    return {'seed': seed, 'arm': arm, 'steps': steps, 'initial_distance': initial,
            'final_distance': float(state['distance']), 'minimum_distance': minimum,
            'safety_violation_observed': collision, 'constraint_violation_steps': violations,
            'claim': 'NO_ARRIVAL_OR_SAFETY_PASS_CLASSIFICATION'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds', nargs='+', type=int, required=True)
    p.add_argument('--steps', type=int, default=800)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.steps <= 0 or len(set(args.seeds)) != len(args.seeds):
        p.error('positive steps and unique development seeds required')
    source = hashes()
    assignments = [{'id': f'{seed}:{arm}', 'seed': seed, 'arm': arm, 'steps': args.steps,
        'source_sha256': source, 'state_source': 'SIMULATOR_TRUTH',
        'runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'mujoco': mujoco.__version__}}
        for seed in args.seeds for arm in ARMS]
    with DevelopmentLedger.create(args.output, study='V9-M5 ideal-state navigation force ablation v1', assignments=assignments, record_events=True) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            try:
                result = run(a['seed'], a['arm'], a['steps'], lambda event: ledger.event(a['id'], details=event))
                details, status = {'episode': result}, 'COMPLETED'
            except (LedgerError, LedgerWriteError):
                raise
            except Exception as exc:
                details, status = {'error_type': type(exc).__name__, 'error': str(exc)}, 'ERROR'
            details['source_sha256_after'] = hashes()
            if details['source_sha256_after'] != source:
                ledger.complete(a['id'], status='ERROR', details=details)
                raise RuntimeError('source changed; preserve incomplete ledger')
            ledger.complete(a['id'], status=status, details=details)
        ledger.finalize()


if __name__ == '__main__':
    main()
