
from app.services.risk import assess_risk
from app.services.ml_risk import predict_ml_risk


def assess_transaction_risk(
    amount_cents: int,
    transfers_last_10min: int,
    account_age_minutes: int,
    failed_transfers_last_hour: int,
) -> dict:

    # 1. Run rule-based detection
    rules = assess_risk(
        amount_cents=amount_cents,
        transfers_last_10min=transfers_last_10min,
        account_age_minutes=account_age_minutes,
        failed_transfers_last_hour=failed_transfers_last_hour,
    )

    # 2. Run machine learning detection
    ml = predict_ml_risk(
        amount_cents=amount_cents,
        transfers_last_10min=transfers_last_10min,
        account_age_minutes=account_age_minutes,
        failed_transfers_last_hour=failed_transfers_last_hour,
    )

    # 3. Recommend manual review if either detects risk
    review_recommended = (
        rules["decision"] != "ALLOW"
        or ml["ml_prediction"] == "FRAUD"
    )

    # 4. Return both assessments
    return {
        "rule_assessment": rules,
        "ml_assessment": ml,
        "review_recommended": review_recommended,
        "automatic_block": False,
    }
