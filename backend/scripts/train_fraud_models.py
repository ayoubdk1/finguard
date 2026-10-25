from sklearn.metrics import confusion_matrix
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.utils.class_weight import compute_sample_weight
from pathlib import Path
import joblib
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    average_precision_score,
)

# 1. Load synthetic transactions
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = BASE_DIR / "data" / "synthetic_transactions.csv"

df = pd.read_csv(DATA_FILE)

# 2. Select features
features = [
    "amount_cents",
    "transfers_last_10min",
    "account_age_minutes",
    "failed_transfers_last_hour",
]

X = df[features]
y = df["is_fraud"]

# 3. Split: 70% training, 30% remaining
X_train, X_temp, y_train, y_temp = train_test_split(
    X,
    y,
    test_size=0.30,
    random_state=42,
    stratify=y,
)

# 4. Split remaining data: 15% validation, 15% test
X_val, X_test, y_val, y_test = train_test_split(
    X_temp,
    y_temp,
    test_size=0.50,
    random_state=42,
    stratify=y_temp,
)

print("Training:", len(X_train))
print("Validation:", len(X_val))
print("Testing:", len(X_test))

# 5. Create ML pipeline
model = make_pipeline(
    StandardScaler(),
    LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=42,
    ),
)

# 6. Train the model
model.fit(X_train, y_train)

# 7. Predict on validation data only
predictions = model.predict(X_val)
probabilities = model.predict_proba(X_val)[:, 1]

# 8. Evaluate performance
print("\nLogistic Regression Results")
print("---------------------------")

print(
    "Precision:",
    round(precision_score(y_val, predictions, zero_division=0), 4),
)
print(
    "Recall:",
    round(recall_score(y_val, predictions, zero_division=0), 4),
)
print(
    "F1-score:",
    round(f1_score(y_val, predictions, zero_division=0), 4),
)
print(
    "Average Precision (AP):",
    round(average_precision_score(y_val, probabilities), 4),
)


# 9. Create Random Forest model
rf_model = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

# 10. Train Random Forest
rf_model.fit(X_train, y_train)

# 11. Predict on validation data
rf_predictions = rf_model.predict(X_val)
rf_probabilities = rf_model.predict_proba(X_val)[:, 1]

# 12. Evaluate Random Forest
print("\nRandom Forest Results")
print("---------------------------")

print(
    "Precision:",
    round(precision_score(y_val, rf_predictions, zero_division=0), 4),
)

print(
    "Recall:",
    round(recall_score(y_val, rf_predictions, zero_division=0), 4),
)

print(
    "F1-score:",
    round(f1_score(y_val, rf_predictions, zero_division=0), 4),
)

print(
    "Average Precision (AP):",
    round(average_precision_score(y_val, rf_probabilities), 4),
)


# 13. Create Gradient Boosting model
gb_model = GradientBoostingClassifier(
    n_estimators=150,
    learning_rate=0.05,
    max_depth=3,
    random_state=42,
)

# 14. Balance the training classes
weights = compute_sample_weight(
    class_weight="balanced",
    y=y_train
)

# 15. Train Gradient Boosting
gb_model.fit(
    X_train,
    y_train,
    sample_weight=weights
)

# 16. Predict on validation data
gb_predictions = gb_model.predict(X_val)
gb_probabilities = gb_model.predict_proba(X_val)[:, 1]

# 17. Evaluate Gradient Boosting
print("\nGradient Boosting Results")
print("---------------------------")

print(
    "Precision:",
    round(precision_score(y_val, gb_predictions, zero_division=0), 4),
)

print(
    "Recall:",
    round(recall_score(y_val, gb_predictions, zero_division=0), 4),
)

print(
    "F1-score:",
    round(f1_score(y_val, gb_predictions, zero_division=0), 4),
)

print(
    "Average Precision (AP):",
    round(average_precision_score(y_val, gb_probabilities), 4),
)

print("\nAll 3 models trained successfully!")



# 18. Compare all three models

results = []

models = [
    ("Logistic Regression", predictions, probabilities),
    ("Random Forest", rf_predictions, rf_probabilities),
    ("Gradient Boosting", gb_predictions, gb_probabilities),
]

for name, pred, proba in models:
    results.append({
        "Model": name,
        "Precision": precision_score(
            y_val, pred, zero_division=0
        ),
        "Recall": recall_score(
            y_val, pred, zero_division=0
        ),
        "F1": f1_score(
            y_val, pred, zero_division=0
        ),
        "AP": average_precision_score(
            y_val, proba
        ),
    })

# 19. Create comparison table
comparison = pd.DataFrame(results)

comparison = comparison.sort_values(
    by="AP",
    ascending=False
)

print("\nMODEL COMPARISON")
print("---------------------------")

print(
    comparison.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}"
    )
)

# 20. Select best validation candidate
best_model = comparison.iloc[0]["Model"]

print("\nBest candidate by validation AP:", best_model)

# 21. Final evaluation on untouched test data

print("\nFINAL TEST EVALUATION")
print("---------------------------")

# Selected using validation AP
final_model = gb_model

# Predictions on unseen test data
test_predictions = final_model.predict(X_test)
test_probabilities = final_model.predict_proba(X_test)[:, 1]

# Calculate evaluation metrics
test_precision = precision_score(
    y_test, test_predictions, zero_division=0
)

test_recall = recall_score(
    y_test, test_predictions, zero_division=0
)

test_f1 = f1_score(
    y_test, test_predictions, zero_division=0
)

test_ap = average_precision_score(
    y_test, test_probabilities
)

# Confusion matrix
tn, fp, fn, tp = confusion_matrix(
    y_test, test_predictions, labels=[0, 1]
).ravel()

print("Model: Gradient Boosting")
print("Test samples:", len(X_test))

print("Precision:", round(test_precision, 4))
print("Recall:", round(test_recall, 4))
print("F1-score:", round(test_f1, 4))
print("Average Precision:", round(test_ap, 4))

print("\nConfusion Matrix")
print("True Positives:", tp)
print("False Positives:", fp)
print("False Negatives:", fn)
print("True Negatives:", tn)

print("\nFinal evaluation completed!")


# 22. Save the selected fraud detection model

MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILE = MODEL_DIR / "fraud_gradient_boosting.joblib"

joblib.dump(final_model, MODEL_FILE)

print("\nModel saved successfully!")
print("Location:", MODEL_FILE)
