from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from random import Random
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from news_dashboard.auth import require_auth
from news_dashboard.db import connect
from news_dashboard.export import assemble_user_export
from news_dashboard.import_export import restore_user_archive
from news_dashboard.main import app
from news_dashboard.reading_progress import activity, daily, rewards
from news_dashboard.user_settings.service import update_analytics_settings

pytestmark = pytest.mark.postgres
Account = tuple[int, list[datetime]]


@pytest.fixture
def active_account(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> Account:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    with connect() as conn:
        uid = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('active-test','unused') RETURNING id"
        ).fetchone()["id"]
    clock = [datetime(2026, 1, 1, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(activity, "utc_now", lambda: clock[0])
    return uid, clock


def payload(window: dict[str, Any], end: int = 15000, start: int = 0) -> activity.ActivityHeartbeat:
    return activity.ActivityHeartbeat(
        window_id=UUID(window["window_id"]), start_ms=start, end_ms=end
    )


def beat(account: Account, end: int = 15000) -> dict[str, Any]:
    uid, clock = account
    window = activity.open_window(uid)
    clock[0] += timedelta(milliseconds=end)
    return activity.heartbeat(uid, payload(window, end))


def test_integer_union_difference_against_discrete_oracle() -> None:
    random = Random(1627)  # noqa: S311 - deterministic interval test corpus, not secrets
    union: list[list[int]] = []
    occupied: set[int] = set()
    for _ in range(1000):
        left = random.randrange(1000)
        right = left + random.randrange(1, 300)
        delta = activity.uncovered(left, right, union)
        assert sum(end - start for start, end in delta) == len(set(range(left, right)) - occupied)
        occupied.update(range(left, right))
        union = activity.merge([*union, [left, right]])
        assert sum(end - start for start, end in union) == len(occupied)


def test_read_only_unknown_even_zero_and_distinct_from_reads(active_account: Account) -> None:
    uid, _ = active_account
    initial = activity.get_activity(uid)
    assert initial["total_ms"] == 0
    assert initial["coverage"]["status"] == "unknown"
    assert set(initial["coverage"]["reasons"]) == {"global_gap_or_unknown", "pre_measurement"}
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM user_activity_totals").fetchone()["n"] == 0
    assert beat(active_account)["total_ms"] == 15000
    assert activity.get_activity(uid)["coverage"]["status"] == "partial"
    assert rewards.daily_collection(uid)["reading_total"] == 0
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM user_reader_evidence").fetchone()["n"] == 0


def test_replay_conflict_expiry_unknown_and_exact_ms(active_account: Account) -> None:
    uid, clock = active_account
    window = activity.open_window(uid)
    clock[0] += timedelta(milliseconds=15001)
    body = payload(window, 15001)
    first = activity.heartbeat(uid, body)
    assert first["accepted_ms"] == 15001
    assert activity.heartbeat(uid, body) == first
    with pytest.raises(HTTPException, match="activity_payload_conflict"):
        activity.heartbeat(uid, payload(window, 15000))
    clock[0] += timedelta(seconds=120)
    with pytest.raises(HTTPException, match="activity_window_expired"):
        activity.heartbeat(uid, body)
    activity.cleanup_activity()
    with pytest.raises(HTTPException, match="activity_window_invalid"):
        activity.heartbeat(uid, body)
    with pytest.raises(HTTPException):
        activity.heartbeat(uid, activity.ActivityHeartbeat(window_id=uuid4(), start_ms=0, end_ms=1))
    assert activity.get_activity(uid)["total_ms"] == 15001


@pytest.mark.parametrize(
    ("elapsed", "end"), [(0, 1), (15000, 15001), (30000, 30000), (30001, 15000)]
)
def test_future_and_expiry_rejected(active_account: Account, elapsed: int, end: int) -> None:
    uid, clock = active_account
    window = activity.open_window(uid)
    clock[0] += timedelta(milliseconds=elapsed)
    with pytest.raises(HTTPException):
        activity.heartbeat(uid, payload(window, end))
    assert activity.get_activity(uid)["total_ms"] == 0


@pytest.mark.parametrize(
    ("start", "end"), [(-1, 1), (0, 0), (1, 1), (2, 1), (0, 30001), (False, 1), (0, 1.5), (0, "15")]
)
def test_strict_boundary_validation(start: Any, end: Any) -> None:
    with pytest.raises(ValidationError):
        activity.ActivityHeartbeat(window_id=uuid4(), start_ms=start, end_ms=end)


def test_interval_union_independent_connections_retries_and_overlap(
    active_account: Account,
) -> None:
    uid, clock = active_account
    windows = [activity.open_window(uid) for _ in range(8)]
    clock[0] += timedelta(seconds=20)
    barrier = Barrier(8)

    def submit(index: int) -> dict[str, Any]:
        barrier.wait()
        return activity.heartbeat(
            uid, payload(windows[index], 20000 if index % 2 else 15000, 5000 if index % 3 else 0)
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))
    assert sum(r["accepted_ms"] for r in results) == 20000
    assert activity.get_activity(uid)["total_ms"] == 20000
    barrier = Barrier(8)

    def replay(_: int) -> dict[str, Any]:
        barrier.wait()
        return activity.heartbeat(uid, payload(windows[0], 15000))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(replay, range(8)))
    assert activity.get_activity(uid)["total_ms"] == 20000
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT sum(active_ms) AS n FROM user_activity_days WHERE user_id=%s", (uid,)
            ).fetchone()["n"]
            == 20000
        )


