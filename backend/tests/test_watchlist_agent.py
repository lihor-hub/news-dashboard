"""Tests for AI watchlists: CRUD, visibility scoping, matching, and evaluation."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.watchlist_agent import (
    WatchlistNotFoundError,
    ai_match,
    create_watchlist,
    delete_watchlist,
    deterministic_match,
    evaluate_watchlists,
    get_watchlist,
    list_nudges,
    list_watchlists,
    preview_matches,
    update_watchlist,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _api_client(user_id: int) -> Any:
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake
    app.dependency_overrides[require_admin] = lambda: fake
    return TestClient(app, raise_server_exceptions=True)


def _make_user(database_url: str, username: str = "alice") -> int:
    user = create_user(username, "pw", db_path=database_url)
    return int(user["id"])


def _add_source(conn: Any, slug: str, name: str, *, owner_user_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
        VALUES (%s, %s, %s, 'tech', 'rss_feed', 10, TRUE, %s)
        """,
        (slug, name, f"https://example.com/{slug}.xml", owner_user_id),
    )


def _add_article(
    conn: Any,
    *,
    slug: str,
    index: int,
    title: str,
    summary: str = "",
    state: str | None = None,
    user_id: int | None = None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
                              category, kind, summary)
        VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed', %s)
        RETURNING id
        """,
        (
            f"https://example.com/{slug}/{index}",
            f"https://example.com/{slug}/{index}",
            title,
            slug,
            slug,
            summary,
        ),
    ).fetchone()
    article_id = int(row["id"])
    if state and user_id:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, archived_at)
            VALUES (%s, %s, %s, CASE WHEN %s = 'archived' THEN NOW() ELSE NULL END)
            """,
            (user_id, article_id, state, state),
        )
    return article_id


# ── deterministic matching ──────────────────────────────────────────────────


def test_deterministic_match_scores_term_overlap() -> None:
    score, explanation = deterministic_match(
        "climate policy", {"title": "New climate policy announced", "summary": "", "tags": ""}
    )
    assert score == 1.0
    assert "climate" in explanation
    assert "policy" in explanation


def test_deterministic_match_no_overlap() -> None:
    score, explanation = deterministic_match(
        "climate policy", {"title": "Local sports results", "summary": "", "tags": ""}
    )
    assert score == 0.0
    assert "No matching" in explanation


def test_deterministic_match_empty_query() -> None:
    score, _ = deterministic_match("the a of", {"title": "anything"})
    assert score == 0.0


# ── CRUD ─────────────────────────────────────────────────────────────────────


