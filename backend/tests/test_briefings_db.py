"""PostgreSQL integration tests for briefings.py.

These tests exercise the actual psycopg %s parameterisation, JSONB round-trip,
TIMESTAMPTZ ordering, and the NULLS LAST clause in _CITED_ARTICLES_SQL.  They
require a live PostgreSQL instance supplied via the session-scoped ``pg_url``
fixture (started by testcontainers) and are skipped when Docker is unavailable.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
import pytest

import news_dashboard.briefings as briefings_mod
from news_dashboard.briefings import (
    CANDIDATE_LIMIT,
    IDEMPOTENCY_WINDOW_MINUTES,
    BriefingGenerationError,
    _get_since_at,
    _validate_content,
    generate_briefing,
    get_briefing,
    get_latest_briefing,
    list_briefings,
    select_candidates,
)
from news_dashboard.db import connect

# ── Seeding helpers ───────────────────────────────────────────────────────────


def _seed_source(pg_url: str, slug: str = "test-source") -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, "Test Source", f"https://example.com/{slug}", "tech", "rss_feed"),
        )


def _seed_user(pg_url: str, username: str = "briefing-user") -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO users(username, password_hash)
            VALUES (%s, %s)
            RETURNING id
            """,
            (username, "hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_article(
    pg_url: str,
    *,
    url: str,
    title: str = "Test Article",
    source_slug: str = "test-source",
    importance_score: int = 50,
    state: str = "new",
    discovered_at: str | None = None,
) -> int:
    extra_cols = ""
    extra_vals: tuple[object, ...] = ()
    if discovered_at is not None:
        extra_cols = ", discovered_at"
        extra_vals = (discovered_at,)
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            f"""
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, importance_score, state{extra_cols}
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s{", %s" if discovered_at else ""})
            RETURNING id
            """,
            (
                url,
                url,
                title,
                source_slug,
                "Test Source",
                "tech",
                "rss_feed",
                importance_score,
                state,
                *extra_vals,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_user_article_state(pg_url: str, user_id: int, article_id: int, state: str) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id, article_id) DO UPDATE SET state = excluded.state
            """,
            (user_id, article_id, state),
        )


def _seed_briefing(
    pg_url: str,
    *,
    title: str = "Test Brief",
    content: dict[str, Any] | None = None,
    created_at: str | None = None,
    until_at: str = "2026-06-13T00:00:00+00:00",
) -> int:
    _content = content or {"sections": [], "worth_opening": []}
    extra_cols = ""
    extra_vals: tuple[object, ...] = ()
    if created_at:
        extra_cols = ", created_at"
        extra_vals = (created_at,)

    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            f"""
            INSERT INTO briefings(
              title, summary, content, status, scope, since_at, until_at, model
              {extra_cols}
            )
            VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s{", %s" if created_at else ""})
            RETURNING id
            """,
            (
                title,
                "A test summary.",
                json.dumps(_content),
                "complete",
                "since_last_briefing",
                "2026-06-12T00:00:00+00:00",
                until_at,
                "claude-sonnet-4-6",
                *extra_vals,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _link_article(
    pg_url: str,
    briefing_id: int,
    article_id: int,
    *,
    section_index: int | None = None,
    citation_index: int | None = None,
) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO briefing_articles(briefing_id, article_id, section_index, citation_index)
            VALUES (%s, %s, %s, %s)
            """,
            (briefing_id, article_id, section_index, citation_index),
        )


# ── Schema / init_db ─────────────────────────────────────────────────────────


def test_postgres_schema_has_briefings_table(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables"
            " WHERE table_name = 'briefings' AND table_schema = 'public'"
        ).fetchone()
    assert row is not None, "briefings table missing after init_db"


def test_postgres_schema_has_briefing_articles_table(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables"
            " WHERE table_name = 'briefing_articles' AND table_schema = 'public'"
        ).fetchone()
    assert row is not None, "briefing_articles table missing after init_db"


def test_postgres_briefings_content_column_is_jsonb(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "SELECT data_type FROM information_schema.columns"
            " WHERE table_name = 'briefings' AND column_name = 'content'"
        ).fetchone()
    assert row is not None
    assert row[0] == "jsonb"


