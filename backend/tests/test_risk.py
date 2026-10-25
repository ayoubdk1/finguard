
import pytest

from app.services.risk import assess_risk


def test_normal_transaction():
    result = assess_risk(5000, 1, 3000, 0)

    assert result["score"] == 0
    assert result["decision"] == "ALLOW"
    assert result["reason_codes"] == []


def test_large_amount():
    result = assess_risk(100000, 1, 3000, 0)

    assert result["score"] == 30
    assert "LARGE_AMOUNT" in result["reason_codes"]


def test_high_velocity():
    result = assess_risk(5000, 3, 3000, 0)

    assert result["score"] == 35
    assert "HIGH_VELOCITY" in result["reason_codes"]


def test_new_account():
    result = assess_risk(5000, 1, 60, 0)

    assert result["score"] == 20
    assert "NEW_ACCOUNT" in result["reason_codes"]


def test_repeated_failures():
    result = assess_risk(5000, 1, 3000, 3)

    assert result["score"] == 25
    assert "REPEATED_FAILURES" in result["reason_codes"]


def test_multiple_risk_factors():
    result = assess_risk(150000, 3, 60, 1)

    assert result["score"] == 85
    assert result["decision"] == "REVIEW"
    assert len(result["reason_codes"]) == 3


def test_highest_risk():
    result = assess_risk(150000, 3, 60, 3)

    assert result["score"] == 100
    assert result["decision"] == "SIMULATED_HOLD"
    assert len(result["reason_codes"]) == 4


def test_invalid_amount():
    with pytest.raises(ValueError):
        assess_risk(-100, 1, 3000, 0)


def test_zero_amount():
    with pytest.raises(ValueError):
        assess_risk(0, 1, 3000, 0)
