from fractions import Fraction as Q
from itertools import product
import pytest
from aegis.development.held_force_motion_1d import segment,DYNAMICS_ID


def args():return dict(position=['0','0'],velocity=['2','2'],force=['-4','-4'],mass=['1','1'],dt='1',disturbance='0',safe_position=['-.1','.4'],dynamics_id=DYNAMICS_ID)


def test_safe_endpoints_can_hide_an_unsafe_interior_apex():
    r=segment(**args())
    assert r['physical_endpoints_contained'] and not r['continuous_segment_containment']
    assert list(map(Q,r['physical_endpoint']))==[0,0]
    assert list(map(Q,r['continuous_position']))==[0,Q('.5')]
    assert '1/2' in r['candidate_extremum_times']
    assert not r['composed_future_containment']


def test_sampled_euler_endpoint_and_physical_held_force_endpoint_are_different_models():
    a=args();a.update(velocity=['0','0'],force=['1','1'],dt='.02',safe_position=['-1','1']);r=segment(**a)
    assert list(map(Q,r['physical_endpoint']))==[Q('.0002')]*2
    assert list(map(Q,r['semi_implicit_endpoint']))==[Q('.0004')]*2
    assert list(map(Q,r['same_held_acceleration_endpoint_defect']))==[Q('.0002')]*2


def test_exact_interval_extrema_enclose_scalar_time_sweeps():
    a=args();a.update(position=['-.01','.02'],velocity=['-1','2'],force=['-4','1'],mass=['.8','1.2'],disturbance='.1');r=segment(**a)
    low,high=map(Q,r['continuous_position'])
    for p,v,f,m,w in product(map(Q,a['position']),map(Q,a['velocity']),map(Q,a['force']),map(Q,a['mass']),(Q('-.1'),Q('.1'))):
        acc=(f+w)/m
        for n in range(41):
            t=Q(n,40);position=p+t*v+t*t*acc/2
            assert low<=position<=high


@pytest.mark.parametrize('velocity,force',[(['-2','-2'],['4','4']),(['1','1'],['0','0']),(['0','0'],['1','1']),(['0','0'],['0','0'])])
def test_minima_monotone_and_stationary_paths(velocity,force):
    a=args();a.update(velocity=velocity,force=force,safe_position=['-3','3']);r=segment(**a)
    assert r['status']=='CONDITIONAL_HELD_FORCE_SEGMENT' and r['continuous_segment_containment']
    assert not r['dispatch'] and not r['hardware_validation'] and not r['operational_authorization']


@pytest.mark.parametrize('key,value',[('dt','0'),('dt',True),('mass',['0','1']),('disturbance','-1'),('velocity',['1','0']),('force',[float('nan'),'1']),('dynamics_id','SEMI_IMPLICIT_WORLD_X_SI_V1')])
def test_unknown_or_wrong_model_never_becomes_contained(key,value):
    a=args();a[key]=value;r=segment(**a)
    assert not r['continuous_segment_containment'] and not r['composed_future_containment']
