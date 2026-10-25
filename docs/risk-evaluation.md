# FinGuard — Fraud Risk Evaluation Report

## 1. Overview

This report evaluates FinGuard's initial rule-based fraud detection engine using 1,000 synthetic financial transactions.

The objective is to establish a baseline before implementing machine learning models.

## 2. Dataset

- Total transactions: 1,000
- Normal transactions: 899 (89.9%)
- Fraudulent transactions: 101 (10.1%)
- Random seed: 42
- Dataset: `backend/data/synthetic_transactions.csv`
- Scored dataset: `backend/data/scored_transactions.csv`

## 3. Risk Classification Results

| Decision | Transactions | Percentage |
|---|---:|---:|
| ALLOW | 816 | 81.6% |
| ALERT | 149 | 14.9% |
| REVIEW | 2 | 0.2% |
| SIMULATED_HOLD | 33 | 3.3% |
| **Total** | **1,000** | **100%** |

A total of 184 transactions (18.4%) were flagged as potentially suspicious.

## 4. Confusion Matrix

For binary evaluation, ALERT, REVIEW, and SIMULATED_HOLD are considered positive fraud predictions.

| Actual / Predicted | Normal | Fraud |
|---|---:|---:|
| Normal | 771 | 128 |
| Fraud | 45 | 56 |

- True Positives: 56
- False Positives: 128
- False Negatives: 45
- True Negatives: 771

## 5. Evaluation Metrics

| Metric | Value |
|---|---:|
| Precision | 30.43% |
| Recall | 55.45% |
| F1-score | 39.30% |
| False Positive Rate | 14.24% |
| Accuracy | 82.70% |

## 6. Interpretation

The initial engine successfully detected 56 out of 101 synthetically labeled fraudulent transactions.

However, it missed 45 fraud cases and incorrectly flagged 128 normal transactions.

The current engine therefore has considerable room for improvement.

Accuracy alone is insufficient because the dataset contains many more normal transactions than fraudulent transactions.

## 7. Limitations

- Fraud labels are synthetic, not verified real-world cases.
- Fraud patterns were artificially generated.
- Risk thresholds have not been optimized on independent validation data.
- Results cannot be generalized to real financial transactions.
- The current engine does not use machine learning.

## 8. Next Steps

- Evaluate alternative detection thresholds.
- Develop baseline machine learning classifiers.
- Use stratified training, validation, and test splits.
- Compare precision, recall, F1-score, and PR-AUC.
- Reduce false positives without significantly increasing missed fraud cases.

## 9. Reference

Scikit-learn — Classification Metrics

https://scikit-learn.org/stable/modules/model_evaluation.html#classification-metrics