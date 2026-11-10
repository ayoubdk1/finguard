import uuid
from app.db.models import Account, AccountType
from app.services.ledger import post_transaction, EntryInput, get_balance


def _deposit(client, account_id, amount_cents):
    resp = client.post(
        "/deposits",
        headers={"Idempotency-Key": f"dep-{uuid.uuid4()}"},
        json={"account_id": str(account_id), "amount_cents": amount_cents},
    )
    assert resp.status_code == 201
    return resp


def test_transfer_exceeds_single_transaction_limit(client, world):
    # Fund Alice with $20,000 (2,000,000 cents)
    _deposit(client, world["alice"].id, 2_000_000)

    # Attempt to transfer $15,000 (1,500,000 cents) -> exceeds single limit of 1,000,000
    resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"tx-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(world["bob"].id),
            "amount_cents": 1_500_000,
            "description": "Large single transfer",
        },
    )
    assert resp.status_code == 422
    assert "exceeds single limit" in resp.json()["detail"].lower()


def test_transfer_exceeds_daily_rolling_limit(client, world):
    # Fund Alice with $60,000 (6,000,000 cents)
    _deposit(client, world["alice"].id, 6_000_000)

    # Do 5 valid transfers of $9,000 (900,000 cents each) = $45,000 transferred
    for i in range(5):
        resp = client.post(
            "/transfers",
            headers={"Idempotency-Key": f"tx-batch-{i}-{uuid.uuid4()}"},
            json={
                "source_account_id": str(world["alice"].id),
                "destination_account_id": str(world["bob"].id),
                "amount_cents": 900_000,
                "description": f"Transfer {i}",
            },
        )
        assert resp.status_code == 201

    # 6th transfer of $9,000 would bring total to $54,000 -> exceeds 50,000 daily limit!
    over_limit_resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"tx-over-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(world["bob"].id),
            "amount_cents": 900_000,
            "description": "Over limit transfer",
        },
    )
    assert over_limit_resp.status_code == 422
    assert "rolling 24h limit" in over_limit_resp.json()["detail"].lower()


def test_refund_successful_workflow(client, world, session):
    # 1. Fund Alice with $500 (50,000 cents)
    _deposit(client, world["alice"].id, 50_000)

    # 2. Transfer $200 (20,000 cents) to Bob
    transfer_resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"tx-orig-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(world["bob"].id),
            "amount_cents": 20_000,
            "description": "Payment for service",
        },
    )
    assert transfer_resp.status_code == 201
    tx_id = transfer_resp.json()["transaction_id"]

    # Check intermediate balances: Alice has $300, Bob has $200
    assert get_balance(session, world["alice"].id) == 30_000
    assert get_balance(session, world["bob"].id) == 20_000

    # 3. Request refund
    refund_resp = client.post(
        f"/transfers/{tx_id}/refund",
        headers={"Idempotency-Key": f"ref-{uuid.uuid4()}"},
    )
    assert refund_resp.status_code == 201
    ref_data = refund_resp.json()
    assert ref_data["amount_cents"] == 20_000
    assert ref_data["source_account_id"] == str(world["bob"].id)
    assert ref_data["destination_account_id"] == str(world["alice"].id)

    # 4. Check balances restored in ledger: Alice back to $500, Bob back to $0
    assert get_balance(session, world["alice"].id) == 50_000
    assert get_balance(session, world["bob"].id) == 0

    # 5. Prevent double refund
    dup_refund = client.post(
        f"/transfers/{tx_id}/refund",
        headers={"Idempotency-Key": f"ref-dup-{uuid.uuid4()}"},
    )
    assert dup_refund.status_code == 409
    assert "already been refunded" in dup_refund.json()["detail"].lower()


def test_refund_fails_if_recipient_has_insufficient_funds(client, world):
    # Alice sends $100 to Bob
    _deposit(client, world["alice"].id, 10_000)
    tx_resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"tx-b-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(world["bob"].id),
            "amount_cents": 10_000,
        },
    )
    assert tx_resp.status_code == 201
    tx_id = tx_resp.json()["transaction_id"]

    # Bob immediately spends his $100 (sending it back or somewhere else)
    spend_resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"tx-spend-{uuid.uuid4()}"},
        json={
            "source_account_id": str(world["bob"].id),
            "destination_account_id": str(world["alice"].id),
            "amount_cents": 10_000,
        },
    )
    assert spend_resp.status_code == 201

    # Now Bob has $0 -> attempting to refund the original transfer must fail (insufficient funds)
    refund_attempt = client.post(
        f"/transfers/{tx_id}/refund",
        headers={"Idempotency-Key": f"ref-fail-{uuid.uuid4()}"},
    )
    assert refund_attempt.status_code == 409
    assert "insufficient funds" in refund_attempt.json()["detail"].lower()
