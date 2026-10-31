import numpy as np
import pytest
from scripts.research.navigation_force_candidate import navigation_force


def test_peak_scaling_preserves_direction_and_same_peak_limit():
    vector = np.array([4., 6., -1.])
    result = navigation_force(vector, method='DIRECTION_PRESERVING_PEAK')
    assert np.max(np.abs(result)) == 2.
    assert np.allclose(np.cross(result, vector), 0.)
    assert not np.allclose(np.cross(navigation_force(vector), vector), 0.)


@pytest.mark.parametrize('vector', [[0., 0., 0.], [.1, -.2, .3], [2., -2., 1.]])
def test_unsaturated_vectors_unchanged(vector):
    assert np.array_equal(navigation_force(vector, method='DIRECTION_PRESERVING_PEAK'), vector)


@pytest.mark.parametrize('vector', [[float('nan'), 0., 0.], [float('inf'), 0., 0.], [1., 2.]])
def test_bad_observation_rejected(vector):
    with pytest.raises(ValueError):
        navigation_force(vector)


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        navigation_force([0., 0., 0.], method='unsafe')
