"""Development execution adapter: persist and execute one explicit argument map.

No batch study, scientific outcome interpretation, authentication or retries.
"""
from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
import numpy as np
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from aegis.env.mujoco_3d_synchronized import SynchronizedAegisMuJoCo3DEnvironment
from scripts.research.configured_noise_pairing import validate
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError

ROOT=Path(__file__).resolve().parents[2]
FILES=('scripts/research/recovery_execution_bridge_v2.py','experiments/benchmark_physical_3d_cbf.py',
       'src/aegis/env/mujoco_3d_cbf.py','src/aegis/env/mujoco_3d_synchronized.py',
       'scripts/research/configured_noise_pairing.py','scripts/research/recovery_noise_pairing.py',
       'scripts/research/development_ledger.py')
STUDY='V9-M5 recovery execution bridge v2 runtime-checked development'


def hashes():
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}


def runtime_snapshot(env):
    return {'configuration':asdict(env.config),'timestep':float(env.model.opt.timestep),
            'integrator':int(env.model.opt.integrator),'gravity':env.model.opt.gravity.tolist(),
            'body_mass':env.model.body_mass.tolist(),'geom_size':env.model.geom_size.tolist()}


def execute(path, config, *, synchronized):
    # JSON round-trip freezes caller-owned lists and prohibits nonfinite values.
    config=json.loads(json.dumps(config,allow_nan=False))
    validate(config)
    expected=set(inspect.signature(run_3d_episode).parameters)-{'env','trace','on_trace','on_physics'}
    if set(config)!=expected:raise ValueError('complete exact benchmark argument map required')
    if type(synchronized) is not bool:raise ValueError('explicit environment selection required')
    source=hashes()
    base=SynchronizedAegisMuJoCo3DEnvironment if synchronized else AegisMuJoCo3DEnvironment
    label=base.ENVIRONMENT_ID if synchronized else 'LEGACY_CLASS_SOURCE_IDENTIFIED_MIXED_PHASE'
    assignment={'id':'development_case','configuration':config,'environment_id':label,'source_sha256':source}
    # The header and START survive construction/reset failures.
    with DevelopmentLedger.create(path,study=STUDY,assignments=[assignment],record_events=True) as ledger:
        ledger.start(assignment['id'])
        def emit(kind,record,env):
            if runtime_snapshot(env)!=expected_runtime:
                raise RuntimeError('runtime drift before event persistence')
            ledger.event(assignment['id'],details={'type':kind,'environment_id':label,
                'simulation_time_seconds':float(env.data.time),'runtime_timestep_seconds':float(env.model.opt.timestep),
                'physical_state_phase':'FORWARD_REFRESH_RESET' if kind=='RESET' else ('SYNCHRONIZED' if synchronized else 'LEGACY_MIXED_POSITION_VELOCITY'),
                'record':record})
        class Instrumented(base):
            def reset(self,rng):
                state=super().reset(rng)
                emit('RESET',{'position':state['robot_pos'].tolist(),'velocity':state['robot_velocity'].tolist(),
                             'target':state['target_pos'].tolist(),'configuration':asdict(self.config),
                             'integrator':int(self.model.opt.integrator),'gravity':self.model.opt.gravity.tolist()},self)
                return state
        env=None;expected_runtime=None
        try:
            env=Instrumented()
            expected_runtime=runtime_snapshot(env)
            ledger.event(assignment['id'],details={'type':'RUNTIME','record':expected_runtime})
            trace=[]
            # The same frozen map recorded above supplies every benchmark argument.
            result=run_3d_episode(env,**config,trace=trace,
                on_trace=lambda r:emit('DECISION',r,env),on_physics=lambda r:emit('PHYSICS',r,env))
        except (LedgerError,LedgerWriteError):
            raise
        except Exception as exc:
            ledger.complete(assignment['id'],status='ERROR',details={'error_type':type(exc).__name__,
                'error':str(exc),'source_sha256_after':hashes(),
                'runtime_before':expected_runtime,'runtime_after':runtime_snapshot(env) if env else None})
            ledger.finalize()
            return
        after=hashes()
        if source!=after or runtime_snapshot(env)!=expected_runtime:
            ledger.complete(assignment['id'],status='ERROR',details={'error':'source/runtime drift','source_sha256_after':after,
                'runtime_before':expected_runtime,'runtime_after':runtime_snapshot(env)})
            raise RuntimeError('source/runtime changed during execution')
        ledger.complete(assignment['id'],status='COMPLETED',details={'episode':result,'source_sha256_after':after,
            'runtime_before':expected_runtime,'runtime_after':runtime_snapshot(env)})
        ledger.finalize()
