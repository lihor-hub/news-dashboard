from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from time import sleep
from typing import Any

import pytest
from fastapi import HTTPException

from news_dashboard.db import connect
from news_dashboard.ingest.service import transition_article_state
from news_dashboard.reading_progress import credits, daily, reader, rewards  # noqa: A004

pytestmark = pytest.mark.postgres


@pytest.fixture
def reading_account(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int]:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    with connect() as conn:
        uid = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('reader','x') RETURNING id"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('reads','Reads','https://example.test/feed','tech','rss_feed')"
        )
        aid = conn.execute(
            """INSERT INTO articles(url,canonical_url,title,summary,source_slug,source_name,
                   category,kind,body,body_status)
               VALUES ('https://example.test/a','https://example.test/a','Python title',
                   'first summary','reads','Reads','tech','rss_feed','A short article body.','ok')
               RETURNING id""",
        ).fetchone()["id"]
    return uid, aid


def count() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT count(*) AS n FROM user_read_credits").fetchone()["n"])


def test_frozen_v1_normalization() -> None:
    assert credits.identity_digest(
        " HTTPS://EXAMPLE.COM/path/?z=2&a=1&utm_source=x#part "
    ) == credits.identity_digest("https://example.com/path?a=1&z=2")
    assert credits.identity_digest("https://example.com/path?a=1") != credits.identity_digest(
        "http://example.com/path?a=1"
    )
    assert credits.identity_digest("https://example.com/") != credits.identity_digest(
        "https://example.com"
    )
    assert len(credits.identity_digest("https://example.com/a")) == 64


def test_same_state_unread_retention_and_first_source(reading_account: tuple[int, int]) -> None:
    uid, aid = reading_account
    transition_article_state(aid, "done", user_id=uid, method="audio_finish")
    assert count() == 0
    transition_article_state(aid, "done", user_id=uid)
    first = rewards.daily_collection(uid)
    assert first["reading_total"] == 1
    assert first["next_reading_target"] == 10
    assert [r["key"] for r in first["items"] if r["unlocked"]] == ["articles_read_1"]
    transition_article_state(aid, "today", user_id=uid)
    transition_article_state(aid, "done", user_id=uid, method="greader")
    assert count() == 1
    with connect() as conn:
        conn.execute("DELETE FROM articles WHERE id=%s", (aid,))
        row = conn.execute("SELECT * FROM user_read_credits").fetchone()
        assert row["article_id"] is None
        assert row["method"] == "manual"
        source = conn.execute("SELECT * FROM user_read_credit_sources").fetchone()
        assert source["title"] == "Python title"
        assert source["summary"] == "first summary"
        daily.lock_account(conn, uid)
        assert not credits.credit_read(conn, uid, url="https://example.test/a", title="Changed")[
            "credit_inserted"
        ]
    assert count() == 1
    with connect() as conn:
        daily.lock_account(conn, uid)
        conn.execute("DELETE FROM users WHERE id=%s", (uid,))
    assert count() == 0


def test_import_live_race_and_rollback(reading_account: tuple[int, int]) -> None:
    uid, _ = reading_account
    barrier = Barrier(2)

    def write(origin: str) -> dict[str, Any]:
        barrier.wait()
        with connect() as conn:
            daily.lock_account(conn, uid)
            return credits.credit_read(
                conn,
                uid,
                url="https://race.test/a",
                origin=origin,
                method="import" if origin == "import" else "manual",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["live", "import"]))
    assert sum(r["credit_inserted"] for r in results) == 1
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_read_credits").fetchone()
        award = conn.execute("SELECT * FROM user_achievements").fetchone()
        assert award["origin"] == row["origin"]
        assert (row["effective_at"] is None) == (row["origin"] == "import")
        assert (award["reward_group_id"] is None) == (row["origin"] == "import")
    with connect() as conn, pytest.raises(RuntimeError), conn.transaction():  # noqa: PT012
        daily.lock_account(conn, uid)
        credits.credit_read(conn, uid, url="https://rollback.test/")
        msg = "rollback"
        raise RuntimeError(msg)
    assert count() == 1


