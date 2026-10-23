"""End-to-end tests through the real FastAPI app (validation, routes, response shapes)."""
import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["sklearn_version_matches_training"] is True


def test_model_info(client):
    j = client.get("/model-info").json()
    assert j["model_name"].startswith("Logistic") and len(j["cohort_score_quantiles"]) == 101
    assert set(j["contradictory"]) == {"htn", "walk"} and 0.7 < j["cv_metrics"]["auc"] < 0.8


def test_predict_examples(client, examples):
    hi = client.post("/predict", json=examples["high_risk_example"])
    lo = client.post("/predict", json=examples["low_risk_example"])
    assert hi.status_code == 200 and lo.status_code == 200
    h, l = hi.json(), lo.json()
    assert h["tier"] == "High" and l["tier"] == "Low" and h["score"] > l["score"]
    assert h["guidance"] and h["drivers"] and h["model_notes"] and h["disclaimer"]
    assert hi.headers["cache-control"] == "no-store"
    assert 0 <= h["percentile"] <= 100 and abs(h["tier_observed_ckd_rate"] - 0.729) < 0.01


def test_validation_rejects_bad_input(client, examples):
    ok = examples["median_profile"]
    for bad in ({**ok, "sex": 2}, {**ok, "bmi": 5}, {**ok, "age": "abc"}, {**ok, "cal": 100}, {**ok, "unknown": 1}):
        assert client.post("/predict", json=bad).status_code == 422
    missing = {k: v for k, v in ok.items() if k != "age"}
    assert client.post("/predict", json=missing).status_code == 422
    assert client.post("/predict", json={**ok, "dy": 60, "age": 50}).status_code == 422     # duration > age


def test_out_of_range_is_accepted_with_warning(client, examples):
    r = client.post("/predict", json={**examples["median_profile"], "dy": 40, "age": 70})
    assert r.status_code == 200 and any(w["code"] == "dy_out_of_range" for w in r.json()["warnings"])


def test_sensitivity(client, examples):
    r = client.post("/sensitivity", json={"profile": examples["median_profile"], "feature": "walk"})
    j = r.json()
    assert r.status_code == 200 and j["contradicts_expectation"] and len(j["series"]) == 2
    assert client.post("/sensitivity", json={"profile": examples["median_profile"], "feature": "nope"}).status_code == 422


def test_examples_and_ui(client):
    assert set(client.get("/examples").json()) == {"high_risk_example", "low_risk_example", "median_profile"}
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/docs").status_code == 200       # auto-generated interactive API docs
