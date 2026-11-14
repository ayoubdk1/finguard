import json
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

MODEL_FILE = Path(__file__).resolve().parents[2] / "models" / "fraud_gradient_boosting.joblib"
META_FILE = Path(__file__).resolve().parents[2] / "models" / "fraud_gradient_boosting.meta.json"

FEATURES = [
    "amount_cents",
    "transfers_last_10min",
    "account_age_minutes",
    "failed_transfers_last_hour",
]


@lru_cache(maxsize=1)
def load_fraud_model():
    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"Saved fraud model not found: {MODEL_FILE}")
    return joblib.load(MODEL_FILE)


@lru_cache(maxsize=1)
def load_model_metadata() -> dict:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def predict_ml_risk(
    amount_cents: int,
    transfers_last_10min: int,
    account_age_minutes: int,
    failed_transfers_last_hour: int,
) -> dict:
    meta = load_model_metadata()
    model_version = meta.get("version", "unversioned")

    try:
        model = load_fraud_model()
        row = pd.DataFrame(
            [
                {
                    "amount_cents": amount_cents,
                    "transfers_last_10min": transfers_last_10min,
                    "account_age_minutes": account_age_minutes,
                    "failed_transfers_last_hour": failed_transfers_last_hour,
                }
            ]
        )
        pred = int(model.predict(row)[0])
        prob = float(model.predict_proba(row)[0][1])

        contributions: dict[str, float] = {}
        importances = getattr(model, "feature_importances_", None)
        if importances is not None and len(importances) == len(FEATURES):
            contributions = {
                feat: round(float(imp), 4)
                for feat, imp in zip(FEATURES, importances)
            }

        return {
            "ml_available": True,
            "model_version": model_version,
            "ml_prediction": "FRAUD" if pred == 1 else "NORMAL",
            "ml_probability": round(prob, 4),
        "fraud_probability": round(prob, 4),
            "feature_contributions": contributions,
        }
    except (FileNotFoundError, ImportError, OSError, Exception) as exc:
        return {
            "ml_available": False,
            "model_version": model_version,
            "ml_prediction": "UNAVAILABLE",
            "ml_probability": None,
            "fraud_probability": None,
            "feature_contributions": {},
            "fallback_reason": str(exc),
        }
