import uuid
from sqlalchemy import select

from app.main import app
from app.security.dependencies import get_current_user
from app.db.models import FraudAlert, FraudAlertStatus, TransferAttempt, User
from app.services import ml_risk
from app.services.risk_assessment import assess_transaction_risk


def test_p3_model_hash_check_and_health_ready(client, monkeypatch, tmp_path):
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["fraud_model"] == "ok"

    fake_model = tmp_path / "tampered.joblib"
    fake_model.write_bytes(b"corrupted-bytes")
    ml_risk.load_fraud_model.cache_clear()
    monkeypatch.setattr(ml_risk, "MODEL_FILE", fake_model)
    assert ml_risk.is_fraud_model_ready() is False
    ml_risk.load_fraud_model.cache_clear()


def test_p3_better_features_and_failed_attempts_tracking(client, session, world):
    assert client.post("/deposits", headers={"Idempotency-Key": f"p3d-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 200_000}).status_code == 201

    bad = client.post("/transfers", headers={"Idempotency-Key": f"p3f-{uuid.uuid4()}"}, json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 500_000})
    assert bad.status_code == 409
    attempts = session.scalars(select(TransferAttempt).where(TransferAttempt.source_account_id == world["alice"].id)).all()
    assert len(attempts) >= 1
    assert attempts[-1].reason == "INSUFFICIENT_FUNDS"

    risk = assess_transaction_risk(amount_cents=100_000, transfers_last_10min=0, account_age_minutes=1000, failed_transfers_last_hour=0, is_new_destination=True, amount_vs_avg_ratio=4.0, normalized_amount_usd_cents=100_000)
    assert "NEW_DESTINATION_HIGH_AMOUNT" in risk["reason_codes"]
    assert "AMOUNT_SPIKE_VS_AVERAGE" in risk["reason_codes"]
    assert risk["automatic_block"] is False


def test_p3_alert_workflow_sla_assignment_and_invalid_transitions(client, session, world):
    analyst = User(id=uuid.uuid4(), email=f"an-{uuid.uuid4().hex[:8]}@example.com", full_name="Analyst", password_hash="x", role="FRAUD_ANALYST", status="ACTIVE")
    session.add(analyst)
    session.flush()
    alert = FraudAlert(account_id=world["alice"].id, risk_score=850, reasons=["HIGH_AMOUNT"], status=FraudAlertStatus.PENDING)
    session.add(alert)
    session.commit()

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: analyst
    try:
        r_assign = client.post(f"/fraud/alerts/{alert.id}/assign", json={"analyst_id": str(analyst.id)})
        assert r_assign.status_code == 200
        assert r_assign.json()["assigned_to"] == str(analyst.id)
        assert isinstance(r_assign.json()["reasons"], list)

        r_inv = client.post(f"/fraud/alerts/{alert.id}/investigate")
        assert r_inv.status_code == 200
        assert r_inv.json()["investigated_at"] is not None

        assert client.post(f"/fraud/alerts/{alert.id}/investigate").status_code == 409

        r_res = client.post(f"/fraud/alerts/{alert.id}/resolve", json={"decision": "APPROVED", "analyst_notes": "verified ok"})
        assert r_res.status_code == 200

        assert client.post(f"/fraud/alerts/{alert.id}/investigate").status_code == 409
        assert client.post(f"/fraud/alerts/{alert.id}/resolve", json={"decision": "BLOCKED", "analyst_notes": "re-resolve"}).status_code == 409
        assert client.post(f"/fraud/alerts/{alert.id}/assign", json={"analyst_id": str(analyst.id)}).status_code == 409
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
