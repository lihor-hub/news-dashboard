"""Scheduler module: periodic ingest, daily digest email, and daily briefing."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class _SchedulerState:
    """Holds the APScheduler instance and the live ingest interval."""

    def __init__(self) -> None:
        self.scheduler: Any = None  # APScheduler BackgroundScheduler instance
        self.interval_minutes: int = 30  # may differ from env var after live update


_state = _SchedulerState()


def _run_ingest() -> None:
    from .body_fetch import prefetch_article_bodies
    from .ingest import ingest_all

    logger.info("Scheduled ingest starting…")
    try:
        results = ingest_all()
        total = sum(v for v in results.values() if v > 0)
        logger.info("Scheduled ingest complete: %d new articles", total)
        if total > 0:
            prefetch_article_bodies()
    except Exception:
        logger.exception("Scheduled ingest failed")
    # Repair stale/missing scores out-of-band.  Guarded separately so a
    # recalculation or scoring failure never fails the ingest run itself.
    _run_recommendation_recalc()


def _run_recommendation_recalc() -> None:
    from .recommendation_jobs import recalculate_stale_recommendations

    try:
        summary = recalculate_stale_recommendations()
        logger.info("Recommendation recalculation: %s", summary.as_dict())
    except Exception:
        logger.exception("Recommendation recalculation failed")


def _run_briefing() -> None:
    from .briefings import (
        BriefingAINotConfiguredError,
        BriefingGenerationError,
        generate_briefing,
    )

    logger.info("Scheduled briefing generation starting…")
    try:
        result = generate_briefing()
        if result.get("status") == "no_candidates":
            logger.info("Scheduled briefing skipped: no candidate articles found.")
        else:
            logger.info("Scheduled briefing complete: id=%s", result.get("id"))
    except BriefingAINotConfiguredError:
        logger.warning("Scheduled briefing skipped: OPENAI_API_KEY not configured.")
    except BriefingGenerationError:
        logger.exception("Scheduled briefing failed (generation error)")
    except Exception:
        logger.exception("Scheduled briefing failed (unexpected error)")


def _run_digest() -> None:
    from .digest import send_digest

    logger.info("Sending daily digest…")
    try:
        sent = send_digest()
        if sent:
            logger.info("Daily digest sent.")
        else:
            logger.info("Daily digest skipped (no new articles or DIGEST_TO not set).")
    except Exception:
        logger.exception("Daily digest failed")


def start_scheduler() -> None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed — background scheduling disabled.")
        return

    # Read settings from DB (overrides env var)
    from .db import get_setting, init_db

    init_db()

    env_interval = int(os.getenv("INGEST_INTERVAL_MINUTES", "30"))
    db_interval = get_setting("ingest_interval_minutes")
    interval_minutes = int(db_interval) if db_interval is not None else env_interval
    _state.interval_minutes = interval_minutes

    db_paused = get_setting("scheduler_paused")
    start_paused = db_paused == "true" if db_paused is not None else False

    digest_cron = os.getenv("DIGEST_CRON", "0 8 * * *")
    briefing_cron = os.getenv("BRIEFING_CRON", "0 9 * * *")

    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        _run_ingest,
        trigger="interval",
        minutes=interval_minutes,
        id="ingest",
        replace_existing=True,
    )

    try:
        parts = digest_cron.strip().split()
        if len(parts) >= 2:
            cron_minute = parts[0]
            cron_hour = parts[1]
        else:
            cron_minute, cron_hour = "0", "8"
    except Exception:
        cron_minute, cron_hour = "0", "8"

    scheduler.add_job(
        _run_digest,
        trigger="cron",
        hour=cron_hour,
        minute=cron_minute,
        id="digest",
        replace_existing=True,
    )

    try:
        b_parts = briefing_cron.strip().split()
        if len(b_parts) >= 2:
            b_minute = b_parts[0]
            b_hour = b_parts[1]
        else:
            b_minute, b_hour = "0", "9"
    except Exception:
        b_minute, b_hour = "0", "9"

    scheduler.add_job(
        _run_briefing,
        trigger="cron",
        hour=b_hour,
        minute=b_minute,
        id="briefing",
        replace_existing=True,
    )

    scheduler.start()
    _state.scheduler = scheduler

    if start_paused:
        try:
            scheduler.pause_job("ingest")
            logger.info("Scheduler started (ingest paused per saved settings).")
        except Exception:
            logger.exception("Failed to pause ingest job on startup")
    else:
        logger.info(
            "Scheduler started: ingest every %d min, digest at %s:%s UTC, briefing at %s:%s UTC",
            interval_minutes,
            cron_hour.zfill(2),
            cron_minute.zfill(2),
            b_hour.zfill(2),
            b_minute.zfill(2),
        )


def stop_scheduler() -> None:
    if _state.scheduler is not None:
        try:
            _state.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")
        except Exception:
            logger.exception("Error stopping scheduler")
        _state.scheduler = None


def get_next_ingest_at() -> str | None:
    """Return ISO timestamp of next scheduled ingest, or None if not running."""
    if _state.scheduler is None:
        return None
    try:
        job = _state.scheduler.get_job("ingest")
        if job and job.next_run_time:
            next_run: datetime = job.next_run_time
            return next_run.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:  # scheduler state is advisory only
        logger.debug("Could not read next ingest run time", exc_info=True)
    return None


def is_paused() -> bool:
    """Return True if the ingest job is currently paused."""
    if _state.scheduler is None:
        return False
    try:
        job = _state.scheduler.get_job("ingest")
        if job is None:
            return False
        return job.next_run_time is None
    except Exception:
        return False


def get_interval_minutes() -> int:
    """Return the current ingest interval in minutes."""
    return _state.interval_minutes


def set_interval(minutes: int) -> None:
    """Reschedule the ingest job with a new interval and persist it."""
    from .db import set_setting

    _state.interval_minutes = minutes
    set_setting("ingest_interval_minutes", str(minutes))

    if _state.scheduler is None:
        return
    try:
        _state.scheduler.reschedule_job("ingest", trigger="interval", minutes=minutes)
        logger.info("Ingest interval updated to %d minutes", minutes)
    except Exception:
        logger.exception("Failed to reschedule ingest job")


def pause_scheduler() -> None:
    """Pause the ingest job and persist state."""
    from .db import set_setting

    set_setting("scheduler_paused", "true")
    if _state.scheduler is None:
        return
    try:
        _state.scheduler.pause_job("ingest")
        logger.info("Ingest job paused")
    except Exception:
        logger.exception("Failed to pause ingest job")


def resume_scheduler() -> None:
    """Resume the ingest job and persist state."""
    from .db import set_setting

    set_setting("scheduler_paused", "false")
    if _state.scheduler is None:
        return
    try:
        _state.scheduler.resume_job("ingest")
        logger.info("Ingest job resumed")
    except Exception:
        logger.exception("Failed to resume ingest job")