def test_import_prerequisites_can_cross_a_later_live_milestone(
    reading_account: tuple[int, int],
) -> None:
    uid, _ = reading_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        for n in range(9):
            credits.credit_read(
                conn, uid, url=f"https://imported.test/{n}", method="import", origin="import"
            )
        assert not conn.execute("SELECT * FROM user_reward_groups").fetchall()
        result = credits.credit_read(conn, uid, url="https://live.test/tenth")
        assert result["newly_unlocked"] == ["articles_read_10"]
        assert result["reward_group_id"] is not None
        first = conn.execute(
            "SELECT * FROM user_achievements WHERE achievement_key='articles_read_1'"
        ).fetchone()
        assert first["origin"] == "import"
        assert first["earned_at"] is None
        assert first["reward_group_id"] is None


def test_all_milestones_and_preserved_unknown(reading_account: tuple[int, int]) -> None:
    uid, _ = reading_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        conn.execute(
            """INSERT INTO user_achievements(user_id,achievement_key,unlocked_at,metadata)
               VALUES (%s,'unknown_reward','2001-01-01','{\"old\":true,\"progress\":\"unknown\"}'),
                      (%s,'hundred_articles_read','2001-01-01','{\"legacy\":true}')""",
            (uid, uid),
        )
        assert conn.execute("SELECT count(*) AS n FROM user_read_credits").fetchone()["n"] == 0
        for n in range(501):
            credits.credit_read(conn, uid, url=f"https://milestones.test/{n}")
    result = rewards.daily_collection(uid)
    assert result["reading_total"] == 501
    assert result["next_reading_target"] is None
    assert {r["key"] for r in result["items"] if r["unlocked"]} == {
        rewards.read_key(n) for n in rewards.READ_TARGETS
    } | {"unknown_reward"}
    old = next(r for r in result["items"] if r["key"] == "unknown_reward")
    assert old["metadata"] == {"old": True, "progress": "unknown"}
    assert old["progress"] == 0
    assert old["recorded_at"].startswith("2001-01-01")
    hundred = next(r for r in result["items"] if r["key"] == "hundred_articles_read")
    assert hundred["recorded_at"].startswith("2001-01-01")
    assert hundred["metadata"] == {"legacy": True}
    assert hundred["origin"] == "legacy"
    assert hundred["earned_at"] is None


@pytest.mark.parametrize(("words", "seconds"), [(100, 30), (480, 60), (1000, 120), (3000, 120)])
def test_time_thresholds(words: int, seconds: int) -> None:
    assert reader.required_seconds("word " * words) == seconds
    assert reader.required_seconds("日本語の記事") == 120


