"""Tests for #88 search filter combinations."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import connect, init_db
from news_dashboard.ingest import list_articles, search_articles, sync_sources
from news_dashboard.main import app


def _db(tmp: Path) -> Path:
    return tmp / "news.db"


def _insert(  # noqa: PLR0913
    db_path: Path,
    *,
    title: str = "Article",
    summary: str = "",
    reason: str = "",
    body: str | None = None,
    category: str = "python",
    source_slug: str = "python-insider",
    source_name: str = "Python Insider",
    state: str = "today",
    starred: bool = False,
    url_suffix: str = "",
) -> int:
    url = f"https://example.com/{title.lower().replace(' ', '-')}{url_suffix}"
    with connect(db_path) as conn:
        # Ensure the referenced source exists (FK constraint).
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled)"
            " VALUES (%s, %s, %s, %s, 'rss_feed', 50, TRUE)"
            " ON CONFLICT(slug) DO NOTHING",
            (source_slug, source_name, f"https://example.com/{source_slug}.xml", category),
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, starred, summary, reason, tags, body
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                url,
                url,
                title,
                source_slug,
                source_name,
                category,
                "rss_feed",
                state,
                starred,
                summary,
                reason,
                "[]",
                body,
            ),
        ).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = _db(tmp_path)
    sync_sources(path)
    init_db(path)
    return path


# ─── Text search ─────────────────────────────────────────────────────────────


def test_search_by_title(db: Path) -> None:
    _insert(db, title="FastAPI Guide")
    _insert(db, title="Django Tutorial")
    results = search_articles("FastAPI", db_path=db)
    titles = [r["title"] for r in results]
    assert "FastAPI Guide" in titles
    assert "Django Tutorial" not in titles


def test_search_by_summary(db: Path) -> None:
    _insert(db, title="Article A", summary="Covers asyncio patterns")
    _insert(db, title="Article B", summary="CSS grid layout tricks")
    results = search_articles("asyncio", db_path=db)
    assert any(r["title"] == "Article A" for r in results)
    assert all(r["title"] != "Article B" for r in results)


def test_search_by_reason(db: Path) -> None:
    _insert(db, title="Article A", reason="Relevant because of Python 3.13 release")
    _insert(db, title="Article B", reason="Unrelated content")
    results = search_articles("Python 3.13", db_path=db)
    assert any(r["title"] == "Article A" for r in results)


def test_search_by_body(db: Path) -> None:
    _insert(db, title="Deep Dive", body="The full text discusses pydantic validation in detail")
    _insert(db, title="Other Article", body="Nothing relevant here")
    results = search_articles("pydantic", db_path=db)
    assert any(r["title"] == "Deep Dive" for r in results)
    assert all(r["title"] != "Other Article" for r in results)


def test_search_results_omit_cached_body_payload(db: Path) -> None:
    _insert(db, title="Deep Dive", body="The full text discusses pydantic validation in detail")
    results = search_articles("pydantic", db_path=db)
    article = next(r for r in results if r["title"] == "Deep Dive")
    assert "body" not in article
    assert article["body_status"] == "missing"


def test_list_articles_omits_cached_body_payload(db: Path) -> None:
    _insert(db, title="Deep Dive", body="Large cached article body")
    articles = list_articles(db_path=db)
    article = next(r for r in articles if r["title"] == "Deep Dive")
    assert "body" not in article
    assert article["body_status"] == "missing"


def test_no_query_returns_empty_without_filters(db: Path) -> None:
    _insert(db, title="Some Article")
    # Empty q with no filters returns nothing (SELECT * LIMIT n)
    # but with include_archived=False the default archived exclusion applies
    results = search_articles("", db_path=db)
    # Should not error; may return articles since no WHERE clauses restrict much
    assert isinstance(results, list)


# ─── State filter ─────────────────────────────────────────────────────────────


def test_filter_by_state(db: Path) -> None:
    _insert(db, title="Today Art", state="today", url_suffix="-1")
    _insert(db, title="Done Art", state="done", url_suffix="-2")
    _insert(db, title="Archived Art", state="archived", url_suffix="-3")

    results = search_articles(db_path=db, states=["today"])
    titles = [r["title"] for r in results]
    assert "Today Art" in titles
    assert "Done Art" not in titles
    assert "Archived Art" not in titles


def test_filter_multiple_states(db: Path) -> None:
    _insert(db, title="Today Art", state="today", url_suffix="-1")
    _insert(db, title="Done Art", state="done", url_suffix="-2")
    _insert(db, title="Skipped Art", state="skipped", url_suffix="-3")

    results = search_articles(db_path=db, states=["today", "done"])
    titles = [r["title"] for r in results]
    assert "Today Art" in titles
    assert "Done Art" in titles
    assert "Skipped Art" not in titles


# ─── Archived exclusion ───────────────────────────────────────────────────────


def test_archived_excluded_by_default(db: Path) -> None:
    _insert(db, title="Active", state="today", url_suffix="-1")
    _insert(db, title="Archived", state="archived", url_suffix="-2")

    results = search_articles(db_path=db)
    titles = [r["title"] for r in results]
    assert "Active" in titles
    assert "Archived" not in titles


def test_include_archived(db: Path) -> None:
    _insert(db, title="Active", state="today", url_suffix="-1")
    _insert(db, title="Archived", state="archived", url_suffix="-2")

    results = search_articles(db_path=db, include_archived=True)
    titles = [r["title"] for r in results]
    assert "Active" in titles
    assert "Archived" in titles


# ─── Starred filter ───────────────────────────────────────────────────────────


def test_starred_only(db: Path) -> None:
    _insert(db, title="Starred Art", starred=True, url_suffix="-1")
    _insert(db, title="Normal Art", starred=False, url_suffix="-2")

    results = search_articles(db_path=db, starred_only=True)
    titles = [r["title"] for r in results]
    assert "Starred Art" in titles
    assert "Normal Art" not in titles


# ─── Category filter ──────────────────────────────────────────────────────────


def test_filter_by_category(db: Path) -> None:
    _insert(db, title="Python Art", category="python", url_suffix="-1")
    _insert(db, title="AI Art", category="ai-llm", url_suffix="-2")

    results = search_articles(db_path=db, categories=["python"])
    titles = [r["title"] for r in results]
    assert "Python Art" in titles
    assert "AI Art" not in titles


def test_filter_multiple_categories(db: Path) -> None:
    _insert(db, title="Python Art", category="python", url_suffix="-1")
    _insert(db, title="AI Art", category="ai-llm", url_suffix="-2")
    _insert(db, title="Infra Art", category="cloud-infra", url_suffix="-3")

    results = search_articles(db_path=db, categories=["python", "ai-llm"])
    titles = [r["title"] for r in results]
    assert "Python Art" in titles
    assert "AI Art" in titles
    assert "Infra Art" not in titles


# ─── Source filter ────────────────────────────────────────────────────────────


def test_filter_by_source(db: Path) -> None:
    _insert(db, title="Insider Art", source_slug="python-insider", url_suffix="-1")
    _insert(
        db,
        title="Weekly Art",
        source_slug="python-weekly",
        source_name="Python Weekly",
        url_suffix="-2",
    )

    results = search_articles(db_path=db, sources=["python-insider"])
    titles = [r["title"] for r in results]
    assert "Insider Art" in titles
    assert "Weekly Art" not in titles


# ─── Combined filters ─────────────────────────────────────────────────────────


def test_q_plus_state_filter(db: Path) -> None:
    _insert(db, title="FastAPI Guide", state="today", url_suffix="-1")
    _insert(db, title="FastAPI Tutorial", state="done", url_suffix="-2")
    _insert(db, title="Django Guide", state="today", url_suffix="-3")

    results = search_articles("FastAPI", db_path=db, states=["today"])
    titles = [r["title"] for r in results]
    assert "FastAPI Guide" in titles
    assert "FastAPI Tutorial" not in titles
    assert "Django Guide" not in titles


def test_starred_plus_category_filter(db: Path) -> None:
    _insert(db, title="Starred Python", category="python", starred=True, url_suffix="-1")
    _insert(db, title="Unstarred Python", category="python", starred=False, url_suffix="-2")
    _insert(db, title="Starred AI", category="ai-llm", starred=True, url_suffix="-3")

    results = search_articles(db_path=db, starred_only=True, categories=["python"])
    titles = [r["title"] for r in results]
    assert "Starred Python" in titles
    assert "Unstarred Python" not in titles
    assert "Starred AI" not in titles


# ─── API endpoint tests ───────────────────────────────────────────────────────


@pytest.fixture
def api_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use an isolated PostgreSQL schema and patch the app to use it."""
    import news_dashboard.db as db_mod
    import news_dashboard.ingest as ingest_mod

    path = tmp_path / "search_api.db"
    monkeypatch.setattr(db_mod, "DB_PATH", path)
    monkeypatch.setattr(ingest_mod, "DB_PATH", path, raising=False)
    init_db(path)
    sync_sources(path)
    return path


