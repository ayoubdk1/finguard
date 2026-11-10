import uuid
from app import main as api_module
from app.db.models import Account, AccountType, FraudAlert, User
from app.security.dependencies import get_current_user
from app.security.permissions import Role


def _override_user(monkeypatch, role: str, session=None, user_id=None):
    user = User(
        id=user_id or uuid.uuid4(),
        email=f"{role.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        full_name=f"Test {role}",
        role=role,
    )
    if session:
        session.add(user)
        session.commit()

    monkeypatch.setitem(
        api_module.app.dependency_overrides,
        get_current_user,
        lambda: user,
    )
    return user


def test_customer_cannot_access_fraud_alerts(client, monkeypatch):
    _override_user(monkeypatch, Role.CUSTOMER)
    resp = client.get("/fraud/alerts")
    assert resp.status_code == 403


def test_fraud_investigation_lifecycle(client, session, world, monkeypatch):
    # 1. Analyst user
    analyst = _override_user(monkeypatch, Role.FRAUD_ANALYST, session=session)

    # 2. Seed a suspicious fraud alert
    alert = FraudAlert(
        account_id=world["alice"].id,
        risk_score=850,  # 0.850
        reasons="HIGH_AMOUNT, VELOCITY_BURST",
        status="PENDING",
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)

    # 3. List alerts as FRAUD_ANALYST
    list_resp = client.get("/fraud/alerts")
    assert list_resp.status_code == 200
    alerts = list_resp.json()
    assert len(alerts) >= 1
    target = next(a for a in alerts if a["id"] == str(alert.id))
    assert target["status"] == "PENDING"
    assert target["risk_score"] == 0.85
    assert "VELOCITY_BURST" in target["reasons"]

    # 4. Start investigation
    investigate_resp = client.post(f"/fraud/alerts/{alert.id}/investigate")
    assert investigate_resp.status_code == 200
    assert investigate_resp.json()["status"] == "INVESTIGATING"
    assert investigate_resp.json()["analyst_id"] == str(analyst.id)

    # 5. Resolve alert: decision BLOCKED
    resolve_resp = client.post(
        f"/fraud/alerts/{alert.id}/resolve",
        json={
            "decision": "BLOCKED",
            "analyst_notes": "Confirmed account takeover attempt. Card and transfers blocked.",
        },
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["status"] == "BLOCKED"
    assert res_data["resolved_at"] is not None
    assert "Confirmed account takeover" in res_data["analyst_notes"]

    # 6. Filter by status: PENDING should no longer show this alert
    pending_resp = client.get("/fraud/alerts?status_filter=PENDING")
    assert pending_resp.status_code == 200
    assert all(a["id"] != str(alert.id) for a in pending_resp.json())

    # 7. Filter by BLOCKED shows it
    blocked_resp = client.get("/fraud/alerts?status_filter=BLOCKED")
    assert blocked_resp.status_code == 200
    assert any(a["id"] == str(alert.id) for a in blocked_resp.json())
