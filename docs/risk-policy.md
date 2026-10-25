
# FinGuard — Fraud Risk Policy

## Objective
Detect potentially suspicious simulated financial
transactions using explainable risk rules.

## Risk score
Every transaction receives a score from 0 to 100.

## Initial detection rules

1. LARGE_AMOUNT
   Transfer >= 100000 cents: +30 points.

2. HIGH_VELOCITY
   3 or more transfers within 10 minutes:
   +35 points.

3. NEW_ACCOUNT
   Account created less than 24 hours ago:
   +20 points.

4. REPEATED_FAILURES
   3 or more failed transfers within 1 hour:
   +25 points.

Final score = min(100, sum of triggered points)

## Decisions

0-39: ALLOW
40-69: ALERT
70-89: REVIEW
90-100: SIMULATED_HOLD

## Important constraints
- Simulation only.
- All amounts use integer cents.
- Every alert includes reason codes.
- Risk evaluation must never break ledger integrity.
- Thresholds are initial assumptions for testing,
  not validated fraud detection thresholds.
