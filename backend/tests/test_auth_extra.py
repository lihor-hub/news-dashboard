"""Additional auth coverage: config helpers, keycloak flow, session edges, admin CRUD."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import news_dashboard.db as db_mod
from news_dashboard import auth as auth_mod
from news_dashboard.auth import (
    create_user,
    exchange_keycloak_code,
    keycloak_authorization_url,
    keycloak_config,
    keycloak_logout_url,
    keycloak_token_request_data,
    verify_session_token,
)
from news_dashboard.db import init_db
from news_dashboard.main import app


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "test.db"
    init_db(db)
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    return db


def _enable_keycloak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://idp.example")
    monkeypatch.setenv("KEYCLOAK_REALM", "nd")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "nd-client")


# ── config helpers ────────────────────────────────────────────────────────────


def test_session_days_invalid_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_DAYS", "not-an-int")
    assert auth_mod._session_days() == 30


def test_keycloak_realm_url_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://pub.example/")
    monkeypatch.setenv("KEYCLOAK_INTERNAL_SERVER_URL", "http://idp:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "nd")
    cfg = keycloak_config()
    assert cfg.public_realm_url == "https://pub.example/realms/nd"
    assert cfg.internal_realm_url == "http://idp:8080/realms/nd"


def test_keycloak_token_request_data_includes_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "s3cret")
    data = keycloak_token_request_data("the-code")
    assert data["code"] == "the-code"
    assert data["client_secret"] == "s3cret"  # noqa: S105 - test fixture value
    assert data["grant_type"] == "authorization_code"


# ── keycloak url builders when disabled/unconfigured ─────────────────────────


def test_keycloak_authorization_url_raises_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KEYCLOAK_AUTH_ENABLED", raising=False)
    with pytest.raises(HTTPException) as exc:
        keycloak_authorization_url("state")
    assert exc.value.status_code == 500


def test_keycloak_logout_url_disabled_returns_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEYCLOAK_AUTH_ENABLED", raising=False)
    assert keycloak_logout_url() == "/login"


def test_keycloak_logout_url_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    out = keycloak_logout_url()
    assert "protocol/openid-connect/logout" in out
    assert "client_id=nd-client" in out


# ── verify_session_token edges ───────────────────────────────────────────────


def test_verify_session_token_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SESSION_SECRET", "x" * 32)
    assert verify_session_token("not-a-real-token") is None


# ── get_current_user via the real dependency (no override) ───────────────────


def test_me_rejects_invalid_session_cookie(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SESSION_SECRET", "x" * 32)
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.get("/api/auth/me", cookies={"nd_session": "tampered"})
    assert resp.status_code == 401


def test_me_rejects_when_user_missing(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SESSION_SECRET", "x" * 32)
    app.dependency_overrides.clear()
    # Valid signature but a user id that does not exist in the DB.
    from news_dashboard.auth import create_session_token

    token = create_session_token(999999, is_admin=False)
    client = TestClient(app)
    resp = client.get("/api/auth/me", cookies={"nd_session": token})
    assert resp.status_code == 401


# ── exchange_keycloak_code with a faked httpx client ─────────────────────────


class _FakeResp:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """Drives exchange_keycloak_code: first POST = token, then GET = userinfo."""

    token_resp: _FakeResp
    user_resp: _FakeResp

    def __init__(self, *_a: Any, **_k: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    async def post(self, *_a: Any, **_k: Any) -> _FakeResp:
        return type(self).token_resp

    async def get(self, *_a: Any, **_k: Any) -> _FakeResp:
        return type(self).user_resp


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, token: _FakeResp, user: _FakeResp) -> None:
    cls = type("Patched", (_FakeAsyncClient,), {"token_resp": token, "user_resp": user})
    monkeypatch.setattr("news_dashboard.auth.httpx.AsyncClient", cls)


def test_exchange_disabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEYCLOAK_AUTH_ENABLED", raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exchange_keycloak_code("code"))
    assert exc.value.status_code == 400


def test_exchange_token_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(monkeypatch, _FakeResp(401, {}), _FakeResp(200, {}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exchange_keycloak_code("code"))
    assert exc.value.status_code == 401


def test_exchange_no_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(monkeypatch, _FakeResp(200, {}), _FakeResp(200, {}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exchange_keycloak_code("code"))
    assert exc.value.status_code == 401


def test_exchange_userinfo_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(monkeypatch, _FakeResp(200, {"access_token": "t"}), _FakeResp(500, {}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exchange_keycloak_code("code"))
    assert exc.value.status_code == 401


def test_exchange_success_creates_user(tmp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(
        monkeypatch,
        _FakeResp(200, {"access_token": "t"}),
        _FakeResp(200, {"preferred_username": "kc_user", "email": "kc@example.com"}),
    )
    user = asyncio.run(exchange_keycloak_code("code"))
    assert user["username"] == "kc_user"
    assert user["email"] == "kc@example.com"


# ── admin user CRUD endpoints (admin override is autouse) ────────────────────


def test_admin_get_user_found_and_missing(tmp_db: Path) -> None:
    created = create_user("dora", "pw123456", email="dora@example.com")
    client = TestClient(app)
    ok = client.get(f"/api/admin/users/{created['id']}")
    assert ok.status_code == 200
    assert ok.json()["username"] == "dora"
    missing = client.get("/api/admin/users/987654")
    assert missing.status_code == 404


def test_admin_update_password_found_and_missing(tmp_db: Path) -> None:
    created = create_user("evan", "pw123456")
    client = TestClient(app)
    ok = client.patch(f"/api/admin/users/{created['id']}/password", json={"password": "newpass123"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "updated"
    missing = client.patch("/api/admin/users/987654/password", json={"password": "newpass123"})
    assert missing.status_code == 404


def test_admin_create_user_conflict_on_duplicate(tmp_db: Path) -> None:
    client = TestClient(app)
    first = client.post("/api/admin/users", json={"username": "frank", "password": "pw123456"})
    assert first.status_code == 200
    dup = client.post("/api/admin/users", json={"username": "frank", "password": "pw123456"})
    assert dup.status_code == 409


def test_admin_generate_user_returns_credentials(tmp_db: Path) -> None:
    client = TestClient(app)
    resp = client.post("/api/admin/users/generate", json={"username": "grace"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "grace"
    assert body["is_admin"] is False
    # The generated password is returned once and must actually log the user in.
    assert isinstance(body["password"], str)
    assert len(body["password"]) >= 12
    login = client.post(
        "/api/auth/login",
        json={"username": "grace", "password": body["password"]},
    )
    assert login.status_code == 200


def test_admin_generate_user_rejects_blank_username(tmp_db: Path) -> None:
    client = TestClient(app)
    resp = client.post("/api/admin/users/generate", json={"username": "   "})
    assert resp.status_code == 422


def test_admin_generate_user_conflict_on_duplicate(tmp_db: Path) -> None:
    client = TestClient(app)
    first = client.post("/api/admin/users/generate", json={"username": "heidi"})
    assert first.status_code == 200
    dup = client.post("/api/admin/users/generate", json={"username": "heidi"})
    assert dup.status_code == 409


def test_admin_generate_user_uses_keycloak_when_enabled(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_keycloak(monkeypatch)
    monkeypatch.setenv("KEYCLOAK_ADMIN_CLIENT_SECRET", secrets.token_hex(8))

    captured: dict[str, Any] = {}

    async def fake_create(username: str, password: str, **kwargs: Any) -> dict[str, Any]:
        captured["username"] = username
        captured["password"] = password
        return {"id": "kc-1", "username": username, "email": None, "temporary": True}

    monkeypatch.setattr("news_dashboard.keycloak_admin.create_keycloak_user", fake_create)
    client = TestClient(app)
    resp = client.post("/api/admin/users/generate", json={"username": "ivan"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "keycloak"
    assert body["id"] == "kc-1"
    assert body["temporary"] is True
    assert body["password"] == captured["password"]
    assert captured["username"] == "ivan"
