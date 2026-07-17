"""PostgreSQL contract tests for scheduled briefing email delivery claims."""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect


def _make_user(database_url: str, username: str) -> int:
    return int(create_user(username, "password123", db_path=database_url)["id"])


@pytest.mark.postgres
def test_briefing_email_opt_in_defaults_false(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_default")

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT briefing_email_enabled FROM users WHERE id = %s", (user_id,)
        ).fetchone()

    assert row is not None
    assert row["briefing_email_enabled"] is False


@pytest.mark.postgres
def test_delivery_local_date_is_unique(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_unique")
    delivery_date = date(2026, 7, 17)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO briefing_email_deliveries(user_id, local_delivery_date) VALUES (%s, %s)",
            (user_id, delivery_date),
        )

    with connect(database_url=pg_clean) as conn, pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO briefing_email_deliveries(user_id, local_delivery_date) VALUES (%s, %s)",
            (user_id, delivery_date),
        )


@pytest.mark.postgres
def test_delivery_status_rejects_unknown_value(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_status")

    with connect(database_url=pg_clean) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO briefing_email_deliveries(user_id, local_delivery_date, status)
            VALUES (%s, %s, 'unknown')
            """,
            (user_id, date(2026, 7, 17)),
        )
