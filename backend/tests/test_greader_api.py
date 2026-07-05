from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import connect
from news_dashboard.main import app


def _make_user(database_url: str, username: str) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'hash') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _seed_source(
    database_url: str, slug: str = "test-source", category: str = "engineering"
) -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, 'rss', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, f"https://example.com/{slug}.xml", category),
        )


def _seed_article(database_url: str, article_id: int, source_slug: str = "test-source") -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO articles(
                id, url, canonical_url, title, source_slug, source_name,
                category, kind, status, importance_score, summary, reason, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                article_id,
                f"https://example.com/{article_id}",
                f"https://example.com/{article_id}",
                f"Article {article_id}",
                source_slug,
                source_slug,
                "engineering",
                "rss",
                "new",
                0.5,
                f"Summary {article_id}",
                "",
                "",
            ),
        )


# ─── service.py — token lifecycle ────────────────────────────────────────────


def test_create_list_revoke_tokens_scoped_to_user(pg_clean: str) -> None:
    from news_dashboard import greader

    alice = _make_user(pg_clean, "alice-greader")
    bob = _make_user(pg_clean, "bob-greader")

    created = greader.create_token(alice, "NetNewsWire", database_url=pg_clean)
    assert created["token"].startswith(greader.TOKEN_PREFIX)
    assert created["token_prefix"] in created["token"]

    assert [t["id"] for t in greader.list_tokens(alice, database_url=pg_clean)] == [created["id"]]
    assert greader.list_tokens(bob, database_url=pg_clean) == []

    assert greader.revoke_token(bob, created["id"], database_url=pg_clean) is None
    revoked = greader.revoke_token(alice, created["id"], database_url=pg_clean)
    assert revoked is not None
    assert revoked["revoked_at"] is not None


def test_created_token_response_never_stores_plaintext(pg_clean: str) -> None:
    from news_dashboard import greader

    alice = _make_user(pg_clean, "alice-hash")
    created = greader.create_token(alice, "client", database_url=pg_clean)
    assert created["token"]

    listed = greader.list_tokens(alice, database_url=pg_clean)[0]
    assert "token" not in listed
    assert "token_hash" not in listed


def test_token_limit_per_user(pg_clean: str) -> None:
    from news_dashboard import greader

    alice = _make_user(pg_clean, "alice-limit")
    for i in range(greader.MAX_TOKENS_PER_USER):
        greader.create_token(alice, f"client-{i}", database_url=pg_clean)

    with pytest.raises(ValueError, match="token limit reached"):
        greader.create_token(alice, "one-too-many", database_url=pg_clean)


def test_authenticate_token_rejects_unknown_revoked_and_malformed(pg_clean: str) -> None:
    from news_dashboard import greader

    alice = _make_user(pg_clean, "alice-auth")
    created = greader.create_token(alice, "client", database_url=pg_clean)
    token = created["token"]

    assert greader.authenticate_token(token, database_url=pg_clean) == alice
    assert greader.authenticate_token("not-a-real-token", database_url=pg_clean) is None
    assert greader.authenticate_token("", database_url=pg_clean) is None

    greader.revoke_token(alice, created["id"], database_url=pg_clean)
    assert greader.authenticate_token(token, database_url=pg_clean) is None


# ─── item id encoding ─────────────────────────────────────────────────────────


def test_item_id_round_trips_short_and_long_forms() -> None:
    from news_dashboard import greader

    long_id = greader.item_long_id(42)
    short_id = greader.item_short_id(42)
    assert long_id == f"tag:google.com,2005:reader/item/{short_id}"
    assert greader.parse_item_id(long_id) == 42
    assert greader.parse_item_id(short_id) == 42
    assert greader.parse_item_id("not-hex") is None


# ─── HTTP endpoints ───────────────────────────────────────────────────────────


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _client_for(user_id: int) -> TestClient:
    from news_dashboard.auth import require_auth

    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


def test_token_management_endpoints(pg_clean: str) -> None:
    alice = _make_user(pg_clean, "alice-http")

    with _client_for(alice) as client:
        created = client.post("/api/users/me/greader-tokens", json={"name": "NetNewsWire"})
        assert created.status_code == 200
        body = created.json()
        assert body["token"].startswith("ndgr_")
        token_id = body["id"]

        listed = client.get("/api/users/me/greader-tokens")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
        assert "token" not in listed.json()["items"][0]

        revoked = client.delete(f"/api/users/me/greader-tokens/{token_id}")
        assert revoked.status_code == 200
        assert revoked.json()["revoked_at"] is not None

    app.dependency_overrides.clear()


def test_client_login_returns_auth_token_or_401(client: TestClient, pg_clean: str) -> None:
    from news_dashboard import greader

    alice = _make_user(pg_clean, "alice-login")
    created = greader.create_token(alice, "client", database_url=pg_clean)

    resp = client.post(
        "/api/greader/accounts/ClientLogin",
        data={"Email": "alice", "Passwd": created["token"]},
    )
    assert resp.status_code == 200
    assert f"Auth={created['token']}" in resp.text

    bad = client.post(
        "/api/greader/accounts/ClientLogin",
        data={"Email": "alice", "Passwd": "bogus"},
    )
    assert bad.status_code == 401


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"GoogleLogin auth={token}"}


def test_protocol_endpoints_require_auth(client: TestClient) -> None:
    resp = client.get("/api/greader/reader/api/0/user-info")
    assert resp.status_code == 401

    resp = client.get(
        "/api/greader/reader/api/0/user-info", headers={"Authorization": "GoogleLogin auth=bogus"}
    )
    assert resp.status_code == 401