def test_automatic_server_bound_replay_body_and_manual_race(
    reading_account: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, aid = reading_account
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(reader, "utc_now", lambda: clock[0])
    version = reader.body_version("A short article body.")
    start = reader.accept_evidence(uid, aid, reader.ReaderEvidence(body_version=version))
    assert count() == 0

    def beat(seq: int) -> reader.ReaderEvidence:
        return reader.ReaderEvidence(
            body_version=version,
            token=start["token"],
            sequence=seq,
            attentive_ms=15000,
            end_ms=2000,
            progress=1,
        )

    # A fast client cannot mint time; identical replay adds zero, changed replay fails.
    response = reader.accept_evidence(uid, aid, beat(1))
    assert response["attentive_ms"] == 0
    assert not response["credited"]
    assert reader.accept_evidence(uid, aid, beat(1)) == response
    with pytest.raises(HTTPException):
        reader.accept_evidence(uid, aid, beat(1).model_copy(update={"progress": 0.95}))
    clock[0] += timedelta(seconds=15)
    assert not reader.accept_evidence(uid, aid, beat(2))["credited"]
    transition_article_state(aid, "done", user_id=uid)
    clock[0] += timedelta(seconds=15)
    completed = reader.accept_evidence(uid, aid, beat(3))
    assert completed["credited"]
    assert not completed["credit_inserted"]
    assert count() == 1
    # Completed receipts remain replayable, but cannot seed a new lease's time after unread.
    transition_article_state(aid, "today", user_id=uid)
    clock[0] += timedelta(seconds=21)
    fresh = reader.accept_evidence(uid, aid, reader.ReaderEvidence(body_version=version))
    clock[0] += timedelta(seconds=15)
    pending = reader.accept_evidence(
        uid,
        aid,
        reader.ReaderEvidence(
            body_version=version,
            token=fresh["token"],
            sequence=1,
            attentive_ms=15000,
            end_ms=2000,
            progress=1,
        ),
    )
    assert not pending["credited"]
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT state FROM user_article_state WHERE user_id=%s AND article_id=%s",
                (uid, aid),
            ).fetchone()["state"]
            == "today"
        )
        conn.execute("UPDATE articles SET body='replacement' WHERE id=%s", (aid,))
    with pytest.raises(HTTPException, match="article_body_changed"):
        reader.accept_evidence(uid, aid, beat(4))


@pytest.mark.parametrize(
    ("progress", "end_ms", "qualified"),
    [
        (0.8999, 2000, False),
        (1.0, 0, False),
        (1.0, 1999, False),
        (0.9, 2000, True),
    ],
)
def test_automatic_progress_and_end_boundaries(
    reading_account: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
    progress: float,
    end_ms: int,
    qualified: bool,
) -> None:
    uid, aid = reading_account
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(reader, "utc_now", lambda: clock[0])
    version = reader.body_version("A short article body.")
    start = reader.accept_evidence(uid, aid, reader.ReaderEvidence(body_version=version))
    clock[0] += timedelta(seconds=15)
    reader.accept_evidence(
        uid,
        aid,
        reader.ReaderEvidence(
            body_version=version,
            token=start["token"],
            sequence=1,
            attentive_ms=15000,
            end_ms=0,
            progress=1,
        ),
    )
    clock[0] += timedelta(seconds=15)
    result = reader.accept_evidence(
        uid,
        aid,
        reader.ReaderEvidence(
            body_version=version,
            token=start["token"],
            sequence=2,
            attentive_ms=15000,
            end_ms=end_ms,
            progress=progress,
        ),
    )
    assert result["credited"] is qualified
    assert count() == int(qualified)


def test_guest_workflow_and_consent_still_work_without_durable_progress(
    reading_account: tuple[int, int],
) -> None:
    from news_dashboard.quizzes.service import submit_quiz
    from news_dashboard.reading_list.service import add_item, update_item
    from news_dashboard.user_settings.service import update_analytics_settings

    uid, aid = reading_account
    with connect() as conn:
        conn.execute("UPDATE users SET is_guest=TRUE WHERE id=%s", (uid,))
        quiz = conn.execute(
            """INSERT INTO user_quizzes(user_id,questions) VALUES
               (%s,'[{"correct_index":0}]') RETURNING id""",
            (uid,),
        ).fetchone()["id"]
    transition_article_state(aid, "done", user_id=uid)
    item = add_item(uid, "https://example.test/guest")
    completed = update_item(uid, item["id"], status="done")
    assert completed is not None
    assert completed["status"] == "done"
    assert submit_quiz(quiz, uid, [0])["score"] == 1
    assert update_analytics_settings(uid, enabled=False)["enabled"] is False
    assert count() == 0
    with connect() as conn:
        assert not conn.execute("SELECT * FROM user_achievements").fetchall()
    with pytest.raises(HTTPException) as forbidden:
        reader.accept_evidence(
            uid,
            aid,
            reader.ReaderEvidence(body_version=reader.body_version("A short article body.")),
        )
    assert forbidden.value.status_code == 403


