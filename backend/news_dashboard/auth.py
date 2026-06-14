"""Authentication: users, sessions, and FastAPI dependencies."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any

import bcrypt
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "nd_session"
_SESSION_SALT = "nd-session-v1"

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
    user = get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    _touch_last_login(user["id"])
    return {k: v for k, v in user.items() if k != "password_hash"}


def init_auth() -> None:
    """Initialise DB and bootstrap first admin on startup."""
    init_db()
    bootstrap_admin()
