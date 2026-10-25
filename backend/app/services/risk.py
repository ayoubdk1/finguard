
def assess_risk(
    amount_cents: int,
    transfers_last_10min: int,
    account_age_minutes: int,
    failed_transfers_last_hour: int,
) -> dict:

    # Validate inputs
    values = (
        amount_cents,
        transfers_last_10min,
        account_age_minutes,
        failed_transfers_last_hour,
    )

    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Risk inputs must be non-negative integers")

    if amount_cents == 0:
        raise ValueError("Transfer amount must be positive")

    score = 0
    reasons = []

    # Rule 1: Large amount
    if amount_cents >= 100000:
        score += 30
        reasons.append("LARGE_AMOUNT")

    # Rule 2: High transaction velocity
    if transfers_last_10min >= 3:
        score += 35
        reasons.append("HIGH_VELOCITY")

    # Rule 3: New account
    if account_age_minutes < 1440:
        score += 20
        reasons.append("NEW_ACCOUNT")

    # Rule 4: Repeated failures
    if failed_transfers_last_hour >= 3:
        score += 25
        reasons.append("REPEATED_FAILURES")

    # Maximum score is 100
    score = min(score, 100)

    # Risk decision
    if score < 40:
        decision = "ALLOW"
    elif score < 70:
        decision = "ALERT"
    elif score < 90:
        decision = "REVIEW"
    else:
        decision = "SIMULATED_HOLD"

    return {
        "score": score,
        "decision": decision,
        "reason_codes": reasons,
    }
