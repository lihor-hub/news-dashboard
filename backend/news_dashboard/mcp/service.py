from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Mapping
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

TOKEN_PREFIX = "ndmcp_"  # noqa: S105 -- token prefix, not a credential
DEFAULT_SCOPES = ("search", "read", "ask", "briefings")
KNOWN_SCOPES = frozenset(DEFAULT_SCOPES)
MAX_TOKENS_PER_USER = 10
MAX_TOKEN_NAME_LENGTH = 120


def mcp_enabled() -> bool:
    """Whether the MCP server is enabled unless explicitly disabled."""
    return (os.getenv("MCP_SERVER_ENABLED") or "").strip().lower() not in {
        "false",
        "0",
        "no",
        "off",
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    token = f"{TOKEN_PREFIX}{secret}"
    return token, _hash_token(token), token[: len(TOKEN_PREFIX) + 8]


def _serialise(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data.pop("token_hash", None)
    for key in ("created_at", "last_used_at", "revoked_at"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            data[key] = value.isoformat()
    scopes = data.get("scopes")
    if isinstance(scopes, str):
        data["scopes"] = [s for s in scopes.split(",") if s]
    return data


def list_tokens(user_id: int, *, database_url: str | None = None) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, name, token_prefix, scopes, created_at, last_used_at, revoked_at
            FROM mcp_tokens
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_serialise(row_to_dict(row)) for row in rows]


def create_token(
    user_id: int,
    name: str,
    *,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Create a new MCP token. Returns the serialised token including the plaintext
    `token` field once — callers must display it now, since only the hash is stored."""
    init_db(database_url=database_url)
    clean_name = name.strip()[:MAX_TOKEN_NAME_LENGTH] or "MCP client"
    token, token_hash, prefix = _generate_token()
    scope_str = ",".join(scopes)
    with connect(database_url=database_url) as conn:
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM mcp_tokens WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        ).fetchone()
        if row_to_dict(active)["n"] >= MAX_TOKENS_PER_USER:
            message = "token limit reached; revoke an existing token first"
            raise ValueError(message)
        row = conn.execute(
            """
            INSERT INTO mcp_tokens(user_id, name, token_hash, token_prefix, scopes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, user_id, name, token_prefix, scopes,
                      created_at, last_used_at, revoked_at
            """,
            (user_id, clean_name, token_hash, prefix, scope_str),
        ).fetchone()
    result = _serialise(row_to_dict(row))
    result["token"] = token
    return result


def revoke_token(
    user_id: int, token_id: int, *, database_url: str | None = None
) -> dict[str, Any] | None:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE mcp_tokens
            SET revoked_at = NOW()
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            RETURNING id, user_id, name, token_prefix, scopes,
                      created_at, last_used_at, revoked_at
            """,
            (token_id, user_id),
        ).fetchone()
    return None if row is None else _serialise(row_to_dict(row))


def authenticate_token(token: str, *, database_url: str | None = None) -> dict[str, Any] | None:
    """Verify a bearer token and return {token_id, user_id, scopes} or None."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    init_db(database_url=database_url)
    token_hash = _hash_token(token)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT id, user_id, scopes, revoked_at FROM mcp_tokens WHERE token_hash = %s",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        data = row_to_dict(row)
        if data["revoked_at"] is not None:
            return None
        conn.execute("UPDATE mcp_tokens SET last_used_at = NOW() WHERE id = %s", (data["id"],))
    scopes = str(data.get("scopes") or "")
    return {
        "token_id": data["id"],
        "user_id": data["user_id"],
        "scopes": {s for s in scopes.split(",") if s},
    }
