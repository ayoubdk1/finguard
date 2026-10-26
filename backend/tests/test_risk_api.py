
def test_high_risk_api(client):
    response = client.post(
        "/risk/assess",
        json={
            "amount_cents": 150000,
            "transfers_last_10min": 4,
            "account_age_minutes": 60,
            "failed_transfers_last_hour": 3
        }
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["rule_assessment"]["score"] == 100
    assert data["rule_assessment"]["decision"] == "SIMULATED_HOLD"
    assert len(data["rule_assessment"]["reason_codes"]) == 4

    assert data["ml_assessment"]["ml_prediction"] in ["FRAUD", "NORMAL"]
    assert 0 <= data["ml_assessment"]["fraud_probability"] <= 1

    assert data["review_recommended"] is True
    assert data["automatic_block"] is False


def test_normal_risk_api(client):
    response = client.post(
        "/risk/assess",
        json={
            "amount_cents": 5000,
            "transfers_last_10min": 1,
            "account_age_minutes": 3000,
            "failed_transfers_last_hour": 0
        }
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["rule_assessment"]["score"] == 0
    assert data["rule_assessment"]["decision"] == "ALLOW"
    assert data["ml_assessment"]["ml_prediction"] in ["FRAUD", "NORMAL"]
    assert data["automatic_block"] is False


def test_invalid_risk_amount(client):
    response = client.post(
        "/risk/assess",
        json={
            "amount_cents": -100,
            "transfers_last_10min": 1,
            "account_age_minutes": 3000,
            "failed_transfers_last_hour": 0
        }
    )

    assert response.status_code == 422
