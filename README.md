# Diabetic CKD Risk Explorer

A research-prototype web app that ranks chronic-kidney-disease (CKD) risk for diabetic patients from 20 non-invasive
questionnaire features, explains the result, and shows general guideline-based health guidance.
Built end-to-end: data audit → model evaluation → FastAPI service → Docker → CI → cloud.

> **Not a medical device.** Trained on 400 patients from one hospital (BIRDEM, Dhaka). It ranks risk in a population like the study sample;
> it does not diagnose. See "Honest limitations".

## What the user sees
* A form for 20 answers (with a BMI helper), validated in the browser and again on the server.
* A **risk group** (lower / moderate / higher) with the *observed* CKD rate of study patients in that group, the percentile among the study patients, and two charts.
* **What shaped the score**: the six answers that moved it most (exact linear SHAP, shown as odds multipliers).
* **Model notes** that openly flag two features whose model direction contradicts clinical knowledge (regular walking, hypertension).
* **General health guidance** written from public diabetes/kidney guidelines (independent of the model; pending clinician review).
* A **what-if explorer** showing how the model's score reacts to changing one answer (labelled as model sensitivity, not advice).

## Architecture
```
 Browser (static/index.html + app.js)
     │  JSON over HTTP
     ▼
 FastAPI  app/main.py ──validates──► schemas.py (Pydantic)
     │                       │
     │                       ├─► model_service.py ─► artifacts/model.joblib  (scikit-learn Pipeline: scaler + logistic regression)
     │                       └─► guidance.py        (rule-based, guideline text)
     ▼
 /predict  /sensitivity  /model-info  /examples  /health  /docs
```

## Quick start (local)
```bash
python -m venv venv
source venv/bin/activate          # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q               # 22 tests should pass
uvicorn app.main:app --reload     # then open http://127.0.0.1:8000  (API docs: /docs)
```

## Docker
```bash
docker build -t ckd-risk-app .
docker run --rm -p 8080:8080 ckd-risk-app      # open http://localhost:8080
```

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/predict` | Score one patient: tier, observed tier rate, percentile, drivers, notes, guidance, warnings |
| POST | `/sensitivity` | Model score as one feature varies (what-if) |
| GET | `/model-info` | Metrics, limitations, tier cut-points, valid ranges |
| GET | `/examples` | Example patient payloads |
| GET | `/health` | Liveness probe |

Example: `curl -X POST localhost:8000/predict -H "Content-Type: application/json" -d @artifacts/example_requests.json` needs one profile; see `/docs` for the schema.

## Repository map
```
app/            main.py (routes) · schemas.py (validation) · model_service.py (model logic) · guidance.py (advice rules) · static/ (UI)
artifacts/      model.joblib · model_metadata.json · example_requests.json   (exported by notebook 02)
tests/          model, guidance and API tests (22)
notebooks/      01 data audit & EDA · 02 modelling, evaluation, explainability
docs/           LEARNING_GUIDE.md (read this) · STEP4_DEPLOY.md · deploy.yml.example
Dockerfile · .github/workflows/ci.yml · requirements*.txt
```

## Key design decisions
* **Honest evaluation:** nested, repeated, patient-level cross-validation; AUC ≈ 0.75 (95% CI 0.71–0.80), calibration slope 1.07. Earlier single-split numbers (0.91–0.95) were not reproducible.
* **Simple model:** regularised logistic regression; all model families were statistically tied, so the simplest won (one-standard-error rule).
* **Explanations without the SHAP library:** for a linear model, SHAP has a closed form; we compute it directly (tested for exact additivity), keeping the image small.
* **Two separate layers:** model output (descriptive) vs guideline advice (never derived from the model).
* **Version pinning:** `scikit-learn==1.7.2` matches the Colab training run; `/health` reports whether versions match.

## Honest limitations
Case-enriched sample (46% CKD) so scores are not population risks · single hospital, n = 400, diabetes medical book-reported lifestyle data ·
associations are not causal · training data are thin beyond ~15 years of diabetes · guidance text awaits clinician review.