@pytest.mark.parametrize("target", rewards.TIME_TARGETS)
def test_exact_badge_boundaries_permanent_group_and_timestamp(
    active_account: Account, target: int
) -> None:
    uid, clock = active_account
    with connect() as conn:
        activity.ensure_total(conn, uid)
        conn.execute(
            "UPDATE user_activity_totals SET total_ms=%s WHERE user_id=%s",
            (target * 1000 - 15001, uid),
        )
    below = beat(active_account)
    assert below["total_ms"] == target * 1000 - 1
    assert f"active_time_{target}" not in below["newly_unlocked"]
    exact = beat(active_account, 1)
    assert f"active_time_{target}" in exact["newly_unlocked"]
    earned_at = clock[0].isoformat()
    # Permanent groups hash the transient window ID; exports omit even that internal cause key.
    assert exact["window_id"] not in str(assemble_user_export(user_id=uid))
    assert beat(active_account, 1)["newly_unlocked"] == []
    update_analytics_settings(uid, enabled=False)
    activity.cleanup_activity()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_achievements WHERE user_id=%s AND achievement_key=%s",
            (uid, f"active_time_{target}"),
        ).fetchone()
        assert row["earned_at"].isoformat() == earned_at
        assert str(row["reward_group_id"]) == exact["reward_group_id"]
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM user_achievements "
                "WHERE user_id=%s AND achievement_key=%s",
                (uid, f"active_time_{target}"),
            ).fetchone()["n"]
            == 1
        )


def test_atomic_rollback_total_days_award_and_ack(
    active_account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, clock = active_account
    with connect() as conn:
        activity.ensure_total(conn, uid)
        conn.execute("UPDATE user_activity_totals SET total_ms=899000 WHERE user_id=%s", (uid,))
    window = activity.open_window(uid)
    clock[0] += timedelta(seconds=15)
    original = rewards.award_rewards

    def fail(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        msg = "rollback"
        raise RuntimeError(msg)

    monkeypatch.setattr(activity, "award_rewards", fail)
    with pytest.raises(RuntimeError):
        activity.heartbeat(uid, payload(window))
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT receipt FROM user_activity_windows WHERE id=%s", (window["window_id"],)
            ).fetchone()["receipt"]
            is None
        )
        assert conn.execute("SELECT count(*) AS n FROM user_activity_days").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM user_achievements").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM user_reward_groups").fetchone()["n"] == 0
    assert activity.get_activity(uid)["total_ms"] == 899000
    monkeypatch.setattr(activity, "award_rewards", original)
    retried = activity.heartbeat(uid, payload(window))
    assert retried["accepted_ms"] == 15000
    assert retried["newly_unlocked"] == ["active_time_900"]


