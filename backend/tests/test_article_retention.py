from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from news_dashboard.db import connect
from news_dashboard.main import app
from news_dashboard.scheduler.retention import (
    ARTICLE_RETENTION_LOCK_KEY,
    MAX_RETENTION_DAYS,
    cleanup_old_articles,
    get_retention_days,
    retention_preview,
    set_retention_days,
)


def _insert_user(pg_clean: str, username: str) -> int:
    with connect(pg_clean) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_article(pg_clean: str, suffix: str, *, days_old: int) -> int:
    discovered_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    with connect(pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES ('retention-source', 'Retention Source', 'https://example.com/feed',
                    'Engineering', 'rss_feed', 50, TRUE)
            ON CONFLICT (slug) DO NOTHING
            """
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind,
              published_at, summary, reason, importance_score, tags, discovered_at
            ) VALUES (%s, %s, %s, 'retention-source', 'Retention Source',
                      'Engineering', 'article', %s, 'summary', 'reason', 50, '[]', %s)
            RETURNING id
            """,
            (
                f"https://example.com/{suffix}",
                f"https://example.com/{suffix}",
                suffix,
                discovered_at,
                discovered_at,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_retention_defaults_to_keep_forever(pg_clean: str) -> None:
    assert get_retention_days(pg_clean) is None


def test_retention_round_trips_positive_days_and_can_be_disabled(pg_clean: str) -> None:
    assert set_retention_days(45, pg_clean) == 45
    assert get_retention_days(pg_clean) == 45

    assert set_retention_days(None, pg_clean) is None
    assert get_retention_days(pg_clean) is None


@pytest.mark.parametrize("days", [0, -1])
def test_retention_rejects_non_positive_days(pg_clean: str, days: int) -> None:
    with pytest.raises(ValueError, match="between 1"):
        set_retention_days(days, pg_clean)


@pytest.mark.parametrize("stored", ["", "abc", "0", "-30"])
def test_malformed_saved_retention_fails_closed(pg_clean: str, stored: str) -> None:
    with connect(pg_clean) as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (%s, %s)",
            ("article_retention_days", stored),
        )

    assert get_retention_days(pg_clean) is None


def test_preview_and_cleanup_share_all_protection_rules(pg_clean: str) -> None:
    set_retention_days(30, pg_clean)
    alice = _insert_user(pg_clean, "retention-alice")
    bob = _insert_user(pg_clean, "retention-bob")
    eligible = _insert_article(pg_clean, "eligible", days_old=40)
    starred = _insert_article(pg_clean, "starred", days_old=40)
    highlighted = _insert_article(pg_clean, "highlighted", days_old=40)
    tagged = _insert_article(pg_clean, "tagged", days_old=40)
    briefed = _insert_article(pg_clean, "briefed", days_old=40)
    shared = _insert_article(pg_clean, "shared", days_old=40)
    canonical = _insert_article(pg_clean, "canonical", days_old=40)
    _insert_article(pg_clean, "recent", days_old=2)

    with connect(pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, starred) VALUES (%s, %s, TRUE)",
            (alice, starred),
        )
        conn.execute(
            """
            INSERT INTO article_highlights(user_id, article_id, highlighted_text)
            VALUES (%s, %s, 'important')
            """,
            (alice, highlighted),
        )
        tag = conn.execute(
            "INSERT INTO user_tags(user_id, name) VALUES (%s, 'Keep') RETURNING id",
            (alice,),
        ).fetchone()
        assert tag is not None
        conn.execute(
            "INSERT INTO article_tags(user_id, article_id, tag_id) VALUES (%s, %s, %s)",
            (alice, tagged, tag["id"]),
        )
        briefing = conn.execute("INSERT INTO briefings DEFAULT VALUES RETURNING id").fetchone()
        assert briefing is not None
        conn.execute(
            "INSERT INTO briefing_articles(briefing_id, article_id) VALUES (%s, %s)",
            (briefing["id"], briefed),
        )
        conn.execute(
            """
            INSERT INTO article_shares(article_id, from_user_id, to_user_id)
            VALUES (%s, %s, %s)
            """,
            (shared, alice, bob),
        )
        duplicate = _insert_article(pg_clean, "canonical-child", days_old=2)
        conn.execute("UPDATE articles SET canonical_id = %s WHERE id = %s", (canonical, duplicate))

    preview = retention_preview(database_url=pg_clean)
    assert preview.enabled is True
    assert preview.retention_days == 30
    assert preview.eligible_articles == 1
    assert preview.protected_articles == 6
    assert preview.estimated_payload_bytes > 0

    result = cleanup_old_articles(pg_clean, batch_size=1)
    assert result.status == "success"
    assert result.deleted_articles == 1
    with connect(pg_clean) as conn:
        assert conn.execute("SELECT 1 FROM articles WHERE id = %s", (eligible,)).fetchone() is None
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE id = ANY(%s)",
            ([starred, highlighted, tagged, briefed, shared, canonical],),
        ).fetchone()
    assert remaining is not None
    assert remaining["n"] == 6