def test_subscription_list_and_stream_contents(client: TestClient, pg_clean: str) -> None:
    from news_dashboard import greader

    _seed_source(pg_clean, "feed-a", category="python")
    alice = _make_user(pg_clean, "alice-stream")
    _seed_article(pg_clean, 1, source_slug="feed-a")
    _seed_article(pg_clean, 2, source_slug="feed-a")
    created = greader.create_token(alice, "client", database_url=pg_clean)
    headers = _auth_header(created["token"])

    subs = client.get("/api/greader/reader/api/0/subscription/list", headers=headers)
    assert subs.status_code == 200
    sub_items = subs.json()["subscriptions"]
    assert any(s["id"] == "feed/feed-a" for s in sub_items)

    contents = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/reading-list",
        headers=headers,
    )
    assert contents.status_code == 200
    items = contents.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] == greader.item_long_id(2)

    feed_contents = client.get(
        "/api/greader/reader/api/0/stream/contents/feed/feed-a",
        headers=headers,
    )
    assert feed_contents.status_code == 200
    assert len(feed_contents.json()["items"]) == 2


def test_stream_contents_continuation_paging(client: TestClient, pg_clean: str) -> None:
    from news_dashboard import greader

    _seed_source(pg_clean, "feed-b")
    alice = _make_user(pg_clean, "alice-paging")
    for i in range(1, 6):
        _seed_article(pg_clean, i, source_slug="feed-b")
    created = greader.create_token(alice, "client", database_url=pg_clean)
    headers = _auth_header(created["token"])

    first_page = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/reading-list",
        params={"n": 2},
        headers=headers,
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 2
    assert first_body["continuation"]

    second_page = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/reading-list",
        params={"n": 2, "c": first_body["continuation"]},
        headers=headers,
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert len(second_body["items"]) == 2
    assert {item["id"] for item in first_body["items"]}.isdisjoint(
        {item["id"] for item in second_body["items"]}
    )


def test_visibility_isolation_between_users(client: TestClient, pg_clean: str) -> None:
    from news_dashboard import greader

    _seed_source(pg_clean, "private-source")
    alice = _make_user(pg_clean, "alice-owner")
    bob = _make_user(pg_clean, "bob-visitor")
    _seed_article(pg_clean, 42, source_slug="private-source")

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE sources SET owner_user_id = %s, enabled = TRUE WHERE slug = %s",
            (alice, "private-source"),
        )

    alice_token = greader.create_token(alice, "client", database_url=pg_clean)
    bob_token = greader.create_token(bob, "client", database_url=pg_clean)

    alice_contents = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/reading-list",
        headers=_auth_header(alice_token["token"]),
    )
    bob_contents = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/reading-list",
        headers=_auth_header(bob_token["token"]),
    )
    assert any(item["id"] == greader.item_long_id(42) for item in alice_contents.json()["items"])
    assert not any(item["id"] == greader.item_long_id(42) for item in bob_contents.json()["items"])


def test_edit_tag_marks_read_and_starred_round_trip(client: TestClient, pg_clean: str) -> None:
    from news_dashboard import greader

    _seed_source(pg_clean, "feed-c")
    alice = _make_user(pg_clean, "alice-edit")
    _seed_article(pg_clean, 99, source_slug="feed-c")
    created = greader.create_token(alice, "client", database_url=pg_clean)
    headers = _auth_header(created["token"])
    item_id = greader.item_long_id(99)

    mark_read = client.post(
        "/api/greader/reader/api/0/edit-tag",
        data={"i": item_id, "a": greader.READ_TAG},
        headers=headers,
    )
    assert mark_read.status_code == 200

    star = client.post(
        "/api/greader/reader/api/0/edit-tag",
        data={"i": item_id, "a": greader.STARRED_TAG},
        headers=headers,
    )
    assert star.status_code == 200

    starred_stream = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/starred",
        headers=headers,
    )
    assert any(item["id"] == item_id for item in starred_stream.json()["items"])

    unread = client.post(
        "/api/greader/reader/api/0/edit-tag",
        data={"i": item_id, "r": greader.READ_TAG},
        headers=headers,
    )
    assert unread.status_code == 200

    unstar = client.post(
        "/api/greader/reader/api/0/edit-tag",
        data={"i": item_id, "r": greader.STARRED_TAG},
        headers=headers,
    )
    assert unstar.status_code == 200

    starred_stream_after = client.get(
        "/api/greader/reader/api/0/stream/contents/user/-/state/com.google/starred",
        headers=headers,
    )
    assert not any(item["id"] == item_id for item in starred_stream_after.json()["items"])


def test_stream_items_ids_and_contents_round_trip(client: TestClient, pg_clean: str) -> None:
    from news_dashboard import greader

    _seed_source(pg_clean, "feed-d")
    alice = _make_user(pg_clean, "alice-ids")
    _seed_article(pg_clean, 7, source_slug="feed-d")
    created = greader.create_token(alice, "client", database_url=pg_clean)
    headers = _auth_header(created["token"])

    ids_resp = client.get("/api/greader/reader/api/0/stream/items/ids", headers=headers)
    assert ids_resp.status_code == 200
    refs = ids_resp.json()["itemRefs"]
    assert refs == [{"id": greader.item_short_id(7)}]

    contents_resp = client.post(
        "/api/greader/reader/api/0/stream/items/contents",
        data={"i": greader.item_long_id(7)},
        headers=headers,
    )
    assert contents_resp.status_code == 200
    assert contents_resp.json()["items"][0]["id"] == greader.item_long_id(7)
