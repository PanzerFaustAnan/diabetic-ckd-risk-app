"""Everything that touches the trained model lives here, with no web code.

Keeping model logic separate from web code ("separation of concerns") means we can test it without starting a server,
and swap the web framework later without touching the maths.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

log = logging.getLogger("ckd")

DISCLAIMER = ("Research prototype built on 400 diabetic patients from one hospital. It ranks risk in a population like the study "
              "sample; it is not a diagnosis and not a medical device. Talk to a doctor about any health concern.")

JOB_TEXT = {1: "Normal (desk-type work)", 2: "Intermediate", 3: "Heavy (physically demanding)"}
# value grids for the what-if explorer (continuous features only; binary/ordinal use their own levels)
GRID = {"age": (20, 75), "dy": (0, 30), "bmi": (15, 40), "cal": (1000, 2400)}
# duration beyond which the training data is thin (70 of 400 patients had > 10 years at window start; 32 had > 15)
SPARSE_DY = 15


class ModelService:
    def __init__(self, artifact_dir: str | Path):
        self.dir = Path(artifact_dir)
        self.meta: dict = json.loads((self.dir / "model_metadata.json").read_text())
        self.model = joblib.load(self.dir / "model.joblib")
        self._validate_artifact()

        self.features: list[str] = self.meta["features"]
        self.fmeta: dict = self.meta["feature_meta"]
        scaler: StandardScaler = self.model.named_steps["sc"]
        lr: LogisticRegression = self.model.named_steps["m"]
        self.mean = scaler.mean_.astype(float)
        self.scale = scaler.scale_.astype(float)
        self.coef = lr.coef_[0].astype(float)
        self.intercept = float(lr.intercept_[0])
        self.cuts = self.meta["risk_tiers"]["cutpoints"]
        self.tier_rates = self.meta["risk_tiers"]["observed_ckd_rate"]
        self.quantiles = np.asarray(self.meta["cohort_score_quantiles"], dtype=float)   # 101 points: 0th..100th percentile
        # features whose model direction contradicts clinical expectation (and is not negligible: |coef| >= 0.1 per SD)
        self.contradictory = [
            f for f, c in zip(self.features, self.coef)
            if self.fmeta[f]["expected_direction"] != 0 and np.sign(c) != self.fmeta[f]["expected_direction"] and abs(c) >= 0.1
        ]
        self.version_ok = sklearn.__version__ == self.meta["versions"]["sklearn"]
        if not self.version_ok:
            log.warning("scikit-learn %s differs from training version %s: results may differ or loading may fail",
                        sklearn.__version__, self.meta["versions"]["sklearn"])

    # ------------------------------------------------------------------ safety checks
    def _validate_artifact(self) -> None:
        """Fail loudly at startup (not silently at the first request) if the artifact is not what the code expects."""
        if not isinstance(self.model, Pipeline) or list(self.model.named_steps) != ["sc", "m"]:
            raise RuntimeError("Expected Pipeline(StandardScaler 'sc', LogisticRegression 'm'); the exported model differs. "
                               "The closed-form explanation in this service only works for that structure.")
        if list(self.model.feature_names_in_) != self.meta["features"]:
            raise RuntimeError("Feature order in model and metadata disagree")

    # ------------------------------------------------------------------ core
    def _frame(self, profile: dict) -> pd.DataFrame:
        return pd.DataFrame([{f: float(profile[f]) for f in self.features}])[self.features]

    def score(self, profile: dict) -> float:
        return float(self.model.predict_proba(self._frame(profile))[0, 1])

    def tier(self, p: float) -> str:
        return "Low" if p < self.cuts[0] else ("Medium" if p < self.cuts[1] else "High")

    def percentile(self, p: float) -> float:
        return float(np.interp(p, self.quantiles, np.linspace(0, 100, 101)))

    # ------------------------------------------------------------------ explanation (closed-form linear SHAP)
    def contributions(self, profile: dict) -> np.ndarray:
        """Exact SHAP values in log-odds for a linear model with independent features:
              phi_j = coef_j * (x_j - mean_j) / scale_j
        and  logit(p) = intercept + sum_j phi_j   (additivity; verified in the tests).
        The 'average patient' is the training mean. No SHAP library needed, which keeps the Docker image small."""
        x = np.array([float(profile[f]) for f in self.features])
        return self.coef * (x - self.mean) / self.scale

    def value_text(self, f: str, v: float) -> str:
        kind = self.fmeta[f]["kind"]
        if f == "sex":
            return "Male" if v >= 0.5 else "Female"
        if f == "job":
            return JOB_TEXT[int(round(v))]
        if kind == "bin":
            return "Yes" if v >= 0.5 else "No"
        return f"{v:g}"

    def drivers(self, profile: dict, n: int = 6) -> list[dict]:
        phi = self.contributions(profile)
        total = float(np.abs(phi).sum()) or 1.0
        order = np.argsort(-np.abs(phi))[:n]
        out = []
        for i in order:
            f = self.features[i]
            out.append(dict(feature=f, label=self.fmeta[f]["label"], value_text=self.value_text(f, float(profile[f])),
                            direction="raises" if phi[i] > 0 else "lowers", odds_multiplier=float(np.exp(phi[i])),
                            contribution=float(phi[i]), share=float(abs(phi[i]) / total)))
        return out

    def model_notes(self) -> list[str]:
        notes = []
        for f in self.contradictory:
            lab = self.fmeta[f]["label"]
            exp = "lower" if self.fmeta[f]["expected_direction"] < 0 else "higher"
            notes.append(f"'{lab}': in the study data this was linked to a {'higher' if exp == 'lower' else 'lower'} score, the opposite of what "
                         f"clinical knowledge predicts (likely reverse causation, selection or measurement effects). Do not change "
                         f"treatment or habits because of this pattern.")
        return notes

    # ------------------------------------------------------------------ soft warnings (out-of-distribution)
    def warnings(self, profile: dict) -> list[dict]:
        w = []
        for f in ("age", "dy", "bmi", "cal"):
            lo, hi = self.fmeta[f]["min"], self.fmeta[f]["max"]
            v = float(profile[f])
            if v < lo or v > hi:
                w.append(dict(code=f"{f}_out_of_range", message=f"{self.fmeta[f]['label']} = {v:g} is outside the range seen in the study "
                                                                  f"({lo:g}-{hi:g}); the estimate is an extrapolation."))
        if SPARSE_DY < float(profile["dy"]) <= self.fmeta["dy"]["max"]:
            w.append(dict(code="dy_sparse", message=f"Only 32 of 400 study patients had more than {SPARSE_DY} years of diabetes at the start of "
                                                    "their observation window, so estimates for long durations are less reliable."))
        return w

    # ------------------------------------------------------------------ what-if
    def sensitivity(self, profile: dict, feature: str) -> dict:
        kind = self.fmeta[feature]["kind"]
        if feature == "job":
            values = [1, 2, 3]
        elif kind == "bin":
            values = [0, 1]
        else:
            lo, hi = GRID[feature]
            values = list(np.linspace(lo, hi, 8))
            if feature in ("age", "dy", "cal"):
                values = [float(round(v)) for v in values]
            else:
                values = [float(round(v, 1)) for v in values]
        series = [dict(value=float(v), value_text=self.value_text(feature, float(v)), score=self.score({**profile, feature: v})) for v in values]
        cur = float(profile[feature])
        contradicts = feature in self.contradictory
        note = ("This shows how the MODEL reacts to a change, not what would happen to a real person."
                + (" For this feature the model's direction is the opposite of clinical expectation, so this curve must not be read as advice." if contradicts else ""))
        return dict(feature=feature, label=self.fmeta[feature]["label"], kind=kind,
                    current=dict(value=cur, value_text=self.value_text(feature, cur), score=self.score(profile)),
                    series=series, contradicts_expectation=contradicts, note=note)

    # ------------------------------------------------------------------ one call that does everything the UI needs
    def predict(self, profile: dict) -> dict:
        p = self.score(profile)
        tier = self.tier(p)
        return dict(score=p, tier=tier, tier_observed_ckd_rate=float(self.tier_rates[tier]), percentile=self.percentile(p),
                    cutpoints=list(self.cuts), drivers=self.drivers(profile), model_notes=self.model_notes(),
                    warnings=self.warnings(profile), disclaimer=DISCLAIMER)

    def info(self) -> dict:
        m = self.meta
        return dict(model_name=m["model_name"], target=m["target"], cohort=m["cohort"], cv_protocol=m["cv_protocol"], cv_metrics=m["cv_metrics"],
                    cv_auc_ci95=m["cv_auc_ci95_pooled_oof"], calibration=m["calibration"], risk_tiers=m["risk_tiers"],
                    limitations=m["limitations"], versions=m["versions"], runtime_sklearn=sklearn.__version__, version_ok=self.version_ok,
                    features={f: dict(label=v["label"], kind=v["kind"], min=v["min"], max=v["max"]) for f, v in self.fmeta.items()},
                    contradictory=self.contradictory,
                    cohort_score_quantiles=m["cohort_score_quantiles"])
