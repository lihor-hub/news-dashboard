import pytest

from news_dashboard.db import active_database_url, describe_database, insert_article_sql, insert_duplicate_article_sql


def test_postgres_url_is_reported_without_password() -> None:
    dsn = "postgresql://news_dashboard:secret-password@postgres:5432/news_dashboard"

    assert describe_database(database_url=dsn) == "postgresql://news_dashboard:***@postgres:5432/news_dashboard"


def test_database_url_is_required(monkeypatch) -> None:
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


def test_duplicate_article_insert_sql_is_postgres_only() -> None:
    sql = insert_duplicate_article_sql()

    assert "ON CONFLICT (url) DO NOTHING" in sql
    assert "%s" in sql
    assert "INSERT OR IGNORE" not in sql
