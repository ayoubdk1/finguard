from app.services.risk import assess_risk
from app.services.ml_risk import predict_ml_risk


def assess_transaction_risk(
    amount_cents: int,
    transfers_last_10min: int,
    account_age_minutes: int,
    failed_transfers_last_hour: int,
) -> dict:
    rules = assess_risk(
        amount_cents=amount_cents,
        transfers_last_10min=transfers_last_10min,
        account_age_minutes=account_age_minutes,
        failed_transfers_last_hour=failed_transfers_last_hour,
    )

    ml = predict_ml_risk(
        amount_cents=amount_cents,
        transfers_last_10min=transfers_last_10min,
        account_age_minutes=account_age_minutes,
        failed_transfers_last_hour=failed_transfers_last_hour,
    )

    ml_available = ml.get("ml_available", ml.get("ml_prediction") in ("FRAUD", "NORMAL"))
    ml_flagged = bool(ml_available and ml.get("ml_prediction") == "FRAUD")
    review_recommended = (rules["decision"] != "ALLOW") or ml_flagged

    return {
        "risk_score": rules.get("risk_score", rules.get("score", 0)),
        "decision": rules["decision"],
        "rule_assessment": rules,
        "ml_assessment": ml,
        "rules_risk_score": rules.get("risk_score", rules.get("score", 0)),
        "rules_decision": rules["decision"],
        "reason_codes": rules["reason_codes"],
        "ml_available": bool(ml_available),
        "model_version": ml.get("model_version"),
        "ml_prediction": ml.get("ml_prediction", "UNAVAILABLE"),
        "ml_probability": ml.get("ml_probability", ml.get("fraud_probability")),
        "feature_contributions": ml.get("feature_contributions", {}),
        "review_recommended": review_recommended,
        "automatic_block": False,
    }
