from copy import deepcopy
import math
import pytest
from scripts.research.recovery_noise_pairing import compare


def trace(positions, query_steps=()):
    rows=[]
    for i,p in enumerate(positions):
        delta=[2-p,0.,0.]
        rows.append(dict(step=i,position=[p,0.,0.],target=[2.,0.,0.],velocity=[p,0.,0.],true_distance=abs(2-p),
            sensor_a=[delta[0]+.1,0.,0.],sensor_b=[delta[0]-.1,0.,0.],range_raw_sample=abs(2-p)+.05,
            velocity_observation=[p+.02,0.,0.],vector_fault_injected=False,range_raw_transport_valid=True,range_fresh=True,
            anchor_requested=i in query_steps,anchor_valid=True if i in query_steps else None,
            anchor=[delta[0]+.03,0.,0.] if i in query_steps else None))
    return rows


def check(a,b):
    return compare(a,b,vector_bias=[0.,0.,0.],anchor_bias=[0.,0.,0.],range_bias=0.,numerical_tolerance=1e-10)


def test_different_trajectories_can_share_innovations_with_shifted_anchor_queries():
    result=check(trace([0.,.1,.2],(0,)),trace([0.,.3,.6],(2,)))
    assert all(result['innovation_agreement'].values())
    assert result['anchor_query_ordinal_agreement'] is True
    assert result['common_query_steps_equal'] is False
    assert result['anchor_request_steps']==[[0],[2]]


def test_mismatched_noise_is_detected_without_hiding_unequal_coverage():
    a=trace([0.,.1,.2],(0,2));b=trace([0.,.3],(1,));b[1]['sensor_a'][0]+=.01
    result=check(a,b)
    assert result['innovation_agreement']['sensor_a'] is False
    assert result['common_decision_steps']==2 and result['unmatched_decision_steps']==[1,0]
    assert result['unmatched_anchor_queries']==[1,0]


def test_absent_data_cannot_pass_coupling_check():
    result=check([],[])
    assert all(v is None for v in result['innovation_agreement'].values())
    assert result['anchor_query_ordinal_agreement'] is None


@pytest.mark.parametrize('defect',['missing_velocity','wrong_distance','fault','orphan_anchor','step'])
def test_incomplete_or_contradictory_observations_reject(defect):
    a=trace([0.,.1]);b=deepcopy(a)
    if defect=='missing_velocity':b[0]['velocity_observation']=None
    elif defect=='wrong_distance':b[0]['true_distance']+=1
    elif defect=='fault':b[0]['vector_fault_injected']=True
    elif defect=='orphan_anchor':b[0]['anchor']=[0.,0.,0.]
    else:b[0]['step']=1
    with pytest.raises(ValueError):check(a,b)
