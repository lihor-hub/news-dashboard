"""PostgreSQL contract tests for scheduled briefing email delivery claims."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier

import psycopg
import pytest

from news_dashboard.auth import create_user
from news_dashboard.briefing_email.service import (
    DeliveryClaimLostError,
    _acquire_delivery,
    _transition_delivery,
    claim_delivery,
    deliver_daily_briefing,
)
from news_dashboard.db import connect


def _make_user(database_url: str, username: str) -> int:
    return int(create_user(username, "password123", db_path=database_url)["id"])


def _seed_complete_briefing(database_url: str, user_id: int, until_at: datetime) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(user_id, since_at, until_at, status, title, summary, content)
            VALUES (%s, %s, %s, 'complete', 'Daily', 'Summary', %s::jsonb)
            RETURNING id
            """,
            (
                user_id,
                until_at - timedelta(hours=24),
                until_at,
                '{"title":"Daily","summary":"Summary","sections":[],"worth_opening":[]}',
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


@pytest.mark.postgres
def test_briefing_email_opt_in_defaults_false(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_default")

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT briefing_email_enabled FROM users WHERE id = %s", (user_id,)
        ).fetchone()

    assert row is not None
    assert row["briefing_email_enabled"] is False


@pytest.mark.postgres
def test_delivery_local_date_is_unique(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_unique")
    delivery_date = date(2026, 7, 17)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO briefing_email_deliveries(user_id, local_delivery_date) VALUES (%s, %s)",
            (user_id, delivery_date),
        )

    with connect(database_url=pg_clean) as conn, pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO briefing_email_deliveries(user_id, local_delivery_date) VALUES (%s, %s)",
            (user_id, delivery_date),
        )


