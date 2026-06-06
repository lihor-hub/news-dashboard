"""Scheduler module: periodic ingest + daily digest email."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_scheduler: Any = None  # APScheduler BackgroundScheduler instance
_interval_minutes: int = 30  # current interval (may differ from env var after live update)


def _run_ingest() -> None:
    from .ingest import ingest_all

    logger.info("Scheduled ingest starting…")
    try:
        results = ingest_all()
        total = sum(v for v in results.values() if v > 0)
        logger.info("Scheduled ingest complete: %d new articles", total)
    except Exception:
        logger.exception("Scheduled ingest failed")


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
    global _scheduler, _interval_minutes

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
    _interval_minutes = interval_minutes

    db_paused = get_setting("scheduler_paused")
    start_paused = db_paused == "true" if db_paused is not None else False

    digest_cron = os.getenv("DIGEST_CRON", "0 8 * * *")

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

    scheduler.start()
    _scheduler = scheduler

    if start_paused:
        try:
            scheduler.pause_job("ingest")
            logger.info("Scheduler started (ingest paused per saved settings).")
        except Exception:
            logger.exception("Failed to pause ingest job on startup")
    else:
        logger.info(
            "Scheduler started: ingest every %d min, digest at %s:%s UTC",
            interval_minutes,
            cron_hour.zfill(2),
            cron_minute.zfill(2),
        )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")
        except Exception:
            logger.exception("Error stopping scheduler")
        _scheduler = None


def get_next_ingest_at() -> str | None:
    """Return ISO timestamp of next scheduled ingest, or None if not running."""
    if _scheduler is None:
        return None
    try:
        job = _scheduler.get_job("ingest")
        if job and job.next_run_time:
            return job.next_run_time.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        pass
    return None


def is_paused() -> bool:
    """Return True if the ingest job is currently paused."""
    if _scheduler is None:
        return False
    try:
        job = _scheduler.get_job("ingest")
        if job is None:
            return False
        return job.next_run_time is None
    except Exception:
        return False


def get_interval_minutes() -> int:
    """Return the current ingest interval in minutes."""
    return _interval_minutes


def set_interval(minutes: int) -> None:
    """Reschedule the ingest job with a new interval and persist it."""
    global _interval_minutes
    from .db import set_setting

    _interval_minutes = minutes
    set_setting("ingest_interval_minutes", str(minutes))

    if _scheduler is None:
        return
    try:
        _scheduler.reschedule_job("ingest", trigger="interval", minutes=minutes)
        logger.info("Ingest interval updated to %d minutes", minutes)
    except Exception:
        logger.exception("Failed to reschedule ingest job")


def pause_scheduler() -> None:
    """Pause the ingest job and persist state."""
    from .db import set_setting

    set_setting("scheduler_paused", "true")
    if _scheduler is None:
        return
    try:
        _scheduler.pause_job("ingest")
        logger.info("Ingest job paused")
    except Exception:
        logger.exception("Failed to pause ingest job")


def resume_scheduler() -> None:
    """Resume the ingest job and persist state."""
    from .db import set_setting

    set_setting("scheduler_paused", "false")
    if _scheduler is None:
        return
    try:
        _scheduler.resume_job("ingest")
        logger.info("Ingest job resumed")
    except Exception:
        logger.exception("Failed to resume ingest job")
