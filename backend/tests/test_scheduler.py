"""Unit tests for scheduler.py — briefing job and cron wiring.

No APScheduler or database is required; all external dependencies are patched.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.briefings import BriefingAINotConfiguredError, BriefingGenerationError
from news_dashboard.scheduler import _run_briefing

# ── helpers ───────────────────────────────────────────────────────────────────

# _run_briefing does `from .briefings import generate_briefing` lazily,
# so the correct patch target is the briefings module itself.
_GEN_PATH = "news_dashboard.briefings.generate_briefing"


# ── _run_briefing — happy path ────────────────────────────────────────────────


def test_run_briefing_calls_generate_briefing() -> None:
    with patch(_GEN_PATH) as mock_gen:
        mock_gen.return_value = {"id": 1, "status": "complete", "title": "Daily Brief"}
        _run_briefing()
    mock_gen.assert_called_once_with()


def test_run_briefing_logs_completion(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.INFO, logger="news_dashboard.scheduler"),
        patch(_GEN_PATH) as mock_gen,
    ):
        mock_gen.return_value = {"id": 42, "status": "complete", "title": "T"}
        _run_briefing()
    assert any("42" in r.message for r in caplog.records)


def test_run_briefing_logs_no_candidates(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.INFO, logger="news_dashboard.scheduler"),
        patch(_GEN_PATH) as mock_gen,
    ):
        mock_gen.return_value = {"status": "no_candidates"}
        _run_briefing()
    assert any("no candidate" in r.message.lower() for r in caplog.records)


# ── _run_briefing — error handling ────────────────────────────────────────────


def test_run_briefing_suppresses_ai_not_configured() -> None:
    with patch(_GEN_PATH) as mock_gen:
        mock_gen.side_effect = BriefingAINotConfiguredError("no key")
        _run_briefing()  # must not raise


def test_run_briefing_logs_warning_when_ai_not_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="news_dashboard.scheduler"),
        patch(_GEN_PATH) as mock_gen,
    ):
        mock_gen.side_effect = BriefingAINotConfiguredError("no key")
        _run_briefing()
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_run_briefing_suppresses_generation_error() -> None:
    with patch(_GEN_PATH) as mock_gen:
        mock_gen.side_effect = BriefingGenerationError("bad json")
        _run_briefing()  # must not raise


def test_run_briefing_suppresses_unexpected_exception() -> None:
    with patch(_GEN_PATH) as mock_gen:
        mock_gen.side_effect = RuntimeError("totally unexpected")
        _run_briefing()  # must not raise


def test_run_briefing_logs_generation_error(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.ERROR, logger="news_dashboard.scheduler"),
        patch(_GEN_PATH) as mock_gen,
    ):
        mock_gen.side_effect = BriefingGenerationError("bad json")
        _run_briefing()
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ── start_scheduler — BRIEFING_CRON wiring ───────────────────────────────────

# All three lazy imports in start_scheduler() must be patched at their source:
#   from apscheduler.schedulers.background import BackgroundScheduler
#   from .db import get_setting, init_db
_BGSCHED_PATH = "apscheduler.schedulers.background.BackgroundScheduler"
_INIT_DB_PATCH_PATH = "news_dashboard.db.init_db"
_GET_SETTING_PATH = "news_dashboard.db.get_setting"


@pytest.fixture(autouse=True)
def _reset_scheduler_state() -> Generator[None]:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    scheduler._state.ingest_interval_enabled = True
    yield
    scheduler._state.scheduler = None
    scheduler._state.ingest_interval_enabled = True


def _start_with_env(
    monkeypatch: pytest.MonkeyPatch,
    briefing_cron: str | None = None,
    *,
    legacy_briefing: bool = False,
) -> MagicMock:
    """Run start_scheduler() with APScheduler mocked; return the mock scheduler."""
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None

    if briefing_cron is not None:
        monkeypatch.setenv("BRIEFING_CRON", briefing_cron)
    else:
        monkeypatch.delenv("BRIEFING_CRON", raising=False)

    if legacy_briefing:
        monkeypatch.setenv("LEGACY_GLOBAL_BRIEFING_ENABLED", "true")
    else:
        monkeypatch.delenv("LEGACY_GLOBAL_BRIEFING_ENABLED", raising=False)

    with (
        patch(_BGSCHED_PATH, return_value=mock_sched),
        patch(_INIT_DB_PATCH_PATH),
        patch(_GET_SETTING_PATH, return_value=None),
    ):
        from news_dashboard import scheduler

        # Reset module-level state between tests
        scheduler._state.scheduler = None
        scheduler.start_scheduler()

    return mock_sched


def test_start_scheduler_does_not_register_legacy_briefing_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_sched = _start_with_env(monkeypatch)
    ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
    assert "briefing" not in ids


def test_start_scheduler_registers_legacy_briefing_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_sched = _start_with_env(monkeypatch, legacy_briefing=True)
    ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
    assert "briefing" in ids


def test_start_scheduler_always_registers_per_user_briefings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_sched = _start_with_env(monkeypatch)
    ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
    assert "per_user_briefings" in ids


def test_start_scheduler_briefing_default_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default BRIEFING_CRON = '0 9 * * *' → hour='9', minute='0' when legacy enabled."""
    mock_sched = _start_with_env(monkeypatch, briefing_cron=None, legacy_briefing=True)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.kwargs["hour"] == "9"
    assert briefing_call.kwargs["minute"] == "0"


