"""Coverage for Keycloak Admin REST user provisioning."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import pytest
from fastapi import HTTPException

from news_dashboard.keycloak_admin import create_keycloak_user


def _enable_keycloak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://idp.example")
    monkeypatch.setenv("KEYCLOAK_REALM", "nd")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "nd-client")
    # Generated at runtime so no credential literal lives in the source.
    monkeypatch.setenv("KEYCLOAK_ADMIN_CLIENT_SECRET", secrets.token_hex(8))


class _FakeResp:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """First POST = admin token, second POST = user creation."""

    token_resp: _FakeResp
    create_resp: _FakeResp

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self._calls = 0

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    async def post(self, *_a: Any, **_k: Any) -> _FakeResp:
        self._calls += 1
        return type(self).token_resp if self._calls == 1 else type(self).create_resp


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, token: _FakeResp, create: _FakeResp) -> None:
    cls = type("Patched", (_FakeAsyncClient,), {"token_resp": token, "create_resp": create})
    monkeypatch.setattr("news_dashboard.keycloak_admin.httpx.AsyncClient", cls)


def test_create_disabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEYCLOAK_AUTH_ENABLED", raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_keycloak_user("alice", "pw"))
    assert exc.value.status_code == 400


def test_create_requires_admin_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    monkeypatch.delenv("KEYCLOAK_ADMIN_CLIENT_SECRET", raising=False)
    _patch_httpx(monkeypatch, _FakeResp(200, {"access_token": "t"}), _FakeResp(201))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_keycloak_user("alice", "pw"))
    assert exc.value.status_code == 500


def test_create_token_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(monkeypatch, _FakeResp(401, {}), _FakeResp(201))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_keycloak_user("alice", "pw"))
    assert exc.value.status_code == 502


def test_create_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(monkeypatch, _FakeResp(200, {"access_token": "t"}), _FakeResp(409))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_keycloak_user("alice", "pw"))
    assert exc.value.status_code == 409


def test_create_success_returns_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_keycloak(monkeypatch)
    _patch_httpx(
        monkeypatch,
        _FakeResp(200, {"access_token": "t"}),
        _FakeResp(
            201,
            headers={"Location": "https://idp.example/admin/realms/nd/users/abc-123"},
        ),
    )
    result = asyncio.run(create_keycloak_user("alice", "pw", email="a@example.com"))
    assert result["id"] == "abc-123"
    assert result["username"] == "alice"
    assert result["email"] == "a@example.com"
    assert result["temporary"] is True