def test_postgres_briefings_created_at_is_timestamptz(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "SELECT data_type FROM information_schema.columns"
            " WHERE table_name = 'briefings' AND column_name = 'created_at'"
        ).fetchone()
    assert row is not None
    assert row[0] == "timestamp with time zone"


# ── get_latest_briefing ───────────────────────────────────────────────────────


def test_get_latest_briefing_returns_none_when_empty(pg_clean: str) -> None:
    assert get_latest_briefing(database_url=pg_clean) is None


def test_get_latest_briefing_returns_briefing(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="First Brief")
    result = get_latest_briefing(database_url=pg_clean)
    assert result is not None
    assert result["title"] == "First Brief"
    assert result["status"] == "complete"
    assert result["scope"] == "since_last_briefing"


def test_get_latest_briefing_returns_most_recent(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="Older Brief", created_at="2026-06-12T10:00:00+00:00")
    _seed_briefing(pg_clean, title="Newest Brief", created_at="2026-06-13T10:00:00+00:00")
    result = get_latest_briefing(database_url=pg_clean)
    assert result is not None
    assert result["title"] == "Newest Brief"


def test_get_latest_briefing_decodes_jsonb_content(pg_clean: str) -> None:
    _seed_source(pg_clean)
    content = {
        "sections": [{"title": "AI News", "body": "...", "citations": []}],
        "worth_opening": [],
    }
    _seed_briefing(pg_clean, content=content)
    result = get_latest_briefing(database_url=pg_clean)
    assert result is not None
    # psycopg should return JSONB as a Python dict (not a JSON string)
    assert isinstance(result["content"], dict)
    assert result["content"]["sections"][0]["title"] == "AI News"


def test_get_latest_briefing_includes_cited_articles(pg_clean: str) -> None:
    _seed_source(pg_clean)
    a_id = _seed_article(pg_clean, url="https://example.com/a1", title="Article One")
    b_id = _seed_briefing(pg_clean)
    _link_article(pg_clean, b_id, a_id, section_index=0, citation_index=0)

    result = get_latest_briefing(database_url=pg_clean)
    assert result is not None
    assert len(result["articles"]) == 1
    art = result["articles"][0]
    assert art["id"] == a_id
    assert art["title"] == "Article One"
    assert art["section_index"] == 0
    assert art["citation_index"] == 0


def test_get_latest_briefing_empty_articles_list_when_no_citations(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean)
    result = get_latest_briefing(database_url=pg_clean)
    assert result is not None
    assert result["articles"] == []


# ── list_briefings ────────────────────────────────────────────────────────────


def test_list_briefings_returns_empty_list(pg_clean: str) -> None:
    assert list_briefings(database_url=pg_clean) == []


def test_list_briefings_returns_metadata_only(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="Brief A")
    items = list_briefings(database_url=pg_clean)
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Brief A"
    # List endpoint omits the content blob and articles
    assert "content" not in item
    assert "articles" not in item


def test_list_briefings_reverse_chronological(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="Old", created_at="2026-06-11T10:00:00+00:00")
    _seed_briefing(pg_clean, title="New", created_at="2026-06-13T10:00:00+00:00")
    items = list_briefings(database_url=pg_clean)
    assert len(items) == 2
    assert items[0]["title"] == "New"
    assert items[1]["title"] == "Old"


def test_list_briefings_limit(pg_clean: str) -> None:
    _seed_source(pg_clean)
    for i in range(5):
        _seed_briefing(pg_clean, title=f"Brief {i}")
    assert len(list_briefings(limit=3, database_url=pg_clean)) == 3


def test_list_briefings_offset(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="First", created_at="2026-06-11T00:00:00+00:00")
    _seed_briefing(pg_clean, title="Second", created_at="2026-06-12T00:00:00+00:00")
    _seed_briefing(pg_clean, title="Third", created_at="2026-06-13T00:00:00+00:00")
    items = list_briefings(limit=2, offset=1, database_url=pg_clean)
    # Reverse chron: Third, Second, First — offset 1 skips Third
    assert len(items) == 2
    assert items[0]["title"] == "Second"
    assert items[1]["title"] == "First"


# ── get_briefing ──────────────────────────────────────────────────────────────


