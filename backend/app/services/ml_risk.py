
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_FILE = BASE_DIR / "models" / "fraud_gradient_boosting.joblib"

FEATURES = [
    "amount_cents",
    "transfers_last_10min",
    "account_age_minutes",
    "failed_transfers_last_hour",
]


@lru_cache(maxsize=1)
def load_fraud_model():
    if not MODEL_FILE.is_file():
        raise FileNotFoundError(
            f"Fraud model not found: {MODEL_FILE}"
        )

    return joblib.load(MODEL_FILE)


def predict_ml_risk(
    amount_cents: int,
    transfers_last_10min: int,
    account_age_minutes: int,
    failed_transfers_last_hour: int,
) -> dict:

    values = [
        amount_cents,
        transfers_last_10min,
        account_age_minutes,
        failed_transfers_last_hour,
    ]

    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Inputs must be non-negative integers")

    if amount_cents == 0:
        raise ValueError("Amount must be positive")

    transaction = pd.DataFrame(
        [values],
        columns=FEATURES
    )

    model = load_fraud_model()

    prediction = int(model.predict(transaction)[0])
    probability = float(
        model.predict_proba(transaction)[0][1]
    )

    return {
        "ml_prediction": "FRAUD" if prediction == 1 else "NORMAL",
        "fraud_probability": round(probability, 4),
        "model": "GradientBoostingClassifier",
    }
