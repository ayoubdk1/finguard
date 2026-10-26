
import pytest

from app.services import risk_assessment


def mock_ml(monkeypatch, prediction):
    # Replace ML prediction with a predictable result
    monkeypatch.setattr(
        risk_assessment,
        "predict_ml_risk",
        lambda **kwargs: {
            "ml_prediction": prediction,
            "fraud_probability": 0.9 if prediction == "FRAUD" else 0.1,
            "model": "TestModel",
        },
    )


def test_high_rule_risk(monkeypatch):
    mock_ml(monkeypatch, "NORMAL")

    result = risk_assessment.assess_transaction_risk(
        150000, 4, 60, 3
    )

    assert result["rule_assessment"]["score"] == 100
    assert result["review_recommended"] is True
    assert result["automatic_block"] is False


def test_ml_detects_fraud(monkeypatch):
    mock_ml(monkeypatch, "FRAUD")

    result = risk_assessment.assess_transaction_risk(
        5000, 1, 3000, 0
    )

    assert result["rule_assessment"]["decision"] == "ALLOW"
    assert result["ml_assessment"]["ml_prediction"] == "FRAUD"
    assert result["review_recommended"] is True


def test_normal_transaction(monkeypatch):
    mock_ml(monkeypatch, "NORMAL")

    result = risk_assessment.assess_transaction_risk(
        5000, 1, 3000, 0
    )

    assert result["rule_assessment"]["score"] == 0
    assert result["review_recommended"] is False
    assert result["automatic_block"] is False


def test_invalid_amount(monkeypatch):
    mock_ml(monkeypatch, "NORMAL")

    with pytest.raises(ValueError):
        risk_assessment.assess_transaction_risk(
            -100, 1, 3000, 0
        )