@pytest.mark.postgres
def test_delivery_status_rejects_unknown_value(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_status")

    with connect(database_url=pg_clean) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO briefing_email_deliveries(user_id, local_delivery_date, status)
            VALUES (%s, %s, 'unknown')
            """,
            (user_id, date(2026, 7, 17)),
        )


@pytest.mark.postgres
def test_claim_delivery_returns_once_for_local_date(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_claim")

    first = claim_delivery(user_id, date(2026, 7, 17), database_url=pg_clean)
    repeated = claim_delivery(user_id, date(2026, 7, 17), database_url=pg_clean)

    assert first is not None
    assert first.status == "claimed"
    assert repeated is None


@pytest.mark.postgres
def test_concurrent_delivery_claim_has_one_winner(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_concurrent_claim")
    delivery_date = date(2026, 7, 17)
    barrier = Barrier(2)

    def claim() -> object:
        barrier.wait()
        return claim_delivery(user_id, delivery_date, database_url=pg_clean)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: claim(), range(2)))

    assert sum(outcome is not None for outcome in outcomes) == 1


@pytest.mark.postgres
def test_reclaimed_delivery_fences_stale_worker_transition(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_fenced")
    delivery_date = date(2026, 7, 17)
    old_worker = claim_delivery(user_id, delivery_date, database_url=pg_clean)
    assert old_worker is not None
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE briefing_email_deliveries SET claimed_at = %s WHERE id = %s",
            (now - timedelta(hours=1), old_worker.id),
        )

    new_worker = _acquire_delivery(user_id, delivery_date, now, pg_clean)
    assert new_worker is not None
    assert new_worker.claim_token != old_worker.claim_token

    with pytest.raises(DeliveryClaimLostError):
        _transition_delivery(
            old_worker,
            "rendered",
            expected_status="claimed",
            database_url=pg_clean,
            now=now,
        )

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT status FROM briefing_email_deliveries WHERE id = %s", (old_worker.id,)
        ).fetchone()
    assert row is not None
    assert row["status"] == "claimed"


@pytest.mark.postgres
def test_stale_sending_delivery_is_never_reclaimed(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_sending")
    delivery_date = date(2026, 7, 17)
    delivery = claim_delivery(user_id, delivery_date, database_url=pg_clean)
    assert delivery is not None
    old = datetime(2026, 7, 17, 16, 0, tzinfo=timezone.utc)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE briefing_email_deliveries SET status = 'sending', claimed_at = %s"
            " WHERE id = %s",
            (old, delivery.id),
        )

    recovered = _acquire_delivery(user_id, delivery_date, old + timedelta(hours=2), pg_clean)

    assert recovered is None


@pytest.mark.postgres
def test_preparation_failure_is_sanitized_and_retryable(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_prepare")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    _seed_complete_briefing(pg_clean, user_id, now)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE users SET email = %s, briefing_email_enabled = TRUE WHERE id = %s",
            ("reader@example.com", user_id),
        )

    def fail_token(_user_id: int) -> str:
        msg = "secret provider details"
        raise RuntimeError(msg)

    monkeypatch.setattr("news_dashboard.briefing_email.service.make_unsubscribe_token", fail_token)
    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.status == "retryable_failed"
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT status, error_code, error_message FROM briefing_email_deliveries WHERE id = %s",
            (outcome.delivery.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "retryable_failed"
    assert row["error_code"] == "preparation_failed"
    assert row["error_message"] == "preparation_failed"


@pytest.mark.postgres
def test_pre_send_configuration_failure_does_not_leave_rendered(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_pre_send")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    _seed_complete_briefing(pg_clean, user_id, now)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE users SET email = %s, briefing_email_enabled = TRUE WHERE id = %s",
            ("reader@example.com", user_id),
        )

    def fail_configuration() -> bool:
        msg = "configuration backend failed"
        raise RuntimeError(msg)

    monkeypatch.setattr("news_dashboard.briefing_email.service.smtp_configured", fail_configuration)
    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.status == "retryable_failed"
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT status, error_code FROM briefing_email_deliveries WHERE id = %s",
            (outcome.delivery.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "retryable_failed"
    assert row["error_code"] == "pre_send_check_failed"


@pytest.mark.postgres
def test_due_retry_rechecks_opt_out_before_sending(pg_clean: str) -> None:
    user_id = _make_user(pg_clean, "email_optout_retry")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    briefing_id = _seed_complete_briefing(pg_clean, user_id, now)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO briefing_email_deliveries(
                user_id, briefing_id, local_delivery_date, status, next_attempt_at
            ) VALUES (%s, %s, %s, 'retryable_failed', %s)
            """,
            (user_id, briefing_id, now.date(), now - timedelta(minutes=1)),
        )

    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.status == "unsubscribed"


@pytest.mark.postgres
def test_delivery_reuses_current_local_day_complete_briefing(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_reuse")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    briefing_id = _seed_complete_briefing(pg_clean, user_id, now)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE users SET email = %s, briefing_email_enabled = TRUE WHERE id = %s",
            ("reader@example.com", user_id),
        )

    def unexpected_generation(**_kwargs: object) -> dict[str, object]:
        msg = "canonical briefing should have been reused"
        raise AssertionError(msg)

    monkeypatch.setattr("news_dashboard.briefings.service.generate_briefing", unexpected_generation)
    monkeypatch.setattr("news_dashboard.briefing_email.service.smtp_configured", lambda: False)
    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.delivery.briefing_id == briefing_id
    assert outcome.status == "permanent_failed"


@pytest.mark.postgres
def test_bucharest_repeated_dst_wall_time_keeps_one_local_date_claim(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_dst_repeat")
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE users SET briefing_timezone = 'Europe/Bucharest' WHERE id = %s",
            (user_id,),
        )
    monkeypatch.setattr(
        "news_dashboard.briefings.service.generate_briefing",
        lambda **_kwargs: {"status": "no_candidates"},
    )
    first_wall_time = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    repeated_wall_time = datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)

    first = deliver_daily_briefing(user_id, now=first_wall_time, database_url=pg_clean)
    repeated = deliver_daily_briefing(user_id, now=repeated_wall_time, database_url=pg_clean)

    assert first.delivery.id == repeated.delivery.id
    assert first.delivery.local_delivery_date == date(2026, 10, 25)
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT count(*) AS count FROM briefing_email_deliveries WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    assert row is not None
    assert row["count"] == 1


