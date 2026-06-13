"""PostgreSQL integration tests for briefings.py.

These tests exercise the actual psycopg %s parameterisation, JSONB round-trip,
TIMESTAMPTZ ordering, and the NULLS LAST clause in _CITED_ARTICLES_SQL.  They
require a live PostgreSQL instance supplied via the session-scoped ``pg_url``
fixture (started by testcontainers) and are skipped when Docker is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from news_dashboard.briefings import get_briefing, get_latest_briefing, list_briefings
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


def _seed_article(
    pg_url: str,
    *,
    url: str,
    title: str = "Test Article",
    source_slug: str = "test-source",
    importance_score: int = 50,
) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, importance_score
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (url, url, title, source_slug, "Test Source", "tech", "rss_feed", importance_score),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_briefing(
    pg_url: str,
    *,
    title: str = "Test Brief",
    content: dict[str, Any] | None = None,
    created_at: str | None = None,
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
                "2026-06-13T00:00:00+00:00",
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
