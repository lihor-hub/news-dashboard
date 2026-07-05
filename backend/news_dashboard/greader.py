"""Google Reader-compatible sync API (v1) for third-party RSS clients.

Lets stock GReader clients (NetNewsWire, Reeder, Unread, ...) subscribe to a
user's sources, read the reading list / per-feed / starred streams, and sync
read/starred state — all read/write through the existing per-user article
state machinery in ``ingest.py``.

Auth is a dedicated per-user API-token mechanism (mirrors ``mcp/service.py``):
tokens are opaque, hashed at rest, and revocable from Settings. GReader
clients present the token as the ``ClientLogin`` password and then send it
back as ``Authorization: GoogleLogin auth=<token>`` (or a plain bearer token)
on every subsequent request.

Item ids are the article id encoded as 16 hex digits, optionally wrapped in
the ``tag:google.com,2005:reader/item/<hex>`` long form real clients expect
from ``stream/contents``. Continuation tokens are just ``o<offset>``.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from news_dashboard.article_visibility import visible_article_sql
from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db, row_to_dict

TOKEN_PREFIX = "ndgr_"  # noqa: S105 -- token prefix, not a credential
MAX_TOKENS_PER_USER = 10
MAX_TOKEN_NAME_LENGTH = 120

READING_LIST_STREAM = "user/-/state/com.google/reading-list"
STARRED_STREAM = "user/-/state/com.google/starred"
READ_TAG = "user/-/state/com.google/read"
STARRED_TAG = "user/-/state/com.google/starred"

DEFAULT_STREAM_LIMIT = 20
MAX_STREAM_LIMIT = 500


# --------------------------------------------------------------------------- #
# Token lifecycle (mirrors news_dashboard.mcp.service)                        #
# --------------------------------------------------------------------------- #


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    token = f"{TOKEN_PREFIX}{secret}"
    return token, _hash_token(token), token[: len(TOKEN_PREFIX) + 8]


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data.pop("token_hash", None)
    for key in ("created_at", "last_used_at", "revoked_at"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            data[key] = value.isoformat()
    return data


def list_tokens(user_id: int, *, database_url: str | None = None) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, name, token_prefix, created_at, last_used_at, revoked_at
            FROM greader_tokens
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_serialise(row_to_dict(row)) for row in rows]


def create_token(user_id: int, name: str, *, database_url: str | None = None) -> dict[str, Any]:
    """Create a new GReader token. Returns the serialised token including the
    plaintext ``token`` field once — callers must display it now."""
    init_db(database_url=database_url)
    clean_name = name.strip()[:MAX_TOKEN_NAME_LENGTH] or "RSS client"
    token, token_hash, prefix = _generate_token()
    with connect(database_url=database_url) as conn:
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM greader_tokens WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        ).fetchone()
        if row_to_dict(active)["n"] >= MAX_TOKENS_PER_USER:
            message = "token limit reached; revoke an existing token first"
            raise ValueError(message)
        row = conn.execute(
            """
            INSERT INTO greader_tokens(user_id, name, token_hash, token_prefix)
            VALUES (%s, %s, %s, %s)
            RETURNING id, user_id, name, token_prefix, created_at, last_used_at, revoked_at
            """,
            (user_id, clean_name, token_hash, prefix),
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
            UPDATE greader_tokens
            SET revoked_at = NOW()
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            RETURNING id, user_id, name, token_prefix, created_at, last_used_at, revoked_at
            """,
            (token_id, user_id),
        ).fetchone()
    return None if row is None else _serialise(row_to_dict(row))


