#!/usr/bin/env python3
"""Separate development evidence study: persist decisions AND physical steps.

Diagnostic repeats only. Never use for V9-M4 Holdout or authorization.
"""
import argparse
import hashlib
from pathlib import Path
import platform
import sys
import mujoco
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError
from scripts.research.study_recovery_monitor_ledger import FILES


def hashes():
    files=FILES+['scripts/research/study_recovery_physics_evidence.py']
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development-seed',type=int,required=True)
    parser.add_argument('--max-steps',type=int,default=400)
    parser.add_argument('--post-stop-steps',type=int,default=50)
    parser.add_argument('--post-abstain-steps',type=int,default=0)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.development_seed<0 or min(args.max_steps,args.post_stop_steps)<=0 or args.post_abstain_steps<0:
        parser.error('nonnegative development seed and positive counts required')
    source=hashes()
    assignments=[{'id':f'{args.development_seed}:{bias[0]}:{arm}', 'seed':args.development_seed,
        'bias_xyz':bias,'controller':arm,'max_steps':args.max_steps,'post_stop_steps':args.post_stop_steps,
        'navigation_force_method':'DIRECTION_PRESERVING_PEAK','recovery_steps_limit':100,
        'source_sha256':source,'runtime':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},
        'post_abstain_steps':args.post_abstain_steps,
        'evidence_scope':'DECISION_PLUS_POST_PHYSICS; ACTIVE_TRUTH_BRAKING_DIAGNOSTICS'}
        for bias in ([0.,0.,0.],[.8,.8,-.3]) for arm in ('AEGIS_3D_ANCHOR_RECOVERY','AEGIS_3D_RECOVERY_MONITOR')]
    study='V9-M5 recovery physical evidence v2' if args.post_abstain_steps else 'V9-M5 recovery physical evidence v1'
    with DevelopmentLedger.create(args.output,study=study,assignments=assignments,record_events=True) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            def emit(kind,event):
                ledger.event(a['id'],details={'type':kind,'record':event})
            try:
                result=run_3d_episode(AegisMuJoCo3DEnvironment(),a['controller'],a['seed'],np.array(a['bias_xyz']),
                    max_steps=a['max_steps'],post_stop_steps=a['post_stop_steps'],trace=[],
                    post_abstain_steps=a['post_abstain_steps'],
                    navigation_force_method=a['navigation_force_method'],recovery_steps=a['recovery_steps_limit'],
                    on_trace=lambda e:emit('DECISION',e),on_physics=lambda e:emit('PHYSICS',e))
                status,detail='COMPLETED',{'episode':result}
            except (LedgerError,LedgerWriteError):
                raise
            except Exception as exc:
                status,detail='ERROR',{'error_type':type(exc).__name__,'error':str(exc)}
            detail['source_sha256_after']=hashes()
            if detail['source_sha256_after']!=source:
                ledger.complete(a['id'],status='ERROR',details=detail)
                raise RuntimeError('source changed; preserve incomplete evidence')
            ledger.complete(a['id'],status=status,details=detail)
        ledger.finalize()


if __name__=='__main__':
    main()