def test_consent_revocation_invalidates_pending_evidence(reading_account: tuple[int, int]) -> None:
    from news_dashboard.user_settings.service import update_analytics_settings

    uid, aid = reading_account
    version = reader.body_version("A short article body.")
    start = reader.accept_evidence(uid, aid, reader.ReaderEvidence(body_version=version))
    update_analytics_settings(uid, enabled=False)
    result = reader.accept_evidence(
        uid, aid, reader.ReaderEvidence(body_version=version, token=start["token"], sequence=1)
    )
    assert not result["available"]
    assert count() == 0
    with connect() as conn:
        assert not conn.execute("SELECT * FROM user_reader_evidence").fetchall()
    transition_article_state(aid, "done", user_id=uid)
    assert count() == 1


def test_three_way_automatic_manual_import_race(
    reading_account: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid, aid = reading_account
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(reader, "utc_now", lambda: clock[0])
    version = reader.body_version("A short article body.")
    start = reader.accept_evidence(uid, aid, reader.ReaderEvidence(body_version=version))
    clock[0] += timedelta(seconds=15)
    first = reader.ReaderEvidence(
        body_version=version,
        token=start["token"],
        sequence=1,
        attentive_ms=15000,
        end_ms=2000,
        progress=1,
    )
    reader.accept_evidence(uid, aid, first)
    clock[0] += timedelta(seconds=15)
    barrier = Barrier(3)

    def write(method: str) -> None:
        barrier.wait()
        if method == "automatic":
            reader.accept_evidence(uid, aid, first.model_copy(update={"sequence": 2}))
        elif method == "manual":
            transition_article_state(aid, "done", user_id=uid)
        else:
            with connect() as conn:
                daily.lock_account(conn, uid)
                credits.credit_read(
                    conn, uid, url="https://example.test/a", origin="import", method="import"
                )

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(write, ["automatic", "manual", "import"]))
    assert count() == 1
    result = rewards.daily_collection(uid)
    assert len([r for r in result["items"] if r["unlocked"]]) == 1


def test_archive_eligibility_unknown_date_silent_and_informational_progress(
    reading_account: tuple[int, int],
) -> None:
    from news_dashboard.export import assemble_user_export
    from news_dashboard.import_export import restore_user_archive

    uid, aid = reading_account
    transition_article_state(aid, "done", user_id=uid, method="audio_finish")
    archive = assemble_user_export(uid)
    archive["articles"][0]["state"] = "today"
    archive["progress"]["read_credits"] = [{"identity_digest": "forged", "method": "manual"}]
    restore_user_archive(uid, archive)
    restore_user_archive(uid, archive)
    assert count() == 1
    with connect() as conn:
        credit = conn.execute("SELECT * FROM user_read_credits").fetchone()
        assert credit["origin"] == "import"
        assert credit["effective_at"] is None
        assert not conn.execute("SELECT * FROM user_reward_groups").fetchall()
    exported = assemble_user_export(uid)
    assert exported["progress"]["read_credits"][0]["origin"] == "import"
    assert "reader_evidence" not in exported["progress"]