def test_get_briefing_returns_none_for_missing_id(pg_clean: str) -> None:
    assert get_briefing(99999, database_url=pg_clean) is None


def test_get_briefing_returns_full_content(pg_clean: str) -> None:
    _seed_source(pg_clean)
    content = {
        "sections": [{"title": "Section 1", "body": "Body.", "citations": []}],
        "worth_opening": [],
    }
    b_id = _seed_briefing(pg_clean, title="Full Brief", content=content)
    result = get_briefing(b_id, database_url=pg_clean)
    assert result is not None
    assert result["id"] == b_id
    assert result["title"] == "Full Brief"
    assert isinstance(result["content"], dict)
    assert result["content"]["sections"][0]["title"] == "Section 1"


def test_get_briefing_returns_cited_articles(pg_clean: str) -> None:
    _seed_source(pg_clean)
    a_id = _seed_article(pg_clean, url="https://example.com/cited", title="Cited Article")
    b_id = _seed_briefing(pg_clean)
    _link_article(pg_clean, b_id, a_id, section_index=0, citation_index=0)

    result = get_briefing(b_id, database_url=pg_clean)
    assert result is not None
    assert len(result["articles"]) == 1
    assert result["articles"][0]["title"] == "Cited Article"


def test_get_briefing_does_not_return_other_briefing_articles(pg_clean: str) -> None:
    _seed_source(pg_clean)
    a1 = _seed_article(pg_clean, url="https://example.com/a1", title="Article A")
    a2 = _seed_article(pg_clean, url="https://example.com/a2", title="Article B")
    b1 = _seed_briefing(pg_clean, title="Brief 1")
    b2 = _seed_briefing(pg_clean, title="Brief 2")
    _link_article(pg_clean, b1, a1)
    _link_article(pg_clean, b2, a2)

    result = get_briefing(b1, database_url=pg_clean)
    assert result is not None
    assert len(result["articles"]) == 1
    assert result["articles"][0]["title"] == "Article A"


# ── NULLS LAST ordering ───────────────────────────────────────────────────────


@pytest.mark.postgres
def test_cited_articles_nulls_last_in_section_index(pg_clean: str) -> None:
    """Articles with NULL section_index must sort after those with an explicit index."""
    _seed_source(pg_clean)
    a_no_section = _seed_article(pg_clean, url="https://example.com/no-section", title="No Section")
    a_section_0 = _seed_article(pg_clean, url="https://example.com/section-0", title="Section 0")
    a_section_1 = _seed_article(pg_clean, url="https://example.com/section-1", title="Section 1")

    b_id = _seed_briefing(pg_clean)
    # Insert out-of-order to prove ordering comes from SQL, not insertion order
    _link_article(pg_clean, b_id, a_no_section, section_index=None, citation_index=None)
    _link_article(pg_clean, b_id, a_section_1, section_index=1, citation_index=0)
    _link_article(pg_clean, b_id, a_section_0, section_index=0, citation_index=0)

    result = get_briefing(b_id, database_url=pg_clean)
    assert result is not None
    titles = [a["title"] for a in result["articles"]]
    # section_index=0 first, then 1, then NULL (NULLS LAST)
    assert titles == ["Section 0", "Section 1", "No Section"]


@pytest.mark.postgres
def test_cited_articles_nulls_last_in_citation_index(pg_clean: str) -> None:
    """Within the same section, NULL citation_index sorts after explicit values."""
    _seed_source(pg_clean)
    a_null_cite = _seed_article(
        pg_clean, url="https://example.com/null-cite", title="No Cite Index"
    )
    a_cite_0 = _seed_article(pg_clean, url="https://example.com/cite-0", title="Cite 0")

    b_id = _seed_briefing(pg_clean)
    _link_article(pg_clean, b_id, a_null_cite, section_index=0, citation_index=None)
    _link_article(pg_clean, b_id, a_cite_0, section_index=0, citation_index=0)

    result = get_briefing(b_id, database_url=pg_clean)
    assert result is not None
    titles = [a["title"] for a in result["articles"]]
    assert titles == ["Cite 0", "No Cite Index"]


# ── _get_since_at ─────────────────────────────────────────────────────────────


