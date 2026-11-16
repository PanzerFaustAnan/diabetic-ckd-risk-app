"""End-to-end tests through the real FastAPI app (validation, routes, response shapes)."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["model"].startswith("Logistic")


def test_model_info(client):
    j = client.get("/model-info").json()
    assert j["model_name"].startswith("Logistic") and len(j["cohort_score_quantiles"]) == 101
    assert set(j["contradictory"]) == {"htn", "walk"} and 0.7 < j["cv_metrics"]["auc"] < 0.8


def test_predict_examples(client, examples):
    hi = client.post("/predict", json=examples["high_risk_example"])
    lo = client.post("/predict", json=examples["low_risk_example"])
    assert hi.status_code == 200 and lo.status_code == 200
    h, low = hi.json(), lo.json()
    assert h["tier"] == "High" and low["tier"] == "Low" and h["score"] > low["score"]
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


def test_hardening(client, examples):
    ok = examples["median_profile"]
    # NaN / Infinity must be a clean 422, not a 500, and the submitted values are never echoed back
    for bad in ('{"bmi": NaN}', '{"bmi": Infinity}'):
        r = client.post("/predict", content=bad, headers={"content-type": "application/json"})
        assert r.status_code == 422 and "input" not in r.json()["detail"][0]
    # oversized bodies are refused before parsing
    big = '{"a":"' + "x" * 100_000 + '"}'
    assert client.post("/predict", content=big, headers={"content-type": "application/json"}).status_code == 413
    # security headers on the UI
    h = client.get("/").headers
    assert h["x-content-type-options"] == "nosniff" and "frame-ancestors 'none'" in h["content-security-policy"]
    assert client.post("/predict", json=ok).status_code == 200


def test_strict_types(client, examples):
    ok = examples["median_profile"]
    for bad in ({**ok, "sex": True}, {**ok, "age": "46"}, {**ok, "sex": "1"}):
        assert client.post("/predict", json=bad).status_code == 422


def test_whatif_duration_never_exceeds_age(client, examples):
    young = {**examples["median_profile"], "age": 20, "dy": 1}
    series = client.post("/sensitivity", json={"profile": young, "feature": "dy"}).json()["series"]
    assert max(pt["value"] for pt in series) <= 20
