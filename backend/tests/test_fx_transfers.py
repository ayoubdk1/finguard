import uuid
from app.db.models import Account, AccountType, User
from app.services.ledger import get_balance


def _deposit(client, account_id, amount_cents):
    resp = client.post(
        "/deposits",
        headers={"Idempotency-Key": f"dep-{uuid.uuid4()}"},
        json={"account_id": str(account_id), "amount_cents": amount_cents},
    )
    assert resp.status_code == 201, f'SERVER RESPONSE: {resp.status_code} -> {resp.text}'
    return resp


def test_list_exchange_rates(client):
    resp = client.get("/fx/rates")
    assert resp.status_code == 200
    rates = resp.json()
    assert len(rates) >= 6
    pairs = {(r["base_currency"], r["target_currency"]) for r in rates}
    assert ("USD", "EUR") in pairs
    assert ("USD", "TND") in pairs


def test_cross_currency_transfer_usd_to_eur(client, session, world):
    # Create Bob EUR account
    bob_eur = Account(
        user_id=world["bob"].user_id,
        name="Bob EUR",
        account_type=AccountType.CUSTOMER,
        currency="EUR",
    )
    session.add(bob_eur)
    session.commit()

    # Fund Alice USD with $500 (50,000 cents)
    _deposit(client, world["alice"].id, 50_000)

    # Transfer 100.00 USD (10,000 cents) from Alice USD to Bob EUR
    resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"fx-usd-eur-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(bob_eur.id),
            "amount_cents": 10_000,
            "description": "Cross-currency USD to EUR",
        },
    )
    assert resp.status_code == 201, f'SERVER RESPONSE: {resp.status_code} -> {resp.text}'
    data = resp.json()
    assert data["is_fx"] is True
    assert data["target_currency"] == "EUR"
    assert data["fee_cents"] == 50
    assert data["converted_amount_cents"] == 9154  # (10000 - 50) * 0.92 = 9154 cents

    # Check ledger balances
    assert get_balance(session, world["alice"].id) == 40_000   # 50000 - 10000 USD cents
    assert get_balance(session, bob_eur.id) == 9154            # 91.54 EUR


def test_cross_currency_transfer_usd_to_tnd(client, session, world):
    # Create Bob TND account (3 decimal places: millimes)
    bob_tnd = Account(
        user_id=world["bob"].user_id,
        name="Bob TND",
        account_type=AccountType.CUSTOMER,
        currency="TND",
    )
    session.add(bob_tnd)
    session.commit()

    # Fund Alice USD with $200 (20,000 cents)
    _deposit(client, world["alice"].id, 20_000)

    # Transfer 100.00 USD (10,000 cents) -> Rate USD/TND = 3.100, Fee = 50 cents (0.50 USD)
    # Net: 99.50 USD * 3.100 = 308.450 TND = 308450 millimes
    resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"fx-usd-tnd-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(bob_tnd.id),
            "amount_cents": 10_000,
            "description": "USD to TND FX transfer",
        },
    )
    assert resp.status_code == 201, f'SERVER RESPONSE: {resp.status_code} -> {resp.text}'
    data = resp.json()
    assert data["is_fx"] is True
    assert data["target_currency"] == "TND"
    assert data["fee_cents"] == 50
    assert data["converted_amount_cents"] == 308450

    assert get_balance(session, bob_tnd.id) == 308450