def test_create_and_list_watchlist(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    created = create_watchlist(
        uid, "AI safety", "artificial intelligence safety", database_url=pg_clean
    )
    assert created["label"] == "AI safety"
    assert created["threshold"] == pytest.approx(0.5)

    items = list_watchlists(uid, database_url=pg_clean)
    assert len(items) == 1
    assert items[0]["id"] == created["id"]


def test_create_watchlist_requires_label_and_query(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with pytest.raises(ValueError, match="label and query"):
        create_watchlist(uid, "", "query", database_url=pg_clean)
    with pytest.raises(ValueError, match="label and query"):
        create_watchlist(uid, "label", "  ", database_url=pg_clean)


def test_create_watchlist_rejects_bad_threshold(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with pytest.raises(ValueError, match="threshold"):
        create_watchlist(uid, "label", "query", threshold=1.5, database_url=pg_clean)


def test_update_watchlist(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    created = create_watchlist(uid, "label", "query", database_url=pg_clean)
    updated = update_watchlist(
        uid, created["id"], enabled=False, threshold=0.8, database_url=pg_clean
    )
    assert updated["enabled"] is False
    assert updated["threshold"] == pytest.approx(0.8)


def test_update_watchlist_not_found_raises(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with pytest.raises(WatchlistNotFoundError):
        update_watchlist(uid, 999999, enabled=False, database_url=pg_clean)


def test_update_watchlist_scoped_to_owner(pg_clean: str) -> None:
    uid = _make_user(pg_clean, "alice")
    other = _make_user(pg_clean, "bob")
    created = create_watchlist(uid, "label", "query", database_url=pg_clean)
    with pytest.raises(WatchlistNotFoundError):
        update_watchlist(other, created["id"], enabled=False, database_url=pg_clean)


def test_delete_watchlist(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    created = create_watchlist(uid, "label", "query", database_url=pg_clean)
    assert delete_watchlist(uid, created["id"], database_url=pg_clean) is True
    assert get_watchlist(uid, created["id"], database_url=pg_clean) is None
    assert delete_watchlist(uid, created["id"], database_url=pg_clean) is False


# ── preview & visibility scoping ────────────────────────────────────────────


def test_preview_matches_visible_articles_only(pg_clean: str) -> None:
    uid = _make_user(pg_clean, "alice")
    other = _make_user(pg_clean, "bob")
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_source(conn, "bobs-feed", "Bob's Private Feed", owner_user_id=other)
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
        _add_article(conn, slug="bobs-feed", index=1, title="Quantum computing news for Bob")

    matches = preview_matches(uid, "quantum computing", use_ai=False, database_url=pg_clean)
    titles = {m["article"]["title"] for m in matches}
    assert "Quantum computing breakthrough" in titles
    assert "Quantum computing news for Bob" not in titles


def test_preview_matches_excludes_archived(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(
            conn,
            slug="global-feed",
            index=1,
            title="Quantum computing archived article",
            state="archived",
            user_id=uid,
        )

    matches = preview_matches(uid, "quantum computing", use_ai=False, database_url=pg_clean)
    assert matches == []


def test_preview_matches_respects_threshold(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing news")

    high_threshold = preview_matches(
        uid,
        "quantum computing breakthrough today",
        threshold=0.9,
        use_ai=False,
        database_url=pg_clean,
    )
    assert high_threshold == []


# ── evaluation & dedupe ──────────────────────────────────────────────────────


def test_evaluate_watchlists_creates_nudge_and_dedupes(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
    create_watchlist(uid, "Quantum", "quantum computing", database_url=pg_clean)

    with patch("news_dashboard.push.send_push_for_user") as mock_push:
        summary = evaluate_watchlists(use_ai=False, database_url=pg_clean)
    assert summary["watchlists_evaluated"] == 1
    assert summary["nudges_created"] == 1
    mock_push.assert_called_once()

    nudges = list_nudges(uid, database_url=pg_clean)
    assert len(nudges) == 1

    # Running again must not create a duplicate nudge for the same article.
    with patch("news_dashboard.push.send_push_for_user") as mock_push_again:
        summary_again = evaluate_watchlists(use_ai=False, database_url=pg_clean)
    assert summary_again["nudges_created"] == 0
    mock_push_again.assert_not_called()
    assert len(list_nudges(uid, database_url=pg_clean)) == 1


def test_evaluate_watchlists_skips_disabled(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
    create_watchlist(uid, "Quantum", "quantum computing", enabled=False, database_url=pg_clean)

    summary = evaluate_watchlists(use_ai=False, database_url=pg_clean)
    assert summary["watchlists_evaluated"] == 0
    assert summary["nudges_created"] == 0


def test_evaluate_watchlists_respects_notify_push_opt_out(pg_clean: str) -> None:
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
    create_watchlist(uid, "Quantum", "quantum computing", notify_push=False, database_url=pg_clean)

    with patch("news_dashboard.push.send_push_for_user") as mock_push:
        summary = evaluate_watchlists(use_ai=False, database_url=pg_clean)
    assert summary["nudges_created"] == 1
    mock_push.assert_not_called()


def test_evaluate_watchlists_uses_fake_ai_judge(pg_clean: str) -> None:
    """AI-configured matching: a fake judge function overrides the deterministic score."""
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        # Search retrieval is keyword-based (candidates must contain the query
        # terms), so the deterministic score would already be 1.0 here; the
        # fake judge's score/explanation below prove the AI path overrides it.
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing conference recap")
    create_watchlist(uid, "Quantum", "quantum computing", threshold=0.5, database_url=pg_clean)

    def fake_judge(_query: str, _article: dict[str, Any]) -> tuple[float, str]:
        return 0.7, "the AI judged this relevant"

    with patch("news_dashboard.push.send_push_for_user"):
        summary = evaluate_watchlists(database_url=pg_clean, ai_judge=fake_judge)

    assert summary["nudges_created"] == 1
    nudge = list_nudges(uid, database_url=pg_clean)[0]
    assert nudge["explanation"] == "the AI judged this relevant"
    assert nudge["score"] == pytest.approx(0.7)


def test_evaluate_watchlists_continues_after_one_failure(pg_clean: str) -> None:
    """A search failure for one watchlist must not abort evaluation of the others."""
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
    create_watchlist(uid, "Broken", "broken query", database_url=pg_clean)
    create_watchlist(uid, "Quantum", "quantum computing", database_url=pg_clean)

    from news_dashboard import ingest

    real_search = ingest.search_articles
    calls = {"count": 0}

    def flaky_search(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls["count"] += 1
        if calls["count"] == 1:
            msg = "boom"
            raise RuntimeError(msg)
        return real_search(*args, **kwargs)

    with (
        patch("news_dashboard.ingest.search_articles", side_effect=flaky_search),
        patch("news_dashboard.push.send_push_for_user"),
    ):
        summary = evaluate_watchlists(use_ai=False, database_url=pg_clean)

    assert summary["watchlists_evaluated"] == 2
    assert summary["nudges_created"] == 1


def test_ai_match_returns_none_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = ai_match("quantum computing", {"title": "Quantum computing news"})
    assert result is None


# ── API endpoint tests ────────────────────────────────────────────────────────


def test_api_create_list_update_delete_watchlist(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.post(
        "/api/watchlists", json={"label": "AI safety", "query": "artificial intelligence safety"}
    )
    assert resp.status_code == 200
    created = resp.json()
    watchlist_id = created["id"]
    assert created["enabled"] is True

    resp = client.get("/api/watchlists")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1

    resp = client.patch(f"/api/watchlists/{watchlist_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = client.delete(f"/api/watchlists/{watchlist_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = client.get("/api/watchlists")
    assert resp.json()["items"] == []


def test_api_create_watchlist_rejects_blank_label(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.post("/api/watchlists", json={"label": "", "query": "quantum"})
    assert resp.status_code == 400


def test_api_update_missing_watchlist_returns_404(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.patch("/api/watchlists/999999", json={"enabled": False})
    assert resp.status_code == 404


def test_api_delete_missing_watchlist_returns_404(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.delete("/api/watchlists/999999")
    assert resp.status_code == 404


def test_api_preview_watchlist(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
    client = _api_client(uid)

    resp = client.post("/api/watchlists/preview", json={"query": "quantum computing"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["article"]["title"] == "Quantum computing breakthrough"


def test_api_list_watchlist_nudges(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "global-feed", "Global Feed")
        _add_article(conn, slug="global-feed", index=1, title="Quantum computing breakthrough")
    create_watchlist(uid, "Quantum", "quantum computing", database_url=pg_clean)
    with patch("news_dashboard.push.send_push_for_user"):
        evaluate_watchlists(use_ai=False, database_url=pg_clean)

    client = _api_client(uid)
    resp = client.get("/api/watchlists/nudges")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["watchlist_label"] == "Quantum"
