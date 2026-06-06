"""Scheduler module: periodic ingest + daily digest email."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_scheduler: Any = None  # APScheduler BackgroundScheduler instance


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
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed — background scheduling disabled.")
        return

    interval_minutes = int(os.getenv("INGEST_INTERVAL_MINUTES", "30"))
    digest_cron = os.getenv("DIGEST_CRON", "0 8 * * *")  # default 08:00

    scheduler = BackgroundScheduler(timezone="UTC")

    # Periodic ingest
    scheduler.add_job(
        _run_ingest,
        trigger="interval",
        minutes=interval_minutes,
        id="ingest",
        replace_existing=True,
    )

    # Daily digest — parse simple "HH MM" or full cron expression
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
