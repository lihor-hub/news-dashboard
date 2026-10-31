"""Frozen recap boundaries, authority, concurrency and portability on real PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, delete_user, require_auth
from news_dashboard.db import connect
from news_dashboard.export import assemble_user_export as export_user_archive
from news_dashboard.import_export import restore_user_archive
from news_dashboard.main import app
from news_dashboard.recaps import service
from news_dashboard.recaps.progress import progress_snapshot, recap_period
from news_dashboard.scheduler.service import _generate_recap_for_user

pytestmark = pytest.mark.postgres
SCHEDULED = datetime(2026, 3, 9, 9, tzinfo=timezone.utc)


@pytest.fixture
def owner(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    return int(create_user("recap-owner", "test-only-password")["id"])


@pytest.mark.parametrize(
    ("instant", "zone", "hours", "start", "end"),
    [
        ("2026-03-09T09:00:00+00:00", "America/New_York", 167, "2026-03-02", "2026-03-09"),
        ("2026-11-02T09:00:00+00:00", "America/New_York", 169, "2026-10-26", "2026-11-02"),
        ("2024-03-01T09:00:00+00:00", "Asia/Kolkata", 168, "2024-02-23", "2024-03-01"),
        ("2027-01-01T09:00:00+00:00", "UTC", 168, "2026-12-25", "2027-01-01"),
    ],
)
def test_period(instant: str, zone: str, hours: int, start: str, end: str) -> None:
    period = recap_period(datetime.fromisoformat(instant), zone)
    assert period["start_local_date"] == start
    assert period["end_local_date"] == end
    assert datetime.fromisoformat(period["end_at"]) - datetime.fromisoformat(
        period["start_at"]
    ) == timedelta(hours=hours)


def test_naive_rejected() -> None:
    with pytest.raises(ValueError, match="timezone aware"):
        recap_period(datetime(2026, 1, 1), "UTC")  # noqa: DTZ001 - deliberate invalid input


def seed(conn: Any, uid: int) -> None:
    conn.execute("UPDATE users SET progress_timezone='America/New_York' WHERE id=%s", (uid,))
    conn.execute(
        """INSERT INTO user_daily_visits(user_id,local_date,timezone,first_visited_at)
        VALUES (%s,'2026-03-02','America/New_York','2026-03-02T05:00:00Z'),
               (%s,'2026-03-03','UTC','2026-03-03T10:00:00Z')""",
        (uid, uid),
    )
    conn.execute(
        """INSERT INTO user_activity_totals(user_id,total_ms,measured_since,coverage_flags)
        VALUES (%s,9999999,'2026-03-02T05:00:00Z',7)""",
        (uid,),
    )
    conn.execute(
        """INSERT INTO user_activity_days(user_id,local_date,timezone,active_ms,coverage_flags)
        VALUES (%s,'2026-03-02','America/New_York',59000,3),
               (%s,'2026-03-03','UTC',999000,5)""",
        (uid, uid),
    )
    for key, origin, earned in [
        ("daily_streak_3", "live", "2026-03-02T05:00:00Z"),
        ("topic_python_1", "live", "2026-03-09T03:59:59Z"),
        ("articles_read_1", "live", "2026-03-09T04:00:00Z"),
        ("breadth_3", "live", "2026-03-10T10:00:00Z"),
        ("old_import", "import", None),
        ("old_history", "historical", None),
        ("unknown", "legacy", None),
    ]:
        conn.execute(
            """INSERT INTO user_achievements(user_id,achievement_key,origin,earned_at)
            VALUES (%s,%s,%s,%s)""",
            (uid, key, origin, earned),
        )


def assemble(uid: int) -> dict[str, Any]:
    return service.assemble_weekly_recap(
        uid, now=SCHEDULED + timedelta(days=10), period=recap_period(SCHEDULED, "America/New_York")
    )


@pytest.mark.parametrize(
    ("briefing_zone", "expected"), [("Asia/Kolkata", "Asia/Kolkata"), ("bad/zone", "UTC")]
)
def test_saved_zone_initializes_once_without_rescheduling(
    owner: int, briefing_zone: str, expected: str
) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET briefing_timezone=%s WHERE id=%s", (briefing_zone, owner))
    first = service.assemble_weekly_recap(owner, now=SCHEDULED)
    assert first["period"]["timezone"] == expected
    with connect() as conn:
        row = conn.execute(
            "SELECT progress_timezone,briefing_timezone FROM users WHERE id=%s", (owner,)
        ).fetchone()
        assert row["progress_timezone"] == expected
        assert row["briefing_timezone"] == briefing_zone
        conn.execute("UPDATE users SET briefing_timezone='Pacific/Honolulu' WHERE id=%s", (owner,))
    assert service.assemble_weekly_recap(owner, now=SCHEDULED)["period"]["timezone"] == expected


def test_invalid_internal_period_does_not_initialize_saved_zone(owner: int) -> None:
    period = {**recap_period(SCHEDULED, "UTC"), "end_at": SCHEDULED.isoformat()}
    with pytest.raises(ValueError, match="Invalid recap period"):
        service.assemble_weekly_recap(owner, period=period)
    with connect() as conn:
        assert (
            conn.execute("SELECT progress_timezone FROM users WHERE id=%s", (owner,)).fetchone()[
                "progress_timezone"
            ]
            is None
        )


def test_naive_generation_does_not_initialize_saved_zone(owner: int) -> None:
    with pytest.raises(ValueError, match="now must be timezone aware"):
        service.assemble_weekly_recap(owner, now=datetime(2026, 3, 9))  # noqa: DTZ001
    with connect() as conn:
        assert (
            conn.execute("SELECT progress_timezone FROM users WHERE id=%s", (owner,)).fetchone()[
                "progress_timezone"
            ]
            is None
        )


def test_observations_starting_at_period_end_are_unavailable(owner: int) -> None:
    period = recap_period(SCHEDULED, "America/New_York")
    with connect() as conn:
        conn.execute(
            """INSERT INTO user_daily_visits(user_id,local_date,timezone,first_visited_at)
            VALUES (%s,%s,%s,%s)""",
            (owner, period["end_local_date"], period["timezone"], period["end_at"]),
        )
        conn.execute(
            "INSERT INTO user_activity_totals(user_id,measured_since) VALUES (%s,%s)",
            (owner, period["end_at"]),
        )
        progress = progress_snapshot(conn, owner, period)
    assert progress["days_visited"] is None
    assert progress["active_seconds"] is None
    for metric in ("visits", "active_time"):
        assert progress["coverage"][metric]["status"] == "unavailable"
        assert progress["coverage"][metric]["measured_from"] is None
    assert progress["rewards"] == []


def test_mixed_zone_rows_and_day_flags_disclose_incomplete_coverage(owner: int) -> None:
    with connect() as conn:
        seed(conn, owner)
        # Old observations need not have a timezone-change flag; the rows are evidence too.
        conn.execute("UPDATE user_activity_totals SET coverage_flags=1 WHERE user_id=%s", (owner,))
        conn.execute("UPDATE user_activity_days SET coverage_flags=25 WHERE user_id=%s", (owner,))
        progress = progress_snapshot(conn, owner, recap_period(SCHEDULED, "America/New_York"))
    assert progress["days_visited"] == 1
    assert progress["active_seconds"] == 59
    assert progress["coverage"]["visits"]["reasons"] == [
        "frozen_observations_only",
        "timezone_change",
    ]
    assert set(progress["coverage"]["active_time"]["reasons"]) == {
        "global_gap_or_unknown",
        "transport_incomplete",
        "retention_unknown",
        "missing_days",
        "timezone_change",
    }
    assert progress["coverage"]["active_time"]["status"] == "partial"


def test_progress_delay_provenance_partial_frozen_and_late(owner: int) -> None:
    with connect() as conn:
        seed(conn, owner)
    data = assemble(owner)
    progress = data["progress"]
    assert (data["week_start"], data["week_end"]) == ("2026-03-02", "2026-03-08")
    assert progress["days_visited"] == 1  # presence, not credited streak; no old-zone rebucket
    assert progress["active_seconds"] == 59  # never lifetime or raw heartbeat minutes
    assert progress["coverage"]["active_time"]["status"] == "partial"
    assert set(progress["coverage"]["active_time"]["reasons"]) >= {
        "global_gap_or_unknown",
        "consent_gap",
        "timezone_change",
    }
    assert [r["key"] for r in progress["rewards"]] == ["daily_streak_3", "topic_python_1"]
    saved = service.save_weekly_recap(owner, data, None)
    assert saved["inserted"]
    winner = saved["snapshot"]
    with connect() as conn:
        conn.execute("UPDATE user_activity_days SET active_ms=900000 WHERE user_id=%s", (owner,))
        conn.execute("UPDATE users SET progress_timezone='UTC' WHERE id=%s", (owner,))
        conn.execute(
            """INSERT INTO user_achievements(user_id,achievement_key,origin,earned_at)
            VALUES (%s,'late_live','live','2026-03-05T10:00:00Z')""",
            (owner,),
        )
    again = service.save_weekly_recap(owner, assemble(owner), "loser narrative")
    assert again == {"snapshot": winner, "inserted": False}
    service.fill_narrative(owner, winner["id"], "first narrative")
    service.fill_narrative(owner, winner["id"], "second narrative")
    stored = service.get_recap(owner, winner["id"])
    assert stored is not None
    assert stored["narrative"] == "first narrative"
    assert stored["data"] == data
    # A stale legacy caller cannot rewrite a v2 row either.
    service.save_weekly_recap(owner, {"week_start": data["week_start"]}, "legacy loser")
    assert service.get_recap(owner, winner["id"]) == stored
    with connect() as conn:
        conn.execute("DELETE FROM user_activity_days WHERE user_id=%s", (owner,))
        conn.execute("DELETE FROM user_achievements WHERE user_id=%s", (owner,))
    assert service.get_recap(owner, winner["id"]) == stored
    assert stored["data"]["progress"]["rewards"][1]["title"] == "Python · Explorer"


def test_unmeasured_zero_consent_and_no_invention(owner: int) -> None:
    empty = assemble(owner)["progress"]
    assert empty["days_visited"] is None
    assert empty["active_seconds"] is None
    with connect() as conn:
        conn.execute(
            """INSERT INTO user_events(user_id,event_type,duration_ms)
               VALUES (%s,'heartbeat',999999)""",
            (owner,),
        )
        conn.execute(
            "INSERT INTO user_activity_totals(user_id,measured_since) VALUES (%s,'2026-03-01')",
            (owner,),
        )
        conn.execute(
            """INSERT INTO user_activity_days(user_id,local_date,timezone,active_ms)
            VALUES (%s,'2026-03-02','America/New_York',0)""",
            (owner,),
        )
        conn.execute("UPDATE users SET analytics_enabled=FALSE WHERE id=%s", (owner,))
    measured = assemble(owner)["progress"]
    assert measured["active_seconds"] == 0
    assert measured["coverage"]["active_time"]["status"] == "partial"
    assert measured["days_visited"] is None
    with connect() as conn:
        conn.execute("UPDATE user_activity_days SET active_ms=500 WHERE user_id=%s", (owner,))
    assert assemble(owner)["progress"]["active_seconds"] == 0.5


def test_all_week_scoped_legacy_sql_half_open(owner: int) -> None:
    period = recap_period(SCHEDULED, "America/New_York")
    start, end = (datetime.fromisoformat(period[k]) for k in ("start_at", "end_at"))
    with connect() as conn:
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('recap','Recap','https://fixture.test/rss','tech','rss_feed')"
        )
        for index, at in enumerate(
            [
                start - timedelta(seconds=1),
                start,
                end - timedelta(seconds=1),
                end,
                end + timedelta(days=1),
            ]
        ):
            aid = conn.execute(
                """INSERT INTO articles
                (url,canonical_url,title,source_slug,source_name,category,kind)
                VALUES (%s,%s,'Test','recap','Recap','tech','rss_feed') RETURNING id""",
                (f"https://fixture.test/{index}", f"https://fixture.test/{index}"),
            ).fetchone()["id"]
            conn.execute(
                """INSERT INTO user_article_state
                (user_id,article_id,state,done_at,starred,starred_at)
                VALUES (%s,%s,'done',%s,TRUE,%s)""",
                (owner, aid, at, at),
            )
            for event in ("heartbeat", "article_close"):
                conn.execute(
                    """INSERT INTO user_events(user_id,event_type,duration_ms,created_at)
                       VALUES (%s,%s,60000,%s)""",
                    (owner, event, at),
                )
    data = assemble(owner)
    assert data["articles_read"] == 2
    assert data["categories"] == [{"category": "tech", "count": 2}]
    assert data["sources"] == [{"source": "Recap", "count": 2}]
    assert data["minutes_read"] == 2
    assert data["saved"]["starred_this_week"] == data["saved"]["read_from_backlog"] == 2
    assert data["dwell"] == {"skims": 0, "reads": 2, "average_seconds": 60.0}


def test_single_consistent_snapshot(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
    original = progress_snapshot

    def during(conn: Any, uid: int, period: dict[str, str]) -> dict[str, Any]:
        result = original(conn, uid, period)
        with connect() as writer:
            writer.execute(
                """INSERT INTO user_events(user_id,event_type,duration_ms,created_at)
                   VALUES (%s,'heartbeat',60000,'2026-03-03')""",
                (uid,),
            )
            writer.execute(
                """INSERT INTO user_achievements(user_id,achievement_key,origin,earned_at)
                   VALUES (%s,'late','live','2026-03-03')""",
                (uid,),
            )
        return result

    monkeypatch.setattr(service, "progress_snapshot", during)
    data = assemble(owner)
    assert data["minutes_read"] == 0
    assert data["progress"]["rewards"] == []
    monkeypatch.setattr(service, "progress_snapshot", original)
    assert assemble(owner)["minutes_read"] == 1


def test_concurrent_first_winner_and_legacy_collision(owner: int) -> None:
    data = assemble(owner)
    barrier = Barrier(2)

    def save(n: int) -> dict[str, Any]:
        barrier.wait(timeout=10)
        return service.save_weekly_recap(owner, {**data, "articles_read": n}, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [4, 99]))
    assert sum(r["inserted"] for r in results) == 1
    assert results[0]["snapshot"] == results[1]["snapshot"]
    legacy = service.save_weekly_recap(
        owner, {"week_start": "2026-02-23", "articles_read": 100}, "old"
    )
    collision = service.save_weekly_recap(owner, {**data, "week_start": "2026-02-23"}, None)
    assert collision == {"snapshot": legacy, "inserted": False}


def test_scheduler_stored_winner_no_loser_push_and_narrative_retry(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = assemble(owner)
    monkeypatch.setattr(service, "assemble_weekly_recap", lambda *_a, **_kw: data)
    inputs = []

    def fail(recap: dict[str, Any]) -> str:
        inputs.append(recap)
        msg = "test narrative failure"
        raise RuntimeError(msg)

    monkeypatch.setattr("news_dashboard.recaps.narrative.generate_recap_narrative", fail)
    pushes = []

    def hook(recap: dict[str, Any]) -> str:
        pushes.append(recap)
        return "ready"

    monkeypatch.setattr("news_dashboard.push.generate_recap_push_hook", hook)
    monkeypatch.setattr("news_dashboard.push.send_push_for_user", lambda *_a, **_kw: None)
    assert _generate_recap_for_user(owner)
    winner = service.list_recaps(owner)[0]
    assert winner["narrative"] is None
    data["articles_read"] = 999

    def retry(recap: dict[str, Any]) -> str:
        inputs.append(recap)
        return "retry"

    monkeypatch.setattr("news_dashboard.recaps.narrative.generate_recap_narrative", retry)
    assert _generate_recap_for_user(owner)
    assert len(pushes) == 1
    assert pushes[0] == winner["data"]
    assert inputs[-1] == winner["data"]
    assert service.list_recaps(owner)[0]["narrative"] == "retry"


def test_api_owner_readonly_archive_informational_and_delete(owner: int) -> None:
    other = create_user("other-recap", "test-only-password")["id"]
    data = assemble(owner)
    row = service.save_weekly_recap(owner, data, None)["snapshot"]

    def current() -> dict[str, Any]:
        return {"id": owner, "username": "recap-owner", "is_admin": False}

    app.dependency_overrides[require_auth] = current
    try:
        with TestClient(app) as client:
            detail = client.get(f"/api/recaps/{row['id']}").json()
            assert client.get("/api/recaps/latest").json() == detail
            assert client.get("/api/recaps").json()["items"] == [detail]
            assert client.get("/api/recaps/0").status_code == 422
            assert client.get("/api/recaps/99999999").status_code == 404
            app.dependency_overrides[require_auth] = lambda: {
                "id": other,
                "username": "other-recap",
                "is_admin": False,
            }
            assert client.get(f"/api/recaps/{row['id']}?user_id={owner}").status_code == 404
    finally:
        app.dependency_overrides.pop(require_auth, None)
    with TestClient(app) as client:
        assert client.get(f"/api/recaps/{row['id']}").status_code == 401
    archive = export_user_archive(owner)
    assert archive["schema_version"] == 2
    assert archive["weekly_recaps"][0]["data"] == data
    assert export_user_archive(other)["weekly_recaps"] == []
    restore_user_archive(other, archive)
    assert service.list_recaps(other) == []
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM user_daily_visits WHERE user_id=%s", (other,)
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM user_achievements WHERE user_id=%s", (other,)
            ).fetchone()["n"]
            == 0
        )
    delete_user(owner)
    assert service.get_recap(owner, row["id"]) is None


def test_actual_import_does_not_fabricate_weekly_rewards_or_measurements(owner: int) -> None:
    with connect() as conn:
        conn.execute("""INSERT INTO sources(slug,name,url,category,kind)
            VALUES ('import-recap','Import','https://fixture.test/feed','tech','rss_feed')""")
    restore_user_archive(
        owner,
        {
            "schema_version": 2,
            "articles": [
                {
                    "canonical_url": "https://fixture.test/imported",
                    "title": "Python programming",
                    "source_slug": "import-recap",
                    "source_name": "Import",
                    "category": "tech",
                    "kind": "rss_feed",
                    "state": "done",
                    "done_at": "2026-03-03T10:00:00Z",
                }
            ],
            "progress": {
                "daily_visits": [{"local_date": "2026-03-03"}],
                "activity": [{"total_ms": 999999}],
                "awards": [{"achievement_key": "forged", "origin": "live"}],
            },
            "weekly_recaps": [{"data": {"snapshot_version": 2}}],
        },
    )
    data = assemble(owner)
    assert data["articles_read"] == 1  # legacy reading-state summary, not live-earned count
    assert data["progress"]["rewards"] == []
    assert data["progress"]["days_visited"] is None
    assert data["progress"]["active_seconds"] is None
    with connect() as conn:
        award = conn.execute(
            "SELECT * FROM user_achievements WHERE user_id=%s", (owner,)
        ).fetchone()
        assert award["origin"] == "import"
        assert award["earned_at"] is None
    assert service.list_recaps(owner) == []


def test_scheduler_race_pushes_once_with_actual_persisted_winner(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from itertools import count

    barrier = Barrier(2)
    sequence = count(10)
    base = assemble(owner)

    def competing(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        data = {**base, "articles_read": next(sequence)}
        barrier.wait(timeout=10)
        return data

    monkeypatch.setattr(service, "assemble_weekly_recap", competing)
    narratives = []
    pushes = []

    def narrative(recap: dict[str, Any]) -> str:
        narratives.append(recap)
        return "safe narrative"

    def hook(recap: dict[str, Any]) -> str:
        pushes.append(recap)
        return "ready"

    monkeypatch.setattr("news_dashboard.recaps.narrative.generate_recap_narrative", narrative)
    monkeypatch.setattr("news_dashboard.push.generate_recap_push_hook", hook)
    monkeypatch.setattr("news_dashboard.push.send_push_for_user", lambda *_a, **_kw: None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(_generate_recap_for_user, [owner, owner])) == [True, True]
    stored = service.list_recaps(owner)[0]
    assert len(pushes) == 1
    assert pushes[0] == stored["data"]
    assert all(recap == stored["data"] for recap in narratives)
    assert stored["narrative"] == "safe narrative"


def test_scheduler_legacy_collision_neither_enriches_nor_pushes(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = assemble(owner)
    legacy = service.save_weekly_recap(
        owner, {"week_start": data["week_start"], "articles_read": 50}, None
    )
    monkeypatch.setattr(service, "assemble_weekly_recap", lambda *_a, **_kw: data)

    def forbidden(*_a: Any, **_kw: Any) -> None:
        pytest.fail("Legacy collision must not generate narrative or push")

    monkeypatch.setattr("news_dashboard.recaps.narrative.generate_recap_narrative", forbidden)
    monkeypatch.setattr("news_dashboard.push.send_push_for_user", forbidden)
    assert _generate_recap_for_user(owner)
    assert service.get_recap(owner, legacy["id"]) == legacy


def test_schedule_briefing_zone_freezes_progress_period_before_delay(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from news_dashboard.scheduler import service as scheduler

    with connect() as conn:
        conn.execute(
            """UPDATE users SET recap_enabled=TRUE,recap_day='mon',briefing_time='18:00',
            briefing_timezone='Asia/Tokyo',progress_timezone='Pacific/Honolulu' WHERE id=%s""",
            (owner,),
        )
    monkeypatch.setattr(scheduler, "datetime", SimpleNamespace(now=lambda _tz: SCHEDULED))
    captured = []

    def generate(uid: int, **kw: Any) -> bool:
        captured.append((uid, kw))
        return True

    monkeypatch.setattr(scheduler, "_generate_recap_for_user", generate)
    result = scheduler._run_weekly_recaps()
    assert result is not None
    assert result[0] == "success"
    assert len(captured) == 1
    assert captured[0][1]["period"] == recap_period(SCHEDULED, "Pacific/Honolulu")
    assert captured[0][1]["period"]["end_local_date"] == "2026-03-08"
