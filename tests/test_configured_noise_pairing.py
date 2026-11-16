from copy import deepcopy
import pytest
from scripts.research.configured_noise_pairing import compare_configured, ZERO_FIELDS, UNIT_FIELDS


def config():
    return dict(seed=2256000,controller_type='AEGIS_3D_RECOVERY_MONITOR',sensor_bias=[0.,0.,0.],
                range_bias_m=0.,anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],
                navigation_force_method='DIRECTION_PRESERVING_PEAK',max_steps=150,recovery_steps=100,
                post_stop_steps=0,post_abstain_steps=0,fail_vectors_after_stop_proposal=False,
                **{k:0 for k in ZERO_FIELDS},**{k:1 for k in UNIT_FIELDS})


def call(a,b):
    return compare_configured([],[],left_config=a,right_config=b,numerical_tolerance=1e-10)


def test_supported_empty_pair_stays_unevaluated():
    r=call(config(),config())
    assert r['configuration_preconditions']=='SUPPORTED_DECLARED_PAIR'
    assert all(v is None for v in r['innovation_agreement'].values())


@pytest.mark.parametrize('key',ZERO_FIELDS+UNIT_FIELDS)
def test_unsupported_configuration_rejects_even_when_both_match(key):
    a=config();a[key]=.5
    with pytest.raises(ValueError):call(a,deepcopy(a))


@pytest.mark.parametrize('defect',['missing','velocity_bias','seed','controller','adaptive','count','bool_zero'])
def test_invalid_or_unsupported_declarations_reject(defect):
    a=config()
    if defect=='missing':a.pop('velocity_replay_probability')
    elif defect=='velocity_bias':a['velocity_bias_xyz']=[.1,0.,0.]
    elif defect=='seed':a['seed']=True
    elif defect=='controller':a['controller_type']='UNKNOWN'
    elif defect=='adaptive':a['fail_vectors_after_stop_proposal']=True
    elif defect=='count':a['max_steps']=0
    else:a['range_latency_steps']=False
    with pytest.raises(ValueError):call(a,deepcopy(a))


def test_different_bias_conditions_are_not_a_pair():
    a=config();b=config();b['sensor_bias']=[.8,.8,-.3]
    with pytest.raises(ValueError,match='unmatched'):call(a,b)
