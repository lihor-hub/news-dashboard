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


def test_pending_discovery_is_bounded_owned_read_only_and_history_typed(
    visit_account: VisitAccount,
) -> None:
    uid, clock = visit_account
    live = [uuid4() for _ in range(23)]
    intro = uuid4()
    with connect() as conn:
        for index, group in enumerate(live):
            conn.execute(
                """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at)
                   VALUES (%s,%s,%s,'live',%s)""",
                (group, uid, f"fixture:{index}", clock[0] + timedelta(seconds=index)),
            )
        conn.execute(
            """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at,summary)
               VALUES (%s,%s,'fixture:intro','historical_intro',%s,%s)""",
            (intro, uid, clock[0], Jsonb({"credited_reads": 42})),
        )
    first = rewards.daily_collection(uid)
    assert first == rewards.daily_collection(uid)
    assert first["pending_reward_group_ids"] == [str(group) for group in live[:20]]
    assert first["historical_group_id"] == str(intro)
    assert not daily.claim_presentation(uid, None, intro)["show"]  # Welcome is enabled.
    with pytest.raises(HTTPException) as exc:
        rewards.claim_reward(uid, intro)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        rewards.claim_reward(uid, live[0], acknowledge=True)
    assert exc.value.status_code == 409
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=False))
    won = daily.claim_presentation(uid, None, intro)
    assert won["authorization"] == {"welcome": False, "history": True, "rewards": False}
    assert not daily.claim_presentation(uid, None, intro)["show"]
    assert rewards.daily_collection(uid)["historical_group_id"] is None


