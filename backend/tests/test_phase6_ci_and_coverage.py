import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db.models import User
from app.db.session import SessionLocal
from app.main import app, validate_production_config
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password
from app.services.audit import mask_ip, mask_pii_in_text


def test_p6_ci_security_sbom_dependabot_codeql_files():
    root = Path(__file__).resolve().parents[2]
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "--cov-fail-under=90" in ci
    assert "compose-smoke-test:" in ci
    assert 'exit-code: "1"' in ci
    assert "continue-on-error: true" not in ci
    assert (root / ".github" / "dependabot.yml").exists()
    assert (root / ".github" / "workflows" / "codeql.yml").exists()
    assert (root / ".github" / "workflows" / "release-sbom.yml").exists()
    assert (root / "scripts" / "load_test_k6.js").exists()
    assert (root / "docs" / "security-allowlist.md").exists()


def test_p6_production_config_validation_and_pii_masking(monkeypatch):
    monkeypatch.setenv("FINGUARD_ENV", "production")
    monkeypatch.setenv("FINGUARD_JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        validate_production_config()

    monkeypatch.setenv("FINGUARD_JWT_SECRET", "a-very-secure-random-production-secret-32chars!")
    monkeypatch.setenv("FINGUARD_DEMO_MODE", "1")
    with pytest.raises(RuntimeError):
        validate_production_config()

    monkeypatch.setenv("FINGUARD_DEMO_MODE", "0")
    monkeypatch.setenv("FINGUARD_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        validate_production_config()

    monkeypatch.setenv("FINGUARD_CORS_ORIGINS", "https://app.finguard.example")
    monkeypatch.setenv("FINGUARD_MFA_ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError):
        validate_production_config()

    assert mask_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334").endswith(":****")
    assert mask_ip("invalid") == "***"
    masked = mask_pii_in_text("user ayoub@example.com from 10.0.0.55")
    assert "ay***@example.com" in masked and "10.0.0.***" in masked


def test_p6_admin_audit_logs_deposit_four_eyes_and_statement_dates(client, world):
    admin1 = User(id=uuid.uuid4(), email=f"p6a1-{uuid.uuid4().hex[:6]}@example.com", full_name="A1", password_hash="x", role="ADMIN", status="ACTIVE")
    admin2 = User(id=uuid.uuid4(), email=f"p6a2-{uuid.uuid4().hex[:6]}@example.com", full_name="A2", password_hash="x", role="ADMIN", status="ACTIVE")
    with SessionLocal() as s2:
        s2.add_all([admin1, admin2])
        s2.commit()

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: admin1
    try:
        r_req = client.post("/deposits/request", json={"account_id": str(world["alice"].id), "amount_cents": 25_000})
        assert r_req.status_code == 201
        appr_id = r_req.json()["id"]
        assert client.post(f"/deposits/{appr_id}/approve").status_code == 409

        app.dependency_overrides[get_current_user] = lambda: admin2
        assert client.post(f"/deposits/{appr_id}/approve").status_code == 200
        assert client.get("/admin/audit-logs").status_code == 200
        assert client.post(f"/admin/users/{admin1.id}/reset-password", json={"new_password": "NewStrongPassword123!"}).status_code == 200
        assert client.get(f"/admin/users/{admin1.id}/login-history").status_code == 200
        assert client.get(f"/admin/users/{admin1.id}/sessions").status_code == 200

        now = datetime.now(timezone.utc)
        st = client.get(
            f"/accounts/{world['alice'].id}/statement",
            params={"from_date": (now - timedelta(days=1)).isoformat(), "to_date": (now + timedelta(days=1)).isoformat()},
        )
        assert st.status_code == 200
        assert st.json()["derived_balance_check"] is True
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p6_auth_lifecycle_coverage(client, monkeypatch):
    monkeypatch.setenv("FINGUARD_JWT_SECRET", "test-secret-key-at-least-32-characters-long")  # gitleaks:allow
    email = f"p6u-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as s2:
        u = User(id=uuid.uuid4(), email=email, full_name="P6 User", password_hash=hash_password("StrongPassword123!"), role="CUSTOMER", status="ACTIVE")
        s2.add(u)
        s2.commit()

    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        r_log = client.post("/auth/login", json={"email": email, "password": "StrongPassword123!"})
        assert r_log.status_code == 200
        toks = r_log.json()
        hdr = {"Authorization": f"Bearer {toks['access_token']}"}
        assert client.get("/auth/me", headers=hdr).status_code == 200
        assert client.post("/auth/refresh", json={"refresh_token": toks["refresh_token"]}).status_code == 200
        assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
        assert client.post("/auth/logout", json={"refresh_token": toks["refresh_token"]}).status_code == 204
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p6_dependencies_email_and_admin_coverage(client, monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.security import dependencies as deps

    monkeypatch.setenv("FINGUARD_JWT_SECRET", "test-secret-key-at-least-32-characters-long")  # gitleaks:allow
    req = SimpleNamespace(url=SimpleNamespace(path="/accounts"), headers={}, state=SimpleNamespace(), client=SimpleNamespace(host="127.0.0.1"))
    with pytest.raises(HTTPException):
        deps.get_current_user(req, credentials=None)
    with pytest.raises(HTTPException):
        deps.get_current_user(req, credentials=SimpleNamespace(scheme="Bearer", credentials="invalid.jwt.token"))

    r_new = client.post("/admin/users", json={"email": f"p6c-{uuid.uuid4().hex[:6]}@example.com", "full_name": "P6 Created", "password": "StrongPassword123!", "role": "CUSTOMER"})
    assert r_new.status_code == 201
    uid = r_new.json()["id"]
    assert client.patch(f"/admin/users/{uid}", json={"full_name": "Updated", "role": "FRAUD_ANALYST", "status": "DISABLED"}).status_code == 200
    assert client.delete(f"/admin/users/{uid}/sessions/{uuid.uuid4()}").status_code in (200, 204, 404)
    assert client.get(f"/accounts/{uuid.uuid4()}/statement").status_code in (403, 404)
    assert client.post(f"/admin/approvals/{uuid.uuid4()}/approve").status_code == 404


def test_p6_outbox_worker_and_health_edge_cases(client, monkeypatch):
    from app.workers import outbox_publisher

    called = {"n": 0}
    monkeypatch.setattr(outbox_publisher, "new_producer", lambda: object())
    monkeypatch.setattr(outbox_publisher, "publish_batch", lambda *a, **kw: called.__setitem__("n", called["n"] + 1) or 1)
    monkeypatch.setattr(outbox_publisher.time, "sleep", lambda s: outbox_publisher._handle_stop(None, None))
    outbox_publisher._running = True
    outbox_publisher.run_worker(0.01)
    assert called["n"] == 1

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:19999")
    monkeypatch.setenv("FINGUARD_STREAMING_ENABLED", "1")
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["detail"]["checks"]["kafka"] == "unreachable"


def test_p6_404_error_branches(client):
    missing = uuid.uuid4()
    assert client.get(f"/accounts/{missing}/balance").status_code == 404
    assert client.get(f"/accounts/{missing}/transactions").status_code == 404
    assert client.post(f"/fraud/alerts/{missing}/assign", json={"analyst_id": str(missing)}).status_code == 404
    assert client.post(f"/fraud/alerts/{missing}/investigate").status_code == 404
    assert client.post(f"/fraud/alerts/{missing}/resolve", json={"decision": "APPROVED", "analyst_notes": "note ok"}).status_code == 404
    assert client.patch(f"/admin/users/{missing}", json={"full_name": "X"}).status_code == 404
    assert client.post(f"/admin/users/{missing}/reset-password", json={"new_password": "StrongPassword123!"}).status_code == 404
    assert client.get(f"/admin/users/{missing}/login-history").status_code == 404
    assert client.get(f"/admin/users/{missing}/sessions").status_code == 404
    assert client.post(f"/admin/approvals/role-change?user_id={missing}&new_role=ADMIN").status_code == 404
    assert client.post(f"/deposits/{missing}/approve").status_code == 404


def test_p6_rbac_403_and_docs_coverage(client):
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200

    cust = User(id=uuid.uuid4(), email=f"p6cu-{uuid.uuid4().hex[:6]}@example.com", full_name="Cust", password_hash="x", role="CUSTOMER", status="ACTIVE")
    missing = uuid.uuid4()
    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: cust
    try:
        assert client.get("/admin/audit-logs").status_code == 403
        assert client.get("/admin/users").status_code == 403
        assert client.post("/admin/users", json={"email": "x@example.com", "full_name": "X", "password": "StrongPassword123!", "role": "CUSTOMER"}).status_code == 403
        assert client.patch(f"/admin/users/{missing}", json={"full_name": "X"}).status_code == 403
        assert client.post(f"/admin/users/{missing}/reset-password", json={"new_password": "StrongPassword123!"}).status_code == 403
        assert client.get(f"/admin/users/{missing}/login-history").status_code == 403
        assert client.get(f"/admin/users/{missing}/sessions").status_code == 403
        assert client.delete(f"/admin/users/{missing}/sessions/{missing}").status_code == 403
        assert client.post(f"/admin/approvals/role-change?user_id={missing}&new_role=ADMIN").status_code == 403
        assert client.post(f"/admin/approvals/{missing}/approve").status_code == 403
        assert client.post("/deposits/request", json={"account_id": str(missing), "amount_cents": 100}).status_code == 403
        assert client.post(f"/deposits/{missing}/approve").status_code == 403
        assert client.get(f"/accounts/{missing}/statement").status_code == 404
        assert client.get("/fraud/alerts").status_code == 403
        assert client.post(f"/fraud/alerts/{missing}/assign", json={"analyst_id": str(missing)}).status_code == 403
        assert client.post(f"/fraud/alerts/{missing}/investigate").status_code == 403
        assert client.post(f"/fraud/alerts/{missing}/resolve", json={"decision": "APPROVED", "analyst_notes": "note ok"}).status_code == 403
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
