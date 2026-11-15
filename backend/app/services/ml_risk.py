import hashlib
import json
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

MODEL_FILE = Path(__file__).resolve().parents[2] / "models" / "fraud_gradient_boosting.joblib"
META_FILE = Path(__file__).resolve().parents[2] / "models" / "fraud_gradient_boosting.meta.json"
FEATURES = ["amount_cents", "transfers_last_10min", "account_age_minutes", "failed_transfers_last_hour"]


@lru_cache(maxsize=1)
def load_model_metadata() -> dict:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


@lru_cache(maxsize=1)
def load_fraud_model():
    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"Saved fraud model not found: {MODEL_FILE}")
    expected_sha = load_model_metadata().get("model_sha256")
    if expected_sha:
        if hashlib.sha256(MODEL_FILE.read_bytes()).hexdigest() != expected_sha:
            raise ValueError("Fraud model SHA-256 verification failed")
    return joblib.load(MODEL_FILE)


def is_fraud_model_ready() -> bool:
    try:
        load_fraud_model()
        return True
    except Exception:
        return False


def predict_ml_risk(amount_cents: int, transfers_last_10min: int, account_age_minutes: int, failed_transfers_last_hour: int) -> dict:
    meta = load_model_metadata()
    model_version = meta.get("version", "unversioned")
    try:
        model = load_fraud_model()
        row = pd.DataFrame([{"amount_cents": amount_cents, "transfers_last_10min": transfers_last_10min, "account_age_minutes": account_age_minutes, "failed_transfers_last_hour": failed_transfers_last_hour}])
        pred = int(model.predict(row)[0])
        prob = float(model.predict_proba(row)[0][1])
        imp = getattr(model, "feature_importances_", None)
        contributions = {f: round(float(v), 4) for f, v in zip(FEATURES, imp)} if imp is not None and len(imp) == len(FEATURES) else {}
        return {"ml_available": True, "model_version": model_version, "ml_prediction": "FRAUD" if pred == 1 else "NORMAL", "ml_probability": round(prob, 4), "fraud_probability": round(prob, 4), "feature_contributions": contributions}
    except Exception as exc:
        return {"ml_available": False, "model_version": model_version, "ml_prediction": "UNAVAILABLE", "ml_probability": None, "fraud_probability": None, "feature_contributions": {}, "fallback_reason": str(exc)}
