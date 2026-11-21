import hashlib
import re
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from rag_api import main
from rag_api.config import Settings
from rag_api.main import create_app
from rag_api.models import User

PASSWORD = "correct-horse-battery"


def make_client(tmp_path, **overrides):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        data_dir=str(tmp_path),
        jwt_secret="x" * 48,
        **overrides,
    )
    app = create_app(settings, SimpleNamespace(index_signature=lambda: "t"))
    return TestClient(app), app


@pytest.fixture
def verified(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_mail", lambda settings, to, subject, body: sent.append((to, body)))
    client, app = make_client(tmp_path, require_email_verification=True)
    with client:
        yield client, app, sent


@pytest.fixture
def plain(tmp_path):
    client, app = make_client(tmp_path)
    with client:
        yield client, app


def signup(client, email="a@example.com"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": "A"})


def token_from(sent):
    return re.search(r"\?verify=([\w-]+)", sent[-1][1]).group(1)


def test_verification_flow(verified):
    client, app, sent = verified
    response = signup(client)
    assert response.status_code == 202 and response.json() == {"verification_required": True}
    assert "set-cookie" not in response.headers and "access_token" not in response.text
    creds = {"email": "a@example.com", "password": PASSWORD}
    login = client.post("/api/v1/auth/login", json=creds)
    assert login.status_code == 403 and login.json()["detail"] == "email_not_verified"
    with app.state.sessions() as db:
        row = db.query(User).one()
        token = token_from(sent)
        assert row.email_verification_token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in (row.email_verification_token_hash or "")
    done = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert done.status_code == 200 and done.json()["access_token"] and done.json()["csrf_token"]
    assert "aster_session" in done.headers["set-cookie"]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400  # single use
    assert client.post("/api/v1/auth/login", json=creds).status_code == 200


def test_invalid_and_expired_tokens(verified):
    client, app, sent = verified
    signup(client)
    assert client.post("/api/v1/auth/verify-email", json={"token": "bogus"}).status_code == 400
    with app.state.sessions() as db:
        db.query(User).update({User.email_verification_expires_at: time.time() - 1})
        db.commit()
    assert client.post("/api/v1/auth/verify-email", json={"token": token_from(sent)}).status_code == 400


def test_resend_is_always_202_and_only_mails_unverified(verified):
    client, _, sent = verified
    signup(client)
    assert len(sent) == 1
    for email in ("a@example.com", "nobody@example.com"):
        assert client.post("/api/v1/auth/resend-verification", json={"email": email}).status_code == 202
    assert len(sent) == 2
    client.post("/api/v1/auth/verify-email", json={"token": token_from(sent)})
    assert client.post("/api/v1/auth/resend-verification", json={"email": "a@example.com"}).status_code == 202
    assert len(sent) == 2


def test_mail_failure_does_not_break_register(verified, monkeypatch):
    client, _, sent = verified

    def boom(*args):
        raise OSError("smtp down")

    monkeypatch.setattr(main, "send_mail", boom)
    assert signup(client).status_code == 202
    monkeypatch.setattr(main, "send_mail", lambda settings, to, subject, body: sent.append((to, body)))
    client.post("/api/v1/auth/resend-verification", json={"email": "a@example.com"})
    assert sent


def test_invite_requires_verified_target(verified):
    client, _, sent = verified
    signup(client, "owner@example.com")
    client.cookies.clear()
    owner = client.post("/api/v1/auth/verify-email", json={"token": token_from(sent)}).json()
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    client.cookies.clear()
    signup(client, "new@example.com")
    invite = {"email": "new@example.com", "role": "viewer"}
    assert client.post("/api/v1/admin/members", headers=headers, json=invite).status_code == 409
    client.post("/api/v1/auth/verify-email", json={"token": token_from(sent)})
    client.cookies.clear()
    assert client.post("/api/v1/admin/members", headers=headers, json=invite).status_code == 200


def test_hosted_requires_smtp_and_cors_rejects_wildcard(tmp_path):
    base = {
        "environment": "hosted",
        "database_url": "postgresql://x/y",
        "storage_backend": "supabase",
        "supabase_url": "u",
        "supabase_service_key": "k",
        "vector_backend": "pinecone",
        "jwt_secret": "x" * 48,
        "data_dir": str(tmp_path),
    }
    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(**base).validate_runtime()
    Settings(**base, smtp_host="smtp.test", web_url="https://app.test").validate_runtime()
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(cors_origins="*", data_dir=str(tmp_path)).validate_runtime()


def test_unverified_mode_off_keeps_session_response(plain):
    client, _ = plain
    response = signup(client)
    assert response.status_code == 200 and response.json()["access_token"]
    cookie = response.headers["set-cookie"]
    assert "aster_session=" in cookie and "HttpOnly" in cookie and "Path=/" in cookie
    assert "Max-Age=7200" in cookie and "SameSite=lax" in cookie and "Secure" not in cookie


def test_hosted_cookie_is_samesite_none_secure(plain):
    client, app = plain
    app.state.settings.environment = "hosted"
    cookie = signup(client).headers["set-cookie"]
    assert "SameSite=none" in cookie and "Secure" in cookie and "HttpOnly" in cookie


def test_cookie_requires_csrf_but_bearer_does_not(plain):
    client, _ = plain
    body = signup(client).json()  # the client jar now holds the session cookie
    bearer = {"Authorization": f"Bearer {body['access_token']}"}
    group = {"name": "g", "members": []}
    assert client.get("/api/v1/auth/me").json()["csrf_token"] == body["csrf_token"]
    assert client.post("/api/v1/groups", json=group).status_code == 403
    assert client.post("/api/v1/groups", json=group, headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert (
        client.post("/api/v1/groups", json=group, headers={"X-CSRF-Token": body["csrf_token"]}).status_code
        == 200
    )
    # Bearer wins over the cookie and needs no CSRF header; me() has no csrf_token for bearer auth.
    assert client.post("/api/v1/groups", json=group, headers=bearer).status_code == 200
    assert "csrf_token" not in client.get("/api/v1/auth/me", headers=bearer).json()


def test_logout_clears_cookie_and_old_cookie_is_rejected(plain):
    client, _ = plain
    body = signup(client).json()
    old = client.cookies.get("aster_session")
    out = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]})
    assert out.status_code == 200 and "Max-Age=0" in out.headers["set-cookie"]
    client.cookies.clear()
    client.cookies.set("aster_session", old)
    assert client.get("/api/v1/auth/me").status_code == 401
