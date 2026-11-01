import numpy as np
import pytest
from aegis.env.sensors.sensor_corruption_suite import (
    CameraGlareModel,
    GlareConfig,
    AtmosphericSmokeFogModel,
    SmokeFogConfig,
    OnlineCovarianceEstimator,
)


def test_camera_glare_alignment():
    config = GlareConfig(
        glare_source_dir=np.array([1.0, 0.0, 0.0]),
        blooming_half_angle_rad=0.35,
        intensity=1.0,
    )
    glare = CameraGlareModel(config)

    # Looking straight into glare source (0 degrees)
    f_direct = glare.compute_glare_factor(np.array([1.0, 0.0, 0.0]))
    assert f_direct > 0.95

    # Looking orthogonal (90 degrees away)
    f_ortho = glare.compute_glare_factor(np.array([0.0, 1.0, 0.0]))
    assert f_ortho == 0.0


def test_camera_glare_corruption_and_dropout():
    config = GlareConfig(
        glare_source_dir=np.array([1.0, 0.0, 0.0]),
        dropout_probability=1.0, # Deterministic dropout when looking directly into glare
        noise_inflation_factor=5.0,
    )
    glare = CameraGlareModel(config)
    true_pos = np.array([2.0, 1.0, 0.5])

    # Direct glare -> total saturation blackout
    corrupted, sigma, is_dropped = glare.corrupt_measurement(
        true_pos, optical_axis=np.array([1.0, 0.0, 0.0]), nominal_sigma=0.05
    )
    assert is_dropped is True
    assert np.all(np.isnan(corrupted))
    assert sigma > 0.25

    # Away from glare -> clean measurement
    corrupted_clean, sigma_clean, is_dropped_clean = glare.corrupt_measurement(
        true_pos, optical_axis=np.array([0.0, 0.0, 1.0]), nominal_sigma=0.05
    )
    assert is_dropped_clean is False
    assert not np.any(np.isnan(corrupted_clean))
    assert np.isclose(sigma_clean, 0.05)


def test_atmospheric_smoke_fog_transmission():
    config = SmokeFogConfig(attenuation_coeff=0.20, max_penetration_range_m=10.0)
    fog = AtmosphericSmokeFogModel(config)

    t_0 = fog.transmission_factor(0.0)
    t_5 = fog.transmission_factor(5.0)
    t_10 = fog.transmission_factor(10.0)

    assert np.isclose(t_0, 1.0)
    assert 0.0 < t_10 < t_5 < t_0


def test_atmospheric_smoke_fog_range_corruption():
    config = SmokeFogConfig(attenuation_coeff=0.30, backscatter_intensity=0.0)
    fog = AtmosphericSmokeFogModel(config)
    rng = np.random.default_rng(42)

    # Moderate range: measurement preserved with inflated variance
    meas, sigma, is_phantom = fog.corrupt_range_measurement(4.0, nominal_sigma=0.05, rng=rng)
    assert not is_phantom
    assert np.isfinite(meas)
    assert sigma > 0.05


def test_online_covariance_estimator_tracking_and_blackout():
    estimator = OnlineCovarianceEstimator(
        window_size=10,
        nominal_sigma_p=0.05,
        nominal_sigma_v=0.08,
        blackout_sigma_thresh=0.25,
    )

    p_true = np.array([1.0, 0.0, 0.5])
    v_true = np.array([0.5, 0.0, 0.0])

    # 1. Feed nominal clean readings
    for _ in range(15):
        p_meas = p_true + np.random.normal(0, 0.02, size=3)
        v_meas = v_true + np.random.normal(0, 0.03, size=3)
        sig_p, sig_v, is_bo = estimator.update(p_true, p_meas, v_true, v_meas)
        assert not is_bo
        assert sig_p < 0.20

    # 2. Feed consecutive dropouts (e.g. glare / smoke sensor loss)
    blackout_detected = False
    for _ in range(5):
        sig_p, sig_v, is_bo = estimator.update(
            p_true, np.full(3, np.nan), v_true, np.full(3, np.nan), is_dropout=True
        )
        if is_bo:
            blackout_detected = True

    assert blackout_detected is True
    assert estimator.current_sigma_p > 0.25
