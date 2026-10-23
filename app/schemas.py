"""Request/response contracts of the API.

Why this file exists
--------------------
FastAPI uses these Pydantic models to (1) VALIDATE every incoming request, (2) generate the
interactive documentation at /docs, and (3) shape every response. A request that breaks a rule
never reaches the model: FastAPI answers 422 with a precise explanation instead.

Two layers of checking (an important design idea):
* HARD limits (here, in the schema): physically impossible or nonsensical values are rejected (HTTP 422).
* SOFT warnings (model_service.py): plausible values that lie outside the range the model was trained on are
  accepted, but the response carries a warning, because the model would be extrapolating.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

FEATURE_NAMES = Literal["sex", "job", "fam", "dy", "age", "bmi", "diet", "med", "ins", "htn", "hd",
                        "sleep", "water", "smoke", "zarda", "walk", "urin", "uti", "pk", "cal"]


class PatientInput(BaseModel):
    """The 20 non-invasive features. Names and codings are identical to the training notebooks."""
    model_config = ConfigDict(extra="forbid")      # a misspelt field name is an error, never silently ignored

    sex: int = Field(..., ge=0, le=1, description="1 = male, 0 = female")
    job: int = Field(..., ge=1, le=3, description="Physical exertion of work: 1 normal, 2 intermediate, 3 heavy")
    fam: int = Field(..., ge=0, le=1, description="Parents had diabetes (1/0)")
    dy: float = Field(..., ge=0, le=70, description="Years since diabetes diagnosis")
    age: float = Field(..., ge=15, le=110, description="Age in years")
    bmi: float = Field(..., ge=10, le=60, description="Body-mass index, kg/m2")
    diet: int = Field(..., ge=0, le=1, description="Follows the suggested diet (1/0)")
    med: int = Field(..., ge=0, le=1, description="Takes oral diabetes medicine (1/0)")
    ins: int = Field(..., ge=0, le=1, description="Takes insulin (1/0)")
    htn: int = Field(..., ge=0, le=1, description="Hypertension (1/0)")
    hd: int = Field(..., ge=0, le=1, description="Heart disease (1/0)")
    sleep: int = Field(..., ge=0, le=1, description="Sufficient sleep, 7-9 h (1/0)")
    water: int = Field(..., ge=0, le=1, description="Sufficient water, more than 2 L/day (1/0)")
    smoke: int = Field(..., ge=0, le=1, description="Smoker (1/0)")
    zarda: int = Field(..., ge=0, le=1, description="Zarda / betel leaf (1/0)")
    walk: int = Field(..., ge=0, le=1, description="Walks 30+ min/day regularly (1/0)")
    urin: int = Field(..., ge=0, le=1, description="Urinates properly, without discomfort (1/0)")
    uti: int = Field(..., ge=0, le=1, description="Urinary infection / urological issue (1/0)")
    pk: int = Field(..., ge=0, le=1, description="Regular pain-killer use (1/0)")
    cal: float = Field(..., ge=500, le=6000, description="Typical calorie intake, kcal/day")

    @model_validator(mode="after")
    def duration_cannot_exceed_age(self):
        # A cross-field rule: you cannot have had diabetes for longer than you have been alive.
        if self.dy > self.age:
            raise ValueError("Diabetes duration (dy) cannot exceed age")
        return self


class Driver(BaseModel):
    feature: str
    label: str
    value_text: str
    direction: Literal["raises", "lowers"]
    odds_multiplier: float = Field(description="exp(contribution): how much this factor multiplies the odds vs an average study patient")
    contribution: float = Field(description="Log-odds contribution relative to the average study patient (exact linear SHAP)")
    share: float = Field(description="Share of the total absolute contribution (0-1)")


class GuidanceItem(BaseModel):
    id: str
    topic: str
    title: str
    text: str
    priority: Literal["high", "normal"] = "normal"


class WarningItem(BaseModel):
    code: str
    message: str


class PredictionResponse(BaseModel):
    score: float = Field(description="Model probability (relative to the case-enriched study sample, NOT a population risk)")
    tier: Literal["Low", "Medium", "High"]
    tier_observed_ckd_rate: float = Field(description="Share of study patients in this tier who had a CKD diagnosis (out-of-fold)")
    percentile: float = Field(description="Percent of study patients with a lower score")
    cutpoints: list[float]
    drivers: list[Driver]
    model_notes: list[str]
    guidance: list[GuidanceItem]
    warnings: list[WarningItem]
    guidance_status: str
    guidance_sources: list[str]
    disclaimer: str


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: PatientInput
    feature: FEATURE_NAMES


class SensitivityPoint(BaseModel):
    value: float
    value_text: str
    score: float


class SensitivityResponse(BaseModel):
    feature: str
    label: str
    kind: str
    current: SensitivityPoint
    series: list[SensitivityPoint]
    contradicts_expectation: bool
    note: str