def test_start_scheduler_briefing_custom_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    """BRIEFING_CRON='30 7 * * *' → hour='7', minute='30' when legacy enabled."""
    mock_sched = _start_with_env(monkeypatch, briefing_cron="30 7 * * *", legacy_briefing=True)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.kwargs["hour"] == "7"
    assert briefing_call.kwargs["minute"] == "30"


def test_start_scheduler_briefing_uses_cron_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_sched = _start_with_env(monkeypatch, legacy_briefing=True)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.kwargs["trigger"] == "cron"


def test_start_scheduler_registers_analytics_retention_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_sched = _start_with_env(monkeypatch)
    retention_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "analytics_retention"
    )
    assert retention_call.kwargs["trigger"] == "cron"
    assert retention_call.kwargs["hour"] == "3"
    assert retention_call.kwargs["minute"] == "0"


def test_start_scheduler_briefing_fn_is_run_briefing(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.scheduler import _run_briefing as expected_fn

    mock_sched = _start_with_env(monkeypatch, legacy_briefing=True)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.args[0] is expected_fn


# ── _run_ingest ───────────────────────────────────────────────────────────────


def test_run_ingest_prefetches_when_new_articles() -> None:
    from news_dashboard import scheduler
    from news_dashboard.ingest import IngestResult

    with (
        patch(
            "news_dashboard.ingest.ingest_all",
            return_value=IngestResult(results={"a": 2, "b": -1}, run_id=1, total_errors=1),
        ) as ingest,
        patch("news_dashboard.body_fetch.prefetch_article_bodies") as prefetch,
        patch.object(scheduler, "_run_recommendation_recalc") as recalc,
    ):
        scheduler._run_ingest()

    ingest.assert_called_once()
    prefetch.assert_called_once()
    recalc.assert_called_once()


def test_run_scheduled_ingest_returns_results_and_runs_maintenance() -> None:
    from news_dashboard import scheduler
    from news_dashboard.ingest import IngestResult

    with (
        patch(
            "news_dashboard.ingest.ingest_all",
            return_value=IngestResult(results={"a": 2, "b": -1}, run_id=1, total_errors=1),
        ) as ingest,
        patch("news_dashboard.body_fetch.prefetch_article_bodies") as prefetch,
        patch.object(scheduler, "_run_recommendation_recalc") as recalc,
    ):
        results = scheduler.run_scheduled_ingest()

    assert results == {"a": 2, "b": -1}
    ingest.assert_called_once()
    prefetch.assert_called_once()
    recalc.assert_called_once()


def test_run_ingest_skips_prefetch_when_no_new_articles() -> None:
    from news_dashboard import scheduler
    from news_dashboard.ingest import IngestResult

    with (
        patch(
            "news_dashboard.ingest.ingest_all",
            return_value=IngestResult(results={"a": 0}, run_id=1, total_errors=0),
        ),
        patch("news_dashboard.body_fetch.prefetch_article_bodies") as prefetch,
        patch.object(scheduler, "_run_recommendation_recalc"),
    ):
        scheduler._run_ingest()

    prefetch.assert_not_called()


def test_run_ingest_suppresses_ingest_failure_but_still_recalcs() -> None:
    from news_dashboard import scheduler

    with (
        patch("news_dashboard.ingest.ingest_all", side_effect=RuntimeError("boom")),
        patch("news_dashboard.body_fetch.prefetch_article_bodies") as prefetch,
        patch.object(scheduler, "_run_recommendation_recalc") as recalc,
    ):
        scheduler._run_ingest()  # must not raise

    prefetch.assert_not_called()
    recalc.assert_called_once()


# ── recommendation recalc jobs ────────────────────────────────────────────────


def test_run_recommendation_recalc_logs_summary() -> None:
    from news_dashboard import scheduler

    summary = MagicMock()
    summary.as_dict.return_value = {"recomputed": 3}
    with patch(
        "news_dashboard.recommendation_jobs.recalculate_stale_recommendations",
        return_value=summary,
    ):
        scheduler._run_recommendation_recalc()
    summary.as_dict.assert_called_once()


def test_run_recommendation_recalc_suppresses_errors() -> None:
    from news_dashboard import scheduler

    with patch(
        "news_dashboard.recommendation_jobs.recalculate_stale_recommendations",
        side_effect=RuntimeError("nope"),
    ):
        scheduler._run_recommendation_recalc()  # must not raise


def test_run_daily_recommendation_recalc_logs_summary() -> None:
    from news_dashboard import scheduler

    summary = MagicMock()
    summary.as_dict.return_value = {"recomputed": 9}
    with patch(
        "news_dashboard.recommendation_jobs.recalculate_all_recommendations",
        return_value=summary,
    ):
        scheduler._run_daily_recommendation_recalc()
    summary.as_dict.assert_called_once()


def test_run_daily_recommendation_recalc_suppresses_errors() -> None:
    from news_dashboard import scheduler

    with patch(
        "news_dashboard.recommendation_jobs.recalculate_all_recommendations",
        side_effect=RuntimeError("nope"),
    ):
        scheduler._run_daily_recommendation_recalc()  # must not raise


# ── _run_digest ───────────────────────────────────────────────────────────────


def test_run_digest_logs_sent(caplog: pytest.LogCaptureFixture) -> None:
    from news_dashboard import scheduler

    with (
        caplog.at_level(logging.INFO, logger="news_dashboard.scheduler"),
        patch("news_dashboard.digest.send_digest", return_value=True),
    ):
        scheduler._run_digest()
    assert any("sent" in r.message.lower() for r in caplog.records)


def test_run_digest_logs_skip(caplog: pytest.LogCaptureFixture) -> None:
    from news_dashboard import scheduler

    with (
        caplog.at_level(logging.INFO, logger="news_dashboard.scheduler"),
        patch("news_dashboard.digest.send_digest", return_value=False),
    ):
        scheduler._run_digest()
    assert any("skipped" in r.message.lower() for r in caplog.records)


def test_run_digest_suppresses_errors() -> None:
    from news_dashboard import scheduler

    with patch("news_dashboard.digest.send_digest", side_effect=RuntimeError("smtp down")):
        scheduler._run_digest()  # must not raise


# ── _parse_cron_hm ────────────────────────────────────────────────────────────


def test_parse_cron_hm_extracts_fields() -> None:
    from news_dashboard.scheduler import _parse_cron_hm

    assert _parse_cron_hm("15 6 * * *", "0", "8") == ("15", "6")


def test_parse_cron_hm_falls_back_on_short_input() -> None:
    from news_dashboard.scheduler import _parse_cron_hm

    assert _parse_cron_hm("nonsense", "0", "8") == ("0", "8")


# ── start_scheduler — extra branches ──────────────────────────────────────────


def test_start_scheduler_handles_missing_apscheduler(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from news_dashboard import scheduler

    # Setting the submodule to None in sys.modules makes the lazy
    # `from apscheduler.schedulers.background import ...` raise ImportError.
    with (
        caplog.at_level(logging.WARNING, logger="news_dashboard.scheduler"),
        patch.dict("sys.modules", {"apscheduler.schedulers.background": None}),
    ):
        scheduler.start_scheduler()
    assert any("APScheduler not installed" in r.message for r in caplog.records)


def test_start_scheduler_pauses_when_db_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None

    def get_setting(key: str) -> str | None:
        return "true" if key == "scheduler_paused" else None

    with (
        patch(_BGSCHED_PATH, return_value=mock_sched),
        patch(_INIT_DB_PATCH_PATH),
        patch(_GET_SETTING_PATH, side_effect=get_setting),
    ):
        from news_dashboard import scheduler

        scheduler._state.scheduler = None
        scheduler.start_scheduler()

    mock_sched.pause_job.assert_called_once_with("ingest")


def test_start_scheduler_uses_db_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None

    def get_setting(key: str) -> str | None:
        return "12" if key == "ingest_interval_minutes" else None

    with (
        patch(_BGSCHED_PATH, return_value=mock_sched),
        patch(_INIT_DB_PATCH_PATH),
        patch(_GET_SETTING_PATH, side_effect=get_setting),
    ):
        from news_dashboard import scheduler

        scheduler._state.scheduler = None
        scheduler.start_scheduler()

    assert scheduler.get_interval_minutes() == 12
    ingest_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "ingest"
    )
    assert ingest_call.kwargs["minutes"] == 12


def test_start_scheduler_can_disable_only_interval_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGEST_INTERVAL_SCHEDULER_ENABLED", "false")
    mock_sched = _start_with_env(monkeypatch)

    ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
    assert "ingest" not in ids
    assert {"digest", "recommendations", "per_user_briefings"} <= set(ids)

    from news_dashboard import scheduler

    assert scheduler.is_ingest_interval_enabled() is False


def test_start_scheduler_ignores_saved_pause_when_interval_ingest_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INGEST_INTERVAL_SCHEDULER_ENABLED", "false")
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None

    def get_setting(key: str) -> str | None:
        return "true" if key == "scheduler_paused" else None

    with (
        patch(_BGSCHED_PATH, return_value=mock_sched),
        patch(_INIT_DB_PATCH_PATH),
        patch(_GET_SETTING_PATH, side_effect=get_setting),
    ):
        from news_dashboard import scheduler

        scheduler._state.scheduler = None
        scheduler.start_scheduler()

    mock_sched.pause_job.assert_not_called()


# ── lifecycle: stop / next-run / pause-state / interval ───────────────────────


def test_stop_scheduler_shuts_down_and_clears() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    scheduler._state.scheduler = mock_sched
    scheduler.stop_scheduler()
    mock_sched.shutdown.assert_called_once_with(wait=False)
    assert scheduler._state.scheduler is None


def test_stop_scheduler_noop_when_not_running() -> None:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    scheduler.stop_scheduler()  # must not raise


def test_get_next_ingest_at_none_when_not_running() -> None:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    assert scheduler.get_next_ingest_at() is None


def test_get_next_ingest_at_returns_iso() -> None:
    from datetime import datetime, timezone

    from news_dashboard import scheduler

    job = MagicMock()
    job.next_run_time = datetime(2026, 6, 23, 8, 0, 0, tzinfo=timezone.utc)
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = job
    scheduler._state.scheduler = mock_sched
    try:
        result = scheduler.get_next_ingest_at()
    finally:
        scheduler._state.scheduler = None
    assert result == "2026-06-23T08:00:00+00:00"


def test_is_paused_false_when_not_running() -> None:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    assert scheduler.is_paused() is False


def test_is_paused_true_when_no_next_run() -> None:
    from news_dashboard import scheduler

    job = MagicMock()
    job.next_run_time = None
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = job
    scheduler._state.scheduler = mock_sched
    try:
        assert scheduler.is_paused() is True
    finally:
        scheduler._state.scheduler = None


def test_is_paused_false_when_job_missing() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None
    scheduler._state.scheduler = mock_sched
    try:
        assert scheduler.is_paused() is False
    finally:
        scheduler._state.scheduler = None


def test_set_interval_persists_and_reschedules() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    scheduler._state.scheduler = mock_sched
    with patch("news_dashboard.db.set_setting") as set_setting:
        try:
            scheduler.set_interval(45)
        finally:
            scheduler._state.scheduler = None
    set_setting.assert_called_once_with("ingest_interval_minutes", "45")
    mock_sched.reschedule_job.assert_called_once()
    assert scheduler.get_interval_minutes() == 45


def test_set_interval_persists_when_scheduler_stopped() -> None:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    with patch("news_dashboard.db.set_setting") as set_setting:
        scheduler.set_interval(60)
    set_setting.assert_called_once_with("ingest_interval_minutes", "60")


def test_pause_scheduler_persists_and_pauses() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    scheduler._state.scheduler = mock_sched
    with patch("news_dashboard.db.set_setting") as set_setting:
        try:
            scheduler.pause_scheduler()
        finally:
            scheduler._state.scheduler = None
    set_setting.assert_called_once_with("scheduler_paused", "true")
    mock_sched.pause_job.assert_called_once_with("ingest")


def test_pause_scheduler_persists_when_stopped() -> None:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    with patch("news_dashboard.db.set_setting") as set_setting:
        scheduler.pause_scheduler()
    set_setting.assert_called_once_with("scheduler_paused", "true")


def test_resume_scheduler_persists_and_resumes() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    scheduler._state.scheduler = mock_sched
    with patch("news_dashboard.db.set_setting") as set_setting:
        try:
            scheduler.resume_scheduler()
        finally:
            scheduler._state.scheduler = None
    set_setting.assert_called_once_with("scheduler_paused", "false")
    mock_sched.resume_job.assert_called_once_with("ingest")


def test_resume_scheduler_persists_when_stopped() -> None:
    from news_dashboard import scheduler

    scheduler._state.scheduler = None
    with patch("news_dashboard.db.set_setting") as set_setting:
        scheduler.resume_scheduler()
    set_setting.assert_called_once_with("scheduler_paused", "false")


# ── error-handler branches (advisory state must never propagate) ──────────────


def test_start_scheduler_pause_failure_is_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None
    mock_sched.pause_job.side_effect = RuntimeError("cannot pause")

    def get_setting(key: str) -> str | None:
        return "true" if key == "scheduler_paused" else None

    with (
        patch(_BGSCHED_PATH, return_value=mock_sched),
        patch(_INIT_DB_PATCH_PATH),
        patch(_GET_SETTING_PATH, side_effect=get_setting),
    ):
        from news_dashboard import scheduler

        scheduler._state.scheduler = None
        scheduler.start_scheduler()  # must not raise


def test_stop_scheduler_suppresses_shutdown_error() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.shutdown.side_effect = RuntimeError("already down")
    scheduler._state.scheduler = mock_sched
    scheduler.stop_scheduler()  # must not raise
    assert scheduler._state.scheduler is None


def test_get_next_ingest_at_suppresses_error() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.get_job.side_effect = RuntimeError("boom")
    scheduler._state.scheduler = mock_sched
    try:
        assert scheduler.get_next_ingest_at() is None
    finally:
        scheduler._state.scheduler = None


def test_is_paused_suppresses_error() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.get_job.side_effect = RuntimeError("boom")
    scheduler._state.scheduler = mock_sched
    try:
        assert scheduler.is_paused() is False
    finally:
        scheduler._state.scheduler = None


def test_set_interval_suppresses_reschedule_error() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.reschedule_job.side_effect = RuntimeError("boom")
    scheduler._state.scheduler = mock_sched
    with patch("news_dashboard.db.set_setting"):
        try:
            scheduler.set_interval(15)  # must not raise
        finally:
            scheduler._state.scheduler = None


def test_pause_scheduler_suppresses_error() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.pause_job.side_effect = RuntimeError("boom")
    scheduler._state.scheduler = mock_sched
    with patch("news_dashboard.db.set_setting"):
        try:
            scheduler.pause_scheduler()  # must not raise
        finally:
            scheduler._state.scheduler = None


def test_resume_scheduler_suppresses_error() -> None:
    from news_dashboard import scheduler

    mock_sched = MagicMock()
    mock_sched.resume_job.side_effect = RuntimeError("boom")
    scheduler._state.scheduler = mock_sched
    with patch("news_dashboard.db.set_setting"):
        try:
            scheduler.resume_scheduler()  # must not raise
        finally:
            scheduler._state.scheduler = None


def test_scheduler_status_reports_external_ingest_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import main

    monkeypatch.setattr(main, "is_ingest_interval_enabled", lambda: False)
    monkeypatch.setattr(main, "get_interval_minutes", lambda: 30)
    monkeypatch.setattr(main, "get_next_ingest_at", lambda: None)
    monkeypatch.setattr(main, "is_paused", lambda: True)

    assert main.scheduler_status() == {
        "interval_minutes": 30,
        "paused": False,
        "next_run_at": None,
        "interval_ingest_enabled": False,
        "ingest_authority": "external",
    }


# ── _run_per_user_briefings — timezone-aware matching ─────────────────────────

# connect/row_to_dict/generate_briefing/push helpers are lazily imported inside
# _run_per_user_briefings, so they must be patched at their source modules.
_CONNECT_PATH = "news_dashboard.db.connect"
_ROW_TO_DICT_PATH = "news_dashboard.db.row_to_dict"
_PER_USER_GEN_PATH = "news_dashboard.briefings.generate_briefing"
_SEND_PUSH_PATH = "news_dashboard.push.send_push_for_user"
_GEN_PUSH_HOOK_PATH = "news_dashboard.push.generate_push_hook"


def _mock_conn_for_rows(user_rows: list[dict[str, Any]]) -> MagicMock:
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchall.return_value = user_rows
    return mock_conn


def test_per_user_briefings_utc_match() -> None:
    """A user with UTC timezone triggers when UTC wall clock matches briefing_time."""
    from datetime import datetime, timezone

    from news_dashboard.scheduler import _run_per_user_briefings

    now = datetime(2026, 6, 29, 9, 0, 0, tzinfo=timezone.utc)
    user_rows = [{"id": 1, "briefing_time": "09:00", "briefing_timezone": "UTC"}]
    mock_conn = _mock_conn_for_rows(user_rows)
    mock_generate = MagicMock(return_value={"id": 1, "status": "complete"})

    with (
        patch("news_dashboard.scheduler.datetime") as mock_dt,
        patch(_CONNECT_PATH, return_value=mock_conn),
        patch(_PER_USER_GEN_PATH, mock_generate),
        patch(_SEND_PUSH_PATH),
        patch(_GEN_PUSH_HOOK_PATH, return_value="Brief ready"),
    ):
        mock_dt.now.return_value = now
        _run_per_user_briefings()

    mock_generate.assert_called_once_with(user_id=1)


def test_per_user_briefings_utc_no_match() -> None:
    """A UTC user is NOT triggered when the current UTC minute differs."""
    from datetime import datetime, timezone

    from news_dashboard.scheduler import _run_per_user_briefings

    now = datetime(2026, 6, 29, 10, 0, 0, tzinfo=timezone.utc)
    user_rows = [{"id": 1, "briefing_time": "09:00", "briefing_timezone": "UTC"}]
    mock_conn = _mock_conn_for_rows(user_rows)
    mock_generate = MagicMock()

    with (
        patch("news_dashboard.scheduler.datetime") as mock_dt,
        patch(_CONNECT_PATH, return_value=mock_conn),
        patch(_PER_USER_GEN_PATH, mock_generate),
    ):
        mock_dt.now.return_value = now
        _run_per_user_briefings()

    mock_generate.assert_not_called()


def test_per_user_briefings_europe_bucharest_summer() -> None:
    """Europe/Bucharest is UTC+3 in summer (EEST). 09:00 local = 06:00 UTC."""
    from datetime import datetime, timezone

    from news_dashboard.scheduler import _run_per_user_briefings

    # 2026-06-29 06:00 UTC = 09:00 Europe/Bucharest (EEST, UTC+3)
    now = datetime(2026, 6, 29, 6, 0, 0, tzinfo=timezone.utc)
    user_rows = [{"id": 42, "briefing_time": "09:00", "briefing_timezone": "Europe/Bucharest"}]
    mock_conn = _mock_conn_for_rows(user_rows)
    mock_generate = MagicMock(return_value={"id": 1, "status": "complete"})

    with (
        patch("news_dashboard.scheduler.datetime") as mock_dt,
        patch(_CONNECT_PATH, return_value=mock_conn),
        patch(_PER_USER_GEN_PATH, mock_generate),
        patch(_SEND_PUSH_PATH),
        patch(_GEN_PUSH_HOOK_PATH, return_value="Brief ready"),
    ):
        mock_dt.now.return_value = now
        _run_per_user_briefings()

    mock_generate.assert_called_once_with(user_id=42)


def test_per_user_briefings_europe_bucharest_winter() -> None:
    """Europe/Bucharest is UTC+2 in winter (EET). 09:00 local = 07:00 UTC."""
    from datetime import datetime, timezone

    from news_dashboard.scheduler import _run_per_user_briefings

    # 2026-01-15 07:00 UTC = 09:00 Europe/Bucharest (EET, UTC+2)
    now = datetime(2026, 1, 15, 7, 0, 0, tzinfo=timezone.utc)
    user_rows = [{"id": 42, "briefing_time": "09:00", "briefing_timezone": "Europe/Bucharest"}]
    mock_conn = _mock_conn_for_rows(user_rows)
    mock_generate = MagicMock(return_value={"id": 1, "status": "complete"})

    with (
        patch("news_dashboard.scheduler.datetime") as mock_dt,
        patch(_CONNECT_PATH, return_value=mock_conn),
        patch(_PER_USER_GEN_PATH, mock_generate),
        patch(_SEND_PUSH_PATH),
        patch(_GEN_PUSH_HOOK_PATH, return_value="Brief ready"),
    ):
        mock_dt.now.return_value = now
        _run_per_user_briefings()

    mock_generate.assert_called_once_with(user_id=42)


def test_per_user_briefings_null_timezone_falls_back_to_utc() -> None:
    """A user with NULL briefing_timezone is treated as UTC."""
    from datetime import datetime, timezone

    from news_dashboard.scheduler import _run_per_user_briefings

    now = datetime(2026, 6, 29, 9, 0, 0, tzinfo=timezone.utc)
    user_rows = [{"id": 5, "briefing_time": "09:00", "briefing_timezone": None}]
    mock_conn = _mock_conn_for_rows(user_rows)
    mock_generate = MagicMock(return_value={"id": 1, "status": "complete"})

    with (
        patch("news_dashboard.scheduler.datetime") as mock_dt,
        patch(_CONNECT_PATH, return_value=mock_conn),
        patch(_PER_USER_GEN_PATH, mock_generate),
        patch(_SEND_PUSH_PATH),
        patch(_GEN_PUSH_HOOK_PATH, return_value="Brief ready"),
    ):
        mock_dt.now.return_value = now
        _run_per_user_briefings()

    mock_generate.assert_called_once_with(user_id=5)
