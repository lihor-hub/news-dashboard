"""Tests for suggesting high-value articles to turn into Learn from Link lessons."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_admin, require_auth
from news_dashboard.db import connect
from news_dashboard.learn_from_link import service
from news_dashboard.main import app


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _add_source(conn: Any, slug: str, name: str, category: str = "tech") -> None:
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
        VALUES (%s, %s, %s, %s, 'rss_feed', 10, TRUE)
        """,
        (slug, name, f"https://example.com/{slug}.xml", category),
    )


def _add_article(  # noqa: PLR0913
    conn: Any,
    *,
    user_id: int,
    slug: str,
    index: int,
    title: str | None = None,
    category: str = "tech",
    state: str = "done",
    starred: bool = False,
    days_old: int = 1,
    importance_score: int = 50,
) -> int:
    row = conn.execute(
        """
        INSERT INTO articles(
          url, canonical_url, title, source_slug, source_name, category, kind,
          discovered_at, importance_score
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', NOW() - (%s * INTERVAL '1 day'), %s)
        RETURNING id
        """,
        (
            f"https://example.com/{slug}/{index}",
            f"https://example.com/{slug}/{index}",
            title or f"{slug} article {index}",
            slug,
            slug,
            category,
            days_old,
            importance_score,
        ),
    ).fetchone()
    article_id = int(row["id"])
    conn.execute(
        """
        INSERT INTO user_article_state(user_id, article_id, state, starred, done_at)
        VALUES (%s, %s, %s, %s, CASE WHEN %s = 'done' THEN NOW() ELSE NULL END)
        """,
        (user_id, article_id, state, starred, state),
    )
    return article_id


@contextmanager
def _api_client(user_id: int, username: str = "alice") -> Generator[TestClient]:
    fake_user = {"id": user_id, "username": username, "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user
    app.dependency_overrides[require_admin] = lambda: fake_user
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_suggests_starred_and_done_articles(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=user_id, slug="blog", index=1, state="done")
        _add_article(conn, user_id=user_id, slug="blog", index=2, state="today", starred=True)
        _add_article(conn, user_id=user_id, slug="blog", index=3, state="skipped")

    suggestions = service.list_lesson_suggestions(user_id, database_url=pg_clean)

    urls = {item["url"] for item in suggestions}
    assert "https://example.com/blog/1" in urls
    assert "https://example.com/blog/2" in urls
    assert "https://example.com/blog/3" not in urls


def test_starred_articles_score_higher_than_unstarred(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=user_id, slug="blog", index=1, state="done", starred=False)
        _add_article(conn, user_id=user_id, slug="blog", index=2, state="done", starred=True)

    suggestions = service.list_lesson_suggestions(user_id, database_url=pg_clean)
    by_url = {item["url"]: item for item in suggestions}

    starred = by_url["https://example.com/blog/2"]
    unstarred = by_url["https://example.com/blog/1"]
    assert starred["score"] > unstarred["score"]
    assert "You starred this article" in starred["reasons"]


def test_excludes_articles_that_already_have_a_lesson(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=user_id, slug="blog", index=1, state="done")

    service.create_lesson(
        user_id, "https://example.com/blog/1", database_url=pg_clean, extract=False
    )

    suggestions = service.list_lesson_suggestions(user_id, database_url=pg_clean)

    assert suggestions == []


def test_excludes_dismissed_suggestions(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        article_id = _add_article(conn, user_id=user_id, slug="blog", index=1, state="done")

    service.dismiss_lesson_suggestion(user_id, article_id, database_url=pg_clean)

    suggestions = service.list_lesson_suggestions(user_id, database_url=pg_clean)

    assert suggestions == []


def test_dismiss_is_idempotent(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        article_id = _add_article(conn, user_id=user_id, slug="blog", index=1, state="done")

    result_one = service.dismiss_lesson_suggestion(user_id, article_id, database_url=pg_clean)
    result_two = service.dismiss_lesson_suggestion(user_id, article_id, database_url=pg_clean)

    assert result_one == {"dismissed": True, "article_id": article_id}
    assert result_two == {"dismissed": True, "article_id": article_id}


def test_suggestions_are_scoped_to_user(pg_clean: str) -> None:
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=alice, slug="blog", index=1, state="done")
        _add_article(conn, user_id=bob, slug="blog", index=2, state="done")

    alice_suggestions = service.list_lesson_suggestions(alice, database_url=pg_clean)
    bob_suggestions = service.list_lesson_suggestions(bob, database_url=pg_clean)

    assert [item["url"] for item in alice_suggestions] == ["https://example.com/blog/1"]
    assert [item["url"] for item in bob_suggestions] == ["https://example.com/blog/2"]


def test_high_importance_articles_are_flagged(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=user_id, slug="blog", index=1, state="done", importance_score=95)

    suggestions = service.list_lesson_suggestions(user_id, database_url=pg_clean)

    assert "High editorial importance score" in suggestions[0]["reasons"]


def test_get_suggestions_endpoint_is_user_scoped(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=alice, slug="blog", index=1, state="done")
        _add_article(conn, user_id=bob, slug="blog", index=2, state="done")

    with _api_client(alice) as client:
        response = client.get("/api/learn/suggestions")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["url"] for item in items] == ["https://example.com/blog/1"]


def test_dismiss_suggestion_endpoint(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        article_id = _add_article(conn, user_id=user_id, slug="blog", index=1, state="done")

    with _api_client(user_id) as client:
        dismiss_response = client.post(
            "/api/learn/suggestions/dismiss", json={"article_id": article_id}
        )
        list_response = client.get("/api/learn/suggestions")

    assert dismiss_response.status_code == 200
    assert dismiss_response.json() == {"dismissed": True, "article_id": article_id}
    assert list_response.json()["items"] == []


def test_dismiss_suggestion_endpoint_does_not_affect_other_users(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    with connect(database_url=pg_clean) as conn:
        _add_source(conn, "blog", "Blog")
        _add_article(conn, user_id=alice, slug="blog", index=1, state="done")
        article_id = _add_article(conn, user_id=bob, slug="blog", index=2, state="done")

    with _api_client(bob, "bob") as client:
        client.post("/api/learn/suggestions/dismiss", json={"article_id": article_id})

    with _api_client(alice) as client:
        response = client.get("/api/learn/suggestions")

    assert [item["url"] for item in response.json()["items"]] == ["https://example.com/blog/1"]
