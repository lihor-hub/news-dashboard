"""Tests for thumbs up/down feedback on briefings and recommendations (#931)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from news_dashboard.ai_feedback import service
from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.recommendations import (
    ArticleSignal,
    _load_user_signals,
    build_affinity_profile,
)

# ── Seeding helpers ───────────────────────────────────────────────────────────


def _setup_db(monkeypatch: pytest.MonkeyPatch, pg_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_url)
    init_db(database_url=pg_url)
    return pg_url


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


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
) -> int:
    _seed_source(pg_url, source_slug)
    ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, importance_score, state, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (url, url, title, source_slug, "Test Source", "tech", "rss_feed", 50, "new", ts),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_briefing(pg_url: str, *, user_id: int, trace_id: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(
                scope, since_at, until_at, status, title, summary, content,
                model, user_id, trace_id
            )
            VALUES ('day', %s, %s, 'complete', 'Title', 'Summary', '{}'::jsonb,
                    'gpt-4o-mini', %s, %s)
            RETURNING id
            """,
            (now - timedelta(hours=1), now, user_id, trace_id),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(user_id: int) -> TestClient:
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


# ── Service: upsert / retract semantics ──────────────────────────────────────


def test_record_feedback_upserts_on_second_call(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id)

    first = service.record_feedback(user_id, "briefing", briefing_id, 1, database_url=database_url)
    second = service.record_feedback(
        user_id, "briefing", briefing_id, -1, comment="changed my mind", database_url=database_url
    )

    assert first["verdict"] == 1
    assert second["id"] == first["id"]
    assert second["verdict"] == -1
    assert second["comment"] == "changed my mind"

    with connect(database_url=database_url) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_feedback WHERE user_id = %s", (user_id,)
        ).fetchone()["count"]
    assert count == 1


def test_record_feedback_allows_per_article_and_whole_briefing_rows(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id)
    article_id = _seed_article(database_url, url="https://example.com/a")

    whole = service.record_feedback(user_id, "briefing", briefing_id, 1, database_url=database_url)
    per_article = service.record_feedback(
        user_id, "briefing", briefing_id, -1, article_id=article_id, database_url=database_url
    )
    # Retracting the whole-briefing verdict twice must not create duplicates.
    service.record_feedback(user_id, "briefing", briefing_id, 1, database_url=database_url)

    assert whole["id"] != per_article["id"]
    with connect(database_url=database_url) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_feedback WHERE user_id = %s", (user_id,)
        ).fetchone()["count"]
    assert count == 2


def test_delete_feedback_retracts_verdict(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id)
    service.record_feedback(user_id, "briefing", briefing_id, 1, database_url=database_url)

    deleted = service.delete_feedback(user_id, "briefing", briefing_id, database_url=database_url)
    deleted_again = service.delete_feedback(
        user_id, "briefing", briefing_id, database_url=database_url
    )

    assert deleted is True
    assert deleted_again is False


def test_get_feedback_map_keys_by_subject_and_article(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id)
    article_id = _seed_article(database_url, url="https://example.com/a")

    service.record_feedback(user_id, "briefing", briefing_id, 1, database_url=database_url)
    service.record_feedback(
        user_id, "briefing", briefing_id, -1, article_id=article_id, database_url=database_url
    )

    feedback_map = service.get_feedback_map(
        user_id, "briefing", [briefing_id], database_url=database_url
    )
    assert feedback_map[f"{briefing_id}:"] == 1
    assert feedback_map[f"{briefing_id}:{article_id}"] == -1


# ── Langfuse trace scoring ────────────────────────────────────────────────────


def test_record_feedback_scores_briefing_trace_when_present(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id, trace_id="trace-abc")

    calls: list[dict[str, object]] = []

    def _fake_create_score(trace_id: str, **kwargs: object) -> bool:
        calls.append({"trace_id": trace_id, **kwargs})
        return True

    monkeypatch.setattr("news_dashboard.ai_client.create_score", _fake_create_score)

    service.record_feedback(user_id, "briefing", briefing_id, -1, database_url=database_url)

    assert len(calls) == 1
    assert calls[0]["trace_id"] == "trace-abc"
    assert calls[0]["value"] == -1


def test_record_feedback_skips_scoring_without_trace(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id, trace_id=None)

    def _fail(*_args: object, **_kwargs: object) -> bool:
        pytest.fail("create_score should not be called without a trace_id")

    monkeypatch.setattr("news_dashboard.ai_client.create_score", _fail)

    service.record_feedback(user_id, "briefing", briefing_id, 1, database_url=database_url)


# ── API endpoints ─────────────────────────────────────────────────────────────


def test_post_and_delete_ai_feedback_endpoints(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    briefing_id = _seed_briefing(database_url, user_id=user_id)

    try:
        with _client_for(user_id) as client:
            posted = client.post(
                "/api/ai-feedback",
                json={"subject_type": "briefing", "subject_id": briefing_id, "verdict": 1},
            )
            listed = client.get(
                "/api/ai-feedback",
                params={"subject_type": "briefing", "subject_ids": str(briefing_id)},
            )
            deleted = client.request(
                "DELETE",
                "/api/ai-feedback",
                params={"subject_type": "briefing", "subject_id": briefing_id},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert posted.status_code == 200
    assert posted.json()["verdict"] == 1
    assert listed.json()["items"][f"{briefing_id}:"] == 1
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


# ── Recommendation scoring integration ────────────────────────────────────────


def test_score_article_thumbs_down_outweighs_implicit_click(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    article_id = _seed_article(
        database_url, url="https://example.com/a", source_slug="disliked-source"
    )
    service.record_feedback(user_id, "recommendation", article_id, -1, database_url=database_url)

    with connect(database_url=database_url) as conn:
        signals = _load_user_signals(conn, user_id)

    assert len(signals) == 1
    profile = build_affinity_profile(signals)
    assert profile.sources["disliked-source"] < 0

    # A single implicit "today" click carries zero weight, so even one explicit
    # thumbs-down must pull the source affinity meaningfully negative.
    implicit_only = build_affinity_profile(
        [ArticleSignal(state="today", starred=False, source_slug="disliked-source")]
    )
    assert profile.sources["disliked-source"] < implicit_only.sources.get("disliked-source", 0.0)
