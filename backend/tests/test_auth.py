"""Tests for #126: users table, login/logout, session cookies, and auth middleware."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import news_dashboard.db as db_mod
from news_dashboard.auth import (
    authenticate,
    bootstrap_admin,
    create_session_token,
    create_user,
    delete_user,
    ensure_keycloak_user,
    get_user_by_id,
    hash_password,
    keycloak_auth_metadata,
    keycloak_authorization_url,
    list_users,
    update_password,
    user_count_from_row,
    verify_password,
    verify_session_token,
)
from news_dashboard.db import init_db
from news_dashboard.main import app

# ── Helpers ──────────────────────────────────────────────────────────────────


def _fresh_client() -> TestClient:
    """Return a TestClient with NO dependency overrides — tests real auth flow."""
    app.dependency_overrides.clear()
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fresh SQLite DB with DB_PATH patched so auth helpers use it."""
    db = tmp_path / "test.db"
    init_db(db)
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    return db


# ── Password hashing ──────────────────────────────────────────────────────────


def test_hash_and_verify_password() -> None:
    h = hash_password("hunter2")
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)


def test_verify_bad_hash() -> None:
    assert not verify_password("x", "not-a-valid-hash")


# ── Session tokens ────────────────────────────────────────────────────────────


def test_create_and_verify_token() -> None:
    token = create_session_token(42, is_admin=True)
    payload = verify_session_token(token)
    assert payload is not None
    assert payload["user_id"] == 42
    assert payload["is_admin"] is True


def test_tampered_token_rejected() -> None:
    token = create_session_token(1, is_admin=False)
    bad = token[:-4] + "xxxx"
    assert verify_session_token(bad) is None


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import itsdangerous

    token = create_session_token(1, is_admin=False)

    def reject_all(self: Any, *a: Any, **kw: Any) -> Any:
        msg = "forced"
        raise itsdangerous.SignatureExpired(msg)

    monkeypatch.setattr(itsdangerous.URLSafeTimedSerializer, "loads", reject_all)
    assert verify_session_token(token) is None


# ── User CRUD ─────────────────────────────────────────────────────────────────


def test_create_and_get_user(tmp_db: Path) -> None:
    user = create_user("alice", "secret", email="a@b.com", is_admin=False)
    assert user["username"] == "alice"
    assert user["email"] == "a@b.com"
    assert not user["is_admin"]

    fetched = get_user_by_id(user["id"])
    assert fetched is not None
    assert fetched["username"] == "alice"


def test_list_users(tmp_db: Path) -> None:
    create_user("u1", "p1")
    create_user("u2", "p2")
    usernames = [u["username"] for u in list_users()]
    assert "u1" in usernames
    assert "u2" in usernames


def test_update_password(tmp_db: Path) -> None:
    user = create_user("bob", "old")
    assert update_password(user["id"], "new-pass")
    assert authenticate("bob", "new-pass") is not None
    assert authenticate("bob", "old") is None


def test_delete_user(tmp_db: Path) -> None:
    user = create_user("carol", "pw")
    assert delete_user(user["id"])
    assert get_user_by_id(user["id"]) is None


# ── authenticate() ────────────────────────────────────────────────────────────


def test_authenticate_correct(tmp_db: Path) -> None:
    create_user("dave", "correct")
    result = authenticate("dave", "correct")
    assert result is not None
    assert result["username"] == "dave"
    assert "password_hash" not in result


def test_authenticate_wrong_password(tmp_db: Path) -> None:
    create_user("eve", "right")
    assert authenticate("eve", "wrong") is None


def test_authenticate_unknown_user(tmp_db: Path) -> None:
    assert authenticate("nobody", "pw") is None


# ── Keycloak auth ──────────────────────────────────────────────────────────────


def test_keycloak_auth_metadata_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEYCLOAK_AUTH_ENABLED", raising=False)
    assert keycloak_auth_metadata()["provider"] == "password"


def test_keycloak_authorization_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("NEWS_DASHBOARD_BASE_URL", "https://news.lihor.ro")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://news.lihor.ro/keycloak")
    url = keycloak_authorization_url("state-123")
    assert url.startswith(
        "https://news.lihor.ro/keycloak/realms/news-dashboard/protocol/openid-connect/auth?"
    )
    assert "client_id=news-dashboard" in url
    assert "redirect_uri=https%3A%2F%2Fnews.lihor.ro%2Fauth%2Fcallback" in url
    assert "state=state-123" in url