def test_consent_revision_same_account_lock_and_reader_invalidation(
    active_account: Account,
) -> None:
    uid, clock = active_account
    window = activity.open_window(uid)
    clock[0] += timedelta(seconds=15)
    update_analytics_settings(uid, enabled=False)
    assert activity.heartbeat(uid, payload(window))["available"] is False
    update_analytics_settings(uid, enabled=True)
    with pytest.raises(HTTPException):
        activity.heartbeat(uid, payload(window))
    assert "consent_gap" in activity.get_activity(uid)["coverage"]["reasons"]
    beat(active_account)
    assert activity.get_activity(uid)["total_ms"] == 15000
    with connect() as conn:
        assert (
            conn.execute("SELECT activity_revision FROM users WHERE id=%s", (uid,)).fetchone()[
                "activity_revision"
            ]
            >= 2
        )
        assert (
            conn.execute(
                "SELECT coverage_flags FROM user_activity_days WHERE user_id=%s", (uid,)
            ).fetchone()["coverage_flags"]
            & activity.CONSENT_GAP
        )


def test_archive_consent_uses_same_window_and_reader_revision_fence(
    active_account: Account,
) -> None:
    uid, clock = active_account
    window = activity.open_window(uid)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('activity-reader','Test','https://example.test/feed','tech','rss_feed')"
        )
        article = conn.execute(
            "INSERT INTO articles(url,canonical_url,title,source_slug,source_name,category,kind) "
            "VALUES (%s,%s,'Reader','activity-reader','Test','tech','rss_feed') RETURNING id",
            ("https://example.test/reader", "https://example.test/reader"),
        ).fetchone()["id"]
        conn.execute(
            """INSERT INTO user_reader_evidence(user_id,article_id,body_version,token,
            lease_until,updated_at,expires_at) VALUES (%s,%s,'version',%s,%s,%s,%s)""",
            (
                uid,
                article,
                uuid4(),
                clock[0] + timedelta(seconds=20),
                clock[0],
                clock[0] + timedelta(hours=24),
            ),
        )
    archive = assemble_user_export(user_id=uid)
    archive["preferences"]["notifications"]["analytics_enabled"] = False
    restore_user_archive(uid, archive)
    assert activity.heartbeat(uid, payload(window))["available"] is False
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM user_reader_evidence WHERE user_id=%s", (uid,)
            ).fetchone()["n"]
            == 0
        )
        disabled_revision = conn.execute(
            "SELECT activity_revision FROM users WHERE id=%s", (uid,)
        ).fetchone()["activity_revision"]
        assert disabled_revision > 0
    archive["preferences"]["notifications"]["analytics_enabled"] = True
    restore_user_archive(uid, archive)
    with pytest.raises(HTTPException, match="activity_window_invalid"):
        activity.heartbeat(uid, payload(window))
    with connect() as conn:
        revision = conn.execute(
            "SELECT activity_revision FROM users WHERE id=%s", (uid,)
        ).fetchone()["activity_revision"]
        assert revision > disabled_revision
    restore_user_archive(uid, archive)
    with connect() as conn:
        assert (
            conn.execute("SELECT activity_revision FROM users WHERE id=%s", (uid,)).fetchone()[
                "activity_revision"
            ]
            == revision
        )
    assert "consent_gap" in activity.get_activity(uid)["coverage"]["reasons"]
    assert activity.get_activity(uid)["total_ms"] == 0


def test_global_disable_and_presentation_preferences(
    active_account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, _ = active_account
    daily.save_preferences(
        uid,
        daily.ProgressPreferencesPatch(
            daily_welcome_enabled=False, reward_animations_enabled=False
        ),
    )
    assert beat(active_account)["total_ms"] == 15000
    window = activity.open_window(uid)
    monkeypatch.setenv("ANALYTICS_ENABLED", "false")
    assert activity.heartbeat(uid, payload(window))["available"] is False
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    with pytest.raises(HTTPException):
        activity.heartbeat(uid, payload(window))


@pytest.mark.parametrize(
    ("zone", "instant"),
    [
        ("America/New_York", "2026-03-08T04:59:50+00:00"),
        ("America/New_York", "2026-11-01T03:59:50+00:00"),
        ("Asia/Kathmandu", "2026-01-01T18:14:50+00:00"),
    ],
)
def test_frozen_local_midnight_dst_and_timezone_change(
    active_account: Account, zone: str, instant: str
) -> None:
    uid, clock = active_account
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(progress_timezone=zone))
    clock[0] = datetime.fromisoformat(instant)
    beat(active_account, 20000)
    with connect() as conn:
        before = conn.execute(
            "SELECT local_date,timezone,active_ms FROM user_activity_days "
            "WHERE active_ms>0 ORDER BY local_date"
        ).fetchall()
        assert [r["active_ms"] for r in before] == [10000, 10000]
    window = activity.open_window(uid)
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(progress_timezone="UTC"))
    clock[0] += timedelta(seconds=15)
    with pytest.raises(HTTPException):
        activity.heartbeat(uid, payload(window))
    with connect() as conn:
        after = conn.execute(
            "SELECT local_date,timezone,active_ms FROM user_activity_days "
            "WHERE active_ms>0 ORDER BY local_date"
        ).fetchall()
        assert after == before
    assert "timezone_change" in activity.get_activity(uid)["coverage"]["reasons"]