def test_cleanup_repeats_bounded_batches_and_is_idempotent(pg_clean: str) -> None:
    set_retention_days(1, pg_clean)
    for number in range(3):
        _insert_article(pg_clean, f"batch-{number}", days_old=2)

    first = cleanup_old_articles(pg_clean, batch_size=1)
    second = cleanup_old_articles(pg_clean, batch_size=1)

    assert first.deleted_articles == 3
    assert first.estimated_deleted_payload_bytes > 0
    assert second.deleted_articles == 0
    assert second.status == "success"


def test_cleanup_drains_canonical_parent_exposed_by_child_deletion(pg_clean: str) -> None:
    set_retention_days(1, pg_clean)
    parent = _insert_article(pg_clean, "old-canonical-parent", days_old=3)
    child = _insert_article(pg_clean, "old-canonical-child", days_old=2)
    with connect(pg_clean) as conn:
        conn.execute("UPDATE articles SET canonical_id = %s WHERE id = %s", (parent, child))

    result = cleanup_old_articles(pg_clean)

    assert result.deleted_articles == 2
    with connect(pg_clean) as conn:
        assert (
            conn.execute("SELECT 1 FROM articles WHERE id = ANY(%s)", ([parent, child],)).fetchone()
            is None
        )


def test_cleanup_skips_when_policy_is_disabled(pg_clean: str) -> None:
    result = cleanup_old_articles(pg_clean)

    assert result.status == "skipped"
    assert result.message == "retention disabled"


def test_cleanup_skips_when_another_cleanup_holds_lock(pg_clean: str) -> None:
    set_retention_days(1, pg_clean)
    with connect(pg_clean) as conn:
        conn.execute(
            "SELECT pg_advisory_lock(%s, hashtext(current_schema()))",
            (ARTICLE_RETENTION_LOCK_KEY,),
        )
        try:
            result = cleanup_old_articles(pg_clean)
        finally:
            conn.execute(
                "SELECT pg_advisory_unlock(%s, hashtext(current_schema()))",
                (ARTICLE_RETENTION_LOCK_KEY,),
            )

    assert result.status == "skipped"
    assert result.message == "cleanup already running"


def test_retention_api_gets_and_updates_policy_without_deleting(
    pg_clean: str, client: TestClient
) -> None:
    old_article = _insert_article(pg_clean, "api-old", days_old=40)

    initial = client.get("/api/scheduler/article-retention")
    updated = client.put("/api/scheduler/article-retention", json={"days": 30})

    assert initial.status_code == 200
    assert initial.json()["days"] is None
    assert initial.json()["schedule"] == "03:30 UTC daily"
    assert updated.status_code == 200
    assert updated.json()["days"] == 30
    assert updated.json()["preview"]["eligible_articles"] == 1
    with connect(pg_clean) as conn:
        assert conn.execute("SELECT 1 FROM articles WHERE id = %s", (old_article,)).fetchone()


@pytest.mark.parametrize("days", [0, -2])
def test_retention_api_rejects_non_positive_days(
    pg_clean: str, client: TestClient, days: int
) -> None:
    response = client.put("/api/scheduler/article-retention", json={"days": days})

    assert response.status_code == 422
    assert get_retention_days(pg_clean) is None


@pytest.mark.parametrize("days", [True, MAX_RETENTION_DAYS + 1, 999_999_999_999])
def test_retention_api_rejects_unsafe_days_without_persisting(
    pg_clean: str, client: TestClient, days: object
) -> None:
    response = client.put("/api/scheduler/article-retention", json={"days": days})

    assert response.status_code == 422
    assert get_retention_days(pg_clean) is None


def test_manual_retention_cleanup_rejects_disabled_policy(
    pg_clean: str, client: TestClient
) -> None:
    response = client.post("/api/scheduler/article-retention/run")

    assert response.status_code == 409


def test_manual_retention_cleanup_deletes_and_records_history(
    pg_clean: str, client: TestClient
) -> None:
    set_retention_days(30, pg_clean)
    _insert_article(pg_clean, "manual-old", days_old=40)

    response = client.post("/api/scheduler/article-retention/run")

    assert response.status_code == 200
    assert response.json()["deleted_articles"] == 1
    with connect(pg_clean) as conn:
        history = conn.execute(
            "SELECT status FROM scheduled_job_runs WHERE job_name = 'article_retention'"
        ).fetchone()
    assert history is not None
    assert history["status"] == "success"


def test_retention_api_requires_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin

    def deny_admin() -> None:
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_admin] = deny_admin
    try:
        response = client.get("/api/scheduler/article-retention")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 403
