from app.services.ml_risk import predict_ml_risk
from app.services.risk import assess_risk


def assess_transaction_risk(
    amount_cents: int,
    transfers_last_10min: int,
    account_age_minutes: int,
    failed_transfers_last_hour: int,
    is_new_destination: bool = False,
    amount_vs_avg_ratio: float = 1.0,
    normalized_amount_usd_cents: int | None = None,
) -> dict:
    effective_amount = (
        normalized_amount_usd_cents
        if normalized_amount_usd_cents is not None
        else amount_cents
    )
    rules = assess_risk(
        amount_cents=effective_amount,
        transfers_last_10min=transfers_last_10min,
        account_age_minutes=account_age_minutes,
        failed_transfers_last_hour=failed_transfers_last_hour,
    )
    ml = predict_ml_risk(
        amount_cents=effective_amount,
        transfers_last_10min=transfers_last_10min,
        account_age_minutes=account_age_minutes,
        failed_transfers_last_hour=failed_transfers_last_hour,
    )

    reason_codes = list(rules.get("reason_codes", []))
    raw_score = float(rules.get("risk_score", rules.get("score", 0)))
    if is_new_destination:
        reason_codes.append("NEW_DESTINATION")
        if effective_amount >= 50_000:
            reason_codes.append("NEW_DESTINATION_HIGH_AMOUNT")
        raw_score += 15.0
    if amount_vs_avg_ratio >= 3.0:
        reason_codes.append("AMOUNT_SPIKE_VS_AVERAGE")
        raw_score += 20.0
    risk_score = min(100.0, round(raw_score, 2))

    decision = rules["decision"]
    if decision == "ALLOW" and risk_score >= 35.0:
        decision = "REVIEW"

    ml_available = ml.get("ml_available", ml.get("ml_prediction") in ("FRAUD", "NORMAL"))
    ml_flagged = bool(ml_available and ml.get("ml_prediction") == "FRAUD")
    review_recommended = (decision != "ALLOW") or ml_flagged

    return {
        "risk_score": risk_score,
        "decision": decision,
        "rule_assessment": rules,
        "ml_assessment": ml,
        "rules_risk_score": risk_score,
        "rules_decision": decision,
        "reason_codes": reason_codes,
        "ml_available": bool(ml_available),
        "model_version": ml.get("model_version"),
        "ml_prediction": ml.get("ml_prediction", "UNAVAILABLE"),
        "ml_probability": ml.get("ml_probability", ml.get("fraud_probability")),
        "feature_contributions": ml.get("feature_contributions", {}),
        "review_recommended": review_recommended,
        "automatic_block": False,
    }
