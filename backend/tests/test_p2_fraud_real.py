import json
import uuid
from pathlib import Path
from app.db.models import FraudAlert, User
from app.services import ml_risk
from sqlalchemy import select


def test_ml_fallback_when_model_missing(monkeypatch, tmp_path):
    ml_risk.load_fraud_model.cache_clear()
    monkeypatch.setattr(ml_risk, "MODEL_FILE", tmp_path / "nonexistent.joblib")
    res = ml_risk.predict_ml_risk(
        amount_cents=200_000,
        transfers_last_10min=4,
        account_age_minutes=30,
        failed_transfers_last_hour=0,
    )
    assert res["ml_available"] is False
    assert res["ml_prediction"] == "UNAVAILABLE"
    ml_risk.load_fraud_model.cache_clear()


def test_model_metadata_sidecar_exists():
    meta_path = Path("backend/models/fraud_gradient_boosting.meta.json")
    if not meta_path.exists():
        meta_path = Path("models/fraud_gradient_boosting.meta.json")
    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["version"] == "1.0.0"
    assert "cv_5fold_ap_ci95" in data
    assert "dataset_sha256" in data


def test_transfer_auto_creates_fraud_alert_and_state_machine(client, session, world, monkeypatch):
    # Ensure test works cleanly even if local OS blocks sklearn DLL
    monkeypatch.setattr(
        "app.services.risk_assessment.predict_ml_risk",
        lambda **kw: {"ml_available": False, "model_version": "1.0.0", "ml_prediction": "UNAVAILABLE", "ml_probability": None, "feature_contributions": {}},
    )

    # Fund Alice with $2,500
    dep = client.post(
        "/deposits",
        headers={"Idempotency-Key": f"p2-dep-{uuid.uuid4()}"},
        json={"account_id": str(world["alice"].id), "amount_cents": 250_000},
    )
    assert dep.status_code == 201

    # High-risk transfer ($1,500 from brand-new account -> LARGE_AMOUNT + NEW_ACCOUNT = 50 -> ALERT)
    tr = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"p2-tr-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(world["bob"].id),
            "amount_cents": 150_000,
            "description": "High value new account",
        },
    )
    assert tr.status_code == 201, tr.text
    tx_id = uuid.UUID(tr.json()["transaction_id"])

    alert = session.scalar(select(FraudAlert).where(FraudAlert.transaction_id == tx_id))
    assert alert is not None
    assert alert.status == "PENDING"
    assert "LARGE_AMOUNT" in alert.reasons

    admin_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    if session.get(User, admin_id) is None:
        session.add(User(id=admin_id, email="test-admin@finguard.local", password_hash="x", role="ADMIN", status="ACTIVE", full_name="Test Admin"))
        session.commit()

    # PENDING -> INVESTIGATING
    inv = client.post(f"/fraud/alerts/{alert.id}/investigate")
    assert inv.status_code == 200
    assert inv.json()["status"] == "INVESTIGATING"

    # INVESTIGATING -> INVESTIGATING rejected (409)
    inv_dup = client.post(f"/fraud/alerts/{alert.id}/investigate")
    assert inv_dup.status_code == 409

    # INVESTIGATING -> BLOCKED suspends account owner
    res = client.post(
        f"/fraud/alerts/{alert.id}/resolve",
        json={"decision": "BLOCKED", "analyst_notes": "Confirmed suspicious activity"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "BLOCKED"

    # BLOCKED -> APPROVED rejected (409 terminal state)
    reopen = client.post(
        f"/fraud/alerts/{alert.id}/resolve",
        json={"decision": "APPROVED", "analyst_notes": "Trying to override terminal state"},
    )
    assert reopen.status_code == 409

    owner = session.get(User, world["alice"].user_id)
    session.refresh(owner)
    assert owner.status == "SUSPENDED"
