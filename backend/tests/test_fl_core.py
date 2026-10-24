"""Unit tests for the federated-learning maths (no database or HTTP involved)."""
import numpy as np

from app import fl_core


def test_federated_average_weights_clinics_by_sample_count():
    d1, d2 = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    result = fl_core.federated_average([d1, d2], [3, 1])
    assert np.allclose(result, [0.75, 0.25])


def test_outlier_delta_is_clipped_to_three_times_the_median_norm():
    deltas = [np.array([1.0, 0.0]), np.array([1.0, 0.0]), np.array([100.0, 0.0])]
    clipped = fl_core.clip_outlier_deltas(deltas)
    assert np.allclose(clipped[0], [1.0, 0.0])
    assert np.allclose(clipped[1], [1.0, 0.0])
    assert np.allclose(clipped[2], [3.0, 0.0])  # a poisoned update can't dominate the average


def test_dp_noise_disabled_leaves_delta_untouched():
    d = np.array([0.5, -0.2, 0.1])
    assert np.array_equal(fl_core.add_dp_noise(d, epsilon=None), d)


def test_dp_noise_enabled_perturbs_delta_without_changing_shape():
    np.random.seed(0)
    d = np.zeros(9)
    noisy = fl_core.add_dp_noise(d, epsilon=2.0)
    assert noisy.shape == d.shape
    assert not np.array_equal(noisy, d)


def test_untrained_model_is_a_coin_flip_with_no_feature_contributions():
    weights = fl_core.blank_weights()
    values = dict(age=45, bmi=26, resting_hr=75, fever_days=2, cough_severity=1,
                  fatigue_score=4, existing_condition=0, bp_systolic=120)
    prob, ranked = fl_core.predict_single(weights, fl_core.REFERENCE_MEAN, fl_core.REFERENCE_STD, values)
    assert prob == 0.5
    assert all(contribution == 0 for _, _, contribution in ranked)


def test_prediction_explanation_names_the_feature_that_drove_it():
    weights = fl_core.blank_weights()
    weights[fl_core.FEATURES.index("fever_days")] = 1.0   # model has learned: fever raises risk
    values = dict(age=45, bmi=26, resting_hr=75, fever_days=5, cough_severity=1,
                  fatigue_score=4, existing_condition=0, bp_systolic=120)
    prob, ranked = fl_core.predict_single(weights, fl_core.REFERENCE_MEAN, fl_core.REFERENCE_STD, values)
    top_feature, _, top_contribution = ranked[0]
    assert top_feature == "fever_days"
    assert top_contribution > 0
    assert prob > 0.8


def test_sigmoid_stays_in_unit_interval_even_for_extreme_inputs():
    for z in (-1e6, -5, 0, 5, 1e6):
        assert 0.0 <= fl_core.sigmoid(z) <= 1.0
