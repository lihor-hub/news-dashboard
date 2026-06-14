"""Unit tests for scheduler.py — briefing job and cron wiring.

No APScheduler or database is required; all external dependencies are patched.
"""

from __future__ import annotations

import logging
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
_INIT_DB_PATH = "news_dashboard.db.init_db"
_GET_SETTING_PATH = "news_dashboard.db.get_setting"


def _start_with_env(monkeypatch: pytest.MonkeyPatch, briefing_cron: str | None = None) -> MagicMock:
    """Run start_scheduler() with APScheduler mocked; return the mock scheduler."""
    mock_sched = MagicMock()
    mock_sched.get_job.return_value = None

    if briefing_cron is not None:
        monkeypatch.setenv("BRIEFING_CRON", briefing_cron)
    else:
        monkeypatch.delenv("BRIEFING_CRON", raising=False)

    with (
        patch(_BGSCHED_PATH, return_value=mock_sched),
        patch(_INIT_DB_PATH),
        patch(_GET_SETTING_PATH, return_value=None),
    ):
        from news_dashboard import scheduler

        # Reset module-level state between tests
        scheduler._state.scheduler = None
        scheduler.start_scheduler()

    return mock_sched


def test_start_scheduler_registers_briefing_job(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_sched = _start_with_env(monkeypatch)
    ids = [c.kwargs.get("id") for c in mock_sched.add_job.call_args_list]
    assert "briefing" in ids


def test_start_scheduler_briefing_default_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default BRIEFING_CRON = '0 9 * * *' → hour='9', minute='0'."""
    mock_sched = _start_with_env(monkeypatch, briefing_cron=None)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.kwargs["hour"] == "9"
    assert briefing_call.kwargs["minute"] == "0"


def test_start_scheduler_briefing_custom_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    """BRIEFING_CRON='30 7 * * *' → hour='7', minute='30'."""
    mock_sched = _start_with_env(monkeypatch, briefing_cron="30 7 * * *")
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.kwargs["hour"] == "7"
    assert briefing_call.kwargs["minute"] == "30"


def test_start_scheduler_briefing_uses_cron_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_sched = _start_with_env(monkeypatch)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.kwargs["trigger"] == "cron"


def test_start_scheduler_briefing_fn_is_run_briefing(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.scheduler import _run_briefing as expected_fn

    mock_sched = _start_with_env(monkeypatch)
    briefing_call = next(
        c for c in mock_sched.add_job.call_args_list if c.kwargs.get("id") == "briefing"
    )
    assert briefing_call.args[0] is expected_fn