def test_retention_preserves_lifetime_and_rejects_pruned_ids(active_account: Account) -> None:
    uid, clock = active_account
    first = beat(active_account)
    clock[0] += timedelta(seconds=120)
    activity.cleanup_activity()
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM user_activity_windows").fetchone()["n"] == 0
        row = conn.execute(
            "SELECT recent_union,rate_count,rate_minute FROM user_activity_totals WHERE user_id=%s",
            (uid,),
        ).fetchone()
        assert row["recent_union"] == []
        assert row["rate_count"] == row["rate_minute"] == 0
    with pytest.raises(HTTPException):
        activity.heartbeat(
            uid,
            activity.ActivityHeartbeat(
                window_id=UUID(first["window_id"]), start_ms=0, end_ms=15000
            ),
        )
    clock[0] += timedelta(days=401)
    activity.cleanup_activity()
    assert activity.get_activity(uid)["total_ms"] == 15000
    assert "retention_unknown" in activity.get_activity(uid)["coverage"]["reasons"]
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM user_activity_days").fetchone()["n"] == 0


def test_capacity_and_rate_limits(active_account: Account) -> None:
    uid, clock = active_account
    for _ in range(16):
        activity.open_window(uid)
    with pytest.raises(HTTPException, match="activity_window_capacity"):
        activity.open_window(uid)
    clock[0] += timedelta(seconds=60)
    for _ in range(60):
        beat(active_account, 1)
    with pytest.raises(HTTPException, match="activity_rate_limit"):
        activity.open_window(uid)


def test_invalid_windows_cannot_evade_account_rate_limit(active_account: Account) -> None:
    uid, _ = active_account
    for _ in range(120):
        with pytest.raises(HTTPException, match="activity_window_invalid"):
            activity.heartbeat(
                uid, activity.ActivityHeartbeat(window_id=uuid4(), start_ms=0, end_ms=1)
            )
    with pytest.raises(HTTPException, match="activity_rate_limit"):
        activity.open_window(uid)
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT rate_count FROM user_activity_totals WHERE user_id=%s", (uid,)
            ).fetchone()["rate_count"]
            == 120
        )
        assert conn.execute("SELECT count(*) AS n FROM user_activity_windows").fetchone()["n"] == 0
    assert activity.get_activity(uid)["total_ms"] == 0


def test_clock_sample_after_waiting_account_lock(active_account: Account) -> None:
    uid, clock = active_account
    ready = Event()
    with connect() as conn:
        daily.lock_account(conn, uid)

        def wait() -> dict[str, Any]:
            ready.set()
            return activity.open_window(uid)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(wait)
            assert ready.wait(5)
            clock[0] += timedelta(seconds=31)
            conn.commit()
            window = future.result(10)
    clock[0] += timedelta(seconds=15)
    assert activity.heartbeat(uid, payload(window))["accepted_ms"] == 15000


def test_waiting_acceptance_observes_consent_transaction(active_account: Account) -> None:
    uid, clock = active_account
    window = activity.open_window(uid)
    clock[0] += timedelta(seconds=15)
    ready = Event()
    with connect() as conn:
        daily.lock_account(conn, uid)
        activity.invalidate(conn, uid)
        conn.execute("UPDATE users SET analytics_enabled=FALSE WHERE id=%s", (uid,))

        def submit() -> dict[str, Any]:
            ready.set()
            return activity.heartbeat(uid, payload(window))

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(submit)
            assert ready.wait(5)
            conn.commit()
            assert future.result(10)["available"] is False
    assert activity.get_activity(uid)["total_ms"] == 0


