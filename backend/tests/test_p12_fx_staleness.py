from datetime import datetime, timedelta, timezone
import uuid
from app.db.models import Account, AccountType, ExchangeRate


def test_stale_exchange_rate_rejected(client, session, world, monkeypatch):
    monkeypatch.setenv("FINGUARD_FX_MAX_AGE_SECONDS", "60")
    bob_eur = Account(user_id=world["bob"].user_id, name="Bob EUR", account_type=AccountType.CUSTOMER, currency="EUR")
    session.add(bob_eur)
    session.add(ExchangeRate(base_currency="USD", target_currency="EUR", rate=920000, fee_bps=50, created_at=datetime.now(timezone.utc) - timedelta(hours=2)))
    session.commit()

    # Ensure only the stale rate is newer or clear fresh ones
    session.query(ExchangeRate).filter(ExchangeRate.base_currency == "USD", ExchangeRate.target_currency == "EUR", ExchangeRate.created_at > datetime.now(timezone.utc) - timedelta(minutes=5)).delete()
    session.commit()

    assert client.post("/deposits", headers={"Idempotency-Key": f"sd-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 20_000}).status_code == 201
    resp = client.post("/transfers", headers={"Idempotency-Key": f"sf-{uuid.uuid4()}"}, json={"source_account_id": str(world["alice"].id), "destination_account_id": str(bob_eur.id), "amount_cents": 5_000})
    assert resp.status_code == 400
    assert "stale" in resp.json()["detail"].lower()
