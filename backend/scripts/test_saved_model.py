
from pathlib import Path

import joblib
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_FILE = BASE_DIR / "models" / "fraud_gradient_boosting.joblib"

# Load our locally trained model
model = joblib.load(MODEL_FILE)

# Simulated transaction
transaction = pd.DataFrame([{
    "amount_cents": 150000,
    "transfers_last_10min": 4,
    "account_age_minutes": 60,
    "failed_transfers_last_hour": 3,
}])

prediction = model.predict(transaction)[0]
probability = model.predict_proba(transaction)[0][1]

print("Model loaded successfully!")
print("Prediction:", "FRAUD" if prediction == 1 else "NORMAL")
print("Fraud probability:", round(float(probability), 4))
