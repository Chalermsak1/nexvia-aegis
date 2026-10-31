import math
import pytest
from scripts.research.dual_gate_noise_diagnostic import stationary_vector_probability, probability_run_within_horizon, run_diagnostic


def test_small_bernoulli_cases():
    assert probability_run_within_horizon(0.5, 1, 2) == pytest.approx(0.75)
    assert probability_run_within_horizon(0.5, 2, 3) == pytest.approx(0.375)
    assert probability_run_within_horizon(0.5, 4, 3) == pytest.approx(0)
    assert probability_run_within_horizon(1.0, 3, 4) == pytest.approx(1)
    assert probability_run_within_horizon(0, 1, 8) == pytest.approx(0)


def test_toy_model_values_and_dropouts():
    result = run_diagnostic(.05, .02, 20, 220, 0)
    assert result["single_source_probability"] == pytest.approx(.899939, abs=1e-6)
    assert result["one_fixed_window_probability"] == pytest.approx(.014744, abs=1e-5)
    assert result["at_least_one_run_in_horizon"] == pytest.approx(.4564, abs=1e-3)
    assert run_diagnostic(.05, .02, 20, 220, .1)["at_least_one_run_in_horizon"] < result["at_least_one_run_in_horizon"]


@pytest.mark.parametrize("prob", [-1., 2., math.nan])
def test_invalid_probability(prob):
    with pytest.raises(ValueError): probability_run_within_horizon(prob, 2, 10)


def test_invalid_model_parameters():
    with pytest.raises(ValueError): stationary_vector_probability(.05, 0)
    with pytest.raises(ValueError): probability_run_within_horizon(.5, 0, 1)
