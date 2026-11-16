import numpy as np
import pytest
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode


@pytest.mark.parametrize('arm,seed,bias,steps,post,expected', [
 ('AEGIS_3D_ANCHOR_RECOVERY',2256000,[.8,.8,-.3],400,5,'POST_STOP_BRAKE'),
 ('AEGIS_3D_RECOVERY_MONITOR',2254000,[0.,0.,0.],130,5,'ABSTAIN_BRAKE'),
 ('AEGIS_3D_ANCHOR_RECOVERY',2256000,[0.,0.,0.],3,0,'MAIN'),
])
def test_physics_sink_preserves_default_results_and_trace(arm,seed,bias,steps,post,expected):
    args = dict(controller_type=arm,seed=seed,sensor_bias=np.array(bias),max_steps=steps,
        post_stop_steps=post,navigation_force_method='DIRECTION_PRESERVING_PEAK')
    a,b,events=[],[],[]
    baseline=run_3d_episode(AegisMuJoCo3DEnvironment(),trace=a,**args)
    observed=run_3d_episode(AegisMuJoCo3DEnvironment(),trace=b,on_physics=events.append,**args)
    assert baseline==observed and a==b
    assert events[-1]['stage']==expected
    assert [e['physics_step'] for e in events]==list(range(1,len(events)+1))
    if expected=='POST_STOP_BRAKE':
        assert sum(e['stage']==expected for e in events)==post
        assert len(events)==observed['steps']-1+post
    elif expected=='ABSTAIN_BRAKE':
        assert sum(e['stage']==expected for e in events)==1
        assert len(events)==observed['steps']


def test_sink_failure_propagates_after_actual_physics():
    env=AegisMuJoCo3DEnvironment()
    def fail(event):
        assert env.step_count==1
        raise OSError('synthetic sink failure')
    with pytest.raises(OSError,match='synthetic sink'):
        run_3d_episode(env,'AEGIS_3D_ANCHOR_RECOVERY',2256000,np.zeros(3),max_steps=3,on_physics=fail)


def test_sink_restricted_to_callable_and_recovery_arms():
    for arm,sink in [('CBF_ONLY',lambda e:None),('AEGIS_3D_ANCHOR_RECOVERY',42)]:
        with pytest.raises(ValueError):
            run_3d_episode(AegisMuJoCo3DEnvironment(),arm,2256000,np.zeros(3),max_steps=1,on_physics=sink)
