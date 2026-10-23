"""FastAPI application: routes only. Model logic is in model_service.py, advice rules in guidance.py."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .guidance import SOURCES, STATUS, build_guidance
from .model_service import ModelService
from .schemas import PatientInput, PredictionResponse, SensitivityRequest, SensitivityResponse

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = Path(os.getenv("MODEL_DIR", ROOT / "artifacts"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger("ckd")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: load the model a single time and keep it in memory (loading per request would be slow)."""
    app.state.service = ModelService(ARTIFACT_DIR)
    app.state.examples = json.loads((ARTIFACT_DIR / "example_requests.json").read_text())
    log.info("Model loaded from %s", ARTIFACT_DIR)
    yield


app = FastAPI(
    title="Diabetic CKD Risk API",
    version="1.0.0",
    description="Research prototype. Ranks CKD risk for diabetic patients from 20 non-invasive features. "
                "NOT a diagnostic tool and NOT a medical device.",
    lifespan=lifespan,
)


@app.middleware("http")
async def no_store_for_api(request: Request, call_next):
    """Health data should never be cached by browsers or proxies."""
    response = await call_next(request)
    if request.url.path in ("/predict", "/sensitivity"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health", tags=["ops"])
def health(request: Request):
    """Liveness/readiness probe: cloud platforms call this to know the container is alive."""
    svc: ModelService = request.app.state.service
    return {"status": "ok", "model": svc.meta["model_name"], "sklearn_version_matches_training": svc.version_ok}


@app.get("/model-info", tags=["ops"])
def model_info(request: Request):
    """Metrics, limitations, tier cut-points and valid input ranges (the UI renders its 'about the model' panel from this)."""
    return request.app.state.service.info()


@app.get("/examples", tags=["ops"])
def examples(request: Request):
    return request.app.state.examples


@app.post("/predict", response_model=PredictionResponse, tags=["prediction"])
def predict(patient: PatientInput, request: Request):
    """Score one patient. Input is validated by PatientInput; invalid input never reaches the model (HTTP 422)."""
    svc: ModelService = request.app.state.service
    profile = patient.model_dump()
    result = svc.predict(profile)
    result["guidance"] = build_guidance(profile, result["tier"])
    result["guidance_status"] = STATUS
    result["guidance_sources"] = SOURCES
    return result


@app.post("/sensitivity", response_model=SensitivityResponse, tags=["prediction"])
def sensitivity(req: SensitivityRequest, request: Request):
    """What-if explorer: model score as ONE feature varies. Describes the model, not causal effects."""
    return request.app.state.service.sensitivity(req.profile.model_dump(), req.feature)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
