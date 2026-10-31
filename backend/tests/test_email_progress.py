"""Personal mail selection, binding and multipart contracts (no external sends)."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from news_dashboard.auth import create_user
from news_dashboard.briefing_email import progress, service
from news_dashboard.briefing_email.rendering import render_briefing_email
from news_dashboard.db import connect
from news_dashboard.reading_progress.daily import lock_account
from news_dashboard.reading_progress.rewards import award_rewards, reward_catalog

NOW = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
MAIL = "reader@example.test"
BASE = "https://news.example"
BOUNDS = {"since_at": NOW - timedelta(days=1), "until_at": NOW}


@pytest.fixture
def reader(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(service, "_preview_sent_at", OrderedDict())
    user = create_user("email-progress", "password123", db_path=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """UPDATE users SET email=%s, progress_timezone='America/New_York',
               briefing_email_enabled=true WHERE id=%s""",
            (MAIL, user["id"]),
        )
    return int(user["id"])


def earn(
    database: str,
    user: int,
    key: str,
    at: datetime = NOW - timedelta(hours=1),
    origin: str = "live",
) -> None:
    with connect(database_url=database) as conn:
        lock_account(conn, user)
        target = reward_catalog()[key][0]
        award_rewards(
            conn,
            user,
            cause_key=key,
            origin=origin,
            earned_at=at if origin == "live" else None,
            candidates=[{"key": key, "criteria_version": 1, "progress": target, "target": target}],
        )


def select(database: str, user: int, **kwargs: Any) -> dict[str, Any] | None:
    return progress.select_progress(
        user, recipient=MAIL, base_url=BASE, now=NOW, database_url=database, **kwargs
    )


def seed_briefing(database: str, user: int) -> dict[str, Any]:
    with connect(database_url=database) as conn:
        row = conn.execute(
            """INSERT INTO briefings(user_id,since_at,until_at,status,title,summary,content)
               VALUES (%s,%s,%s,'complete','Daily','News summary',
                       '{"sections":[]}'::jsonb) RETURNING *""",
            (user, BOUNDS["since_at"], BOUNDS["until_at"]),
        ).fetchone()
    return dict(row)


@pytest.mark.postgres
def test_bounded_deterministic_highest_topic_and_live_only(pg_clean: str, reader: int) -> None:
    earn(pg_clean, reader, "articles_read_1", BOUNDS["since_at"])
    earn(pg_clean, reader, "topic_python_1", NOW - timedelta(hours=1))
    earn(pg_clean, reader, "topic_python_10", NOW - timedelta(hours=2))
    earn(pg_clean, reader, "topic_ruby_1", NOW - timedelta(hours=3))
    earn(pg_clean, reader, "daily_streak_3", NOW)  # Exclusive end.
    earn(pg_clean, reader, "articles_read_10", origin="import")
    earn(pg_clean, reader, "articles_read_50", origin="historical")
    payload = select(pg_clean, reader, briefing=BOUNDS)
    assert payload is not None
    assert payload["titles"] == ["Python · Enthusiast", "Ruby · Explorer"]
    assert payload["streak"] is None
    assert payload["href"] == BASE + "/reading-dna#progress"
    assert "-0500" in payload["period"]
    assert "email" not in payload
    assert "user_id" not in payload


@pytest.mark.postgres
@pytest.mark.parametrize("origin", ["historical", "import", "legacy"])
def test_nonlive_is_not_recent_even_when_recorded_now(
    pg_clean: str, reader: int, origin: str
) -> None:
    earn(pg_clean, reader, "articles_read_1", origin=origin)
    assert select(pg_clean, reader, briefing=BOUNDS) is None


@pytest.mark.postgres
def test_inclusive_start_future_omitted_and_unknown_not_emailed(pg_clean: str, reader: int) -> None:
    earn(pg_clean, reader, "articles_read_1", BOUNDS["since_at"])
    earn(pg_clean, reader, "articles_read_10", NOW + timedelta(seconds=1))
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_achievements(user_id,achievement_key) VALUES (%s,'unknown')",
            (reader,),
        )
    payload = select(pg_clean, reader, briefing=BOUNDS)
    assert payload is not None
    assert payload["titles"] == ["1 articles read"]


@pytest.mark.postgres
@pytest.mark.parametrize(
    "bounds",
    [
        {},
        {"since_at": "bad", "until_at": NOW},
        {"since_at": NOW.replace(tzinfo=None), "until_at": NOW},
        {"since_at": NOW, "until_at": NOW},
        {"since_at": NOW, "until_at": NOW + timedelta(days=1)},
    ],
)
def test_uncertain_or_future_period_omits(
    pg_clean: str, reader: int, bounds: dict[str, Any]
) -> None:
    earn(pg_clean, reader, "articles_read_1")
    assert select(pg_clean, reader, briefing=bounds) is None


@pytest.mark.postgres
@pytest.mark.parametrize(
    ("days", "age", "visible"),
    [
        (0, 0, False),
        (1, 0, False),
        (2, 0, False),
        (3, 0, True),
        (4, 1, True),
        (8, 2, False),
        (8, -1, False),
    ],
)
def test_streak_is_current_send_time_not_best_or_legacy(
    pg_clean: str,
    reader: int,
    days: int,
    age: int,
    visible: bool,
) -> None:
    if days:
        with connect(database_url=pg_clean) as conn:
            conn.execute(
                """INSERT INTO user_daily_visit_state(
                     user_id,last_credited_date,current_streak_days,
                     best_streak_days,next_credit_at) VALUES (%s,%s,%s,100,%s)""",
                (reader, NOW.date() - timedelta(days=age), days, NOW + timedelta(hours=12)),
            )
    payload = select(pg_clean, reader, briefing=BOUNDS)
    assert bool(payload) is visible
    if payload:
        assert f"{days}-day daily streak" in payload["streak"]
        assert "At preparation for sending on 2026-01-15 07:00 -0500" in payload["streak"]


@pytest.mark.postgres
@pytest.mark.parametrize(
    ("zone", "offset"), [("America/New_York", "-0400"), ("Europe/Bucharest", "+0300")]
)
def test_legacy_is_trailing_24h_not_dst_calendar_day(
    pg_clean: str,
    reader: int,
    zone: str,
    offset: str,
) -> None:
    instant = datetime(2026, 3, 29, 12, tzinfo=timezone.utc)
    with connect(database_url=pg_clean) as conn:
        conn.execute("UPDATE users SET progress_timezone=%s WHERE id=%s", (zone, reader))
    earn(pg_clean, reader, "articles_read_1", instant - timedelta(hours=24))
    payload = progress.select_progress(
        reader, recipient=MAIL, base_url=BASE, now=instant, database_url=pg_clean
    )
    assert payload
    assert offset in payload["period"]
    assert payload["titles"] == ["1 articles read"]


@pytest.mark.postgres
@pytest.mark.parametrize("change", ["guest", "duplicate", "case_collision", "email", "deleted"])
def test_binding_omits_wrong_guest_ambiguous_changed_or_deleted(
    pg_clean: str,
    reader: int,
    change: str,
) -> None:
    earn(pg_clean, reader, "articles_read_1")
    with connect(database_url=pg_clean) as conn:
        if change == "guest":
            conn.execute("UPDATE users SET is_guest=true WHERE id=%s", (reader,))
        elif change in {"duplicate", "case_collision"}:
            conn.execute(
                "INSERT INTO users(username,password_hash,email) VALUES ('other','x',%s)",
                (MAIL if change == "duplicate" else MAIL.upper(),),
            )
        elif change == "email":
            conn.execute("UPDATE users SET email='other@example.test' WHERE id=%s", (reader,))
        else:
            conn.execute("DELETE FROM users WHERE id=%s", (reader,))
    assert select(pg_clean, reader) is None


@pytest.mark.parametrize(
    "value", ["", "a@example.test,b@example.test", "a@example.test\r\nBcc:x@y", "bad", "a@@b"]
)
def test_mailbox_rejects_ambiguity(value: str) -> None:
    assert progress.mailbox(value) is None


def test_mailbox_preserves_local_case_and_normalizes_domain() -> None:
    assert progress.mailbox("Reader <Reader@EXAMPLE.test>") == "Reader@example.test"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "//evil/reading-dna#progress",
        "https://user:pass@news.example/reading-dna#progress",
        "https://news.example/other#progress",
        "https://news.example/reading-dna?user=1#progress",
        "https://news.example:bad/reading-dna#progress",
    ],
)
def test_unsafe_url_omits_section(url: str) -> None:
    assert progress.render_progress({"href": url}, html=True) == ""


def test_both_renderers_share_escaped_accessible_section() -> None:
    from news_dashboard import digest

    payload = {
        "titles": ['Python <script> & "test"'],
        "period": "Period <start>",
        "streak": None,
        "href": BASE + "/reading-dna#progress",
    }
    rendered = render_briefing_email(
        {"title": "Daily", "summary": "Summary"},
        progress=payload,
        local_date=date(2026, 1, 15),
        timezone_name="UTC",
        briefing_url=BASE,
        preferences_url=BASE,
        unsubscribe_url=BASE,
    )
    for html in [rendered.html_body, digest._render_html([], user_id=1, progress=payload)]:
        assert "Your progress" in html
        assert "View my progress" in html
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert 'aria-labelledby="email-progress-heading"' in html
    for text in [rendered.text_body, digest._render_text([], user_id=1, progress=payload)]:
        assert 'Python <script> & "test"' in text
        assert "&lt;" not in text
    assert "Python" not in rendered.subject
    assert rendered.html_body.index("Summary") < rendered.html_body.index("Your progress")


@pytest.mark.postgres
@pytest.mark.parametrize("mode", ["scheduled", "preview", "legacy"])
@pytest.mark.parametrize("final_check_timeout", [False, True])
def test_real_selection_once_both_mime_readonly_existing_send(
    pg_clean: str,
    reader: int,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    final_check_timeout: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from news_dashboard import digest

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("APP_BASE_URL", BASE)
    monkeypatch.setenv("TOKEN_SECRET", "email-progress-test-secret")
    monkeypatch.setenv("DIGEST_TO", MAIL)
    monkeypatch.setenv("DIGEST_USER_ID", str(reader))
    briefing = seed_briefing(pg_clean, reader)
    earn(pg_clean, reader, "topic_python_1")
    actual = progress.select_progress

    failed_checks = Mock()

    def timeout(conn: Any, *_: Any) -> bool:
        failed_checks()
        conn.execute("SET LOCAL statement_timeout = '1ms'")
        conn.execute("SELECT pg_sleep(0.05) /* private-topic-secret */")
        pytest.fail("Expected a real PostgreSQL statement timeout")

    def fixed_clock(*args: Any, **kwargs: Any) -> Any:
        kwargs["now"] = NOW
        payload = actual(*args, **kwargs)
        assert payload
        if final_check_timeout:
            # Selection succeeds; only the final optional ownership query times out.
            monkeypatch.setattr(progress, "recipient_matches", timeout)
        return payload

    selected = Mock(side_effect=fixed_clock)
    monkeypatch.setattr(service, "select_progress", selected)
    monkeypatch.setattr(digest, "select_progress", selected)
    monkeypatch.setattr(service, "_safe_email_enrichment", lambda *_: None)
    sent = Mock(return_value=None)
    monkeypatch.setattr(service, "send_email", sent)
    monkeypatch.setattr(service, "smtp_configured", lambda: True)
    monkeypatch.setattr(digest, "_send_email", sent)
    monkeypatch.setattr(
        digest, "_get_top_new_articles", lambda *_, **__: [{"id": 1, "title": "News"}]
    )
    if mode == "scheduled":
        assert (
            service.deliver_daily_briefing(reader, now=NOW, database_url=pg_clean).status == "sent"
        )
    elif mode == "preview":
        assert service.send_preview(reader, database_url=pg_clean)
    else:
        assert digest.send_digest()
    assert selected.call_count == 1
    assert sent.call_count == 1
    if mode == "legacy":
        _, html, text = sent.call_args.args
    else:
        html, text = sent.call_args.kwargs["html_body"], sent.call_args.kwargs["text_body"]
    for body in (html, text):
        assert ("Python · Explorer" in body) is not final_check_timeout
        assert ("Your progress" in body) is not final_check_timeout
        assert "News" in body
    if final_check_timeout:
        failed_checks.assert_called_once()
        assert "Email progress unavailable; omitted" in caplog.text
        assert "private-topic-secret" not in caplog.text
        assert MAIL not in caplog.text
        assert "Python" not in caplog.text
    else:
        assert str(briefing["since_at"].date()) in text
    if mode == "scheduled":
        with connect(database_url=pg_clean) as conn:
            delivery = conn.execute(
                "SELECT status, next_attempt_at FROM briefing_email_deliveries WHERE user_id=%s",
                (reader,),
            ).fetchone()
            assert delivery["status"] == "sent"
            assert delivery["next_attempt_at"] is None
        assert (
            service.deliver_daily_briefing(
                reader, now=NOW + timedelta(hours=2), database_url=pg_clean
            ).status
            == "sent"
        )
        assert sent.call_count == 1
        assert selected.call_count == 1
    with connect(database_url=pg_clean) as conn:
        for table in ("user_daily_visits", "user_activity_days", "user_read_credits"):
            assert (
                conn.execute(
                    f"SELECT count(*) AS n FROM {table} WHERE user_id=%s", (reader,)
                ).fetchone()["n"]
                == 0
            )
        assert (
            conn.execute(
                "SELECT claimed_at FROM user_reward_groups WHERE user_id=%s", (reader,)
            ).fetchone()["claimed_at"]
            is None
        )


@pytest.mark.postgres
@pytest.mark.parametrize("mode", ["scheduled", "preview", "legacy"])
@pytest.mark.parametrize("change", ["email", "guest", "duplicate", "optout"])
def test_delivery_rechecks_binding_and_consent_races(
    pg_clean: str,
    reader: int,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    change: str,
) -> None:
    from news_dashboard import digest

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("APP_BASE_URL", BASE)
    monkeypatch.setenv("TOKEN_SECRET", "email-progress-test-secret")
    monkeypatch.setenv("DIGEST_TO", MAIL)
    monkeypatch.setenv("DIGEST_USER_ID", str(reader))
    seed_briefing(pg_clean, reader)
    earn(pg_clean, reader, "topic_python_1")
    monkeypatch.setattr(service, "_safe_email_enrichment", lambda *_: None)
    monkeypatch.setattr(service, "smtp_configured", lambda: True)
    monkeypatch.setattr(digest, "_get_top_new_articles", lambda *_, **__: [{"id": 1}])
    sent = Mock(return_value=None)
    monkeypatch.setattr(service, "send_email", sent)
    monkeypatch.setattr(digest, "_send_email", sent)
    real = progress.select_progress

    def selecting(*args: Any, **kwargs: Any) -> Any:
        kwargs["now"] = NOW
        result = real(*args, **kwargs)
        assert result
        with connect(database_url=pg_clean) as conn:
            if change == "email":
                conn.execute("UPDATE users SET email='new@example.test' WHERE id=%s", (reader,))
            elif change == "guest":
                conn.execute("UPDATE users SET is_guest=true WHERE id=%s", (reader,))
            elif change == "optout":
                conn.execute("UPDATE users SET briefing_email_enabled=false WHERE id=%s", (reader,))
            else:
                conn.execute(
                    """INSERT INTO users(username,password_hash,email)
                             VALUES ('collision','x',%s)""",
                    (MAIL.upper(),),
                )
        return result

    monkeypatch.setattr(service, "select_progress", selecting)
    monkeypatch.setattr(digest, "select_progress", selecting)
    if mode == "preview" and change in {"guest", "email"}:
        with pytest.raises(service.PreviewUnavailableError):
            service.send_preview(reader, database_url=pg_clean)
        sent.assert_not_called()
        return
    if mode == "scheduled":
        outcome = service.deliver_daily_briefing(reader, now=NOW, database_url=pg_clean)
        if change in {"guest", "optout"}:
            assert outcome.status == "unsubscribed"
            sent.assert_not_called()
            return
        assert outcome.status == "sent"
    elif mode == "preview":
        assert service.send_preview(reader, database_url=pg_clean)
    else:
        assert digest.send_digest()
    # Explicit previews and deployment-owned legacy digest do not inherit canonical opt-out.
    expected = change == "optout"
    if mode == "legacy":
        bodies = sent.call_args.args[1:]
    else:
        bodies = [sent.call_args.kwargs[key] for key in ("html_body", "text_body")]
    for body in bodies:
        assert ("Your progress" in body) is expected


@pytest.mark.postgres
def test_partial_live_without_group_and_other_owner_omitted(pg_clean: str, reader: int) -> None:
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """INSERT INTO user_achievements(user_id,achievement_key,origin,earned_at)
                      VALUES (%s,'articles_read_1','live',%s)""",
            (reader, NOW - timedelta(hours=1)),
        )
    other = create_user("other-owner", "password123", db_path=pg_clean)
    earn(pg_clean, other["id"], "topic_python_1")
    assert select(pg_clean, reader, briefing=BOUNDS) is None


@pytest.mark.postgres
def test_selector_failure_omits_without_private_logs(
    pg_clean: str,
    reader: int,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        msg = "private-topic-secret"
        raise RuntimeError(msg)

    monkeypatch.setattr(progress, "recipient_matches", unavailable)
    assert select(pg_clean, reader) is None
    assert "private-topic-secret" not in caplog.text
    assert "Email progress unavailable; omitted" in caplog.text


@pytest.mark.postgres
def test_empty_news_does_not_send_progress_campaign(
    pg_clean: str,
    reader: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import digest

    earn(pg_clean, reader, "topic_python_1")
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("DIGEST_TO", MAIL)
    monkeypatch.setenv("DIGEST_USER_ID", str(reader))
    monkeypatch.setattr(digest, "_get_top_new_articles", lambda *_, **__: [])
    sent = Mock(return_value=None)
    monkeypatch.setattr(digest, "_send_email", sent)
    monkeypatch.setattr(service, "send_email", sent)
    monkeypatch.setattr(service, "_find_local_day_briefing", lambda *_: None)
    monkeypatch.setattr(
        "news_dashboard.briefings.service.generate_briefing",
        lambda **_: {"status": "no_candidates"},
    )
    assert digest.send_digest() is False
    assert (
        service.deliver_daily_briefing(reader, now=NOW, database_url=pg_clean).status == "skipped"
    )
    sent.assert_not_called()
