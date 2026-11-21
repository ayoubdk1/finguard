import uuid
from app.main import app
from app.db.models import Account, AccountType, User
from app.security.dependencies import get_current_user


def test_account_freeze_unfreeze_and_close_lifecycle(client, session, world):
    # Cannot close account with non-zero balance
    assert client.post("/deposits", headers={"Idempotency-Key": f"d-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 10_000}).status_code == 201
    assert client.patch(f"/accounts/{world['alice'].id}/status", json={"status": "CLOSED"}).status_code == 409

    # Freeze Alice -> blocks deposit and transfer
    fr = client.patch(f"/accounts/{world['alice'].id}/status", json={"status": "FROZEN"})
    assert fr.status_code == 200 and fr.json()["status"] == "FROZEN"
    assert client.post("/deposits", headers={"Idempotency-Key": f"d2-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 1_000}).status_code == 403
    assert client.post("/transfers", headers={"Idempotency-Key": f"t1-{uuid.uuid4()}"}, json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 1_000}).status_code == 403

    # Unfreeze Alice -> transfer works again
    assert client.patch(f"/accounts/{world['alice'].id}/status", json={"status": "ACTIVE"}).status_code == 200
    assert client.post("/transfers", headers={"Idempotency-Key": f"t2-{uuid.uuid4()}"}, json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 1_000}).status_code == 201

    # Close zero-balance account -> cannot reopen
    empty = Account(user_id=world["alice"].user_id, name="Empty", account_type=AccountType.CUSTOMER, currency="USD")
    session.add(empty)
    session.commit()
    assert client.patch(f"/accounts/{empty.id}/status", json={"status": "CLOSED"}).status_code == 200
    assert client.patch(f"/accounts/{empty.id}/status", json={"status": "ACTIVE"}).status_code == 409


def test_customer_cannot_change_account_status(client, world):
    cust = User(id=uuid.uuid4(), email=f"c-{uuid.uuid4().hex[:6]}@example.com", full_name="Cust", role="CUSTOMER", status="ACTIVE")
    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: cust
    try:
        assert client.patch(f"/accounts/{world['alice'].id}/status", json={"status": "FROZEN"}).status_code == 403
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
