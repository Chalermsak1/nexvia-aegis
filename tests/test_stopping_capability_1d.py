from fractions import Fraction as Q
from itertools import product
import pytest
from aegis.development.stopping_capability_1d import analyze,segment


def args():return dict(position=['0','0'],velocity=['.3','.3'],mass=['1','1'],adverse_force_max='0',brake_force_min='1',delay_seconds='.08',ramp_rate_min='100',sample_seconds='.02',horizon_seconds='5',safe_position=['-.5','.32'])


def test_exact_delay_then_held_force_stop_and_no_post_stop_claim():
    r=analyze(**args());expected=Q('.3')*Q('.10')+Q('.3')**2/2
    assert r['stop_observed_in_bound'] and Q(r['stop_position_upper'])==expected
    assert Q(r['stop_time_upper_seconds'])==Q('.4')
    assert r['first_stop_prefix_contained'] and r['full_trajectory_containment'] is None
    assert r['post_stop_containment']=='UNRESOLVED_REST_CONTROL_REQUIRED'


@pytest.mark.parametrize('force',['0','.01'])
def test_absent_or_insufficient_brake_does_not_gain_stopping_claim(force):
    a=args();a.update(brake_force_min=force,adverse_force_max='.01',horizon_seconds='.1');r=analyze(**a)
    assert r['finite_trace_contained'] and not r['stop_observed_in_bound']
    assert r['stopping_capability']=='NO_WORST_CASE_STOPPING_CAPABILITY' and r['first_stop_prefix_contained'] is None


def test_exact_boundary_and_just_outside_remain_distinct():
    r=analyze(**args());stop=Q(r['stop_position_upper'])
    a=args();a['safe_position']=['-.5',str(stop)];assert analyze(**a)['first_stop_prefix_contained']
    a['safe_position']=['-.5',str(stop-Q(1,10**12))];assert not analyze(**a)['first_stop_prefix_contained']


def test_slow_ramp_and_later_engagement_increase_stop_bound():
    base=args();fast=analyze(**base);slow=analyze(**dict(base,ramp_rate_min='1'));late=analyze(**dict(base,delay_seconds='.3'))
    assert Q(slow['stop_position_upper'])>Q(fast['stop_position_upper'])
    assert Q(late['stop_position_upper'])>Q(fast['stop_position_upper'])


def test_uncertain_mass_bound_contains_independent_scalar_trajectories():
    a=args();a.update(mass=['.9','1.1'],adverse_force_max='.01',ramp_rate_min='4');r=analyze(**a);upper=Q(r['stop_position_upper'])
    for mass,w in product((Q('.9'),Q(1),Q('1.1')),(Q(0),Q('.01'))):
        p=Q(0);v=Q('.3')
        for row in r['segments']:
            dt=Q(row['duration_seconds']);force=Q(row['brake_force_lower']);acc=(w-force)/mass
            if acc<0 and v+acc*dt<=0:dt=-v/acc
            z=segment(p,v,acc,dt);p,v=z['position'],z['velocity'];assert z['maximum']<=upper
            if v==0:break
        assert v==0 and p<=upper


def test_oversized_delay_is_horizon_incomplete_not_success():
    a=args();a.update(delay_seconds='10',horizon_seconds='.1');r=analyze(**a)
    assert r['stopping_capability']=='HORIZON_INCOMPLETE' and r['stop_time_upper_seconds'] is None


def test_intersample_excursion_is_present_even_with_safe_endpoints():
    r=segment(Q('.31998'),Q('.02'),Q(-2),Q('.02'))
    assert r['position']<=Q('.32') and r['maximum']>Q('.32')


@pytest.mark.parametrize('key,value',[('mass',['0','1']),('velocity',['-.1','.3']),('ramp_rate_min','-1'),('sample_seconds','0'),('horizon_seconds','1000')])
def test_unsupported_model_inputs_are_rejected(key,value):
    a=args();a[key]=value
    with pytest.raises(ValueError):analyze(**a)


def test_time_varying_mass_and_finer_ramp_remain_below_conservative_stop_bound():
    a=args();a.update(mass=['.9','1.1'],adverse_force_max='.01',ramp_rate_min='1');r=analyze(**a)
    h=Q('.0025');p=Q(0);v=Q('.3');t=Q(0);trace=[]
    for n in range(2000):
        m=Q('.9') if n%2 else Q('1.1');w=Q('.01') if n%3 else Q(0)
        force=min(Q(1),max(Q(0),t-Q('.08')));acc=(w-force)/m;duration=h
        if acc<0 and v+acc*h<=0:duration=-v/acc
        z=segment(p,v,acc,duration);trace.append(dict(t=str(t),p=str(p),v=str(v),m=str(m),w=str(w),force=str(force),maximum=str(z['maximum'])))
        assert z['maximum']<=Q(r['stop_position_upper'])
        p,v=z['position'],z['velocity'];t+=duration
        if v==0:break
    assert v==0 and t<=Q(r['stop_time_upper_seconds'])
