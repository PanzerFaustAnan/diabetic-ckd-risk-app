"""Unit tests for the model logic (no web server involved)."""
import math

import numpy as np
import pytest

# GOLDEN VALUES: scores produced by the exported model.joblib with the pinned library versions. If a dependency upgrade or a
# re-export changes them, this test fails and forces a conscious decision ("regression test" / "golden-master test").
GOLDEN = {"high_risk_example": 0.9775, "low_risk_example": 0.0418, "median_profile": None}


def test_artifact_loads_and_matches_metadata(service):
    assert service.features == service.meta["features"]
    assert service.version_ok, "scikit-learn differs from the training version; see requirements.txt"


def test_golden_scores(service, examples):
    for name, expected in GOLDEN.items():
        if expected is not None:
            assert service.score(examples[name]) == pytest.approx(expected, abs=2e-3)


def test_scores_are_probabilities_and_ordered(service, examples):
    hi, lo, med = (service.score(examples[k]) for k in ("high_risk_example", "low_risk_example", "median_profile"))
    assert 0 < lo < med < hi < 1


def test_contributions_are_additive_in_log_odds(service, examples):
    """Closed-form linear SHAP must reproduce the model exactly: logit(p) = intercept + sum(phi)."""
    for ex in examples.values():
        phi = service.contributions(ex)
        p = service.score(ex)
        logit = math.log(p / (1 - p))
        assert logit == pytest.approx(service.intercept + phi.sum(), abs=1e-9)


def test_average_patient_has_zero_contributions(service):
    avg = dict(zip(service.features, service.mean))
    assert np.allclose(service.contributions(avg), 0)


def test_drivers_sorted_and_shares_sum_below_one(service, examples):
    d = service.drivers(examples["high_risk_example"], n=6)
    assert [x["share"] for x in d] == sorted((x["share"] for x in d), reverse=True)
    assert sum(x["share"] for x in d) <= 1 + 1e-9
    assert all((x["odds_multiplier"] > 1) == (x["direction"] == "raises") for x in d)


def test_tiers_and_percentile(service):
    c0, c1 = service.cuts
    assert service.tier(c0 - 1e-6) == "Low" and service.tier(c0) == "Medium" and service.tier(c1) == "High"
    assert service.percentile(0.0) == 0 and service.percentile(1.0) == 100
    assert service.percentile(0.5) < service.percentile(0.6)


def test_contradictory_features_detected(service):
    # the audit in notebook 02 found exactly these two
    assert set(service.contradictory) == {"htn", "walk"}
    assert len(service.model_notes()) == 2


def test_out_of_range_warnings(service, examples):
    p = dict(examples["median_profile"], dy=40.0, age=60.0)          # beyond the training maximum (32)
    codes = {w["code"] for w in service.warnings(p)}
    assert "dy_out_of_range" in codes
    p = dict(examples["median_profile"], dy=20.0)
    assert "dy_sparse" in {w["code"] for w in service.warnings(p)}
    assert service.warnings(examples["median_profile"]) == []


def test_sensitivity_shapes(service, examples):
    s = service.sensitivity(examples["median_profile"], "uti")
    assert [pt["value"] for pt in s["series"]] == [0, 1] and s["series"][1]["score"] > s["series"][0]["score"]
    s = service.sensitivity(examples["median_profile"], "bmi")
    assert len(s["series"]) == 8 and s["series"][-1]["score"] > s["series"][0]["score"]
    assert service.sensitivity(examples["median_profile"], "walk")["contradicts_expectation"] is True
    assert service.sensitivity(examples["median_profile"], "uti")["contradicts_expectation"] is False