def test_get_since_at_returns_24h_ago_when_no_briefings(pg_clean: str) -> None:
    before = datetime.now(timezone.utc) - timedelta(hours=24, seconds=5)
    result = _get_since_at(database_url=pg_clean)
    after = datetime.now(timezone.utc) - timedelta(hours=24) + timedelta(seconds=5)
    assert before <= result <= after


def test_get_since_at_returns_previous_briefing_until_at(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean)
    result = _get_since_at(database_url=pg_clean)
    # _seed_briefing sets until_at = "2026-06-13T00:00:00+00:00"
    expected = datetime(2026, 6, 13, 0, 0, 0, tzinfo=timezone.utc)
    assert result == expected


def test_get_since_at_uses_most_recent_briefing(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, created_at="2026-06-11T00:00:00+00:00")
    _seed_briefing(pg_clean, created_at="2026-06-13T00:00:00+00:00")
    # Both briefings have until_at = "2026-06-13T00:00:00+00:00" (seeded default)
    # Most recent by created_at is the second one
    result = _get_since_at(database_url=pg_clean)
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


# ── select_candidates ─────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeBriefingConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> _FakeBriefingConn:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> _FakeCursor:
        self.calls.append((query, params))
        return _FakeCursor(self.rows)


def test_select_candidates_sql_ignores_global_workflow_state(monkeypatch: Any) -> None:
    since_at = datetime(2026, 6, 17, 0, 0, tzinfo=timezone.utc)
    until_at = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
    fake_conn = _FakeBriefingConn(
        [{"id": 1, "title": "Done article", "importance_score": 90, "discovered_at": since_at}]
    )

    def _connect(**_: object) -> _FakeBriefingConn:
        return fake_conn

    monkeypatch.setattr(briefings_mod, "connect", _connect)

    candidates = select_candidates(since_at, until_at=until_at, database_url="postgresql://test")

    query, params = fake_conn.calls[0]
    assert "state = 'today'" not in query
    assert "discovered_at::timestamptz >= %s" in query
    assert "discovered_at::timestamptz < %s" in query
    assert params == (since_at, until_at, CANDIDATE_LIMIT)
    assert candidates[0]["title"] == "Done article"


def test_select_candidates_sql_ignores_user_workflow_state(monkeypatch: Any) -> None:
    since_at = datetime(2026, 6, 17, 0, 0, tzinfo=timezone.utc)
    until_at = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
    fake_conn = _FakeBriefingConn(
        [
            {
                "id": 2,
                "title": "User skipped article",
                "importance_score": 80,
                "discovered_at": since_at,
            }
        ]
    )

    def _connect(**_: object) -> _FakeBriefingConn:
        return fake_conn

    monkeypatch.setattr(briefings_mod, "connect", _connect)

    candidates = select_candidates(
        since_at,
        until_at=until_at,
        database_url="postgresql://test",
        user_id=7,
    )

    query, params = fake_conn.calls[0]
    assert "COALESCE(uas.state, 'today') = 'today'" not in query
    assert "LEFT JOIN user_article_state" in query
    assert params == (7, 7, since_at, until_at, 7, CANDIDATE_LIMIT)
    assert candidates[0]["title"] == "User skipped article"


def test_select_candidates_returns_current_day_articles_regardless_workflow_state(
    pg_clean: str,
) -> None:
    _seed_source(pg_clean)
    since_at = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_article(pg_clean, url="https://example.com/today-1", title="Today 1", state="today")
    _seed_article(pg_clean, url="https://example.com/later-1", title="Later 1", state="later")
    _seed_article(pg_clean, url="https://example.com/done-1", title="Done 1", state="done")
    _seed_article(pg_clean, url="https://example.com/skipped-1", title="Skipped 1", state="skipped")

    candidates = select_candidates(since_at, database_url=pg_clean)
    titles = [a["title"] for a in candidates]
    assert "Today 1" in titles
    assert "Later 1" in titles
    assert "Done 1" in titles
    assert "Skipped 1" in titles


