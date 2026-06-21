import pytest

from news_dashboard.db import (
    POSTGRES_MULTIUSER_SCHEMA,
    POSTGRES_SCHEMA,
    active_database_url,
    describe_database,
    insert_article_sql,
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