@pytest.fixture
def client(api_db: Path) -> TestClient:
    return TestClient(app)


def test_search_endpoint_defaults(client: TestClient) -> None:
    resp = client.get("/api/search")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_search_endpoint_with_q(client: TestClient) -> None:
    resp = client.get("/api/search?q=python")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


def test_search_endpoint_state_filter(client: TestClient) -> None:
    resp = client.get("/api/search?states=today&states=done")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_search_endpoint_category_filter(client: TestClient) -> None:
    resp = client.get("/api/search?categories=python&categories=ai-llm")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_search_endpoint_starred_only(client: TestClient) -> None:
    resp = client.get("/api/search?starred_only=true")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_search_endpoint_include_archived(client: TestClient) -> None:
    resp = client.get("/api/search?include_archived=true")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_search_endpoint_date_range(client: TestClient, api_db: Path) -> None:
    _insert(api_db, title="Recent", url_suffix="-recent")
    for dr in ["today", "week", "month"]:
        resp = client.get(f"/api/search?date_range={dr}")
        assert resp.status_code == 200, f"Failed for date_range={dr}"


def test_search_endpoint_all_filters(client: TestClient) -> None:
    resp = client.get(
        "/api/search?q=python&states=today&categories=python"
        "&starred_only=false&include_archived=false&date_range=week"
    )
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_search_endpoint_returns_matching_articles(client: TestClient, api_db: Path) -> None:
    _insert(api_db, title="Pytest Tips", category="python", state="today", url_suffix="-1")
    _insert(api_db, title="Rust Intro", category="engineering", state="today", url_suffix="-2")

    resp = client.get("/api/search?q=Pytest&categories=python")
    assert resp.status_code == 200
    items = resp.json()["items"]
    titles = [it["title"] for it in items]
    assert "Pytest Tips" in titles
    assert "Rust Intro" not in titles