def test_select_candidates_for_user_ignores_user_workflow_state(pg_clean: str) -> None:
    _seed_source(pg_clean)
    user_id = _seed_user(pg_clean)
    since_at = datetime.now(timezone.utc) - timedelta(hours=1)
    article_id = _seed_article(
        pg_clean,
        url="https://example.com/user-done-1",
        title="User Done 1",
        state="today",
    )
    _set_user_article_state(pg_clean, user_id, article_id, "done")

    candidates = select_candidates(since_at, database_url=pg_clean, user_id=user_id)

    assert [a["title"] for a in candidates] == ["User Done 1"]


def test_select_candidates_filters_by_since_at(pg_clean: str) -> None:
    _seed_source(pg_clean)
    since_at = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    _seed_article(
        pg_clean,
        url="https://example.com/recent",
        title="Recent",
        state="today",
        discovered_at=recent_ts,
    )
    _seed_article(
        pg_clean,
        url="https://example.com/old",
        title="Old",
        state="today",
        discovered_at=old_ts,
    )

    candidates = select_candidates(since_at, database_url=pg_clean)
    titles = [a["title"] for a in candidates]
    assert "Recent" in titles
    assert "Old" not in titles


def test_select_candidates_caps_at_limit(pg_clean: str) -> None:
    _seed_source(pg_clean)
    since_at = datetime.now(timezone.utc) - timedelta(hours=1)
    for i in range(CANDIDATE_LIMIT + 5):
        _seed_article(
            pg_clean,
            url=f"https://example.com/art-{i}",
            title=f"Article {i}",
            state="today",
        )

    candidates = select_candidates(since_at, database_url=pg_clean)
    assert len(candidates) == CANDIDATE_LIMIT


def test_select_candidates_ordered_by_importance_desc(pg_clean: str) -> None:
    _seed_source(pg_clean)
    since_at = datetime.now(timezone.utc) - timedelta(hours=1)
    _seed_article(
        pg_clean,
        url="https://example.com/low",
        title="Low",
        state="today",
        importance_score=10,
    )
    _seed_article(
        pg_clean,
        url="https://example.com/high",
        title="High",
        state="today",
        importance_score=90,
    )

    candidates = select_candidates(since_at, database_url=pg_clean)
    assert candidates[0]["title"] == "High"
    assert candidates[1]["title"] == "Low"


# ── _validate_content (pure unit tests, no DB required) ───────────────────────


def test_validate_content_strips_unknown_citations() -> None:
    raw = {
        "title": "T",
        "summary": "S",
        "sections": [{"title": "A", "body": "B", "citations": [1, 2, 99]}],
        "worth_opening": [1, 88],
    }
    result = _validate_content(raw, candidate_ids={1, 2})
    assert result["sections"][0]["citations"] == [1, 2]
    assert result["worth_opening"] == [1]


def test_validate_content_raises_on_missing_title() -> None:
    raw: dict[str, Any] = {"summary": "S", "sections": []}
    with pytest.raises(BriefingGenerationError, match="missing required keys"):
        _validate_content(raw, candidate_ids=set())


def test_validate_content_raises_on_missing_sections() -> None:
    raw: dict[str, Any] = {"title": "T", "summary": "S"}
    with pytest.raises(BriefingGenerationError, match="missing required keys"):
        _validate_content(raw, candidate_ids=set())


def test_validate_content_handles_empty_worth_opening() -> None:
    raw: dict[str, Any] = {"title": "T", "summary": "S", "sections": []}
    result = _validate_content(raw, candidate_ids={1, 2})
    assert result["worth_opening"] == []


# ── generate_briefing (end-to-end with fake AI) ───────────────────────────────


