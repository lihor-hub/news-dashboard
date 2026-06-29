"""Tests for #126: users table, login/logout, session cookies, and auth middleware."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard import login_throttle
from news_dashboard.auth import (
    authenticate,
    bootstrap_admin,
    consume_otp,
    create_otp_for_user,
    create_session_token,
    create_user,
    delete_user,
    ensure_keycloak_user,
    get_user_by_id,
    hash_password,
    init_auth,
    keycloak_auth_metadata,
    keycloak_authorization_url,
    keycloak_registration_url,
    keycloak_token_request_data,
    list_users,
    update_password,
    user_count_from_row,
    verify_password,
    verify_session_token,
)
from news_dashboard.db import connect, init_db
from news_dashboard.main import app

# ── Helpers ──────────────────────────────────────────────────────────────────


def _fresh_client() -> TestClient:
    """Return a TestClient with NO dependency overrides — tests real auth flow."""
    app.dependency_overrides.clear()
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def tmp_db(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Fresh PostgreSQL test database routed through DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    return pg_clean


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


def test_create_and_get_user(tmp_db: str) -> None:
    user = create_user("alice", "secret", email="a@b.com", is_admin=False)
    assert user["username"] == "alice"
    assert user["email"] == "a@b.com"
    assert not user["is_admin"]

    fetched = get_user_by_id(user["id"])
    assert fetched is not None
    assert fetched["username"] == "alice"


def test_create_user_passes_boolean_admin_value(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCursor:
        def fetchone(self) -> dict[str, Any]:
            return {
                "id": 1,
                "username": "admin",
                "email": None,
                "is_admin": True,
                "created_at": "now",
            }

    class FakeConnection:
        params: tuple[Any, ...] | None = None

        def execute(self, _sql: str, params: tuple[Any, ...]) -> FakeCursor:
            self.params = params
            return FakeCursor()

    class FakeConnect:
        conn = FakeConnection()

        def __enter__(self) -> FakeConnection:
            return self.conn

        def __exit__(self, *args: object) -> None:
            return None

    fake_connect = FakeConnect()
    monkeypatch.setattr("news_dashboard.auth.connect", lambda: fake_connect)

    create_user("admin", "secret", is_admin=True)

    assert fake_connect.conn.params is not None
    assert fake_connect.conn.params[3] is True


def test_list_users(tmp_db: str) -> None:
    create_user("u1", "p1")
    create_user("u2", "p2")
    usernames = [u["username"] for u in list_users()]
    assert "u1" in usernames
    assert "u2" in usernames


def test_update_password(tmp_db: str) -> None:
    user = create_user("bob", "old")
    assert update_password(user["id"], "new-pass")
    assert authenticate("bob", "new-pass") is not None
    assert authenticate("bob", "old") is None


def test_delete_user(tmp_db: str) -> None:
    user = create_user("carol", "pw")
    assert delete_user(user["id"])
    assert get_user_by_id(user["id"]) is None


# ── authenticate() ────────────────────────────────────────────────────────────


def test_authenticate_correct(tmp_db: str) -> None:
    create_user("dave", "correct")
    result = authenticate("dave", "correct")
    assert result is not None
    assert result["username"] == "dave"
    assert "password_hash" not in result


def test_authenticate_wrong_password(tmp_db: str) -> None:
    create_user("eve", "right")
    assert authenticate("eve", "wrong") is None


def test_authenticate_unknown_user(tmp_db: str) -> None:
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


def test_keycloak_token_request_data_includes_optional_client_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("NEWS_DASHBOARD_BASE_URL", "https://news.lihor.ro")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "news-dashboard")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "client-secret")

    data = keycloak_token_request_data("code-123")

    assert data == {
        "grant_type": "authorization_code",
        "client_id": "news-dashboard",
        "client_secret": "client-secret",
        "code": "code-123",
        "redirect_uri": "https://news.lihor.ro/auth/callback",
    }


def test_keycloak_token_request_data_omits_blank_client_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", " ")

    data = keycloak_token_request_data("code-123")

    assert "client_secret" not in data


def test_ensure_keycloak_user_creates_local_user(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_ADMIN_USERNAMES", "ioachim")
    user = ensure_keycloak_user(
        {"preferred_username": "ioachim", "email": "ioachim@example.test", "sub": "kc-sub"}
    )
    assert user["username"] == "ioachim"
    assert user["email"] == "ioachim@example.test"
    assert user["is_admin"]


def test_password_login_disabled_when_keycloak_enabled(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    create_user("local", "pw")
    assert authenticate("local", "pw") is None


def test_init_auth_requires_session_secret_for_keycloak(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://news.lihor.ro/keycloak")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("TEST_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="SESSION_SECRET env var is not set"):
        init_auth()


def test_init_auth_accepts_keycloak_when_session_secret_is_set(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://news.lihor.ro/keycloak")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")

    init_auth()


# ── Bootstrap ─────────────────────────────────────────────────────────────────


def test_bootstrap_creates_first_admin(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "adminpass")
    bootstrap_admin()
    users = list_users()
    assert len(users) == 1
    assert users[0]["username"] == "admin"
    assert users[0]["is_admin"]


def test_bootstrap_noop_if_users_exist(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_login_sets_cookie(tmp_db: str) -> None:
    create_user("frank", "frankpass", is_admin=False)
    client = _fresh_client()
    resp = client.post("/api/auth/login", json={"username": "frank", "password": "frankpass"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "frank"
    assert "nd_session" in resp.cookies


def test_login_wrong_password_returns_401(tmp_db: str) -> None:
    create_user("grace", "right")
    client = _fresh_client()
    resp = client.post("/api/auth/login", json={"username": "grace", "password": "wrong"})
    assert resp.status_code == 401
    assert "nd_session" not in resp.cookies


def test_logout_clears_cookie(tmp_db: str) -> None:
    create_user("henry", "pw")
    client = _fresh_client()
    client.post("/api/auth/login", json={"username": "henry", "password": "pw"})
    resp = client.get("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.cookies.get("nd_session", "") == ""


# ── Auth middleware: protected routes require session ─────────────────────────


def test_protected_route_without_session_returns_401(tmp_db: str) -> None:
    client = _fresh_client()
    resp = client.get("/api/articles", cookies={})
    assert resp.status_code == 401


def test_protected_route_with_valid_session(tmp_db: str) -> None:
    user = create_user("irene", "pw")
    token = create_session_token(user["id"], is_admin=False)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.get("/api/articles")
    assert resp.status_code == 200


def test_auth_me_returns_current_user(tmp_db: str) -> None:
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


def test_admin_route_blocked_for_non_admin(tmp_db: str) -> None:
    user = create_user("regular", "pw", is_admin=False)
    token = create_session_token(user["id"], is_admin=False)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.get("/api/admin/users")
    assert resp.status_code == 403


def test_admin_list_users(tmp_db: str) -> None:
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


def test_admin_create_user(tmp_db: str) -> None:
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


def test_admin_delete_user(tmp_db: str) -> None:
    admin = create_user("theadmin", "pw", is_admin=True)
    target = create_user("victim", "pw2", is_admin=False)
    token = create_session_token(admin["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.delete(f"/api/admin/users/{target['id']}")
    assert resp.status_code == 200
    assert get_user_by_id(target["id"]) is None


def test_admin_cannot_delete_self(tmp_db: str) -> None:
    admin = create_user("self", "pw", is_admin=True)
    token = create_session_token(admin["id"], is_admin=True)
    client = _fresh_client()
    client.cookies.set("nd_session", token)
    resp = client.delete(f"/api/admin/users/{admin['id']}")
    assert resp.status_code == 400


# ── Health endpoint is public ─────────────────────────────────────────────────


def test_health_is_public(tmp_db: str) -> None:
    client = _fresh_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}
    # Public health must not leak internal DB details.
    assert "database" not in body
    assert "next_ingest_at" not in body


# ── OTP authentication ────────────────────────────────────────────────────────


def test_create_and_consume_otp(tmp_db: str) -> None:
    user = create_user("otp_user", "irrelevant", email="otp@example.com")
    otp = create_otp_for_user(user["id"])
    assert len(otp) == 6
    assert otp.isdigit()

    result = consume_otp("otp@example.com", otp)
    assert result is not None
    assert result["username"] == "otp_user"


def test_otp_wrong_code_rejected(tmp_db: str) -> None:
    user = create_user("otp_wrong", "irrelevant", email="wrong@example.com")
    create_otp_for_user(user["id"])
    assert consume_otp("wrong@example.com", "000000") is None


def test_otp_consumed_only_once(tmp_db: str) -> None:
    user = create_user("otp_once", "irrelevant", email="once@example.com")
    otp = create_otp_for_user(user["id"])
    assert consume_otp("once@example.com", otp) is not None
    # Second use of the same OTP must fail
    assert consume_otp("once@example.com", otp) is None


def test_otp_unknown_email_returns_none(tmp_db: str) -> None:
    assert consume_otp("nobody@example.com", "123456") is None


def test_otp_expired_rejected(tmp_db: str) -> None:
    from news_dashboard.db import connect as db_connect

    user = create_user("otp_exp", "irrelevant", email="exp@example.com")
    create_otp_for_user(user["id"])

    # Force expiry by backdating the record in the database
    with db_connect() as conn:
        conn.execute(
            "UPDATE user_otps SET expires_at = NOW() - INTERVAL '1 hour' WHERE user_id = %s",
            (user["id"],),
        )
    assert consume_otp("exp@example.com", "000000") is None


def test_otp_request_endpoint_returns_sent_for_unknown_email(tmp_db: str) -> None:
    client = _fresh_client()
    resp = client.post("/api/auth/otp/request", json={"email": "ghost@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}


def test_otp_login_endpoint_full_flow(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import news_dashboard.email as email_mod

    sent: list[tuple[str, str]] = []

    def _fake_send(to: str, code: str) -> None:
        sent.append((to, code))

    monkeypatch.setattr(email_mod, "send_otp_email", _fake_send)

    create_user("ep_user", "pw", email="ep@example.com")
    client = _fresh_client()

    resp = client.post("/api/auth/otp/request", json={"email": "ep@example.com"})
    assert resp.status_code == 200
    assert len(sent) == 1
    _, code = sent[0]

    resp = client.post("/api/auth/otp/login", json={"email": "ep@example.com", "otp": code})
    assert resp.status_code == 200
    assert resp.json()["username"] == "ep_user"
    assert "nd_session" in resp.cookies


def test_otp_login_endpoint_bad_code(tmp_db: str) -> None:
    create_user("bad_otp", "pw", email="bad@example.com")
    client = _fresh_client()
    resp = client.post("/api/auth/otp/login", json={"email": "bad@example.com", "otp": "000000"})
    assert resp.status_code == 401


def test_health_details_requires_admin(tmp_db: str) -> None:
    client = _fresh_client()
    resp = client.get("/api/health/details")
    assert resp.status_code in (401, 403)


def test_ensure_keycloak_user_does_not_provision_default_sources(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keycloak auth enabled to run ensure_keycloak_user
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    user = ensure_keycloak_user(
        {
            "preferred_username": "newkeycloakuser",
            "email": "newuser@example.test",
            "sub": "kc-sub-2",
        }
    )
    assert user["username"] == "newkeycloakuser"

    # Verify that the catalog is synced but no global subscriptions are enabled
    # until the user completes onboarding.
    with connect() as conn:
        default_sources_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sources WHERE owner_user_id IS NULL"
        ).fetchone()["count"]
        user_subs_count = conn.execute(
            "SELECT COUNT(*) AS count FROM user_sources WHERE user_id = %s AND enabled IS TRUE",
            (user["id"],),
        ).fetchone()["count"]

        assert default_sources_count > 0
        assert user_subs_count == 0


def test_keycloak_registration_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("NEWS_DASHBOARD_BASE_URL", "https://news.lihor.ro")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://news.lihor.ro/keycloak")
    url = keycloak_registration_url("state-456")
    assert url.startswith(
        "https://news.lihor.ro/keycloak/realms/news-dashboard/protocol/openid-connect/registrations?"
    )
    assert "client_id=news-dashboard" in url
    assert "redirect_uri=https%3A%2F%2Fnews.lihor.ro%2Fauth%2Fcallback" in url
    assert "state=state-456" in url


def test_keycloak_register_endpoint_redirects_and_sets_cookie(
    tmp_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://news.lihor.ro/keycloak")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")

    client = _fresh_client()
    resp = client.get("/auth/register", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"].startswith(
        "https://news.lihor.ro/keycloak/realms/news-dashboard/protocol/openid-connect/registrations?"
    )
    assert "nd_oauth_state" in resp.cookies


# ── Login throttle ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=False)
def clean_throttle() -> Generator[None]:
    login_throttle.reset_all()
    login_throttle._reset_clock()
    yield
    login_throttle.reset_all()
    login_throttle._reset_clock()


def test_throttle_returns_429_after_threshold(tmp_db: str, clean_throttle: None) -> None:
    create_user("throttled_user", "correct")
    client = _fresh_client()
    payload = {"username": "throttled_user", "password": "wrong"}
    for _ in range(5):
        resp = client.post("/api/auth/login", json=payload)
        assert resp.status_code == 401
    resp = client.post("/api/auth/login", json=payload)
    assert resp.status_code == 429


def test_throttle_response_body_does_not_reveal_username(tmp_db: str, clean_throttle: None) -> None:
    create_user("secret_user", "correct")
    client = _fresh_client()
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "secret_user", "password": "wrong"})
    resp = client.post("/api/auth/login", json={"username": "secret_user", "password": "wrong"})
    assert resp.status_code == 429
    body = resp.text
    assert "secret_user" not in body


def test_successful_login_clears_throttle(tmp_db: str, clean_throttle: None) -> None:
    create_user("clearme", "right")
    client = _fresh_client()
    for _ in range(4):
        client.post("/api/auth/login", json={"username": "clearme", "password": "wrong"})
    # Correct password resets the counter
    resp = client.post("/api/auth/login", json={"username": "clearme", "password": "right"})
    assert resp.status_code == 200
    # Should be able to fail again without immediately hitting 429
    resp = client.post("/api/auth/login", json={"username": "clearme", "password": "wrong"})
    assert resp.status_code == 401


def test_throttle_window_expiry(tmp_db: str, clean_throttle: None) -> None:
    from datetime import datetime, timezone

    create_user("windowed", "correct")
    client = _fresh_client()

    # Record 5 failures at t=0
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    login_throttle._set_clock(lambda: t0)
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "windowed", "password": "wrong"})

    # Confirm throttled at t=0
    resp = client.post("/api/auth/login", json={"username": "windowed", "password": "wrong"})
    assert resp.status_code == 429

    # Advance clock past the 15-minute window
    from datetime import timedelta

    t_after = t0 + timedelta(minutes=16)
    login_throttle._set_clock(lambda: t_after)

    # Failures should have expired; a wrong-password attempt returns 401, not 429
    resp = client.post("/api/auth/login", json={"username": "windowed", "password": "wrong"})
    assert resp.status_code == 401


def test_throttle_below_threshold_returns_401(tmp_db: str, clean_throttle: None) -> None:
    create_user("below", "correct")
    client = _fresh_client()
    for _ in range(4):
        resp = client.post("/api/auth/login", json={"username": "below", "password": "wrong"})
        assert resp.status_code == 401


def test_throttle_does_not_affect_keycloak_mode(
    clean_throttle: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "1")
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://kc.example.com")
    client = _fresh_client()
    # Saturate the throttle counter for this key
    login_throttle.record_failure("anyuser")
    login_throttle.record_failure("anyuser")
    login_throttle.record_failure("anyuser")
    login_throttle.record_failure("anyuser")
    login_throttle.record_failure("anyuser")
    # Keycloak mode should still return 409, not 429
    resp = client.post("/api/auth/login", json={"username": "anyuser", "password": "pw"})
    assert resp.status_code == 409
