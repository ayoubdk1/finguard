
# FinGuard — Machine Learning Evaluation

## 1. Objective

Evaluate machine learning models for detecting
potentially fraudulent simulated transactions.

## 2. Dataset

Total transactions: 1000
Normal: 899
Fraud: 101

Training: 700
Validation: 150
Testing: 150

Random seed: 42
Stratified splitting was used.

## 3. Features

- amount_cents
- transfers_last_10min
- account_age_minutes
- failed_transfers_last_hour

Target: is_fraud

## 4. Validation Model Comparison

| Model | Precision | Recall | F1 | AP |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.3529 | 0.8000 | 0.4898 | 0.6307 |
| Random Forest | 0.4762 | 0.6667 | 0.5556 | 0.7969 |
| Gradient Boosting | 0.5263 | 0.6667 | 0.5882 | 0.7980 |

Selected model: Gradient Boosting
Selection criterion: Highest validation AP.

## 5. Final Test Results

Model: Gradient Boosting
Test samples: 150

Precision: 61.11%
Recall: 73.33%
F1-score: 66.67%
Average Precision: 82.76%
Accuracy: 92.67%

## 6. Confusion Matrix

True Positives: 11
False Positives: 7
False Negatives: 4
True Negatives: 128

## 7. Interpretation

The selected model correctly detected 11 of
15 synthetically labeled fraudulent transactions.

Four fraud cases were missed, while seven normal
transactions were incorrectly classified as fraud.

## 8. Limitations

- Synthetic dataset only.
- Small test sample (150 transactions).
- Fraud labels are artificially generated.
- Results are not representative of real banks.
- No real-world deployment validation.
- Model performance may change with new data.

## 9. Next Steps

1. Save the trained model.
2. Add model prediction services.
3. Develop fraud assessment API.
4. Evaluate additional thresholds.
5. Compare ML decisions with rule-based scoring.

## References

https://scikit-learn.org/stable/modules/model_evaluation.html

https://scikit-learn.org/stable/common_pitfalls.html