def _fake_ai(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
    """Minimal deterministic AI stub: puts the first two candidates in a section."""
    ids = [c["id"] for c in candidates[:2]]
    return {
        "title": "Fake Briefing",
        "summary": "A fake summary.",
        "sections": [{"title": "Top Stories", "body": "Stuff happened.", "citations": ids}],
        "worth_opening": ids[:1],
    }


def test_generate_briefing_no_candidates_returns_status(pg_clean: str) -> None:
    # No articles seeded → no today candidates
    result = generate_briefing(database_url=pg_clean, ai_fn=_fake_ai)
    assert result == {"status": "no_candidates"}


def test_generate_briefing_creates_briefing_row(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_article(pg_clean, url="https://example.com/a1", title="Article 1", state="today")
    _seed_article(pg_clean, url="https://example.com/a2", title="Article 2", state="today")

    result = generate_briefing(database_url=pg_clean, ai_fn=_fake_ai)

    assert result["title"] == "Fake Briefing"
    assert result["summary"] == "A fake summary."
    assert result["status"] == "complete"
    assert result["scope"] == "current_day"
    assert result["since_at"] is not None
    assert result["until_at"] is not None


def test_generate_briefing_uses_current_day_window_not_previous_briefing_until(
    pg_clean: str,
) -> None:
    _seed_source(pg_clean)
    future_until_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    _seed_briefing(pg_clean, until_at=future_until_at)
    article_id = _seed_article(
        pg_clean,
        url="https://example.com/current-day-after-previous",
        title="Current Day After Previous",
        state="done",
        discovered_at=(datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
    )

    result = generate_briefing(
        database_url=pg_clean,
        ai_fn=_fake_ai,
        idempotency_window_minutes=0,
    )

    assert result["scope"] == "current_day"
    assert {a["id"] for a in result["articles"]} == {article_id}


def test_generate_briefing_links_section_citations(pg_clean: str) -> None:
    _seed_source(pg_clean)
    # Use distinct importance scores so candidate ordering is deterministic
    a1 = _seed_article(
        pg_clean, url="https://example.com/b1", title="B1", state="today", importance_score=90
    )
    a2 = _seed_article(
        pg_clean, url="https://example.com/b2", title="B2", state="today", importance_score=10
    )

    # _fake_ai puts candidates[0] (a1, score=90) and candidates[1] (a2, score=10) in citations
    result = generate_briefing(database_url=pg_clean, ai_fn=_fake_ai)

    article_ids = {a["id"] for a in result["articles"]}
    assert a1 in article_ids
    assert a2 in article_ids

    cited = {a["id"]: a for a in result["articles"]}
    assert cited[a1]["section_index"] == 0
    assert cited[a1]["citation_index"] == 0  # a1 is candidates[0] → citation index 0
    assert cited[a2]["section_index"] == 0
    assert cited[a2]["citation_index"] == 1  # a2 is candidates[1] → citation index 1


def test_generate_briefing_worth_opening_gets_null_indices(pg_clean: str) -> None:
    _seed_source(pg_clean)
    # Seed with distinct importance scores for deterministic candidate order:
    # candidates order will be: a1 (90), a2 (50), a3 (10)
    a1 = _seed_article(
        pg_clean, url="https://example.com/c1", title="C1", state="today", importance_score=90
    )
    a2 = _seed_article(
        pg_clean, url="https://example.com/c2", title="C2", state="today", importance_score=50
    )
    a3 = _seed_article(
        pg_clean, url="https://example.com/c3", title="C3", state="today", importance_score=10
    )

    # Use a closure so the AI references known IDs directly, ignoring candidate order
    def _ai_worth_only(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
        return {
            "title": "T",
            "summary": "S",
            # a1 and a2 are section citations; a3 appears only in worth_opening
            "sections": [{"title": "S0", "body": "B", "citations": [a1, a2]}],
            "worth_opening": [a3],
        }

    result = generate_briefing(database_url=pg_clean, ai_fn=_ai_worth_only)
    by_id = {a["id"]: a for a in result["articles"]}

    assert a3 in by_id
    assert by_id[a3]["section_index"] is None
    assert by_id[a3]["citation_index"] is None
    assert a1 in by_id
    assert by_id[a1]["section_index"] == 0
    assert by_id[a1]["citation_index"] == 0
    assert a2 in by_id
    assert by_id[a2]["section_index"] == 0
    assert by_id[a2]["citation_index"] == 1


def test_generate_briefing_persisted_to_db(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_article(pg_clean, url="https://example.com/d1", title="D1", state="today")

    generate_briefing(database_url=pg_clean, ai_fn=_fake_ai)

    briefings = list_briefings(database_url=pg_clean)
    assert len(briefings) == 1
    assert briefings[0]["title"] == "Fake Briefing"


# ── Failed-status persistence ─────────────────────────────────────────────────


def test_generate_briefing_persists_failed_row_on_generation_error(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_article(pg_clean, url="https://example.com/e1", title="E1", state="today")

    def _bad_ai(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
        msg = "simulated AI failure"
        raise BriefingGenerationError(msg)

    with pytest.raises(BriefingGenerationError):
        generate_briefing(database_url=pg_clean, ai_fn=_bad_ai)

    briefings = list_briefings(database_url=pg_clean)
    assert len(briefings) == 1
    assert briefings[0]["status"] == "failed"
    assert "simulated AI failure" in (briefings[0]["error"] or "")


def test_generate_briefing_failed_row_has_no_content(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_article(pg_clean, url="https://example.com/f1", title="F1", state="today")

    def _bad_ai(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
        msg = "boom"
        raise BriefingGenerationError(msg)

    with pytest.raises(BriefingGenerationError):
        generate_briefing(database_url=pg_clean, ai_fn=_bad_ai)

    result = get_latest_briefing(database_url=pg_clean)
    assert result is not None
    assert result["status"] == "failed"
    assert result["content"] is None
    assert result["articles"] == []


# ── Idempotency guard ─────────────────────────────────────────────────────────


def test_generate_briefing_returns_recent_briefing_without_calling_ai(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="Existing Brief")  # created_at = NOW()

    def _should_not_run(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
        msg = "AI was called inside idempotency window"
        raise AssertionError(msg)

    result = generate_briefing(
        database_url=pg_clean,
        ai_fn=_should_not_run,
        idempotency_window_minutes=IDEMPOTENCY_WINDOW_MINUTES,
    )
    assert result["title"] == "Existing Brief"


def test_generate_briefing_skips_idempotency_when_window_is_zero(pg_clean: str) -> None:
    _seed_source(pg_clean)
    _seed_briefing(pg_clean, title="Old Brief")
    _seed_article(pg_clean, url="https://example.com/g1", title="G1", state="today")

    result = generate_briefing(
        database_url=pg_clean,
        ai_fn=_fake_ai,
        idempotency_window_minutes=0,
    )
    # A window of 0 minutes means no guard — a new briefing should be generated
    assert result["title"] == "Fake Briefing"
    assert len(list_briefings(database_url=pg_clean)) == 2  # old + new


def test_generate_briefing_with_user_id_succeeds_on_reread(pg_clean: str) -> None:
    """Regression: _save_briefing must pass user_id to get_briefing after insert.

    Briefings owned by a user have a non-NULL user_id column, so get_briefing
    with user_id=None (the previous bug) silently returned None and raised
    "Could not re-read briefing N after insert".
    """
    _seed_source(pg_clean)
    user_id = _seed_user(pg_clean, username="reread-user")
    _seed_article(
        pg_clean,
        url="https://example.com/user-reread-a1",
        title="User Article 1",
        state="today",
    )

    result = generate_briefing(database_url=pg_clean, ai_fn=_fake_ai, user_id=user_id)

    assert result["title"] == "Fake Briefing"
    assert result["status"] == "complete"


def test_generate_briefing_ignores_failed_rows_in_idempotency_check(pg_clean: str) -> None:
    _seed_source(pg_clean)
    a1 = _seed_article(pg_clean, url="https://example.com/h1", title="H1", state="today")

    def _bad_then_good_ai(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
        # First call: fail; second call (outside the guard): succeed
        return {
            "title": "Recovery Brief",
            "summary": "S",
            "sections": [{"title": "S", "body": "B", "citations": [a1]}],
            "worth_opening": [],
        }

    def _always_fail(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
        msg = "fail"
        raise BriefingGenerationError(msg)

    with pytest.raises(BriefingGenerationError):
        generate_briefing(
            database_url=pg_clean,
            ai_fn=_always_fail,
            idempotency_window_minutes=IDEMPOTENCY_WINDOW_MINUTES,
        )

    # Failed row exists — but it should NOT block a retry
    result = generate_briefing(
        database_url=pg_clean,
        ai_fn=_bad_then_good_ai,
        idempotency_window_minutes=IDEMPOTENCY_WINDOW_MINUTES,
    )
    assert result["status"] == "complete"
    assert result["title"] == "Recovery Brief"
