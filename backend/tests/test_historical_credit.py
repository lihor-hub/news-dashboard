"""Historical tooling is exercised only on freshly seeded dedicated PG fixtures."""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from news_dashboard.db import connect, init_db
from news_dashboard.export import assemble_user_export
from news_dashboard.import_export import restore_user_archive
from news_dashboard.ingest.service import transition_article_state
from news_dashboard.reading_progress import credits, daily, history, rewards  # noqa: A004

pytestmark = pytest.mark.postgres


@pytest.fixture
def historical_account(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    with connect() as conn:
        uid = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('history-fixture','x') RETURNING id"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('history','History','https://fixture.test/feed','tech','rss_feed')"
        )
    return int(uid)


def seed(uid: int, count: int = 1, *, state: str = "done", done_at: str | None = None) -> list[int]:
    with connect() as conn:
        ids = []
        for _ in range(count):
            url = f"https://fixture.test/{uuid4()}"
            aid = conn.execute(
                """INSERT INTO articles(url,canonical_url,title,
                   source_slug,source_name,category,kind)
                VALUES (%s,%s,'Python guide','history','History','tech','rss_feed') RETURNING id""",
                (url, url),
            ).fetchone()["id"]
            conn.execute(
                """INSERT INTO user_article_state(user_id,article_id,state,done_at)
                   VALUES (%s,%s,%s,%s)""",
                (uid, aid, state, done_at),
            )
            ids.append(aid)
    return ids


def run_batch(uid: int) -> dict[str, Any]:
    with connect() as conn:
        return history.batch(conn, uid)


def prepare(uid: int) -> dict[str, Any]:
    with connect() as conn:
        return history.prepare(
            conn, uid, protection_ref="fresh test fixture; no operational protection claimed"
        )


def test_eligibility_dates_legacy_no_invented_activity_and_export(historical_account: int) -> None:
    uid = historical_account
    seed(uid, state="done")
    seed(uid, state="today", done_at="2099-01-01")
    seed(uid, state="archived", done_at="2001-01-01")
    seed(uid, state="today")
    lost = seed(uid)[0]
    with connect() as conn:
        conn.execute("DELETE FROM articles WHERE id=%s", (lost,))
        conn.execute(
            """INSERT INTO user_achievements(user_id,achievement_key,unlocked_at,metadata)
            VALUES (%s,'retired_unknown','2000-01-01','{"old":true}'),
            (%s,'hundred_articles_read','2000-01-01','{}')""",
            (uid, uid),
        )
    before = prepare(uid)
    init_db()  # Idempotent additive schema cannot run the operator.
    assert rewards.daily_collection(uid)["history_status"] == "running"
    result = run_batch(uid)
    assert result["credited_reads"] == result["eligible"] == 3
    assert result["scanned"] == 4
    assert result["preserved_rewards"] == 2
    assert run_batch(uid) == result
    assert prepare(uid) == result
    assert result["cutoff_at"] == before["cutoff_at"]
    collection = rewards.daily_collection(uid)
    assert collection["reading_total"] == 3  # Never infer 100 from the old badge.
    assert collection["history_status"] == "complete"
    assert collection["historical_reconciliation"] == result
    with connect() as conn:
        assert all(
            r["effective_at"] is None
            and r["origin"] == "historical"
            and r["topics_finalized_version"] == 1
            for r in conn.execute("SELECT * FROM user_read_credits").fetchall()
        )
        old = conn.execute(
            "SELECT * FROM user_achievements WHERE achievement_key='retired_unknown'"
        ).fetchone()
        assert old["unlocked_at"].year == 2000
        assert old["metadata"] == {"old": True}
        assert conn.execute("SELECT COUNT(*) AS n FROM user_daily_visits").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM user_activity_totals").fetchone()["n"] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM user_reward_groups WHERE kind='live'"
            ).fetchone()["n"]
            == 0
        )
    archive = assemble_user_export(uid)
    assert archive["progress"]["historical_reconciliation"] == [result]
    # Uploaded state/claims/counters cannot authorize anything on restore.
    archive["progress"]["historical_reconciliation"][0]["credited_reads"] = 999999
    restore_user_archive(uid, archive)
    assert rewards.daily_collection(uid)["historical_reconciliation"]["credited_reads"] == 3


