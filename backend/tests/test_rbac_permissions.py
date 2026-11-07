from uuid import uuid4

from app import main as api_module
from app.db.models import User
from app.security.dependencies import get_current_user
from app.security.permissions import Permission, Role, has_permission


def _override_user(monkeypatch, role: str, user_id=None):
    user = User(
        id=user_id or uuid4(),
        email=f"{role.lower()}@finguard.local",
        full_name=f"Test {role}",
        role=role,
    )
    monkeypatch.setitem(
        api_module.app.dependency_overrides,
        get_current_user,
        lambda: user,
    )
    return user


def test_role_permission_matrix():
    assert has_permission(Role.CUSTOMER, Permission.DEPOSIT_CREATE)
    assert not has_permission(Role.CUSTOMER, Permission.MONITORING_READ)
    assert has_permission(Role.AUDITOR, Permission.MONITORING_READ)
    assert not has_permission(Role.AUDITOR, Permission.RISK_ASSESS)
    assert has_permission(Role.FRAUD_ANALYST, Permission.RISK_ASSESS)
    assert not has_permission(Role.FRAUD_ANALYST, Permission.TRANSFER_CREATE)
    assert has_permission(Role.ADMIN, Permission.ACCOUNT_CREATE_ANY)
    assert not has_permission("UNKNOWN_ROLE", Permission.ACCOUNT_READ_OWN)


def test_customer_cannot_read_monitoring_events(client, monkeypatch):
    _override_user(monkeypatch, Role.CUSTOMER)
    response = client.get("/monitoring/events")
    assert response.status_code == 403


def test_auditor_and_fraud_analyst_can_read_monitoring(client, monkeypatch):
    for role in (Role.AUDITOR, Role.FRAUD_ANALYST):
        _override_user(monkeypatch, role)
        response = client.get("/monitoring/events")
        assert response.status_code == 200


def test_auditor_can_read_all_accounts_but_cannot_deposit_or_assess_risk(
    client, world, monkeypatch
):
    _override_user(monkeypatch, Role.AUDITOR)

    accounts_resp = client.get("/accounts")
    assert accounts_resp.status_code == 200
    assert len(accounts_resp.json()) >= 2

    bal_resp = client.get(f"/accounts/{world['alice'].id}/balance")
    assert bal_resp.status_code == 200

    dep_resp = client.post(
        "/deposits",
        headers={"Idempotency-Key": f"idem-{uuid4()}"},
        json={"account_id": str(world["alice"].id), "amount_cents": 1000},
    )
    assert dep_resp.status_code == 403

    risk_resp = client.post(
        "/risk/assess",
        json={
            "amount_cents": 50000,
            "transfers_last_10min": 1,
            "account_age_minutes": 120,
            "failed_transfers_last_hour": 0,
        },
    )
    assert risk_resp.status_code == 403


def test_fraud_analyst_can_assess_risk_but_cannot_transfer(
    client, world, monkeypatch
):
    _override_user(monkeypatch, Role.FRAUD_ANALYST)

    risk_resp = client.post(
        "/risk/assess",
        json={
            "amount_cents": 50000,
            "transfers_last_10min": 1,
            "account_age_minutes": 120,
            "failed_transfers_last_hour": 0,
        },
    )
    assert risk_resp.status_code == 200

    tx_resp = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"idem-{uuid4()}"},
        json={
            "source_account_id": str(world["alice"].id),
            "destination_account_id": str(world["bob"].id),
            "amount_cents": 500,
        },
    )
    assert tx_resp.status_code == 403


def test_production_env_disables_demo_mode(client, monkeypatch):
    monkeypatch.delitem(
        api_module.app.dependency_overrides,
        get_current_user,
        raising=False,
    )
    monkeypatch.setenv("FINGUARD_ENV", "production")
    response = client.get("/accounts")
    assert response.status_code == 401
