from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier, Event
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg.errors import ForeignKeyViolation
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.export import assemble_user_export
from news_dashboard.import_export import restore_user_archive
from news_dashboard.main import app
from news_dashboard.reading_progress import daily, rewards

pytestmark = pytest.mark.postgres
VisitAccount = tuple[int, list[datetime]]


@pytest.fixture
def visit_account(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> VisitAccount:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    with connect() as conn:
        uid = conn.execute(
            """INSERT INTO users(username,password_hash)
               VALUES ('visit-test','not-a-password') RETURNING id"""
        ).fetchone()["id"]
    clock = [datetime(2026, 1, 1, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(daily, "utc_now", lambda: clock[0])
    return uid, clock


def advance(clock: list[datetime], days: int = 1) -> None:
    clock[0] += timedelta(days=days)


def test_read_only_and_same_day(visit_account: VisitAccount) -> None:
    uid, _ = visit_account
    assert daily.get_daily_streak(uid)["current_streak_days"] == 0
    assert daily.get_preferences(uid)["timezone_initialized"] is False
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM user_daily_visits").fetchone()["n"] == 0
    first = daily.record_visit(uid)
    assert first["visit_kind"] == "first"
    assert first["current_streak_days"] == 1
    assert len(first["seven_days"]) == 7
    assert daily.record_visit(uid)["current_streak_days"] == 1
    assert daily.claim_presentation(uid, date(2026, 1, 1))["show"] is True
    assert daily.claim_presentation(uid, date(2026, 1, 1))["show"] is False


def test_concurrent_visits_claims_and_lost_response(visit_account: VisitAccount) -> None:
    uid, _ = visit_account
    barrier = Barrier(8)

    def visit(_: int) -> dict[str, Any]:
        barrier.wait()
        return daily.record_visit(uid)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(visit, range(8)))
    assert {r["current_streak_days"] for r in results} == {1}

    def claim(_: int) -> dict[str, Any]:
        barrier.wait()
        return daily.claim_presentation(uid, date(2026, 1, 1))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert sum(r["show"] for r in results) == 1
    assert not daily.claim_presentation(uid, date(2026, 1, 1))["show"]
    with connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM user_daily_visits").fetchone()["n"] == 1


def test_consecutive_gap_stale_best_and_permanent_milestones(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    for n in range(1, 101):
        result = daily.record_visit(uid)
        assert result["current_streak_days"] == n
        assert result["newly_unlocked"] == (
            [f"daily_streak_{n}"] if n in rewards.DAILY_TARGETS else []
        )
        advance(clock)
    advance(clock)
    assert daily.get_daily_streak(uid)["current_streak_days"] == 0
    result = daily.record_visit(uid)
    assert result["visit_kind"] == "restart"
    assert result["best_streak_days"] == 100
    assert len([a for a in rewards.daily_collection(uid)["items"] if a["unlocked"]]) == 5


@pytest.mark.parametrize(
    ("start", "hours"), [("2026-03-08T05:00:00+00:00", 23), ("2026-11-01T04:00:00+00:00", 25)]
)
def test_dst_calendar_midnight_not_24_hours(
    visit_account: VisitAccount, start: str, hours: int
) -> None:
    uid, clock = visit_account
    daily.save_preferences(
        uid, daily.ProgressPreferencesPatch(progress_timezone="America/New_York")
    )
    clock[0] = datetime.fromisoformat(start)
    result = daily.record_visit(uid)
    assert datetime.fromisoformat(result["next_credit_at"]) - clock[0] == timedelta(hours=hours)
    clock[0] += timedelta(hours=hours, microseconds=-1)
    assert daily.record_visit(uid)["current_streak_days"] == 1
    clock[0] += timedelta(microseconds=1)
    assert daily.record_visit(uid)["current_streak_days"] == 2


def test_travel_guard_and_frozen_observation(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    first = daily.record_visit(uid)
    daily.save_preferences(
        uid, daily.ProgressPreferencesPatch(progress_timezone="Pacific/Kiritimati")
    )
    suppressed = daily.record_visit(uid)
    assert suppressed["local_date"] == "2026-01-02"
    assert suppressed["next_credit_at"] == first["next_credit_at"]
    assert not suppressed["seven_days"][-1]["credited"]
    clock[0] = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert daily.record_visit(uid)["current_streak_days"] == 2
    daily.save_preferences(
        uid, daily.ProgressPreferencesPatch(progress_timezone="Pacific/Honolulu")
    )
    assert daily.get_daily_streak(uid)["current_streak_days"] == 0
    assert daily.record_visit(uid)["newly_unlocked"] == []
    with connect() as conn:
        rows = conn.execute("SELECT timezone FROM user_daily_visits ORDER BY local_date").fetchall()
        assert [r["timezone"] for r in rows] == ["UTC", "Pacific/Kiritimati"]
        assert (
            conn.execute("SELECT briefing_timezone FROM users WHERE id=%s", (uid,)).fetchone()[
                "briefing_timezone"
            ]
            == "UTC"
        )


def test_bootstrap_fractional_zone_and_forward_jump(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    with connect() as conn:
        conn.execute("UPDATE users SET briefing_timezone='Asia/Kathmandu' WHERE id=%s", (uid,))
    result = daily.record_visit(uid)
    assert result["timezone"] == "Asia/Kathmandu"
    assert result["next_credit_at"].endswith("18:15:00+00:00")
    advance(clock, 3)
    assert daily.record_visit(uid)["visit_kind"] == "restart"


def test_popup_suppression_does_not_disable_tracking(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    daily.record_visit(uid)
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=False))
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=True))
    assert not daily.claim_presentation(uid, date(2026, 1, 1))["show"]
    advance(clock)
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=False))
    assert daily.record_visit(uid)["current_streak_days"] == 2
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=True))
    assert not daily.claim_presentation(uid, date(2026, 1, 2))["show"]
    advance(clock)
    assert daily.record_visit(uid)["welcome_target"]