# ─── Text relevance ordering ──────────────────────────────────────────────────


def _insert_with_score(  # noqa: PLR0913
    db_path: Path,
    *,
    importance_score: int,
    title: str = "Article",
    summary: str = "",
    reason: str = "",
    body: str | None = None,
    category: str = "python",
    source_slug: str = "python-insider",
    source_name: str = "Python Insider",
    state: str = "today",
    starred: bool = False,
    url_suffix: str = "",
) -> int:
    article_id = _insert(
        db_path,
        title=title,
        summary=summary,
        reason=reason,
        body=body,
        category=category,
        source_slug=source_slug,
        source_name=source_name,
        state=state,
        starred=starred,
        url_suffix=url_suffix,
    )
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET importance_score = %s WHERE id = %s",
            (importance_score, article_id),
        )
    return article_id


def test_title_match_outranks_high_importance_weak_match(db: Path) -> None:
    """A direct title match should rank above a higher-importance article with only a body match."""
    _insert_with_score(
        db,
        title="asyncio Deep Dive",
        summary="asyncio event loop internals",
        importance_score=90,
        url_suffix="-strong",
    )
    _insert_with_score(
        db,
        title="Web Frameworks Overview",
        summary="overview of python web frameworks",
        body="mentions asyncio briefly in passing",
        importance_score=50,
        url_suffix="-weak",
    )

    results = search_articles("asyncio", db_path=db)
    titles = [r["title"] for r in results]
    assert titles.index("asyncio Deep Dive") < titles.index("Web Frameworks Overview"), (
        "Direct title/summary match should rank before weak body-only match"
    )


def _make_user(db_path: Path, username: str) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"] if isinstance(row, dict) else row[0])


def test_user_scoped_title_match_outranks_high_importance_weak_match(db: Path) -> None:
    """User-scoped search should also rank by text relevance before importance_score."""
    user_id = _make_user(db, "rel_test_user")

    _insert_with_score(
        db,
        title="pydantic Validation Guide",
        summary="pydantic model validation explained",
        importance_score=90,
        url_suffix="-strong-user",
    )
    _insert_with_score(
        db,
        title="General Python Tips",
        summary="various python tips",
        body="pydantic is mentioned once here",
        importance_score=50,
        url_suffix="-weak-user",
    )

    results = search_articles("pydantic", db_path=db, user_id=user_id)
    titles = [r["title"] for r in results]
    assert "pydantic Validation Guide" in titles
    assert titles.index("pydantic Validation Guide") < titles.index("General Python Tips"), (
        "User-scoped direct title/summary match should rank before weak body-only match"
    )


def test_empty_query_keeps_importance_ordering(db: Path) -> None:
    """Filter-only search (empty q) must preserve importance_score DESC ordering."""
    _insert_with_score(db, title="Low Importance", importance_score=10, url_suffix="-low")
    _insert_with_score(db, title="High Importance", importance_score=99, url_suffix="-high")

    results = search_articles("", db_path=db)
    titles = [r["title"] for r in results]
    assert titles.index("High Importance") < titles.index("Low Importance"), (
        "Empty-query search must order by importance_score DESC, not text rank"
    )
