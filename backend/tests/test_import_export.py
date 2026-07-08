"""Tests for #999 personal archive import and restore."""

from __future__ import annotations

import json
from typing import Any

import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.export import SCHEMA_VERSION, assemble_user_export
from news_dashboard.import_export import ArchiveImportError, restore_user_archive
from news_dashboard.ingest import set_article_starred, sync_sources, transition_article_state


def _make_user(db_url: str, username: str) -> int:
    return int(create_user(username, "password123", db_path=db_url)["id"])


def _insert_article(db_url: str, *, url_suffix: str) -> int:
    with connect(database_url=db_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                f"https://example.com/art{url_suffix}",
                f"https://example.com/art{url_suffix}",
                f"Article {url_suffix}",
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _base_archive(**overrides: object) -> dict[str, Any]:
    archive: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "includes_article_bodies": False,
        "articles": [],
        "briefings": [],
        "ai_memories": [],
        "ai_memory_events": [],
        "source_subscriptions": [],
        "preferences": {},
    }
    archive.update(overrides)
    return archive


# ── validation ─────────────────────────────────────────────────────────────


def test_rejects_wrong_schema_version(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_bad_schema")

    with pytest.raises(ArchiveImportError, match="schema_version"):
        restore_user_archive(uid, _base_archive(schema_version=1), database_url=pg_clean)


def test_rejects_non_object_payload(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_bad_payload")

    not_an_object: Any = []
    with pytest.raises(ArchiveImportError, match="JSON object"):
        restore_user_archive(uid, not_an_object, database_url=pg_clean)


def test_rejects_too_many_articles(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_too_many")

    archive = _base_archive(articles=[{"canonical_url": f"https://x/{i}"} for i in range(20_001)])

    with pytest.raises(ArchiveImportError, match="too many"):
        restore_user_archive(uid, archive, database_url=pg_clean)


# ── article state restore ───────────────────────────────────────────────────


def test_restores_article_state_by_matching_existing_article(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_match_alice")
    aid = _insert_article(pg_clean, url_suffix="match1")

    archive = _base_archive(
        articles=[
            {
                "id": 999999,
                "canonical_url": "https://example.com/artmatch1",
                "title": "Article match1",
                "state": "done",
                "starred": True,
                "done_at": "2026-01-01T00:00:00+00:00",
                "starred_at": "2026-01-01T00:00:00+00:00",
            }
        ]
    )

    result = restore_user_archive(uid, archive, database_url=pg_clean)

    assert result["articles"] == {"added": 1, "updated": 0, "skipped": 0}

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT state, starred FROM user_article_state WHERE user_id = %s AND article_id = %s",
            (uid, aid),
        ).fetchone()
    assert row is not None
    assert row["state"] == "done"
    assert row["starred"] is True


def test_restores_minimal_article_when_source_exists(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_minimal")

    archive = _base_archive(
        articles=[
            {
                "canonical_url": "https://example.com/brand-new-article",
                "title": "Brand New Article",
                "source_slug": "python-insider",
                "source_name": "Python Insider",
                "category": "python",
                "kind": "rss_feed",
                "state": "later",
            }
        ]
    )

    result = restore_user_archive(uid, archive, database_url=pg_clean)

    assert result["articles"] == {"added": 1, "updated": 0, "skipped": 0}

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT id FROM articles WHERE canonical_url = %s",
            ("https://example.com/brand-new-article",),
        ).fetchone()
        assert row is not None
        state_row = conn.execute(
            "SELECT state FROM user_article_state WHERE user_id = %s AND article_id = %s",
            (uid, row["id"]),
        ).fetchone()
    assert state_row is not None
    assert state_row["state"] == "later"


def test_skips_article_with_unknown_source_and_no_existing_match(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_unknown_source")

    archive = _base_archive(
        articles=[
            {
                "canonical_url": "https://example.com/orphan",
                "title": "Orphan Article",
                "source_slug": "does-not-exist",
                "source_name": "Nowhere",
                "category": "python",
                "kind": "rss_feed",
            }
        ]
    )

    result = restore_user_archive(uid, archive, database_url=pg_clean)

    assert result["articles"] == {"added": 0, "updated": 0, "skipped": 1}


def test_reimporting_same_article_is_idempotent(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_idempotent")
    _insert_article(pg_clean, url_suffix="idem1")

    archive = _base_archive(
        articles=[
            {
                "canonical_url": "https://example.com/artidem1",
                "title": "Article idem1",
                "state": "done",
                "starred": False,
            }
        ]
    )

    first = restore_user_archive(uid, archive, database_url=pg_clean)
    second = restore_user_archive(uid, archive, database_url=pg_clean)

    assert first["articles"] == {"added": 1, "updated": 0, "skipped": 0}
    assert second["articles"] == {"added": 0, "updated": 1, "skipped": 0}

    with connect(database_url=pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM user_article_state WHERE user_id = %s", (uid,)
        ).fetchone()
    assert count is not None
    assert count["n"] == 1


def test_import_never_restores_data_for_another_user(pg_clean: str) -> None:
    """An archive can only ever write rows for the importing user_id."""
    sync_sources(pg_clean)
    uid_alice = _make_user(pg_clean, "import_scope_alice")
    uid_bob = _make_user(pg_clean, "import_scope_bob")
    aid = _insert_article(pg_clean, url_suffix="scope1")

    archive = _base_archive(
        articles=[
            {
                "canonical_url": "https://example.com/artscope1",
                "title": "Article scope1",
                "state": "done",
            }
        ]
    )

    restore_user_archive(uid_alice, archive, database_url=pg_clean)

    with connect(database_url=pg_clean) as conn:
        bob_row = conn.execute(
            "SELECT 1 FROM user_article_state WHERE user_id = %s AND article_id = %s",
            (uid_bob, aid),
        ).fetchone()
    assert bob_row is None


# ── briefings restore ────────────────────────────────────────────────────────


def test_restores_briefing_and_cited_articles(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_brief")
    aid = _insert_article(pg_clean, url_suffix="brief1")

    archive = _base_archive(
        briefings=[
            {
                "id": 12345,
                "created_at": "2026-02-01T09:00:00+00:00",
                "scope": "since_last_briefing",
                "status": "complete",
                "title": "Morning Brief",
                "summary": "Summary text",
                "cited_articles": [
                    {"article_id": 12345, "canonical_url": "https://example.com/artbrief1"}
                ],
            }
        ]
    )

    result = restore_user_archive(uid, archive, database_url=pg_clean)
    assert result["briefings"] == {"added": 1, "updated": 0, "skipped": 0}

    with connect(database_url=pg_clean) as conn:
        brow = conn.execute("SELECT id, title FROM briefings WHERE user_id = %s", (uid,)).fetchone()
        assert brow is not None
        cited = conn.execute(
            "SELECT article_id FROM briefing_articles WHERE briefing_id = %s", (brow["id"],)
        ).fetchall()
    assert brow["title"] == "Morning Brief"
    assert [c["article_id"] for c in cited] == [aid]


def test_reimporting_same_briefing_is_idempotent(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_brief_idem")

    archive = _base_archive(
        briefings=[
            {
                "created_at": "2026-02-02T09:00:00+00:00",
                "title": "Morning Brief",
                "summary": "v1",
            }
        ]
    )
    restore_user_archive(uid, archive, database_url=pg_clean)

    archive["briefings"][0]["summary"] = "v2"
    restore_user_archive(uid, archive, database_url=pg_clean)

    with connect(database_url=pg_clean) as conn:
        rows = conn.execute("SELECT summary FROM briefings WHERE user_id = %s", (uid,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["summary"] == "v2"


# ── AI memory restore ────────────────────────────────────────────────────────


def test_restores_ai_memory_by_content_and_source(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_memory")

    archive = _base_archive(
        ai_memories=[
            {
                "id": 555,
                "memory_type": "preference",
                "content": "Prefers concise summaries",
                "source": "explicit",
                "confidence": 0.9,
                "active": True,
            }
        ],
        ai_memory_events=[
            {
                "event_type": "created",
                "source": "explicit",
                "content": "Prefers concise summaries",
                "created_at": "2026-01-05T00:00:00+00:00",
            }
        ],
    )

    result = restore_user_archive(uid, archive, database_url=pg_clean)
    assert result["ai_memories"] == {"added": 1, "updated": 0, "skipped": 0}
    assert result["ai_memory_events"] == {"added": 1, "skipped": 0}

    with connect(database_url=pg_clean) as conn:
        mem_row = conn.execute(
            "SELECT content, confidence FROM user_ai_memories WHERE user_id = %s", (uid,)
        ).fetchone()
    assert mem_row is not None
    assert mem_row["content"] == "Prefers concise summaries"


def test_reimporting_same_ai_memory_updates_not_duplicates(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_memory_idem")

    archive = _base_archive(
        ai_memories=[
            {"content": "Likes long-form articles", "source": "explicit", "confidence": 0.5}
        ]
    )
    restore_user_archive(uid, archive, database_url=pg_clean)

    archive["ai_memories"][0]["confidence"] = 1.0
    second = restore_user_archive(uid, archive, database_url=pg_clean)

    assert second["ai_memories"] == {"added": 0, "updated": 1, "skipped": 0}

    with connect(database_url=pg_clean) as conn:
        rows = conn.execute(
            "SELECT confidence FROM user_ai_memories WHERE user_id = %s", (uid,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["confidence"] == 1.0


def test_reimporting_same_memory_event_is_not_duplicated(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "import_memory_event_idem")

    archive = _base_archive(
        ai_memory_events=[
            {
                "event_type": "created",
                "source": "explicit",
                "content": "Some note",
                "created_at": "2026-01-06T00:00:00+00:00",
            }
        ]
    )
    restore_user_archive(uid, archive, database_url=pg_clean)
    second = restore_user_archive(uid, archive, database_url=pg_clean)

    assert second["ai_memory_events"] == {"added": 0, "skipped": 1}

    with connect(database_url=pg_clean) as conn:
        rows = conn.execute(
            "SELECT 1 FROM user_ai_memory_events WHERE user_id = %s", (uid,)
        ).fetchall()
    assert len(rows) == 1


# ── round trip ───────────────────────────────────────────────────────────────


def test_export_then_import_round_trip_into_fresh_user(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid_source = _make_user(pg_clean, "roundtrip_source")
    aid = _insert_article(pg_clean, url_suffix="rt1")
    transition_article_state(aid, "done", db_path=pg_clean, user_id=uid_source)
    set_article_starred(aid, True, db_path=pg_clean, user_id=uid_source)

    archive = assemble_user_export(uid_source, database_url=pg_clean)

    uid_dest = _make_user(pg_clean, "roundtrip_dest")
    result = restore_user_archive(uid_dest, archive, database_url=pg_clean)

    assert result["articles"]["added"] == 1

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT state, starred FROM user_article_state WHERE user_id = %s AND article_id = %s",
            (uid_dest, aid),
        ).fetchone()
    assert row is not None
    assert row["state"] == "done"
    assert row["starred"] is True


# ── API endpoint ──────────────────────────────────────────────────────────────


def test_import_endpoint_restores_archive(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    import io

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid = _make_user(pg_clean, "endpoint_import_user")
    _insert_article(pg_clean, url_suffix="ep_import1")

    archive = _base_archive(
        articles=[
            {
                "canonical_url": "https://example.com/artep_import1",
                "title": "Article ep_import1",
                "state": "done",
            }
        ]
    )

    fake_user = {"id": uid, "username": "endpoint_import_user", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            body = json.dumps(archive).encode("utf-8")
            resp = client.post(
                "/api/users/me/import",
                files={"file": ("archive.json", io.BytesIO(body), "application/json")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["articles"] == {"added": 1, "updated": 0, "skipped": 0}
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_import_endpoint_rejects_invalid_json(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    import io

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid = _make_user(pg_clean, "endpoint_import_bad")
    fake_user = {"id": uid, "username": "endpoint_import_bad", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.post(
                "/api/users/me/import",
                files={"file": ("archive.json", io.BytesIO(b"not json"), "application/json")},
            )
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(require_auth, None)