def test_two_device_live_claim_lost_response_ack_and_rollback(
    visit_account: VisitAccount,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid, clock = visit_account
    ids = []
    for index, target in enumerate((3, 7)):
        with connect() as conn:
            daily.lock_account(conn, uid)
            result = rewards.award_rewards(
                conn,
                uid,
                cause_key=f"fixture:{index}",
                origin="live",
                earned_at=clock[0],
                candidates=[
                    {
                        "key": f"daily_streak_{target}",
                        "criteria_version": 1,
                        "progress": target,
                        "target": target,
                    }
                ],
            )
            ids.append(result["reward_group_id"])
    barrier = Barrier(2)

    def claim() -> dict[str, Any]:
        barrier.wait()
        return rewards.claim_reward(uid, ids[0])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        assert sum(f.result()["show"] for f in futures) == 1
    assert not rewards.claim_reward(uid, ids[0])["show"]  # Lost winning response.
    assert rewards.daily_collection(uid)["pending_reward_group_ids"] == [ids[1]]
    assert rewards.claim_reward(uid, ids[0], acknowledge=True)["acknowledged"]
    assert rewards.claim_reward(uid, ids[0], acknowledge=True)["acknowledged"]
    original = rewards.descriptor

    def fail(row: Any) -> Any:
        msg = "Serialization failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(rewards, "descriptor", fail)
    with pytest.raises(RuntimeError):
        rewards.claim_reward(uid, ids[1])
    monkeypatch.setattr(rewards, "descriptor", original)
    assert rewards.claim_reward(uid, ids[1])["show"]
    assert len([item for item in rewards.daily_collection(uid)["items"] if item["unlocked"]]) == 2


def test_welcome_one_previous_seven_saved_dates_summary_is_not_toast_authority(
    visit_account: VisitAccount,
) -> None:
    uid, clock = visit_account
    clock[0] = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    with connect() as conn:
        daily.lock_account(conn, uid)
        group = rewards.award_rewards(
            conn,
            uid,
            cause_key="fixture:recent",
            origin="live",
            earned_at=clock[0] - timedelta(days=7),
            candidates=[
                {"key": "topic_python_10", "criteria_version": 1, "progress": 10, "target": 10},
                {"key": "articles_read_10", "criteria_version": 1, "progress": 10, "target": 10},
            ],
        )["reward_group_id"]
        rewards.award_rewards(
            conn,
            uid,
            cause_key="fixture:today",
            origin="live",
            earned_at=clock[0],
            candidates=[
                {"key": "daily_streak_3", "criteria_version": 1, "progress": 3, "target": 3}
            ],
        )
    daily.record_visit(uid)
    receipt = daily.claim_presentation(uid, clock[0].date())
    assert receipt["welcome"]["recent_reward"]["key"] == "topic_python_10"
    assert receipt["authorization"]["rewards"] is False
    assert rewards.claim_reward(uid, group)["show"]  # Summary never consumes the live group.
    clock[0] += timedelta(days=1)
    daily.record_visit(uid)
    next_day = daily.claim_presentation(uid, clock[0].date())
    assert next_day["welcome"]["recent_reward"]["key"] == "daily_streak_3"


@pytest.mark.parametrize("welcome", [True, False])
@pytest.mark.parametrize("animations", [True, False])
def test_presentation_preferences_independent_and_leave_records(
    visit_account: VisitAccount,
    welcome: bool,
    animations: bool,
) -> None:
    uid, _ = visit_account
    daily.record_visit(uid)
    daily.save_preferences(uid, daily.ProgressPreferencesPatch(daily_welcome_enabled=welcome))
    daily.save_preferences(
        uid, daily.ProgressPreferencesPatch(reward_animations_enabled=animations)
    )
    result = daily.get_preferences(uid)
    assert result["daily_welcome_enabled"] is welcome
    assert result["reward_animations_enabled"] is animations
    assert daily.get_daily_streak(uid)["current_streak_days"] == 1


@pytest.mark.parametrize(
    "value", [True, 1767225600, "2026-01-01T00:00:00Z", "2026-W01-1", "20260101"]
)
def test_presentation_targets_are_exact_calendar_strings(value: Any) -> None:
    from news_dashboard.reading_progress.router import PresentationClaim, WelcomeClaim

    for model in (PresentationClaim, WelcomeClaim):
        with pytest.raises(ValidationError):
            model.model_validate({"expected_visit_date": value})


def test_invalid_history_bundle_rolls_back_both_targets(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    group = uuid4()
    daily.record_visit(uid)
    with connect() as conn:
        conn.execute(
            """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at,summary)
            VALUES (%s,%s,'fixture:invalid','historical_intro',%s,%s)""",
            (group, uid, clock[0], Jsonb({"credited_reads": 42, "url": "private-unexpected"})),
        )
    with pytest.raises(HTTPException) as exc:
        daily.claim_presentation(uid, clock[0].date(), group)
    assert exc.value.status_code == 409
    assert daily.get_daily_streak(uid)["welcome_target"] is not None
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT claimed_at FROM user_reward_groups WHERE id=%s", (group,)
            ).fetchone()["claimed_at"]
            is None
        )


def test_two_device_atomic_bundle_and_independent_patch_races(visit_account: VisitAccount) -> None:
    uid, clock = visit_account
    group = uuid4()
    daily.record_visit(uid)
    with connect() as conn:
        conn.execute(
            """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at,summary)
            VALUES (%s,%s,'fixture:race','historical_intro',%s,%s)""",
            (group, uid, clock[0], Jsonb({"credited_reads": 42})),
        )
    barrier = Barrier(2)

    def bundle() -> dict[str, Any]:
        barrier.wait()
        return daily.claim_presentation(uid, clock[0].date(), group)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(bundle) for _ in range(2)]
        receipts = [future.result() for future in futures]
    assert sum(r["authorization"]["welcome"] for r in receipts) == 1
    assert sum(r["authorization"]["history"] for r in receipts) == 1
    assert any(r["authorization"]["welcome"] and r["authorization"]["history"] for r in receipts)
    barrier = Barrier(2)

    def patch(key: str) -> None:
        barrier.wait()
        daily.save_preferences(uid, daily.ProgressPreferencesPatch.model_validate({key: False}))

    with ThreadPoolExecutor(max_workers=2) as pool:
        patch_futures = [
            pool.submit(patch, key)
            for key in ("daily_welcome_enabled", "reward_animations_enabled")
        ]
        for future in patch_futures:
            future.result()
    saved = daily.get_preferences(uid)
    assert saved["daily_welcome_enabled"] is False
    assert saved["reward_animations_enabled"] is False