@pytest.mark.parametrize("existing", [True, False])
def test_opposite_order_archive_restores_keep_every_credit(
    reading_account: tuple[int, int], monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    from news_dashboard import import_export

    uid, _ = reading_account
    with connect() as conn:
        second = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('importer','x') RETURNING id"
        ).fetchone()["id"]
        if existing:
            conn.execute(
                """INSERT INTO articles(url,canonical_url,title,source_slug,source_name,
                                        category,kind)
                   VALUES ('https://example.test/0','https://example.test/0','Second',
                           'reads','Reads','tech','rss_feed')"""
            )
    # URL order deliberately opposes existing article-ID order.
    articles = [
        {
            "canonical_url": url,
            "state": "done",
            "title": "Imported",
            "source_slug": "reads",
            "source_name": "Reads",
            "category": "tech",
            "kind": "rss_feed",
        }
        for url in (
            ["https://example.test/a", "https://example.test/0"]
            if existing
            else ["https://example.test/new-z", "https://example.test/new-a"]
        )
    ]
    start = Barrier(2)
    original = import_export._upsert_article_state

    def hold_article(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        # Keep real transaction locks across scheduling of the other connection.
        sleep(0.2)

    monkeypatch.setattr(import_export, "_upsert_article_state", hold_article)

    def restore(account: int) -> dict[str, Any]:
        start.wait(timeout=10)
        return import_export.restore_user_archive(
            account,
            {"schema_version": 2, "articles": articles if account == uid else articles[::-1]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(restore, [uid, second]))
    assert [result["articles"] for result in results] == [
        {"added": 2, "updated": 0, "skipped": 0},
        {"added": 2, "updated": 0, "skipped": 0},
    ]
    with connect() as conn:
        for account in (uid, second):
            assert (
                conn.execute(
                    """SELECT count(*) AS n FROM user_article_state
                       WHERE user_id=%s AND state='done'""",
                    (account,),
                ).fetchone()["n"]
                == 2
            )
            rows = conn.execute(
                "SELECT origin, effective_at FROM user_read_credits WHERE user_id=%s", (account,)
            ).fetchall()
            assert len(rows) == 2
            assert all(row["origin"] == "import" and row["effective_at"] is None for row in rows)
        assert not conn.execute("SELECT * FROM user_reward_groups").fetchall()


def test_reading_list_article_dedup_and_nonarticle_exclusion(
    reading_account: tuple[int, int],
) -> None:
    from news_dashboard.reading_list.service import add_item, update_item

    uid, aid = reading_account
    article = add_item(uid, "https://example.test/a?utm_medium=email")
    with connect() as conn:
        conn.execute("UPDATE reading_list_items SET kind='article' WHERE id=%s", (article["id"],))
    update_item(uid, article["id"], status="done")
    transition_article_state(aid, "done", user_id=uid)
    assert count() == 1
    other = add_item(uid, "https://example.test/video")
    with connect() as conn:
        conn.execute("UPDATE reading_list_items SET kind='video' WHERE id=%s", (other["id"],))
    update_item(uid, other["id"], status="done")
    assert count() == 1


def test_two_accounts_private_article_authorization_and_lease_expiry(
    reading_account: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid, aid = reading_account
    with connect() as conn:
        second = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('other','x') RETURNING id"
        ).fetchone()["id"]
        conn.execute("UPDATE sources SET owner_user_id=%s WHERE slug='reads'", (uid,))
    assert transition_article_state(aid, "done", user_id=second) is None
    from news_dashboard.import_export import restore_user_archive

    restored = restore_user_archive(
        second,
        {
            "schema_version": 2,
            "articles": [{"canonical_url": "https://example.test/a", "state": "done"}],
        },
    )
    assert restored["articles"] == {"added": 0, "updated": 0, "skipped": 1}
    assert count() == 0
    version = reader.body_version("A short article body.")
    with pytest.raises(HTTPException) as error:
        reader.accept_evidence(second, aid, reader.ReaderEvidence(body_version=version))
    assert error.value.status_code == 404
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr(reader, "utc_now", lambda: clock[0])
    start = reader.accept_evidence(uid, aid, reader.ReaderEvidence(body_version=version))
    clock[0] += timedelta(seconds=21)
    with pytest.raises(HTTPException) as expired:
        reader.accept_evidence(
            uid,
            aid,
            reader.ReaderEvidence(
                body_version=version,
                token=start["token"],
                sequence=1,
                attentive_ms=15000,
                end_ms=2000,
                progress=1,
            ),
        )
    assert expired.value.status_code == 409
    assert count() == 0
