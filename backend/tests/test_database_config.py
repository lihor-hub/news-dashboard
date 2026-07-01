from urllib.parse import quote, urlsplit

import pytest

from news_dashboard.db import (
    POSTGRES_MULTIUSER_SCHEMA,
    POSTGRES_SCHEMA,
    active_database_url,
    describe_database,
    insert_article_sql,
    placeholders,
    row_to_dict,
    search_articles_sql,
)


def test_postgres_url_is_reported_without_password() -> None:
    dsn = "postgresql://news_dashboard:secret-password@postgres:5432/news_dashboard"

    assert (
        describe_database(database_url=dsn)
        == "postgresql://news_dashboard:***@postgres:5432/news_dashboard"
    )


def test_postgres_articles_schema_includes_embedding_column() -> None:
    postgres_schema = "\n".join(POSTGRES_SCHEMA).lower()

    assert "embedding bytea" in postgres_schema
    assert "alter table articles add column if not exists embedding bytea" in postgres_schema


def test_postgres_schema_includes_user_article_recommendations() -> None:
    postgres_schema = "\n".join(POSTGRES_MULTIUSER_SCHEMA).lower()

    assert "create table if not exists user_article_recommendations" in postgres_schema
    assert "primary key (user_id, article_id)" in postgres_schema
    assert "idx_uar_user_score" in postgres_schema


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)

    with pytest.raises(RuntimeError, match="Postgres is required"):
        active_database_url()


def test_non_postgres_database_url_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL must start"):
        active_database_url("sqlite:///tmp/news.db")


def test_article_insert_sql_is_postgres_only() -> None:
    sql = insert_article_sql()

    assert "ON CONFLICT (url) DO NOTHING" in sql
    assert "%s" in sql
    assert "INSERT OR IGNORE" not in sql


def test_active_database_url_builds_from_postgres_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_USER", "alice")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    monkeypatch.setenv("POSTGRES_DB", "mydb")
    monkeypatch.setenv("POSTGRES_PORT", "6543")

    assert active_database_url() == "postgresql://alice:pw@db.internal:6543/mydb"


def test_active_database_url_encodes_postgres_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_USER", "ali/ce@example")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p/w#x:@ space")
    monkeypatch.setenv("POSTGRES_DB", "my/db #1")
    monkeypatch.setenv("POSTGRES_PORT", "6543")

    parts = urlsplit(active_database_url())

    assert parts.scheme == "postgresql"
    assert parts.username == "ali%2Fce%40example"
    assert parts.password == quote("p/w#x:@ space", safe="")
    assert parts.hostname == "db.internal"
    assert parts.port == 6543
    assert parts.path == "/my%2Fdb%20%231"


def test_describe_database_passes_through_url_without_password() -> None:
    dsn = "postgresql://news_dashboard@postgres:5432/news_dashboard"
    assert describe_database(database_url=dsn) == dsn


# ── row_to_dict ───────────────────────────────────────────────────────────────


def test_row_to_dict_from_mapping() -> None:
    assert row_to_dict({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_row_to_dict_from_iterable_keys() -> None:
    class _Row:
        def __init__(self) -> None:
            self._d = {"x": 10, "y": 20}

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(self._d)

        def __getitem__(self, key: str) -> int:
            return self._d[key]

    assert row_to_dict(_Row()) == {"x": 10, "y": 20}


# ── placeholders ──────────────────────────────────────────────────────────────


def test_placeholders_builds_one_per_value() -> None:
    assert placeholders([1, 2, 3]) == "%s, %s, %s"


def test_placeholders_rejects_empty() -> None:
    with pytest.raises(ValueError, match="at least one value"):
        placeholders([])


# ── search_articles_sql ───────────────────────────────────────────────────────


def test_search_articles_sql_no_terms_orders_by_recency() -> None:
    sql, params = search_articles_sql([], 25)
    assert "ORDER BY discovered_at DESC" in sql
    assert params == [25]


def test_search_articles_sql_builds_ilike_clauses_per_term() -> None:
    sql, params = search_articles_sql(["ai", "gpu"], 10)
    assert sql.count("title ILIKE %s") == 2
    assert " AND " in sql
    # Five ILIKE params per term, plus the trailing limit.
    assert params == ["%ai%"] * 5 + ["%gpu%"] * 5 + [10]
    assert "ORDER BY importance_score DESC" in sql