def authenticate_token(token: str, *, database_url: str | None = None) -> int | None:
    """Verify a bearer token and return the owning user_id, or None."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    init_db(database_url=database_url)
    token_hash = _hash_token(token)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT id, user_id, revoked_at FROM greader_tokens WHERE token_hash = %s",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        data = row_to_dict(row)
        if data["revoked_at"] is not None:
            return None
        conn.execute("UPDATE greader_tokens SET last_used_at = NOW() WHERE id = %s", (data["id"],))
    return int(data["user_id"])


# --------------------------------------------------------------------------- #
# Item id encoding                                                             #
# --------------------------------------------------------------------------- #

_ITEM_TAG_PREFIX = "tag:google.com,2005:reader/item/"


def item_short_id(article_id: int) -> str:
    return f"{article_id:016x}"


def item_long_id(article_id: int) -> str:
    return f"{_ITEM_TAG_PREFIX}{item_short_id(article_id)}"


def parse_item_id(value: str) -> int | None:
    hex_part = value[len(_ITEM_TAG_PREFIX) :] if value.startswith(_ITEM_TAG_PREFIX) else value
    try:
        return int(hex_part, 16)
    except ValueError:
        return None


def _encode_continuation(offset: int) -> str | None:
    return f"o{offset}" if offset > 0 else None


def _decode_continuation(value: str | None) -> int:
    if not value or not value.startswith("o"):
        return 0
    try:
        return max(0, int(value[1:]))
    except ValueError:
        return 0


# --------------------------------------------------------------------------- #
# Data access                                                                  #
# --------------------------------------------------------------------------- #


def _fetch_stream_articles(
    user_id: int,
    *,
    source_slug: str | None = None,
    starred_only: bool = False,
    limit: int,
    offset: int,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    clauses = [
        "(a.canonical_id IS NULL OR COALESCE(uas.state, 'today') != 'archived')",
        f"({visible_article_sql('a')})",
    ]
    params: list[Any] = [user_id]
    if source_slug is not None:
        clauses.append("a.source_slug = %s")
        params.append(source_slug)
    if starred_only:
        clauses.append("COALESCE(uas.starred, FALSE) IS TRUE")
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            f"""
            SELECT a.id, a.title, a.url, a.summary, a.source_slug, a.source_name,
                   a.category, a.published_at, a.discovered_at,
                   COALESCE(uas.state, 'today') AS state,
                   COALESCE(uas.starred, FALSE) AS starred
            FROM articles a
            JOIN sources a_src ON a_src.slug = a.source_slug
            LEFT JOIN user_sources a_us
              ON a_us.source_slug = a.source_slug AND a_us.user_id = %s
            LEFT JOIN user_article_state uas
              ON uas.article_id = a.id AND uas.user_id = %s
            WHERE {where}
            ORDER BY a.discovered_at DESC, a.id DESC
            LIMIT %s OFFSET %s
            """,
            [user_id, user_id, *params],
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def _fetch_articles_by_ids(
    user_id: int, article_ids: list[int], *, database_url: str | None = None
) -> list[dict[str, Any]]:
    if not article_ids:
        return []
    from news_dashboard.db import placeholders

    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            f"""
            SELECT a.id, a.title, a.url, a.summary, a.source_slug, a.source_name,
                   a.category, a.published_at, a.discovered_at,
                   COALESCE(uas.state, 'today') AS state,
                   COALESCE(uas.starred, FALSE) AS starred
            FROM articles a
            JOIN sources a_src ON a_src.slug = a.source_slug
            LEFT JOIN user_sources a_us
              ON a_us.source_slug = a.source_slug AND a_us.user_id = %s
            LEFT JOIN user_article_state uas
              ON uas.article_id = a.id AND uas.user_id = %s
            WHERE a.id IN ({placeholders(article_ids)})
              AND ({visible_article_sql("a")})
            ORDER BY a.discovered_at DESC, a.id DESC
            """,
            [user_id, user_id, *article_ids, user_id],
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_visible_sources(user_id: int, *, database_url: str | None = None) -> list[dict[str, Any]]:
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT s.slug, s.name, s.url, s.category
            FROM sources s
            WHERE (s.owner_user_id IS NULL OR s.owner_user_id = %s)
              AND s.deleted_at IS NULL
            ORDER BY s.category, s.priority DESC, s.name
            """,
            (user_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def _article_to_item(article: dict[str, Any]) -> dict[str, Any]:
    categories = [READING_LIST_STREAM]
    if article["state"] not in ("today", "later"):
        categories.append(READ_TAG)
    if article["starred"]:
        categories.append(STARRED_TAG)
    return {
        "id": item_long_id(article["id"]),
        "title": article["title"],
        "canonical": [{"href": article["url"]}],
        "alternate": [{"href": article["url"]}],
        "summary": {"content": article.get("summary") or ""},
        "author": article.get("source_name"),
        "categories": categories,
        "origin": {
            "streamId": f"feed/{article['source_slug']}",
            "title": article.get("source_name"),
        },
        "crawlTimeMsec": "0",
        "published": _to_epoch(article.get("published_at") or article.get("discovered_at")),
    }


def _to_epoch(value: Any) -> int:
    if value is None:
        return 0
    from datetime import datetime

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0
    if isinstance(value, datetime):
        return int(value.timestamp())
    return 0


def apply_edit_tag(user_id: int, article_id: int, *, add: list[str], remove: list[str]) -> None:
    import contextlib

    from news_dashboard.ingest import set_article_starred, transition_article_state

    for tag in add:
        if tag == READ_TAG:
            with contextlib.suppress(ValueError):
                transition_article_state(article_id, "done", user_id=user_id)
        elif tag == STARRED_TAG:
            with contextlib.suppress(ValueError):
                set_article_starred(article_id, True, user_id=user_id)
    for tag in remove:
        if tag == READ_TAG:
            with contextlib.suppress(ValueError):
                transition_article_state(article_id, "today", user_id=user_id)
        elif tag == STARRED_TAG:
            with contextlib.suppress(ValueError):
                set_article_starred(article_id, False, user_id=user_id)


# --------------------------------------------------------------------------- #
# Token management endpoints (session-cookie auth, mounted on `api`)          #
# --------------------------------------------------------------------------- #


class TokenCreateRequest(BaseModel):
    name: str


router = APIRouter()
public_greader_router = APIRouter(prefix="/api/greader")


@router.get("/api/users/me/greader-tokens")
def list_greader_tokens(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": list_tokens(int(current_user["id"]))}


@router.post("/api/users/me/greader-tokens")
def create_greader_token(
    payload: TokenCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return create_token(int(current_user["id"]), payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/users/me/greader-tokens/{token_id}")
def revoke_greader_token(
    token_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    token = revoke_token(int(current_user["id"]), token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="token not found")
    return token


# --------------------------------------------------------------------------- #
# GReader protocol endpoints (own bearer/GoogleLogin auth, publicly mounted)   #
# --------------------------------------------------------------------------- #


def _authenticate(authorization: str | None) -> int:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    lowered = authorization.lower()
    if lowered.startswith("googlelogin "):
        raw = authorization[len("GoogleLogin ") :].split()
        parts = dict(item.split("=", 1) for item in raw if "=" in item)
        token = parts.get("auth", "")
    elif lowered.startswith("bearer "):
        token = authorization[len("Bearer ") :].strip()
    else:
        token = authorization.strip()
    user_id = authenticate_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or revoked token")
    return user_id


@public_greader_router.post("/accounts/ClientLogin")
def client_login(
    email: Annotated[str, Form(alias="Email")] = "",
    client_secret: Annotated[str, Form(alias="Passwd")] = "",
) -> PlainTextResponse:
    # GReader clients send the API token as the "Passwd" form field — it is
    # a high-entropy opaque token (secrets.token_urlsafe), not a user-chosen
    # password, so SHA-256 (matching mcp/service.py's token hashing) applies.
    _ = email
    user_id = authenticate_token(client_secret)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    body = f"SID={client_secret}\nLSID={client_secret}\nAuth={client_secret}\n"
    return PlainTextResponse(body)


@public_greader_router.get("/reader/api/0/token")
def reader_token(
    authorization: Annotated[str | None, Header()] = None,
) -> PlainTextResponse:
    user_id = _authenticate(authorization)
    return PlainTextResponse(f"greader-post-token-{user_id}")


@public_greader_router.get("/reader/api/0/user-info")
def user_info(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    from news_dashboard.auth import get_user_by_id

    user_id = _authenticate(authorization)
    user = get_user_by_id(user_id)
    return {
        "userId": str(user_id),
        "userName": (user or {}).get("username"),
        "userEmail": (user or {}).get("email"),
    }


@public_greader_router.get("/reader/api/0/subscription/list")
def subscription_list(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user_id = _authenticate(authorization)
    subscriptions = [
        {
            "id": f"feed/{source['slug']}",
            "title": source["name"],
            "categories": [
                {
                    "id": f"user/-/label/{source['category']}",
                    "label": source["category"],
                }
            ],
            "url": source["url"],
            "htmlUrl": source["url"],
        }
        for source in list_visible_sources(user_id)
    ]
    return {"subscriptions": subscriptions}


def _stream_articles(
    user_id: int, stream_id: str, *, limit: int, offset: int
) -> list[dict[str, Any]]:
    if stream_id == READING_LIST_STREAM:
        return _fetch_stream_articles(user_id, limit=limit, offset=offset)
    if stream_id == STARRED_STREAM:
        return _fetch_stream_articles(user_id, starred_only=True, limit=limit, offset=offset)
    if stream_id.startswith("feed/"):
        return _fetch_stream_articles(
            user_id, source_slug=stream_id[len("feed/") :], limit=limit, offset=offset
        )
    raise HTTPException(status_code=404, detail=f"unknown stream: {stream_id}")


@public_greader_router.get("/reader/api/0/stream/contents/{stream_id:path}")
def stream_contents(
    stream_id: str,
    authorization: Annotated[str | None, Header()] = None,
    n: Annotated[int, Query()] = DEFAULT_STREAM_LIMIT,
    c: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    user_id = _authenticate(authorization)
    limit = max(1, min(n, MAX_STREAM_LIMIT))
    offset = _decode_continuation(c)
    articles = _stream_articles(user_id, stream_id, limit=limit + 1, offset=offset)
    has_more = len(articles) > limit
    articles = articles[:limit]
    return {
        "id": stream_id,
        "updated": _to_epoch(None),
        "items": [_article_to_item(a) for a in articles],
        "continuation": _encode_continuation(offset + limit) if has_more else None,
    }


@public_greader_router.get("/reader/api/0/stream/items/ids")
def stream_items_ids(
    authorization: Annotated[str | None, Header()] = None,
    s: Annotated[str, Query()] = READING_LIST_STREAM,
    n: Annotated[int, Query()] = DEFAULT_STREAM_LIMIT,
    c: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    user_id = _authenticate(authorization)
    limit = max(1, min(n, MAX_STREAM_LIMIT))
    offset = _decode_continuation(c)
    articles = _stream_articles(user_id, s, limit=limit + 1, offset=offset)
    has_more = len(articles) > limit
    articles = articles[:limit]
    return {
        "itemRefs": [{"id": item_short_id(a["id"])} for a in articles],
        "continuation": _encode_continuation(offset + limit) if has_more else None,
    }


@public_greader_router.post("/reader/api/0/stream/items/contents")
def stream_items_contents(
    i: Annotated[list[str] | None, Form()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user_id = _authenticate(authorization)
    ids = [parse_item_id(v) for v in (i or [])]
    article_ids = [aid for aid in ids if aid is not None]
    articles = _fetch_articles_by_ids(user_id, article_ids)
    return {"items": [_article_to_item(a) for a in articles]}


@public_greader_router.post("/reader/api/0/edit-tag")
def edit_tag(
    i: Annotated[list[str] | None, Form()] = None,
    a: Annotated[list[str] | None, Form()] = None,
    r: Annotated[list[str] | None, Form()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> PlainTextResponse:
    user_id = _authenticate(authorization)
    add_tags = a or []
    remove_tags = r or []
    for raw_id in i or []:
        article_id = parse_item_id(raw_id)
        if article_id is None:
            continue
        apply_edit_tag(user_id, article_id, add=add_tags, remove=remove_tags)
    return PlainTextResponse("OK")


__all__ = ["public_greader_router", "router"]
