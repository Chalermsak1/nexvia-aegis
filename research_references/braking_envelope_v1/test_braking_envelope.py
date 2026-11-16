from fractions import Fraction as F
import pytest
from braking_envelope import evaluate


BASE = dict(approach_speed_upper_m_s=2., clearance_lower_m=10., total_delay_upper_s=1.,
            outward_acceleration_upper_m_s2=1., braking_deceleration_lower_m_s2=3.,
            opposing_disturbance_upper_m_s2=1.)


def calc(**changes):
    return evaluate(**(BASE | changes))


def test_exact_analytic_case():
    expected = F(2)*F(1)+F(1,2)*F(1)*F(1)**2+(F(2)+F(1)*F(1))**2/(2*(F(3)-F(1)))
    assert expected == F(19,4)
    r=calc()
    assert r.delay_travel_m == 2.5 and r.braking_travel_m == 2.25
    assert r.total_travel_bound_m == float(expected)
    assert r.speed_after_delay_bound_m_s == 3 and r.net_braking_m_s2 == 2


def test_zero_delay_reduces_to_braking_distance():
    r=calc(total_delay_upper_s=0)
    assert r.delay_travel_m == 0 and r.total_travel_bound_m == 1


def test_boundary_equality_is_bound_satisfaction_not_safety_claim():
    r=calc(clearance_lower_m=4.75)
    assert r.bound_satisfied is True and r.clearance_margin_m == 0
    assert r.classification == 'BOUND_SATISFIED_UNDER_ASSUMPTIONS'
    assert calc(clearance_lower_m=4.74).bound_satisfied is False


def test_stationary_no_acceleration_has_zero_travel():
    r=calc(approach_speed_upper_m_s=0,outward_acceleration_upper_m_s2=0,clearance_lower_m=0)
    assert r.total_travel_bound_m == 0 and r.bound_satisfied is True


def test_delay_monotonicity():
    distances=[calc(total_delay_upper_s=t).total_travel_bound_m for t in [0,.5,1,2]]
    assert all(a<b for a,b in zip(distances,distances[1:]))


def test_disturbance_monotonicity():
    distances=[calc(opposing_disturbance_upper_m_s2=d).total_travel_bound_m for d in [0,.5,1,2]]
    assert all(a<b for a,b in zip(distances,distances[1:]))


@pytest.mark.parametrize('braking,disturbance',[(0,0),(1,1),(1,2)])
def test_no_positive_net_braking_is_unsupported(braking,disturbance):
    r=calc(braking_deceleration_lower_m_s2=braking,opposing_disturbance_upper_m_s2=disturbance)
    assert r.classification=='UNSUPPORTED_NO_POSITIVE_NET_BRAKING'
    assert r.bound_satisfied is None and r.total_travel_bound_m is None


@pytest.mark.parametrize('field',list(BASE))
@pytest.mark.parametrize('value',[-1,True,None,float('nan'),float('inf'),float('-inf')])
def test_invalid_inputs_reject(field,value):
    with pytest.raises(ValueError):calc(**{field:value})


def test_finite_inputs_with_overflow_do_not_make_a_positive_claim():
    r=calc(approach_speed_upper_m_s=1e308,total_delay_upper_s=1e308)
    assert r.classification=='UNSUPPORTED_NUMERIC_RANGE'
    assert r.bound_satisfied is None and r.total_travel_bound_m is None


def test_positive_motion_underflow_is_not_zero_clearance_satisfaction():
    r=calc(approach_speed_upper_m_s=1e-200,total_delay_upper_s=0,clearance_lower_m=0)
    assert r.classification=='UNSUPPORTED_NUMERIC_RANGE' and r.bound_satisfied is None
