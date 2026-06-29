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
        self.ingest_interval_enabled: bool = True


_state = _SchedulerState()


def _env_flag_enabled(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def run_scheduled_ingest() -> dict[str, int]:
    from news_dashboard.body_fetch import prefetch_article_bodies
    from news_dashboard.ingest import ingest_all

    logger.info("Scheduled ingest starting…")
    results: dict[str, int] = {}
    try:
        ingest_result = ingest_all()
        results = ingest_result.results
        total = sum(v for v in results.values() if v > 0)
        logger.info("Scheduled ingest complete: %d new articles", total)
        if total > 0:
            prefetch_article_bodies()
    except Exception:
        logger.exception("Scheduled ingest failed")
    # Repair stale/missing scores out-of-band.  Guarded separately so a
    # recalculation or scoring failure never fails the ingest run itself.
    _run_recommendation_recalc()
    return results


def _run_ingest() -> None:
    run_scheduled_ingest()


def _run_recommendation_recalc() -> None:
    from news_dashboard.recommendation_jobs import recalculate_stale_recommendations

    try:
        summary = recalculate_stale_recommendations()
        logger.info("Recommendation recalculation: %s", summary.as_dict())
    except Exception:
        logger.exception("Recommendation recalculation failed")


def _run_daily_recommendation_recalc() -> None:
    from news_dashboard.recommendation_jobs import recalculate_all_recommendations

    logger.info("Daily recommendation recalculation starting…")
    try:
        summary = recalculate_all_recommendations()
        logger.info("Daily recommendation recalculation: %s", summary.as_dict())
    except Exception:
        logger.exception("Daily recommendation recalculation failed")


def _run_analytics_retention() -> None:
    from news_dashboard.analytics import DEFAULT_EVENT_RETENTION_DAYS, prune_old_events

    retention_days = int(os.getenv("ANALYTICS_RETENTION_DAYS", str(DEFAULT_EVENT_RETENTION_DAYS)))
    try:
        deleted = prune_old_events(retention_days=retention_days)
        logger.info(
            "Analytics retention pruned %d events older than %d days",
            deleted,
            retention_days,
        )
    except Exception:
        logger.exception("Analytics retention failed")


def _run_briefing() -> None:
    from news_dashboard.briefings import (
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
        logger.warning("Briefing skipped: no AI key set (FREE_LLM_API_KEY / OPENAI_API_KEY).")
    except BriefingGenerationError:
        logger.exception("Scheduled briefing failed (generation error)")
    except Exception:
        logger.exception("Scheduled briefing failed (unexpected error)")


def _run_per_user_briefings() -> None:
    """Generate briefings for users whose local scheduled time matches the current instant."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from news_dashboard.briefings import (
        BriefingAINotConfiguredError,
        BriefingGenerationError,
        generate_briefing,
    )
    from news_dashboard.db import connect, row_to_dict
    from news_dashboard.push import generate_push_hook, send_push_for_user

    now = datetime.now(timezone.utc)

    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, briefing_time, briefing_timezone FROM users"
                " WHERE briefing_push_enabled = TRUE OR briefing_time IS NOT NULL",
            ).fetchall()
        user_rows = [row_to_dict(r) for r in rows]
    except Exception:
        logger.exception("Per-user briefing: failed to query users")
        return

    user_ids: list[int] = []
    for row in user_rows:
        tz_name: str = row.get("briefing_timezone") or "UTC"
        briefing_time: str = row.get("briefing_time") or "09:00"
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, KeyError):
            tz = ZoneInfo("UTC")
        local_hm = now.astimezone(tz).strftime("%H:%M")
        if local_hm == briefing_time:
            user_ids.append(int(row["id"]))

    for user_id in user_ids:
        logger.info("Per-user briefing: generating for user_id=%s", user_id)
        try:
            result = generate_briefing(user_id=user_id)
            if result.get("status") == "no_candidates":
                logger.info("Per-user briefing: skipped for user_id=%s (no candidates)", user_id)
            else:
                logger.info(
                    "Per-user briefing: complete for user_id=%s id=%s", user_id, result.get("id")
                )
                try:
                    briefing_id = result.get("id")
                    target_url = f"/briefs/{briefing_id}" if briefing_id is not None else None
                    push_title = generate_push_hook(result)
                    send_push_for_user(
                        user_id,
                        push_title,
                        "",
                        target_url=target_url,
                    )
                except Exception:
                    logger.exception(
                        "Per-user briefing: push notification failed for user_id=%s", user_id
                    )
        except BriefingAINotConfiguredError:
            logger.warning("Per-user briefing: skipped for user_id=%s (AI not configured)", user_id)
        except BriefingGenerationError:
            logger.exception("Per-user briefing: generation error for user_id=%s", user_id)
        except Exception:
            logger.exception("Per-user briefing: unexpected error for user_id=%s", user_id)


def _run_digest() -> None:
    from news_dashboard.digest import send_digest

    logger.info("Sending daily digest…")
    try:
        sent = send_digest()
        if sent:
            logger.info("Daily digest sent.")
        else:
            logger.info("Daily digest skipped (no new articles or DIGEST_TO not set).")
    except Exception:
        logger.exception("Daily digest failed")


def _parse_cron_hm(cron: str, default_minute: str, default_hour: str) -> tuple[str, str]:
    """Extract (minute, hour) from a cron string, falling back to defaults.

    Only the first two fields matter for our daily jobs; a malformed value
    degrades to the supplied defaults rather than failing scheduler startup.
    """
    try:
        parts = cron.strip().split()
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        logger.debug("Could not parse cron %r; using defaults", cron, exc_info=True)
    return default_minute, default_hour


def start_scheduler() -> None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed — background scheduling disabled.")
        return

    # Read settings from DB (overrides env var)
    from news_dashboard.db import get_setting, init_db

    init_db()

    env_interval = int(os.getenv("INGEST_INTERVAL_MINUTES", "30"))
    db_interval = get_setting("ingest_interval_minutes")
    interval_minutes = int(db_interval) if db_interval is not None else env_interval
    _state.interval_minutes = interval_minutes
    _state.ingest_interval_enabled = _env_flag_enabled(
        "INGEST_INTERVAL_SCHEDULER_ENABLED", default=True
    )

    db_paused = get_setting("scheduler_paused")
    start_paused = db_paused == "true" if db_paused is not None else False

    digest_cron = os.getenv("DIGEST_CRON", "0 8 * * *")
    briefing_cron = os.getenv("BRIEFING_CRON", "0 9 * * *")
    recommendations_cron = os.getenv("RECOMMENDATIONS_CRON", "30 7 * * *")

    scheduler = BackgroundScheduler(timezone="UTC")

    if _state.ingest_interval_enabled:
        scheduler.add_job(
            _run_ingest,
            trigger="interval",
            minutes=interval_minutes,
            id="ingest",
            replace_existing=True,
        )
    else:
        logger.info("Interval ingest scheduler disabled by INGEST_INTERVAL_SCHEDULER_ENABLED.")

    cron_minute, cron_hour = _parse_cron_hm(digest_cron, "0", "8")
    scheduler.add_job(
        _run_digest,
        trigger="cron",
        hour=cron_hour,
        minute=cron_minute,
        id="digest",
        replace_existing=True,
    )

    legacy_global_briefing_enabled = _env_flag_enabled(
        "LEGACY_GLOBAL_BRIEFING_ENABLED", default=False
    )
    b_minute, b_hour = _parse_cron_hm(briefing_cron, "0", "9")
    if legacy_global_briefing_enabled:
        scheduler.add_job(
            _run_briefing,
            trigger="cron",
            hour=b_hour,
            minute=b_minute,
            id="briefing",
            replace_existing=True,
        )
    else:
        logger.info(
            "Legacy global briefing job not registered; per-user briefings are the active path. "
            "Set LEGACY_GLOBAL_BRIEFING_ENABLED=true to restore the old behaviour."
        )

    r_minute, r_hour = _parse_cron_hm(recommendations_cron, "30", "7")
    scheduler.add_job(
        _run_daily_recommendation_recalc,
        trigger="cron",
        hour=r_hour,
        minute=r_minute,
        id="recommendations",
        replace_existing=True,
    )

    scheduler.add_job(
        _run_analytics_retention,
        trigger="cron",
        hour="3",
        minute="0",
        id="analytics_retention",
        replace_existing=True,
    )

    scheduler.add_job(
        _run_per_user_briefings,
        trigger="interval",
        minutes=1,
        id="per_user_briefings",
        replace_existing=True,
    )

    scheduler.start()
    _state.scheduler = scheduler

    if start_paused and _state.ingest_interval_enabled:
        try:
            scheduler.pause_job("ingest")
            logger.info("Scheduler started (ingest paused per saved settings).")
        except Exception:
            logger.exception("Failed to pause ingest job on startup")
    elif legacy_global_briefing_enabled:
        logger.info(
            "Scheduler started: ingest every %d min, digest at %s:%s UTC, "
            "legacy briefing at %s:%s UTC, recommendations at %s:%s UTC",
            interval_minutes,
            cron_hour.zfill(2),
            cron_minute.zfill(2),
            b_hour.zfill(2),
            b_minute.zfill(2),
            r_hour.zfill(2),
            r_minute.zfill(2),
        )
    else:
        logger.info(
            "Scheduler started: ingest every %d min, digest at %s:%s UTC, "
            "per-user briefings active, recommendations at %s:%s UTC",
            interval_minutes,
            cron_hour.zfill(2),
            cron_minute.zfill(2),
            r_hour.zfill(2),
            r_minute.zfill(2),
        )


def is_ingest_interval_enabled() -> bool:
    """Return whether this process owns the interval ingest job."""
    return _state.ingest_interval_enabled


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
    from news_dashboard.db import set_setting

    _state.interval_minutes = minutes
    set_setting("ingest_interval_minutes", str(minutes))

    if _state.scheduler is None or not _state.ingest_interval_enabled:
        return
    try:
        _state.scheduler.reschedule_job("ingest", trigger="interval", minutes=minutes)
        logger.info("Ingest interval updated to %d minutes", minutes)
    except Exception:
        logger.exception("Failed to reschedule ingest job")


def pause_scheduler() -> None:
    """Pause the ingest job and persist state."""
    from news_dashboard.db import set_setting

    set_setting("scheduler_paused", "true")
    if _state.scheduler is None or not _state.ingest_interval_enabled:
        return
    try:
        _state.scheduler.pause_job("ingest")
        logger.info("Ingest job paused")
    except Exception:
        logger.exception("Failed to pause ingest job")


def resume_scheduler() -> None:
    """Resume the ingest job and persist state."""
    from news_dashboard.db import set_setting

    set_setting("scheduler_paused", "false")
    if _state.scheduler is None or not _state.ingest_interval_enabled:
        return
    try:
        _state.scheduler.resume_job("ingest")
        logger.info("Ingest job resumed")
    except Exception:
        logger.exception("Failed to resume ingest job")