def test_ensure_keycloak_user_creates_local_user(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_ADMIN_USERNAMES", "ioachim")
    user = ensure_keycloak_user(
        {"preferred_username": "ioachim", "email": "ioachim@example.test", "sub": "kc-sub"}
    )
    assert user["username"] == "ioachim"
    assert user["email"] == "ioachim@example.test"
    assert user["is_admin"]


def test_password_login_disabled_when_keycloak_enabled(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    create_user("local", "pw")
    assert authenticate("local", "pw") is None


# ── Bootstrap ─────────────────────────────────────────────────────────────────


def test_bootstrap_creates_first_admin(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "adminpass")
    bootstrap_admin()
    users = list_users()
    assert len(users) == 1
    assert users[0]["username"] == "admin"
    assert users[0]["is_admin"]


def test_bootstrap_noop_if_users_exist(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "pw")
    create_user("existing", "pw2")
    bootstrap_admin()
    users = list_users()
    assert len(users) == 1
    assert users[0]["username"] == "existing"


def test_user_count_from_row_reads_aliased_count() -> None:
    assert user_count_from_row({"n": 3}) == 3


# ── Login / logout API ────────────────────────────────────────────────────────


def test_login_sets_cookie(tmp_db: Path) -> None:
    create_user("frank", "frankpass", is_admin=False)
    client = _fresh_client()
    resp = client.post("/api/auth/login", json={"username": "frank", "password": "frankpass"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "frank"
    assert "nd_session" in resp.cookies


def test_login_wrong_password_returns_401(tmp_db: Path) -> None:
    create_user("grace", "right")
    client = _fresh_client()
    resp = client.post("/api/auth/login", json={"username": "grace", "password": "wrong"})
    assert resp.status_code == 401
    assert "nd_session" not in resp.cookies


def test_logout_clears_cookie(tmp_db: Path) -> None:
    create_user("henry", "pw")
    client = _fresh_client()
    client.post("/api/auth/login", json={"username": "henry", "password": "pw"})
    resp = client.get("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.cookies.get("nd_session", "") == ""


# ── Auth middleware: protected routes require session ─────────────────────────


def test_protected_route_without_session_returns_401(tmp_db: Path) -> None:
    client = _fresh_client()
    resp = client.get("/api/articles", cookies={})
    assert resp.status_code == 401


def test_protected_route_with_valid_session(tmp_db: Path) -> None:
    user = create_user("irene", "pw")
    token = create_session_token(user["id"], is_admin=False)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.get("/api/articles")
    assert resp.status_code == 200


def test_auth_me_returns_current_user(tmp_db: Path) -> None:
    user = create_user("jane", "pw", is_admin=True)
    token = create_session_token(user["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "jane"
    assert data["is_admin"] is True


# ── Admin-only routes ─────────────────────────────────────────────────────────


def test_admin_route_blocked_for_non_admin(tmp_db: Path) -> None:
    user = create_user("regular", "pw", is_admin=False)
    token = create_session_token(user["id"], is_admin=False)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.get("/api/admin/users")
    assert resp.status_code == 403


def test_admin_list_users(tmp_db: Path) -> None:
    admin = create_user("superadmin", "pw", is_admin=True)
    create_user("other", "pw2")
    token = create_session_token(admin["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.get("/api/admin/users")
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()["items"]]
    assert "superadmin" in usernames
    assert "other" in usernames


def test_admin_create_user(tmp_db: Path) -> None:
    admin = create_user("superadmin", "pw", is_admin=True)
    token = create_session_token(admin["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "newpass", "is_admin": False},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "newuser"


def test_admin_delete_user(tmp_db: Path) -> None:
    admin = create_user("theadmin", "pw", is_admin=True)
    target = create_user("victim", "pw2", is_admin=False)
    token = create_session_token(admin["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.delete(f"/api/admin/users/{target['id']}")
    assert resp.status_code == 200
    assert get_user_by_id(target["id"]) is None


def test_admin_cannot_delete_self(tmp_db: Path) -> None:
    admin = create_user("self", "pw", is_admin=True)
    token = create_session_token(admin["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.delete(f"/api/admin/users/{admin['id']}")
    assert resp.status_code == 400


# ── Health endpoint is public ─────────────────────────────────────────────────


def test_health_is_public(tmp_db: Path) -> None:
    client = _fresh_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
