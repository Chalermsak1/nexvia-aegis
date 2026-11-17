from copy import deepcopy
from fractions import Fraction as Q
import random
import pytest
from aegis.development.independent_clock_mapping import IndependentClockMap


def mapper(rate=None):return IndependentClockMap(local_epoch='L',remote_epoch='R',rate_bounds=rate or ['1','1'],max_extrapolation=100)
def exchange(name='x',l1=100,r2=1000,r3=1000,l4=200):
    return dict(id=name,local_epoch='L',remote_epoch='R',local_send=l1,remote_receive=r2,remote_send=r3,local_receive=l4)
def mapped(m,t=1000):return m.map_event(t,local_epoch='L',remote_epoch='R')


def test_asymmetric_transport_is_interval_not_exact_midpoint():
    m=mapper();m.add(exchange());r=mapped(m)
    assert r['local_interval']==['100','200'] and r['exact_integer_tick'] is False
    assert Q(r['local_interval'][0])<=101<=Q(r['local_interval'][1])
    assert not r['operational_authorization']


def test_zero_delay_exchange_can_produce_exact_point_mapping():
    m=mapper();m.add(exchange(l1=10,r2=100,r3=110,l4=20))
    r=mapped(m,105);assert r['local_interval']==['15','15'] and r['exact_integer_tick']


def test_exact_polygon_contains_independently_generated_affine_clocks_and_asymmetry():
    rng=random.Random(116)
    for trial in range(12):
        rate=Q(rng.randint(9995,10005),10000);offset=Q(-5000)
        m=mapper(['.999','1.001'])
        for i in range(3):
            r2=10000+i*30;r3=r2+rng.randint(1,5)
            receive=rate*r2+offset;send=rate*r3+offset
            l1=receive.numerator//receive.denominator-rng.randint(0,15)
            l4=-((-send.numerator)//send.denominator)+rng.randint(0,25)
            assert m.add(exchange(str(i),l1,r2,r3,l4))['status']=='CONDITIONAL_CLOCK_MAP_UPDATED'
        for t in range(10000,10100,7):
            lo,hi=map(Q,mapped(m,t)['local_interval']);assert lo<=rate*t+offset<=hi


def test_replayed_exchange_does_not_add_information_and_equivocation_latches():
    m=mapper();e=exchange();m.add(e);first=mapped(m)
    assert m.add(e)['status']=='REPLAY_IGNORED' and mapped(m)==first
    bad=deepcopy(e);bad['local_receive']=201
    assert m.add(bad)['status']=='CONTRADICTORY_CLOCK_EVIDENCE'
    assert mapped(m)['local_interval'] is None


def test_conflicting_independent_exchanges_are_not_averaged():
    m=mapper();m.add(exchange(l1=10,r2=100,r3=110,l4=20))
    assert m.add(exchange('y',30,100,110,40))['status']=='CONTRADICTORY_CLOCK_EVIDENCE'


def test_clock_epochs_and_extrapolation_limits_preserved():
    m=mapper();assert mapped(m)['status']=='UNKNOWN_CLOCK_MAPPING'
    m.add(exchange());assert mapped(m,1101)['status']=='EXTRAPOLATION_LIMIT'
    assert m.map_event(1000,local_epoch='new-L',remote_epoch='R')['status']=='CLOCK_EPOCH_REJECTED'
    e=exchange('y');e['remote_epoch']='new-R';assert m.add(e)['status']=='CLOCK_EPOCH_REJECTED'


@pytest.mark.parametrize('values',[(True,1000,1000,200),(-1,1000,1000,200),(201,1000,1000,200),(100,1001,1000,200)])
def test_invalid_timestamp_order_and_types_rejected(values):
    with pytest.raises(ValueError):mapper().add(exchange('x',*values))


@pytest.mark.parametrize('rate',[['0','1'],['2','1'],[True,'1'],['1e999999999','1']])
def test_rate_bounds_are_explicit_positive_and_resource_bounded(rate):
    with pytest.raises(ValueError):mapper(rate)


def test_no_silent_exchange_eviction():
    m=mapper()
    for i in range(64):m.add(exchange(str(i)))
    with pytest.raises(ValueError):m.add(exchange('65'))
    assert mapped(m)['status']=='CONDITIONAL_INTERVAL_MAPPING'
