from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.auto_enrichment import (
    EnrichmentSummary,
    _candidates,
    auto_enrich_limit,
    prefetch_then_auto_enrich,
    run_auto_enrichment,
)
from news_dashboard.db import connect
from news_dashboard.main import app


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 5), ("-2", 0), ("0", 0), ("8", 8), ("99", 20)]
)
def test_auto_enrich_limit_is_defaulted_and_clamped(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: int
) -> None:
    if raw is None:
        monkeypatch.delenv("AI_AUTO_ENRICH_LIMIT", raising=False)
    else:
        monkeypatch.setenv("AI_AUTO_ENRICH_LIMIT", raw)

    assert auto_enrich_limit() == expected


def test_auto_enrich_limit_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AUTO_ENRICH_LIMIT", "many")

    assert auto_enrich_limit() == 5


def _seed(pg_url: str) -> tuple[int, int, list[int]]:
    with connect(database_url=pg_url) as conn:
        first = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES ('u1', 'x') RETURNING id"
        ).fetchone()
        second = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES ('u2', 'x') RETURNING id"
        ).fetchone()
        assert first
        assert second
        user1, user2 = int(first["id"]), int(second["id"])
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES"
            " ('global','Global','https://g','tech','rss_feed'),"
            " ('private','Private','https://p','tech','rss_feed')"
        )
        conn.execute("UPDATE sources SET owner_user_id = %s WHERE slug = 'private'", (user1,))
        ids: list[int] = []
        for ordinal, source in enumerate(("global", "global", "private"), 1):
            row = conn.execute(
                """
                INSERT INTO articles(url,canonical_url,title,source_slug,source_name,category,kind,
                                     body,body_status,discovered_at)
                VALUES (%s,%s,%s,%s,'S','tech','rss_feed','body','ok',
                        NOW() - %s * INTERVAL '1 minute')
                RETURNING id
                """,
                (f"https://a/{ordinal}", f"https://a/{ordinal}", f"A{ordinal}", source, ordinal),
            ).fetchone()
            assert row
            ids.append(int(row["id"]))
    return user1, user2, ids


def test_preference_defaults_off_and_api_persists(pg_clean: str) -> None:
    user1, _, _ = _seed(pg_clean)
    app.dependency_overrides[require_auth] = lambda: {"id": user1, "username": "u1"}
    try:
        with TestClient(app) as client:
            initial = client.get("/api/settings/automatic-ai-enrichment")
            saved = client.put("/api/settings/automatic-ai-enrichment", json={"enabled": True})
            loaded = client.get("/api/settings/automatic-ai-enrichment")
        assert initial.json()["enabled"] is False
        assert saved.json()["enabled"] is True
        assert loaded.json()["enabled"] is True
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_candidates_rank_dedupe_and_enforce_visibility(pg_clean: str) -> None:
    user1, user2, article_ids = _seed(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute("UPDATE users SET auto_ai_enrichment_enabled = TRUE")
        conn.execute(
            "INSERT INTO user_sources(user_id,source_slug,enabled) VALUES (%s,'global',FALSE)",
            (user1,),
        )
        for values in (
            (user1, article_ids[0], 0.9),
            (user2, article_ids[0], 0.8),
            (user2, article_ids[1], 0.95),
        ):
            conn.execute(
                """
                INSERT INTO user_article_recommendations(
                  user_id,article_id,recommendation_score,cold_start_score,stale
                ) VALUES (%s,%s,%s,0,FALSE)
                """,
                values,
            )
    eligible, candidates = _candidates(2, pg_clean)
    assert eligible == 3
    assert [row["article_id"] for row in candidates] == [article_ids[1], article_ids[0]]
    assert candidates[1]["user_id"] == user2
    assert len({row["article_id"] for row in candidates}) == len(candidates)


def test_run_is_gated_and_isolates_each_type_and_article(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user1, _, article_ids = _seed(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute("UPDATE users SET auto_ai_enrichment_enabled = TRUE WHERE id = %s", (user1,))
    calls: list[tuple[str, int]] = []

    def insights(article_id: int, **_kwargs: object) -> list[str]:
        calls.append(("insights", article_id))
        if article_id == article_ids[0]:
            msg = "provider secret body"
            raise RuntimeError(msg)
        return ["ok"]

    def perspectives(article_id: int, **_kwargs: object) -> dict[str, list[str]]:
        calls.append(("perspectives", article_id))
        return {"verified_facts": ["ok"]}

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    assert run_auto_enrichment(pg_clean).attempted == 0
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("AI_AUTO_ENRICH_LIMIT", "2")
    monkeypatch.setattr("news_dashboard.insights.get_or_generate_insights", insights)
    monkeypatch.setattr("news_dashboard.perspectives.get_or_generate_perspectives", perspectives)
    summary = run_auto_enrichment(pg_clean)
    assert summary.eligible == 3
    assert summary.attempted == 2
    assert summary.failed == 1
    assert summary.generated == 3
    assert len(calls) == 4


def test_prefetch_finishes_before_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "news_dashboard.body_fetch.prefetch_article_bodies", lambda: calls.append("prefetch")
    )

    def enrich() -> EnrichmentSummary:
        calls.append("enrich")
        return EnrichmentSummary()

    monkeypatch.setattr("news_dashboard.auto_enrichment.run_auto_enrichment", enrich)
    prefetch_then_auto_enrich()
    assert calls == ["prefetch", "enrich"]
