import math
import pytest
from aegis.development.passive_motion_reference import passive_path_reference


def reference(**kw):
    params = dict(speed_upper_m_s=.5, delay_upper_seconds=.06, mass_kg=1., damping_lower_kg_s=2., persistent_force_upper_n=0., available=True)
    params.update(kw); return passive_path_reference(**params)


def test_analytic_coast_plus_exponential_tail():
    r = reference()
    assert r['additional_path_upper_m'] == pytest.approx(.28)
    assert r['finite_time_rest_claim'] is False


def test_discrete_implicit_euler_trajectory_never_exceeds_tail_bound():
    v, dt, traveled = .5, .02, .5 * .06
    bound = reference()['additional_path_upper_m']
    for _ in range(500):
        v /= 1. + 2. * dt
        traveled += v * dt
        assert traveled <= bound + 1e-14
    assert traveled == pytest.approx(bound, abs=1e-8)
    assert v > 0  # Finite-time exact rest is not implied.


@pytest.mark.parametrize('force', [math.nextafter(0., 1.), 1e-6, 1.])
def test_any_persistent_disturbance_allowance_makes_infinite_travel_unsupported(force):
    r = reference(persistent_force_upper_n=force)
    assert r['classification'] == 'UNSUPPORTED_PERSISTENT_DISTURBANCE'
    assert r['additional_path_upper_m'] is None


@pytest.mark.parametrize('kwargs', [dict(available=False), dict(damping_lower_kg_s=0.)])
def test_unavailable_damper_returns_no_bound(kwargs):
    assert reference(**kwargs)['additional_path_upper_m'] is None


@pytest.mark.parametrize('kwargs', [dict(speed_upper_m_s=None), dict(speed_upper_m_s=True), dict(delay_upper_seconds=-1.), dict(mass_kg=0.), dict(damping_lower_kg_s=float('nan')), dict(available=1), dict(persistent_force_upper_n=-1.)])
def test_invalid_inputs(kwargs):
    with pytest.raises(ValueError): reference(**kwargs)


def test_numeric_range_and_monotonicity():
    assert reference(speed_upper_m_s=1e308, mass_kg=1e308)['classification'] == 'UNSUPPORTED_NUMERIC_RANGE'
    base = reference()['additional_path_upper_m']
    assert reference(delay_upper_seconds=.1)['additional_path_upper_m'] > base
    assert reference(mass_kg=2.)['additional_path_upper_m'] > base
    assert reference(damping_lower_kg_s=1.)['additional_path_upper_m'] > base
    assert reference(speed_upper_m_s=0.)['additional_path_upper_m'] == 0.
