"""Authentication: local users, optional Keycloak SSO, sessions, and dependencies."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlencode

import bcrypt
import httpx
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "nd_session"
_SESSION_SALT = "nd-session-v1"


@dataclass(frozen=True)
class KeycloakConfig:
    enabled: bool
    public_server_url: str
    internal_server_url: str
    realm: str
    client_id: str
    client_secret: str | None
    base_url: str

    @property
    def public_realm_url(self) -> str:
        return f"{self.public_server_url}/realms/{self.realm}"

    @property
    def internal_realm_url(self) -> str:
        return f"{self.internal_server_url}/realms/{self.realm}"

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url}/auth/callback"


# --------------------------------------------------------------------------- #
# Config helpers                                                                #
# --------------------------------------------------------------------------- #


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _strip_url(value: str | None) -> str:
    return (value or "").strip().rstrip("/")


def keycloak_config() -> KeycloakConfig:
    public_server = _strip_url(os.getenv("KEYCLOAK_SERVER_URL"))
    internal_server = _strip_url(os.getenv("KEYCLOAK_INTERNAL_SERVER_URL")) or public_server
    return KeycloakConfig(
        enabled=_truthy(os.getenv("KEYCLOAK_AUTH_ENABLED")),
        public_server_url=public_server,
        internal_server_url=internal_server,
        realm=(os.getenv("KEYCLOAK_REALM") or "news-dashboard").strip(),
        client_id=(os.getenv("KEYCLOAK_CLIENT_ID") or "news-dashboard").strip(),
        client_secret=(os.getenv("KEYCLOAK_CLIENT_SECRET") or "").strip() or None,
        base_url=_strip_url(os.getenv("NEWS_DASHBOARD_BASE_URL")) or "http://localhost:8080",
    )


def keycloak_auth_metadata() -> dict[str, Any]:
    config = keycloak_config()
    return {
        "provider": "keycloak" if config.enabled else "password",
        "keycloak_enabled": config.enabled,
        "login_url": "/auth/login" if config.enabled else None,
        "logout_url": "/auth/logout" if config.enabled else "/api/auth/logout",
    }


def _keycloak_admin_usernames() -> set[str]:
    raw = os.getenv("KEYCLOAK_ADMIN_USERNAMES", "")
    return {u.strip().lower() for u in raw.split(",") if u.strip()}


# --------------------------------------------------------------------------- #
# Session secret — required in production; tests may set TEST_SESSION_SECRET.  #
# --------------------------------------------------------------------------- #


def _get_secret() -> str:
    secret = os.getenv("SESSION_SECRET") or os.getenv("TEST_SESSION_SECRET")
    if not secret:
        msg = (
            "SESSION_SECRET env var is not set. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
        raise RuntimeError(msg)
    return secret


def _session_days() -> int:
    try:
        return int(os.getenv("SESSION_DAYS", "30"))
    except ValueError:
        return 30


# --------------------------------------------------------------------------- #
# Password helpers                                                              #
# --------------------------------------------------------------------------- #


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Session cookie helpers                                                        #
# --------------------------------------------------------------------------- #


def create_session_token(user_id: int, is_admin: bool) -> str:
    s = URLSafeTimedSerializer(_get_secret(), salt=_SESSION_SALT)
    return s.dumps({"u": user_id, "a": int(is_admin)})


def verify_session_token(token: str) -> dict[str, Any] | None:
    s = URLSafeTimedSerializer(_get_secret(), salt=_SESSION_SALT)
    max_age = _session_days() * 86400
    try:
        payload = s.loads(token, max_age=max_age)
        return {"user_id": payload["u"], "is_admin": bool(payload["a"])}
    except (BadSignature, SignatureExpired, KeyError):
        return None


# --------------------------------------------------------------------------- #
# User DB helpers                                                               #
# --------------------------------------------------------------------------- #


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, email, is_admin, created_at, last_login_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        return row_to_dict(row) if row else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, email, is_admin, created_at, last_login_at, password_hash"
            " FROM users WHERE username=?",
            (username,),
        ).fetchone()
        return row_to_dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, email, is_admin, created_at, last_login_at "
            "FROM users WHERE email=?",
            (email,),
        ).fetchone()
        return row_to_dict(row) if row else None


def create_user(
    username: str,
    password: str,
    *,
    email: str | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    password_hash = hash_password(password)
    with connect() as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash, email, is_admin)"
            " VALUES(?, ?, ?, ?) RETURNING id, username, email, is_admin, created_at",
            (username, password_hash, email, 1 if is_admin else 0),
        ).fetchone()
        if row is None:
            msg = "User insert returned no row"
            raise RuntimeError(msg)
        return row_to_dict(row)


def list_users() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, username, email, is_admin, created_at, last_login_at FROM users ORDER BY id"
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def update_password(user_id: int, new_password: str) -> bool:
    new_hash = hash_password(new_password)
    with connect() as conn:
        cursor = conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
        return bool(cursor.rowcount > 0)


def delete_user(user_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        return bool(cursor.rowcount > 0)


def _touch_last_login(user_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (user_id,))


# --------------------------------------------------------------------------- #
# Bootstrap: create first admin from env vars on startup                       #
# --------------------------------------------------------------------------- #


def user_count_from_row(row: Any) -> int:
    return int(row_to_dict(row)["n"])


def bootstrap_admin() -> None:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        with connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            if user_count_from_row(row) == 0:
                logger.warning(
                    "No users exist and BOOTSTRAP_ADMIN_USERNAME/BOOTSTRAP_ADMIN_PASSWORD "
                    "are not set. The app will start but login is impossible. "
                    "Set these env vars to create the first admin account."
                )
        return

    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        if user_count_from_row(row) > 0:
            return  # users already exist; bootstrap is a no-op

    user = create_user(username, password, is_admin=True)
    logger.info("Bootstrap admin created: username=%s id=%s", user["username"], user["id"])


# --------------------------------------------------------------------------- #
# FastAPI dependencies                                                          #
# --------------------------------------------------------------------------- #


async def get_current_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    user = get_user_by_id(payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_auth(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return user


async def require_admin(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# --------------------------------------------------------------------------- #
# Login / logout helpers (called from main.py)                                 #
# --------------------------------------------------------------------------- #


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    """Return user dict if credentials are valid, None otherwise."""
    if keycloak_config().enabled:
        return None
    user = get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    _touch_last_login(user["id"])
    return {k: v for k, v in user.items() if k != "password_hash"}


def keycloak_authorization_url(state: str) -> str:
    config = keycloak_config()
    if not config.enabled or not config.public_server_url:
        raise HTTPException(status_code=500, detail="Keycloak authentication is not configured")
    params = urlencode(
        {
            "client_id": config.client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": config.redirect_uri,
            "state": state,
        }
    )
    return f"{config.public_realm_url}/protocol/openid-connect/auth?{params}"


def keycloak_token_request_data(code: str) -> dict[str, str]:
    config = keycloak_config()
    data = {
        "grant_type": "authorization_code",
        "client_id": config.client_id,
        "code": code,
        "redirect_uri": config.redirect_uri,
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret
    return data


def ensure_keycloak_user(info: dict[str, Any]) -> dict[str, Any]:
    username = str(
        info.get("preferred_username") or info.get("email") or info.get("sub") or ""
    ).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Keycloak profile did not include a username")
    email = str(info.get("email") or "").strip() or None

    existing = get_user_by_username(username)
    if not existing and email:
        existing = get_user_by_email(email)
    if existing:
        _touch_last_login(int(existing["id"]))
        return get_user_by_id(int(existing["id"])) or existing

    # Local users are still the app's authorization boundary for per-user data.
    # Keycloak-created users get an unusable random password because Keycloak owns login.
    user = create_user(
        username,
        secrets.token_urlsafe(48),
        email=email,
        is_admin=username.lower() in _keycloak_admin_usernames(),
    )
    _touch_last_login(int(user["id"]))
    return get_user_by_id(int(user["id"])) or user


async def exchange_keycloak_code(code: str) -> dict[str, Any]:
    config = keycloak_config()
    if not config.enabled:
        raise HTTPException(status_code=400, detail="Keycloak authentication is disabled")
    token_url = f"{config.internal_realm_url}/protocol/openid-connect/token"
    userinfo_url = f"{config.internal_realm_url}/protocol/openid-connect/userinfo"
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            token_url,
            data=keycloak_token_request_data(code),
            headers={"Accept": "application/json"},
        )
        if token_response.status_code >= 400:
            raise HTTPException(status_code=401, detail="Keycloak token exchange failed")
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Keycloak token response had no access token",
            )
        user_response = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if user_response.status_code >= 400:
            raise HTTPException(status_code=401, detail="Keycloak userinfo lookup failed")
        return ensure_keycloak_user(user_response.json())


def keycloak_logout_url() -> str:
    config = keycloak_config()
    if not config.enabled or not config.public_server_url:
        return "/login"
    params = urlencode({"client_id": config.client_id, "post_logout_redirect_uri": config.base_url})
    return f"{config.public_realm_url}/protocol/openid-connect/logout?{params}"


def init_auth() -> None:
    """Initialise DB and bootstrap first admin on startup."""
    init_db()
    config = keycloak_config()
    if config.enabled:
        _get_secret()
        if not config.public_server_url or not config.internal_server_url:
            message = "Keycloak authentication is enabled but KEYCLOAK_SERVER_URL is not set"
            raise RuntimeError(message)
        return
    bootstrap_admin()