def _enable_email(database_url: str, user_id: int) -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE users SET email = %s, briefing_email_enabled = TRUE WHERE id = %s",
            ("reader@example.com", user_id),
        )


@pytest.mark.postgres
def test_smtp_success_persists_full_delivery_transition(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_smtp_success")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    briefing_id = _seed_complete_briefing(pg_clean, user_id, now)
    _enable_email(pg_clean, user_id)
    monkeypatch.setattr("news_dashboard.briefing_email.service.smtp_configured", lambda: True)
    monkeypatch.setattr("news_dashboard.briefing_email.service.send_email", lambda **_kwargs: None)

    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.status == "sent"
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            """
            SELECT status, briefing_id, attempt_count, sent_at, next_attempt_at, error_code
            FROM briefing_email_deliveries WHERE id = %s
            """,
            (outcome.delivery.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "sent"
    assert row["briefing_id"] == briefing_id
    assert row["attempt_count"] == 1
    assert row["sent_at"] == now
    assert row["next_attempt_at"] is None
    assert row["error_code"] is None


@pytest.mark.postgres
def test_retryable_smtp_failure_persists_due_retry(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_smtp_retry")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    _seed_complete_briefing(pg_clean, user_id, now)
    _enable_email(pg_clean, user_id)
    monkeypatch.setattr("news_dashboard.briefing_email.service.smtp_configured", lambda: True)
    monkeypatch.setattr(
        "news_dashboard.briefing_email.service.send_email", lambda **_kwargs: "smtp_error"
    )

    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.status == "retryable_failed"
    assert outcome.delivery.attempt_count == 1
    assert outcome.delivery.next_attempt_at == now + timedelta(minutes=15)
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT status, error_code, error_message, sent_at FROM briefing_email_deliveries"
            " WHERE id = %s",
            (outcome.delivery.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "retryable_failed"
    assert row["error_code"] == "smtp_error"
    assert row["error_message"] == "smtp_error"
    assert row["sent_at"] is None


@pytest.mark.postgres
def test_nonretryable_transport_failure_is_permanent_and_sanitized(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_smtp_permanent")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    _seed_complete_briefing(pg_clean, user_id, now)
    _enable_email(pg_clean, user_id)
    monkeypatch.setattr("news_dashboard.briefing_email.service.smtp_configured", lambda: True)
    monkeypatch.setattr(
        "news_dashboard.briefing_email.service.send_email",
        lambda **_kwargs: "smtp_not_configured",
    )

    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert outcome.status == "permanent_failed"
    assert outcome.delivery.attempt_count == 1
    assert outcome.delivery.next_attempt_at is None
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT error_code, error_message FROM briefing_email_deliveries WHERE id = %s",
            (outcome.delivery.id,),
        ).fetchone()
    assert row is not None
    assert row["error_code"] == "smtp_not_configured"
    assert row["error_message"] == "smtp_not_configured"


@pytest.mark.postgres
def test_delivery_claim_exists_before_generation_and_no_candidates_persists_skipped(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean, "email_claim_before_generation")
    now = datetime(2026, 7, 17, 18, 0, tzinfo=timezone.utc)
    observed: dict[str, object] = {}

    def generate(**_kwargs: object) -> dict[str, object]:
        with connect(database_url=pg_clean) as conn:
            row = conn.execute(
                "SELECT status FROM briefing_email_deliveries WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        observed["status_during_generation"] = row["status"] if row is not None else None
        return {"status": "no_candidates"}

    monkeypatch.setattr("news_dashboard.briefings.service.generate_briefing", generate)
    outcome = deliver_daily_briefing(user_id, now=now, database_url=pg_clean)

    assert observed["status_during_generation"] == "claimed"
    assert outcome.status == "skipped"
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT status FROM briefing_email_deliveries WHERE id = %s",
            (outcome.delivery.id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "skipped"
