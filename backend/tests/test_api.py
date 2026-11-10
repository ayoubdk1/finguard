import uuid
import pytest
from app.db.models import Account, AccountType
from app.services.ledger import EntryInput, post_transaction


def test_create_user(client):
    email = f"api-{uuid.uuid4().hex}@example.com"

    response = client.post(
        "/users",
        json={
            "email": email,
            "full_name": "API Test User"
        }
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == email
    assert data["full_name"] == "API Test User"
    assert "id" in data
    assert "created_at" in data


def test_create_account(client):
    # Create a test user
    user_response = client.post(
        "/users",
        json={
            "email": f"account-{uuid.uuid4().hex}@example.com",
            "full_name": "Account Test User"
        }
    )

    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    # Create an account for this user
    response = client.post(
        "/accounts",
        json={
            "user_id": user_id,
            "name": "Test TND Account",
            "currency": "TND"
        }
    )

    assert response.status_code == 201

    data = response.json()

    assert data["user_id"] == user_id
    assert data["name"] == "Test TND Account"
    assert data["currency"] == "TND"
    assert data["account_type"] == "CUSTOMER"
    assert "id" in data


def test_create_account_user_not_found(client):
    response = client.post(
        "/accounts",
        json={
            "user_id": "00000000-0000-0000-0000-000000000000",
            "name": "Invalid Account",
            "currency": "TND"
        }
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_deposit_idempotency(client, session):
    # 1. Create a test user
    user_response = client.post(
        "/users",
        json={
            "email": f"deposit-{uuid.uuid4().hex}@example.com",
            "full_name": "Deposit Test User"
        }
    )
    assert user_response.status_code == 201

    # 2. Create a TND customer account
    account_response = client.post(
        "/accounts",
        json={
            "user_id": user_response.json()["id"],
            "name": "Deposit Test Account",
            "currency": "TND"
        }
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]

    # 3. Create a simulated funding account
    funding = Account(
        name="SYSTEM_FUNDING",
        account_type=AccountType.SYSTEM,
        currency="TND"
    )
    session.add(funding)
    session.commit()

    # 4. Make the first deposit
    key = f"deposit-test-{uuid.uuid4().hex}"
    headers = {"Idempotency-Key": key}

    body = {
        "account_id": account_id,
        "amount_cents": 5000,
        "description": "Automated deposit test"
    }

    first = client.post(
        "/deposits",
        json=body,
        headers=headers
    )

    assert first.status_code == 201, first.text
    assert first.json()["balance_cents"] == 5000

    # 5. Retry with the same key
    second = client.post(
        "/deposits",
        json=body,
        headers=headers
    )

    assert second.status_code == 201
    assert (
        second.json()["transaction_id"]
        == first.json()["transaction_id"]
    )
    assert second.json()["balance_cents"] == 5000

    # 6. Reuse key with a different amount
    changed_body = {
        **body,
        "amount_cents": 6000
    }

    conflict = client.post(
        "/deposits",
        json=changed_body,
        headers=headers
    )

    assert conflict.status_code == 409

    # 7. Verify balance remains unchanged
    balance = client.get(
        f"/accounts/{account_id}/balance"
    )

    assert balance.status_code == 200
    assert balance.json()["balance_cents"] == 5000

import pytest


@pytest.mark.parametrize(
    "currency, amount_minor",
    [
        ("TND", 12500),  # 12.500 TND
        ("USD", 1250),   # 12.50 USD
        ("EUR", 1250),   # 12.50 EUR
    ],
)
def test_multi_currency_deposit(
    client, session, currency, amount_minor
):
    # 1. Create a test user
    user_response = client.post(
        "/users",
        json={
            "email": f"multi-{uuid.uuid4().hex}@example.com",
            "full_name": "Multi Currency Test User",
        },
    )
    assert user_response.status_code == 201

    # 2. Create a customer account in the selected currency
    account_response = client.post(
        "/accounts",
        json={
            "user_id": user_response.json()["id"],
            "name": f"{currency} Account",
            "currency": currency,
        },
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]

    # 3. Create a funding account in the SAME currency
    funding = Account(
        name="SYSTEM_FUNDING",
        account_type=AccountType.SYSTEM,
        currency=currency,
    )
    session.add(funding)
    session.commit()

    # 4. Make the first deposit
    key = f"multi-deposit-{uuid.uuid4().hex}"
    headers = {"Idempotency-Key": key}

    body = {
        "account_id": account_id,
        "amount_cents": amount_minor,
        "description": f"{currency} deposit test",
    }

    first = client.post(
        "/deposits",
        json=body,
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert first.json()["balance_cents"] == amount_minor
    assert first.json()["currency"] == currency

    # 5. Retry with the same idempotency key
    second = client.post(
        "/deposits",
        json=body,
        headers=headers,
    )

    assert second.status_code == 201, second.text
    assert (
        second.json()["transaction_id"]
        == first.json()["transaction_id"]
    )
    assert second.json()["balance_cents"] == amount_minor
@pytest.mark.parametrize(
    "currency, amount_minor",
    [
        ("TND", 12500),
        ("USD", 1250),
        ("EUR", 1250),
    ],
)
def test_deposit_supported_currencies(client, session, currency, amount_minor):
    # 1. Create a test user
    user_response = client.post(
        "/users",
        json={
            "email": f"multi-{uuid.uuid4().hex}@example.com",
            "full_name": "Multi Currency Test User",
        },
    )
    assert user_response.status_code == 201

    # 2. Create a customer account in the selected currency
    account_response = client.post(
        "/accounts",
        json={
            "user_id": user_response.json()["id"],
            "name": f"{currency} Account",
            "currency": currency,
        },
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]

    # 3. Create a funding account in the SAME currency
    funding = Account(
        name="SYSTEM_FUNDING",
        account_type=AccountType.SYSTEM,
        currency=currency,
    )
    session.add(funding)
    session.commit()

    # 4. Make the first deposit
    key = f"multi-deposit-{uuid.uuid4().hex}"
    headers = {"Idempotency-Key": key}

    body = {
        "account_id": account_id,
        "amount_cents": amount_minor,
        "description": f"{currency} deposit test",
    }

    first = client.post(
        "/deposits",
        json=body,
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert first.json()["balance_cents"] == amount_minor
    assert first.json()["currency"] == currency

    # 5. Retry with the same idempotency key
    second = client.post(
        "/deposits",
        json=body,
        headers=headers,
    )

    assert second.status_code == 201, second.text
    assert (
        second.json()["transaction_id"]
        == first.json()["transaction_id"]
    )
    assert second.json()["balance_cents"] == amount_minor


def test_deposit_without_matching_funding_account(client):
    # 1. Create a test user
    user_response = client.post(
        "/users",
        json={
            "email": f"missing-{uuid.uuid4().hex}@example.com",
            "full_name": "Missing Funding Test User",
        },
    )
    assert user_response.status_code == 201

    # 2. Create an EUR customer account
    account_response = client.post(
        "/accounts",
        json={
            "user_id": user_response.json()["id"],
            "name": "EUR Account",
            "currency": "EUR",
        },
    )
    assert account_response.status_code == 201

    # 3. Attempt deposit without an EUR SYSTEM_FUNDING account
    response = client.post(
        "/deposits",
        json={
            "account_id": account_response.json()["id"],
            "amount_cents": 1250,
        },
        headers={
            "Idempotency-Key": f"missing-{uuid.uuid4().hex}"
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "EUR SYSTEM_FUNDING account not found"
    )


def test_transfer_api(client, session, world):
    alice = world["alice"]
    bob = world["bob"]
    funding = world["funding"]

    # 1. Give Alice 5000 cents for testing
    post_transaction(
        session=session,
        idempotency_key=f"setup-{uuid.uuid4().hex}",
        entries=[
            EntryInput(funding.id, -5000),
            EntryInput(alice.id, 5000),
        ],
        description="Test funding"
    )

    # 2. Transfer 2000 cents from Alice to Bob
    key = f"transfer-test-{uuid.uuid4().hex}"
    headers = {"Idempotency-Key": key}

    body = {
        "source_account_id": str(alice.id),
        "destination_account_id": str(bob.id),
        "amount_cents": 2000,
        "description": "Automated transfer test"
    }

    first = client.post(
        "/transfers",
        json=body,
        headers=headers
    )

    assert first.status_code == 201, first.text
    assert first.json()["source_balance_cents"] == 3000
    assert first.json()["destination_balance_cents"] == 2000

    # 3. Retry the same transfer
    second = client.post(
        "/transfers",
        json=body,
        headers=headers
    )

    assert second.status_code == 201
    assert (
        second.json()["transaction_id"]
        == first.json()["transaction_id"]
    )
    assert second.json()["source_balance_cents"] == 3000

    # 4. Reuse key with a different amount
    conflict = client.post(
        "/transfers",
        json={**body, "amount_cents": 1500},
        headers=headers
    )

    assert conflict.status_code == 409

    # 5. Try transferring more than Alice owns
    insufficient = client.post(
        "/transfers",
        json={**body, "amount_cents": 100000},
        headers={
            "Idempotency-Key": f"insufficient-{uuid.uuid4().hex}"
        }
    )

    assert insufficient.status_code == 409

    # 6. Verify final balances
    alice_balance = client.get(
        f"/accounts/{alice.id}/balance"
    )

    bob_balance = client.get(
        f"/accounts/{bob.id}/balance"
    )

    assert alice_balance.status_code == 200
    assert bob_balance.status_code == 200
    assert alice_balance.json()["balance_cents"] == 3000
    assert bob_balance.json()["balance_cents"] == 2000


def test_balance_and_transaction_history(client, session, world):
    alice = world["alice"]
    bob = world["bob"]
    funding = world["funding"]

    # 1. Deposit 5000 cents into Alice's account
    post_transaction(
        session=session,
        idempotency_key=f"history-deposit-{uuid.uuid4().hex}",
        entries=[
            EntryInput(funding.id, -5000),
            EntryInput(alice.id, 5000),
        ],
        description="History test deposit"
    )

    # 2. Transfer 2000 cents from Alice to Bob
    post_transaction(
        session=session,
        idempotency_key=f"history-transfer-{uuid.uuid4().hex}",
        entries=[
            EntryInput(alice.id, -2000),
            EntryInput(bob.id, 2000),
        ],
        description="History test transfer"
    )

    # 3. Verify Alice's balance
    balance = client.get(
        f"/accounts/{alice.id}/balance"
    )

    assert balance.status_code == 200
    assert balance.json()["balance_cents"] == 3000
    assert balance.json()["currency"] == "USD"

    # 4. Verify Alice's transaction history
    response = client.get(
        f"/accounts/{alice.id}/transactions"
    )

    assert response.status_code == 200

    data = response.json()
    assert data["account_id"] == str(alice.id)
    assert len(data["transactions"]) == 2

    amounts = sorted(
        tx["amount_cents"]
        for tx in data["transactions"]
    )

    assert amounts == [-2000, 5000]

    for tx in data["transactions"]:
        assert tx["status"] == "POSTED"
        assert tx["currency"] == "USD"
        assert "transaction_id" in tx
        assert "created_at" in tx

    # 5. Verify Bob's balance
    bob_balance = client.get(
        f"/accounts/{bob.id}/balance"
    )

    assert bob_balance.status_code == 200
    assert bob_balance.json()["balance_cents"] == 2000


def test_create_account_supported_currencies(client):
    user_response = client.post(
        "/users",
        json={
            "email": f"currencies-{uuid.uuid4().hex}@example.com",
            "full_name": "Currency Test User"
        }
    )

    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    for currency in ["TND", "USD", "EUR"]:
        response = client.post(
            "/accounts",
            json={
                "user_id": user_id,
                "name": f"{currency} Account",
                "currency": currency
            }
        )

        assert response.status_code == 201, response.text
        assert response.json()["currency"] == currency


def test_create_account_unsupported_currency(client):
    user_response = client.post(
        "/users",
        json={
            "email": f"unsupported-{uuid.uuid4().hex}@example.com",
            "full_name": "Unsupported Currency User"
        }
    )

    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    response = client.post(
        "/accounts",
        json={
            "user_id": user_id,
            "name": "JPY Account",
            "currency": "JPY"
        }
    )

    assert response.status_code == 422


def test_create_account_defaults_to_tnd(client):
    user_response = client.post(
        "/users",
        json={
            "email": f"default-{uuid.uuid4().hex}@example.com",
            "full_name": "Default Currency User"
        }
    )

    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    response = client.post(
        "/accounts",
        json={
            "user_id": user_id,
            "name": "Default Account"
        }
    )

    assert response.status_code == 201, response.text
    assert response.json()["currency"] == "TND"
@pytest.mark.parametrize(
    "currency, amount_minor",
    [
        ("TND", 12500),
        ("USD", 1250),
        ("EUR", 1250),
    ],
)
def test_same_currency_transfers(
    client, session, currency, amount_minor
):
    # 1. Create two customer accounts
    user_response = client.post(
        "/users",
        json={
            "email": f"transfer-{uuid.uuid4().hex}@example.com",
            "full_name": "Transfer Test User",
        },
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["id"]

    source_response = client.post(
        "/accounts",
        json={
            "user_id": user_id,
            "name": f"{currency} Source",
            "currency": currency,
        },
    )
    assert source_response.status_code == 201

    destination_response = client.post(
        "/accounts",
        json={
            "user_id": user_id,
            "name": f"{currency} Destination",
            "currency": currency,
        },
    )
    assert destination_response.status_code == 201

    source_id = source_response.json()["id"]
    destination_id = destination_response.json()["id"]

    # 2. Create funding account
    funding = Account(
        name="SYSTEM_FUNDING",
        account_type=AccountType.SYSTEM,
        currency=currency,
    )
    session.add(funding)
    session.commit()

    # 3. Fund the source account
    post_transaction(
        session=session,
        idempotency_key=f"fund-{uuid.uuid4().hex}",
        entries=[
            EntryInput(funding.id, -amount_minor),
            EntryInput(uuid.UUID(source_id), amount_minor),
        ],
        description="Initial test funding",
    )

    # 4. Transfer the full amount
    response = client.post(
        "/transfers",
        json={
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "amount_cents": amount_minor,
            "description": f"{currency} transfer",
        },
        headers={
            "Idempotency-Key": f"transfer-{uuid.uuid4().hex}"
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["currency"] == currency
    assert response.json()["source_balance_cents"] == 0
    assert response.json()["destination_balance_cents"] == amount_minor
def test_reject_cross_currency_transfer(client, world, session):
    # Deposit funds into Alice's account
    client.post(
        "/deposits",
        headers={"Idempotency-Key": f"dep-{uuid.uuid4()}"},
        json={"account_id": str(world["alice"].id), "amount_cents": 5000},
    )

    from app.db.models import Account, AccountType
    unsupported_acc = Account(
        user_id=world["bob"].user_id,
        name="Unsupported Currency Account",
        account_type=AccountType.CUSTOMER,
        currency="GBP",
    )
    session.add(unsupported_acc)
    session.commit()

    response = client.post(
        "/transfers",
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(unsupported_acc.id),
            "amount_cents": 1000,
        },
        headers={"Idempotency-Key": f"cross-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 400
    assert "no exchange rate found" in response.json()["detail"].lower()
def test_admin_can_list_all_customer_accounts(client, world):
    response = client.get("/accounts")

    assert response.status_code == 200

    accounts = response.json()
    account_ids = {account["id"] for account in accounts}

    assert str(world["alice"].id) in account_ids
    assert str(world["bob"].id) in account_ids

    # System funding accounts must not be exposed.
    assert all(
        account["account_type"] == "CUSTOMER"
        for account in accounts
    )


def test_customer_can_only_list_own_accounts(
    client, world, monkeypatch
):
    from app import main as api_module
    from app.security.dependencies import get_current_user
    from app.db.models import User

    alice_user = User(
        id=world["alice"].user_id,
        email="alice-test@finguard.local",
        full_name="Alice",
        role="CUSTOMER",
    )

    monkeypatch.setitem(
        api_module.app.dependency_overrides,
        get_current_user,
        lambda: alice_user,
    )

    response = client.get("/accounts")

    assert response.status_code == 200

    accounts = response.json()

    assert len(accounts) == 1
    assert accounts[0]["id"] == str(world["alice"].id)