@pytest.mark.parametrize(
    "patch",
    [
        {"progress_timezone": ""},
        {"progress_timezone": "../UTC"},
        {"progress_timezone": "x" * 256},
        {"progress_timezone": None},
        {"daily_welcome_enabled": 1},
        {"daily_welcome_enabled": None},
        {"reward_animations_enabled": "yes"},
        {"unknown": True},
    ],
)
def test_preferences_reject_invalid_values(patch: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        daily.ProgressPreferencesPatch.model_validate(patch)


def test_atomic_history_stale_bundle_and_exact_reward_retry(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    group = uuid4()
    with connect() as conn:
        conn.execute(
            """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at,summary)
               VALUES (%s,%s,'intro','historical_intro',%s,%s)""",
            (
                group,
                uid,
                clock[0],
                Jsonb({"credited_reads": 42, "exact_earned_dates_known": False}),
            ),
        )
    daily.record_visit(uid)
    assert daily.claim_presentation(uid, date(2025, 12, 31), group)["reason"] == "stale_visit"
    result = daily.claim_presentation(uid, date(2026, 1, 1), group)
    assert result["authorization"] == {"welcome": True, "history": True, "rewards": False}
    assert not daily.claim_presentation(uid, date(2026, 1, 1), group)["show"]
    groups = []
    for n in (3, 7):
        with connect() as conn:
            daily.lock_account(conn, uid)
            groups.append(
                rewards.award_rewards(
                    conn,
                    uid,
                    cause_key=f"test:{n}",
                    origin="live",
                    earned_at=clock[0],
                    candidates=[
                        {
                            "key": f"daily_streak_{n}",
                            "criteria_version": 1,
                            "progress": n,
                            "target": n,
                        }
                    ],
                )["reward_group_id"]
            )
    assert rewards.claim_reward(uid, groups[0])["show"]
    assert not rewards.claim_reward(uid, groups[0])["show"]
    assert rewards.claim_reward(uid, groups[1])["show"]
    assert rewards.claim_reward(uid, groups[0], acknowledge=True)["acknowledged"]
    with pytest.raises(HTTPException) as exc:
        rewards.claim_reward(uid, group)
    assert exc.value.status_code == 409


def test_rollback_export_import_and_account_cascade(
    visit_account: VisitAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, clock = visit_account
    daily.record_visit(uid)
    for _ in range(2):
        advance(clock)
        daily.record_visit(uid)
    archive = assemble_user_export(uid)
    assert len(archive["progress"]["daily_visits"]) == 3
    assert archive["progress"]["awards"][0]["origin"] == "live"
    with connect() as conn:
        second = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('second','x') RETURNING id"
        ).fetchone()["id"]
    restore_user_archive(second, archive)
    assert daily.get_daily_streak(second)["current_streak_days"] == 0
    assert not [a for a in rewards.daily_collection(second)["items"] if a["unlocked"]]
    assert not assemble_user_export(second)["progress"]["daily_visits"]
    group = archive["progress"]["reward_groups"][0]["id"]
    with pytest.raises(HTTPException):
        rewards.claim_reward(second, group)
    with pytest.raises(ForeignKeyViolation), connect() as conn:
        conn.execute(
            """INSERT INTO user_achievements(
               user_id,achievement_key,origin,earned_at,reward_group_id)
               VALUES (%s,'bad','live',%s,%s)""",
            (second, clock[0], group),
        )
    advance(clock)

    def fail(*args: Any, **kwargs: Any) -> Any:
        msg = "simulated award failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(daily, "award_rewards", fail)
    with pytest.raises(RuntimeError):
        daily.record_visit(uid)
    assert len(assemble_user_export(uid)["progress"]["daily_visits"]) == 3
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(1623,%s)", (uid,))
        conn.execute("DELETE FROM users WHERE id=%s", (uid,))
    with connect() as conn:
        for table in (
            "user_daily_visits",
            "user_daily_visit_state",
            "user_reward_groups",
            "user_achievements",
        ):
            assert (
                conn.execute(
                    f"SELECT count(*) AS n FROM {table} WHERE user_id=%s", (uid,)
                ).fetchone()["n"]
                == 0
            )
    init_db()
    init_db()


def test_legacy_and_unknown_rewards_keep_original_dates_and_metadata(
    visit_account: VisitAccount,
) -> None:
    uid, clock = visit_account
    with connect() as conn:
        for key in ("seven_day_streak", "retired?unknown"):
            conn.execute(
                """INSERT INTO user_achievements(user_id,achievement_key,unlocked_at,metadata)
                VALUES (%s,%s,%s,%s)""",
                (uid, key, clock[0], Jsonb({"original": True})),
            )
    items = {a["key"]: a for a in rewards.daily_collection(uid)["items"]}
    assert items["seven_day_streak"]["title"] == "Legacy reading streak (7 days)"
    unknown = items["retired?unknown"]
    assert unknown["metadata"] == {"original": True}
    assert unknown["recorded_at"] == clock[0].isoformat()
    assert unknown["earned_at"] is None
    assert unknown["origin"] == "legacy"
    assert "retired%3Funknown" in unknown["href"]


def test_waiting_lock_samples_clock_after_midnight(
    visit_account: VisitAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, clock = visit_account
    clock[0] = datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone.utc)
    daily.record_visit(uid)
    waiting = Event()
    original = daily.lock_account

    def lock(conn: Any, user_id: int) -> dict[str, Any]:
        waiting.set()
        return original(conn, user_id)

    monkeypatch.setattr(daily, "lock_account", lock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(1623,%s)", (uid,))
            future = pool.submit(daily.record_visit, uid)
            assert waiting.wait(5)
            clock[0] += timedelta(seconds=1)
        result = future.result(timeout=5)
    assert result["local_date"] == "2026-01-02"
    assert result["current_streak_days"] == 2
    assert daily.claim_presentation(uid, date(2026, 1, 1))["reason"] == "stale_visit"
    assert daily.claim_presentation(uid, date(2026, 1, 2))["show"]


def test_preference_disable_races_claim_without_replay(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    daily.record_visit(uid)
    barrier = Barrier(2)

    def disable() -> dict[str, Any]:
        barrier.wait()
        return daily.save_preferences(
            uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=False)
        )

    def claim() -> dict[str, Any]:
        barrier.wait()
        return daily.claim_presentation(uid, clock[0].date())

    with ThreadPoolExecutor(max_workers=2) as pool:
        disabled = pool.submit(disable)
        claimed = pool.submit(claim)
        assert disabled.result()["daily_welcome_enabled"] is False
        assert claimed.result()["reason"] in ("claimed", "disabled")
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=True))
    assert not daily.claim_presentation(uid, clock[0].date())["show"]


def test_invalid_archive_preferences_roll_back_and_explicit_utc_wins(
    visit_account: VisitAccount,
) -> None:
    from news_dashboard.import_export import ArchiveImportError

    uid, _ = visit_account
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(progress_timezone="UTC"))
    with connect() as conn:
        conn.execute("UPDATE users SET briefing_timezone='Asia/Tokyo' WHERE id=%s", (uid,))
    assert daily.record_visit(uid)["timezone"] == "UTC"
    archive = assemble_user_export(uid)
    archive["preferences"]["progress"]["daily_welcome_enabled"] = "yes"
    with pytest.raises(ArchiveImportError):
        restore_user_archive(uid, archive)
    assert daily.get_preferences(uid)["daily_welcome_enabled"]


def test_api_real_auth_validation_guest_and_isolation(visit_account: VisitAccount) -> None:
    uid, _ = visit_account
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.post("/api/users/me/daily-visit", json={}).status_code == 401
        app.dependency_overrides[require_auth] = lambda: {"id": uid}
        assert (
            client.post("/api/users/me/daily-visit", json={"date": "2000-01-01"}).status_code == 422
        )
        assert client.post("/api/users/me/daily-visit", json={}).json()["current_streak_days"] == 1
        assert (
            client.patch(
                "/api/users/me/progress-preferences", json={"progress_timezone": "invalid"}
            ).status_code
            == 422
        )
        assert client.post("/api/users/me/presentation/claim", json={}).status_code == 422
        with connect() as conn:
            conn.execute("UPDATE users SET is_guest=TRUE WHERE id=%s", (uid,))
        assert client.post("/api/users/me/daily-visit", json={}).status_code == 403
        assert client.get("/api/users/me/daily-streak").json() == {"available": False}
