import uuid
from app.db.models import User
from app.security.passwords import hash_password


def test_httponly_refresh_cookie_login_refresh_logout(client, session):
    email = f"ck-{uuid.uuid4().hex[:8]}@example.com"
    pwd = "StrongPassword!123"
    u = User(id=uuid.uuid4(), email=email, full_name="Cookie User", password_hash=hash_password(pwd), role="CUSTOMER", status="ACTIVE")
    session.add(u)
    session.commit()

    login = client.post("/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    sc = login.headers.get("set-cookie", "").lower()
    assert "finguard_refresh_token=" in sc and "httponly" in sc and "samesite=strict" in sc

    # Refresh using cookie only (empty JSON body)
    ref = client.post("/auth/refresh", json={})
    assert ref.status_code == 200
    assert ref.json()["access_token"]

    # Logout clears cookie
    out = client.post("/auth/logout", json={})
    assert out.status_code == 204
    assert client.post("/auth/refresh", json={}).status_code == 401