def test_acceptance_expiry_uses_clock_after_account_lock(active_account: Account) -> None:
    uid, clock = active_account
    window = activity.open_window(uid)
    clock[0] += timedelta(seconds=15)
    ready = Event()
    with connect() as conn:
        daily.lock_account(conn, uid)

        def submit() -> dict[str, Any]:
            ready.set()
            return activity.heartbeat(uid, payload(window))

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(submit)
            assert ready.wait(5)
            clock[0] += timedelta(seconds=15)
            conn.commit()
            with pytest.raises(HTTPException, match="activity_window_expired"):
                future.result(10)
    assert activity.get_activity(uid)["total_ms"] == 0


def test_400_saved_local_dates_and_cleanup_lock_order(active_account: Account) -> None:
    uid, clock = active_account
    activity.open_window(uid)
    with connect() as conn:
        for offset in (399, 400):
            conn.execute(
                "INSERT INTO user_activity_days(user_id,local_date,timezone,active_ms) "
                "VALUES (%s,%s,'UTC',10)",
                (uid, clock[0].date() - timedelta(days=offset)),
            )
    ready = Event()
    with connect() as conn:
        daily.lock_account(conn, uid)

        def cleanup() -> None:
            ready.set()
            activity.cleanup_activity()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(cleanup)
            assert ready.wait(5)
            conn.execute("UPDATE user_activity_totals SET total_ms=20 WHERE user_id=%s", (uid,))
            conn.commit()
            future.result(10)
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM user_activity_days WHERE user_id=%s", (uid,)
            ).fetchone()["n"]
            == 1
        )
    assert activity.get_activity(uid)["total_ms"] == 20


def test_owned_export_informational_import_cascade_and_api(active_account: Account) -> None:
    uid, clock = active_account
    first = beat(active_account)
    archive = assemble_user_export(user_id=uid)
    exported = archive["progress"]
    assert exported["activity"][0]["total_ms"] == 15000
    assert exported["activity_days"][0]["active_ms"] == 15000
    assert not {"recent_union", "receipt", "payload_hash", "window_id", "rate_count"} & set(
        exported["activity"][0]
    )
    exported["activity"][0]["total_ms"] = 72000000
    exported["awards"].append({"achievement_key": "active_time_72000"})
    restore_user_archive(uid, archive)
    assert activity.get_activity(uid)["total_ms"] == 15000
    assert not any(
        row["unlocked"]
        for row in rewards.daily_collection(uid)["items"]
        if row["key"].startswith("active_time_")
    )
    with connect() as conn:
        other = conn.execute(
            "INSERT INTO users(username,password_hash) "
            "VALUES ('other-active','unused') RETURNING id"
        ).fetchone()["id"]
    with pytest.raises(HTTPException):
        activity.heartbeat(
            other,
            activity.ActivityHeartbeat(
                window_id=UUID(first["window_id"]), start_ms=0, end_ms=15000
            ),
        )
    assert activity.get_activity(other)["total_ms"] == 0
    client = TestClient(app)
    app.dependency_overrides[require_auth] = lambda: {"id": uid, "is_guest": False}
    try:
        assert client.get("/api/users/me/activity").json()["total_ms"] == 15000
        assert (
            client.post("/api/users/me/activity/window", json={"user_id": other}).status_code == 422
        )
        assert (
            client.post(
                "/api/users/me/activity/heartbeat",
                json={"window_id": first["window_id"], "start_ms": 0, "end_ms": 30001},
            ).status_code
            == 422
        )
        with connect() as conn:
            conn.execute("UPDATE users SET is_guest=TRUE WHERE id=%s", (uid,))
        assert client.post("/api/users/me/activity/window", json={}).status_code == 403
        assert client.get("/api/users/me/activity").json() == {"available": False}
    finally:
        app.dependency_overrides.pop(require_auth, None)
    assert client.get("/api/users/me/activity").status_code == 401
    clock[0] += timedelta(seconds=1)
    with connect() as conn:
        daily.lock_account(conn, uid, mutation=False)
        conn.execute("DELETE FROM users WHERE id=%s", (uid,))
    with connect() as conn:
        for table in ("user_activity_totals", "user_activity_days", "user_activity_windows"):
            assert (
                conn.execute(
                    f"SELECT count(*) AS n FROM {table} WHERE user_id=%s", (uid,)
                ).fetchone()["n"]
                == 0
            )
