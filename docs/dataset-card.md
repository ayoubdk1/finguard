
# FinGuard — Synthetic Transaction Dataset

## 1. Overview

Dataset: synthetic_transactions.csv

Purpose: Fraud detection research and testing.

Total transactions: 1000
Normal transactions: 899 (89.9%)
Fraudulent transactions: 101 (10.1%)

## 2. Dataset Generation

Generator:
backend/scripts/generate_synthetic_transactions.py

Random seed: 42
Generation method: Python random module.

All transactions are simulated.
No real banking or customer information is used.

## 3. Features

| Feature | Description |
|---|---|
| transaction_id | Unique simulated ID |
| amount_cents | Amount stored as integer cents |
| transfers_last_10min | Recent transfer count |
| account_age_minutes | Account age in minutes |
| failed_transfers_last_hour | Recent failure count |
| is_fraud | Synthetic classification label |

## 4. Target Variable

is_fraud:
- 0 = Normal
- 1 = Fraudulent

The labels are generated synthetically.
They are not verified real-world fraud cases.

## 5. Intended Uses

- Testing rule-based fraud detection
- Training baseline classification models
- Comparing fraud detection algorithms
- Evaluating classification metrics

## 6. Limitations

- Synthetic data does not represent real banking traffic.
- The fraud rate is intentionally approximately 10%.
- Features are generated conditional on the fraud label.
- Generated patterns may be easier to learn than real fraud.
- There are no genuine customer behavior histories.
- Model performance cannot establish real-world accuracy.

## 7. Future Evaluation

Use separate training, validation, and test sets.

Suggested split:
- Training: 70%
- Validation: 15%
- Testing: 15%

Use stratification to preserve class proportions.

Evaluate precision, recall, F1-score, and PR-AUC.

