import os
from pathlib import Path

import pytest

from news_dashboard.ingest import ingest_all, list_articles, set_article_status, sync_sources


def _require_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set TEST_DATABASE_URL to run Postgres integration tests")
    monkeypatch.setenv("DATABASE_URL", database_url)


def test_sync_sources_and_status_transition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_test_database(monkeypatch)
    db_path = tmp_path / "news.db"
    sync_sources(db_path)
    assert list_articles(db_path=db_path) == []

    # Insert one deterministic article directly to test status transitions without network.
    from news_dashboard.db import connect

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name, category, kind)
            VALUES ('https://example.com/a', 'https://example.com/a', 'Example', 'python-insider', 'Python Insider', 'python', 'rss_feed')
            """
        )

    articles = list_articles(db_path=db_path)
    assert len(articles) == 1
    assert articles[0]["status"] == "new"

    updated = set_article_status(articles[0]["id"], "read", db_path=db_path)
    assert updated is not None
    assert updated["status"] == "read"
    assert updated["read_at"] is not None


def test_invalid_status_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_test_database(monkeypatch)
    db_path = tmp_path / "news.db"
    sync_sources(db_path)
    try:
        set_article_status(1, "maybe", db_path=db_path)
    except ValueError as exc:
        assert "invalid status" in str(exc)
    else:
        raise AssertionError("invalid status should fail")