def test_atomic_interruption_resume_and_after_commit_retry(
    historical_account: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = historical_account
    seed(uid, 202)
    prepare(uid)
    original = credits.credit_article
    calls = 0

    def crash(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 3:
            msg = "fixture crash before commit"
            raise RuntimeError(msg)
        return original(*args, **kwargs)

    monkeypatch.setattr(history, "credit_article", crash)
    with pytest.raises(RuntimeError):
        run_batch(uid)
    with connect() as conn:
        state = history.snapshot(conn, uid)
        assert state is not None
        assert state["cursor_article_id"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM user_read_credits").fetchone()["n"] == 0
    monkeypatch.setattr(history, "credit_article", original)
    first = run_batch(uid)  # Lost response after commit is retried from committed cursor.
    assert first["credited_reads"] == 200
    assert first["status"] == "running"
    assert rewards.daily_collection(uid)["historical_group_id"] is None
    final = run_batch(uid)
    assert final["credited_reads"] == 202
    assert final["status"] == "complete"
    assert run_batch(uid) == final
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM user_reward_groups").fetchone()["n"] == 1


def test_caller_savepoint_and_live_first_import_behind_cursor(historical_account: int) -> None:
    uid = historical_account
    ids = seed(uid, 201)
    with connect() as conn:
        conn.execute("UPDATE user_article_state SET state='today' WHERE article_id=%s", (ids[1],))
    prepare(uid)
    transition_article_state(ids[0], "done", user_id=uid)

    def rollback_batch(conn: Any) -> None:
        with conn.transaction():
            history.batch(conn, uid)
            msg = "caller savepoint rollback"
            raise RuntimeError(msg)

    with connect() as conn:
        with pytest.raises(RuntimeError, match="savepoint rollback"):
            rollback_batch(conn)
        state = history.snapshot(conn, uid)
        assert state is not None
        assert state["cursor_article_id"] == 0
    run_batch(uid)
    # Simulate a future restore of previously ineligible evidence behind cursor.
    with connect() as conn:
        conn.execute(
            "DELETE FROM user_article_state WHERE user_id=%s AND article_id=%s", (uid, ids[1])
        )
        url = conn.execute("SELECT url FROM articles WHERE id=%s", (ids[1],)).fetchone()["url"]
    restore_user_archive(
        uid,
        {
            "schema_version": 2,
            "articles": [
                {"canonical_url": url, "state": "done", "done_at": "2099-01-01T00:00:00Z"}
            ],
        },
    )
    final = run_batch(uid)
    assert final["status"] == "complete"
    transition_article_state(ids[1], "done", user_id=uid)
    with connect() as conn:
        origins = {
            r["article_id"]: r["origin"]
            for r in conn.execute("SELECT * FROM user_read_credits").fetchall()
        }
        assert origins[ids[0]] == "live"
        assert origins[ids[1]] == "import"
        assert len(origins) == 201


def test_two_workers_live_race_and_account_delete(historical_account: int) -> None:
    uid = historical_account
    ids = seed(uid, 10)
    prepare(uid)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures: list[Future[Any]] = [
            pool.submit(run_batch, uid),
            pool.submit(run_batch, uid),
            pool.submit(transition_article_state, ids[0], "done", user_id=uid),
        ]
        for future in futures:
            future.result(timeout=20)
    collection = rewards.daily_collection(uid)
    assert collection["reading_total"] == 10
    group = collection["historical_group_id"]
    visit = daily.record_visit(uid)
    from datetime import date

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _: daily.claim_presentation(
                    uid, date.fromisoformat(visit["local_date"]), historical_group_id=group
                ),
                range(2),
            )
        )
    assert sum(c["authorization"]["history"] for c in claims) == 1
    assert rewards.claim_reward(uid, group, acknowledge=True)["acknowledged"]
    assert rewards.claim_reward(uid, group, acknowledge=True)["acknowledged"]
    with connect() as conn:
        daily.lock_account(conn, uid)
        conn.execute("DELETE FROM users WHERE id=%s", (uid,))
    with pytest.raises(HTTPException):
        run_batch(uid)
    with connect() as conn:
        assert (
            conn.execute("SELECT COUNT(*) AS n FROM user_historical_credit_state").fetchone()["n"]
            == 0
        )


def test_locked_source_not_skipped(historical_account: int) -> None:
    uid = historical_account
    aid = seed(uid, 2)[0]
    prepare(uid)
    locked = Event()
    release = Event()

    def hold() -> None:
        with connect() as conn:
            conn.execute("SELECT id FROM articles WHERE id=%s FOR UPDATE", (aid,))
            locked.set()
            assert release.wait(10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(hold)
        assert locked.wait(5)
        worker = pool.submit(run_batch, uid)
        assert not worker.done()
        release.set()
        holder.result(timeout=10)
        assert worker.result(timeout=10)["credited_reads"] == 2


def test_operator_entry_read_only_and_explicit_actions(
    historical_account: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    uid = historical_account
    seed(uid, state="today", done_at="2099-01-01")

    def invoke(action: str, *extra: str) -> Any:
        monkeypatch.setattr(
            "sys.argv",
            ["history", action, "--user-id", str(uid), "--policy", history.POLICY, *extra],
        )
        history.main()
        return json.loads(capsys.readouterr().out)

    assert invoke("status") is None
    assert invoke("dry-run")["retained_eligible_rows"] == 1
    assert invoke("status") is None
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM user_read_credits").fetchone()["n"] == 0
    assert invoke("prepare", "--protection-ref", "fresh fixture only")["status"] == "running"
    assert invoke("batch")["credited_reads"] == 1
    assert invoke("batch")["credited_reads"] == 1
    assert invoke("status")["status"] == "complete"
    monkeypatch.setattr(
        "sys.argv", ["history", "batch", "--user-id", str(uid), "--policy", "uploaded-v2"]
    )
    with pytest.raises(SystemExit):
        history.main()


def test_preserved_only_intro_and_historical_first_permanence(historical_account: int) -> None:
    uid = historical_account
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_achievements(user_id,achievement_key) VALUES (%s,'unknown_retired')",
            (uid,),
        )
    prepare(uid)
    assert run_batch(uid)["credited_reads"] == 0
    assert rewards.daily_collection(uid)["historical_group_id"] is not None
    # New evidence after the frozen horizon uses synchronous live credit, not a rerun.
    aid = seed(uid)[0]
    transition_article_state(aid, "done", user_id=uid)
    assert run_batch(uid)["credited_reads"] == 0
    assert rewards.daily_collection(uid)["reading_total"] == 1


def test_completion_rollback_and_historical_first_survives_retention(
    historical_account: int,
) -> None:
    uid = historical_account
    aid = seed(uid)[0]
    prepare(uid)
    with connect() as conn:
        assert history.batch(conn, uid)["status"] == "complete"
        conn.rollback()  # Crash before the completion/group commit.
    assert rewards.daily_collection(uid)["historical_group_id"] is None
    assert run_batch(uid)["credited_reads"] == 1
    transition_article_state(aid, "done", user_id=uid)
    with connect() as conn:
        url = conn.execute("SELECT url FROM articles WHERE id=%s", (aid,)).fetchone()["url"]
        conn.execute("DELETE FROM articles WHERE id=%s", (aid,))
    restore_user_archive(
        uid,
        {
            "schema_version": 2,
            "articles": [{"canonical_url": url, "title": "Ruby changed subject", "state": "done"}],
        },
    )
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_read_credits WHERE user_id=%s", (uid,)).fetchone()
        assert row["origin"] == "historical"
        assert row["effective_at"] is None
        assert row["article_id"] is None
        assert (
            conn.execute("SELECT topic_id FROM user_topic_credits").fetchone()["topic_id"]
            == "python"
        )
    assert rewards.daily_collection(uid)["reading_total"] == 1


def test_import_and_delete_wait_on_operator_account_lock(historical_account: int) -> None:
    uid = historical_account
    aid = seed(uid)[0]
    prepare(uid)
    with connect() as conn:
        url = conn.execute("SELECT url FROM articles WHERE id=%s", (aid,)).fetchone()["url"]
    # A source after capture is not in the horizon; import must credit it itself.
    new_aid = seed(uid, state="today")[0]
    with connect() as conn:
        new_url = conn.execute("SELECT url FROM articles WHERE id=%s", (new_aid,)).fetchone()["url"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(run_batch, uid)
        imported = pool.submit(
            restore_user_archive,
            uid,
            {
                "schema_version": 2,
                "articles": [
                    {"canonical_url": url, "state": "done"},
                    {"canonical_url": new_url, "state": "done"},
                ],
            },
        )
        work.result(timeout=20)
        imported.result(timeout=20)
    assert rewards.daily_collection(uid)["reading_total"] == 2
    with connect() as conn:
        daily.lock_account(conn, uid)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(run_batch, uid)
            conn.execute("DELETE FROM users WHERE id=%s", (uid,))
            conn.commit()
            with pytest.raises(HTTPException):
                pending.result(timeout=20)


def test_empty_no_intro_and_unprepared_rejected(historical_account: int) -> None:
    uid = historical_account
    with pytest.raises(ValueError, match="Prepare a protected horizon"):
        run_batch(uid)
    with connect() as conn, pytest.raises(ValueError, match="retention-protection reference"):
        history.prepare(conn, uid, protection_ref=" ")
    prepare(uid)
    assert run_batch(uid)["status"] == "complete"
    assert rewards.daily_collection(uid)["historical_group_id"] is None
