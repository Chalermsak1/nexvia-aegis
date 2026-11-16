"""Actual short development traces; not the proposed eight-assignment study."""
import json
import numpy as np
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from aegis.env.mujoco_3d_synchronized import SynchronizedAegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from scripts.research.recovery_noise_pairing import compare, innovations
from scripts.research.development_ledger import DevelopmentLedger, inspect


def test_actual_traces_match_declared_streams_and_common_prefix(tmp_path):
    path=tmp_path/'actual_noise_trace.jsonl'
    assignments=[{'id':label,'seed':2256000,'controller':'AEGIS_3D_RECOVERY_MONITOR',
                  'max_steps':150,'scope':'DEVELOPMENT_NOISE_INTEGRATION_FIXTURE'}
                 for label in ('legacy','synchronized')]
    traces=[]
    with DevelopmentLedger.create(path,study='V9-M5 actual noise trace integration fixture v1',assignments=assignments,record_events=True) as ledger:
        for a,cls in zip(assignments,(AegisMuJoCo3DEnvironment,SynchronizedAegisMuJoCo3DEnvironment)):
            ledger.start(a['id']);trace=[]
            result=run_3d_episode(cls(),a['controller'],a['seed'],np.zeros(3),max_steps=150,
                trace=trace,navigation_force_method='DIRECTION_PRESERVING_PEAK',
                on_trace=lambda row:ledger.event(a['id'],details={'type':'DECISION','record':row}))
            ledger.complete(a['id'],status='COMPLETED',details={'episode':result})
            traces.append(trace)
        ledger.finalize()
    kwargs=dict(vector_bias=[0.,0.,0.],anchor_bias=[0.,0.,0.],range_bias=0.)
    pairing=compare(*traces,**kwargs,numerical_tolerance=1e-10)
    for trace in traces:
        rows,queries=innovations(trace,**kwargs)
        streams=np.random.SeedSequence(2256000).spawn(10)
        sensors=np.random.default_rng(streams[1]);velocity=np.random.default_rng(streams[5]);anchor=np.random.default_rng(streams[3])
        for row in rows:
            np.testing.assert_allclose(row['sensor_a'],sensors.normal(0,.05,3),rtol=0,atol=1e-10)
            np.testing.assert_allclose(row['sensor_b'],sensors.normal(0,.05,3),rtol=0,atol=1e-10)
            np.testing.assert_allclose(row['range'],[sensors.normal(0,.05)],rtol=0,atol=1e-10)
            np.testing.assert_allclose(row['velocity'],velocity.normal(0,.02,3),rtol=0,atol=1e-10)
        assert queries, 'fixture must exercise at least one actual anchor delivery'
        for q in queries:
            np.testing.assert_allclose(q['innovation'],anchor.normal(0,.04,3),rtol=0,atol=1e-10)
    assert all(pairing['innovation_agreement'].values())
    assert pairing['anchor_query_ordinal_agreement'] is True
    assert inspect(path)['state']=='FINALIZED'
    (tmp_path/'pairing.json').write_text(json.dumps(pairing,indent=2)+'\n')
