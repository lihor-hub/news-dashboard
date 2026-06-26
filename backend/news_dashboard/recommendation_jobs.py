"""Background repair and observability for recommendation scores.

The Today read path is intentionally a cheap LEFT JOIN against
``user_article_recommendations`` that falls back to the cold-start SQL when a
score is absent — it never recomputes the model synchronously.  This module
provides the *out-of-band* path that keeps those stored scores fresh:

* :func:`mark_user_recommendations_stale` flags a user's scores after a
  preference change so they become eligible for recalculation.
* :func:`find_recalculation_candidates` finds users whose scores are stale,
  missing, or produced by a superseded scoring formula / embedding scheme.
* :func:`recalculate_stale_recommendations` recomputes those users in the
  background, isolating per-user failures so one bad user (or a transient
  scoring error during ingestion) never blocks the rest.
* :func:`recommendation_health` reports counts operators can use to diagnose
  stale or missing recommendation data without reading the whole table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.recommendations import CURRENT_MODEL_VERSIONS, recompute_user_recommendations

logger = logging.getLogger(__name__)

# An article is a live recommendation candidate for a user when it is in their
# today/later feed (mirrors the candidate predicate in ``_load_candidates``).
_CANDIDATE_PREDICATE = (
    "(a.canonical_id IS NULL OR COALESCE(uas.state, 'today') != 'archived')"
    " AND COALESCE(uas.state, 'today') IN ('today', 'later')"
)


@dataclass(frozen=True)
class RecalculationSummary:
    """Outcome of a background recalculation sweep."""

    users_considered: int = 0
    users_recalculated: int = 0
    users_failed: int = 0
    scores_written: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "users_considered": self.users_considered,
            "users_recalculated": self.users_recalculated,
            "users_failed": self.users_failed,
            "scores_written": self.scores_written,
        }


def mark_user_recommendations_stale(
    conn: Any,
    user_id: int,
) -> None:
    """Flag all of a user's stored scores stale after a preference change.

    A workflow action (done/skip/archive/later/star) changes the affinity and
    semantic profile that every one of the user's scores is derived from, so the
    whole set is marked eligible for recalculation rather than trying to guess
    which individual articles moved.  Runs on the caller's connection so it joins
    the same transaction as the state write.
    """
    conn.execute(
        "UPDATE user_article_recommendations SET stale = TRUE WHERE user_id = %s AND stale = FALSE",
        (user_id,),
    )


def find_recalculation_candidates(
    *,
    db_path: Path | None = None,
    database_url: str | None = None,
) -> list[int]:
    """Return ids of users with stale, missing, or superseded scores.

    A user needs recalculation when any of these hold:

    * an existing score is flagged ``stale`` (preference history changed), or
    * an existing score was produced by a model version no longer current
      (scoring formula or embedding scheme changed), or
    * a live today/later candidate article has no stored score at all (new
      article ingested, or a score that previously failed to persist).
    """
    init_db(db_path, database_url=database_url)
    versions = list(CURRENT_MODEL_VERSIONS)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            f"""
            SELECT u.id
            FROM users u
            WHERE EXISTS (
                SELECT 1 FROM user_article_recommendations uar
                WHERE uar.user_id = u.id
                  AND (uar.stale = TRUE OR uar.model_version <> ALL(%s))
            )
            OR EXISTS (
                SELECT 1 FROM articles a
                LEFT JOIN user_article_state uas
                  ON uas.article_id = a.id AND uas.user_id = u.id
                LEFT JOIN user_article_recommendations uar
                  ON uar.user_id = u.id AND uar.article_id = a.id
                WHERE {_CANDIDATE_PREDICATE}
                  AND uar.user_id IS NULL
            )
            ORDER BY u.id
            """,
            (versions,),
        ).fetchall()
    return [int(row_to_dict(row)["id"]) for row in rows]


def recalculate_stale_recommendations(
    *,
    db_path: Path | None = None,
    database_url: str | None = None,
    limit_per_user: int = 1000,
) -> RecalculationSummary:
    """Recompute scores for every user with stale/missing/superseded scores.

    Each user is recomputed independently and guarded so a single failure is
    logged and counted but never aborts the sweep — this is what lets ingestion
    continue when scoring transiently fails for one user.
    """
    user_ids = find_recalculation_candidates(db_path=db_path, database_url=database_url)
    recalculated = 0
    failed = 0
    scores = 0
    for user_id in user_ids:
        try:
            scores += recompute_user_recommendations(
                user_id,
                db_path=db_path,
                database_url=database_url,
                limit=limit_per_user,
            )
            recalculated += 1
        except Exception:
            failed += 1
            logger.exception("Recommendation recalculation failed for user %s", user_id)
    summary = RecalculationSummary(
        users_considered=len(user_ids),
        users_recalculated=recalculated,
        users_failed=failed,
        scores_written=scores,
    )
    logger.info(
        "Recommendation recalculation complete: considered=%d recalculated=%d failed=%d written=%d",
        summary.users_considered,
        summary.users_recalculated,
        summary.users_failed,
        summary.scores_written,
    )
    return summary


def _all_user_ids(*, db_path: Path | None = None, database_url: str | None = None) -> list[int]:
    """Return every user id, ordered, for an unconditional recompute sweep."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute("SELECT id FROM users ORDER BY id").fetchall()
    return [int(row_to_dict(row)["id"]) for row in rows]


def recalculate_all_recommendations(
    *,
    db_path: Path | None = None,
    database_url: str | None = None,
    limit_per_user: int = 1000,
) -> RecalculationSummary:
    """Recompute scores for *every* user, regardless of staleness.

    Unlike :func:`recalculate_stale_recommendations`, this refreshes users whose
    stored scores are neither stale nor missing — needed for the daily sweep
    because the freshness factor decays with article age, so scores drift over
    time even when a user's preferences and the model version are unchanged.
    Per-user failures are isolated so one bad user never aborts the sweep.
    """
    user_ids = _all_user_ids(db_path=db_path, database_url=database_url)
    recalculated = 0
    failed = 0
    scores = 0
    for user_id in user_ids:
        try:
            scores += recompute_user_recommendations(
                user_id,
                db_path=db_path,
                database_url=database_url,
                limit=limit_per_user,
            )
            recalculated += 1
        except Exception:
            failed += 1
            logger.exception("Daily recommendation recalculation failed for user %s", user_id)
    summary = RecalculationSummary(
        users_considered=len(user_ids),
        users_recalculated=recalculated,
        users_failed=failed,
        scores_written=scores,
    )
    logger.info(
        "Daily recommendation recalculation complete: "
        "considered=%d recalculated=%d failed=%d written=%d",
        summary.users_considered,
        summary.users_recalculated,
        summary.users_failed,
        summary.scores_written,
    )
    return summary


def recommendation_health(
    *,
    db_path: Path | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Diagnostic snapshot of stored recommendation freshness.

    Returns total/stale/outdated score counts, the number of live candidate
    pairs missing a score, a per-model-version breakdown, and the oldest score
    timestamp — enough to diagnose stale or missing recommendation data from a
    single admin call without scanning the table by hand.
    """
    init_db(db_path, database_url=database_url)
    versions = list(CURRENT_MODEL_VERSIONS)
    with connect(db_path, database_url=database_url) as conn:
        totals = row_to_dict(
            conn.execute(
                """
                SELECT
                  COUNT(*) AS total_scores,
                  COUNT(*) FILTER (WHERE stale) AS stale_scores,
                  COUNT(*) FILTER (WHERE model_version <> ALL(%s)) AS outdated_scores,
                  MIN(computed_at) AS oldest_computed_at,
                  MAX(updated_at) AS newest_updated_at
                FROM user_article_recommendations
                """,
                (versions,),
            ).fetchone()
        )
        missing = row_to_dict(
            conn.execute(
                f"""
                SELECT COUNT(*) AS missing_scores
                FROM users u
                JOIN articles a ON TRUE
                LEFT JOIN user_article_state uas
                  ON uas.article_id = a.id AND uas.user_id = u.id
                LEFT JOIN user_article_recommendations uar
                  ON uar.user_id = u.id AND uar.article_id = a.id
                WHERE {_CANDIDATE_PREDICATE}
                  AND uar.user_id IS NULL
                """,
            ).fetchone()
        )
        by_version = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT model_version, COUNT(*) AS count
                FROM user_article_recommendations
                GROUP BY model_version
                ORDER BY count DESC, model_version
                """,
            ).fetchall()
        ]

    oldest = totals.get("oldest_computed_at")
    newest = totals.get("newest_updated_at")
    return {
        "total_scores": int(totals.get("total_scores") or 0),
        "stale_scores": int(totals.get("stale_scores") or 0),
        "outdated_scores": int(totals.get("outdated_scores") or 0),
        "missing_scores": int(missing.get("missing_scores") or 0),
        "oldest_computed_at": oldest.isoformat() if oldest is not None else None,
        "newest_updated_at": newest.isoformat() if newest is not None else None,
        "current_model_versions": sorted(CURRENT_MODEL_VERSIONS),
        "by_model_version": [
            {"model_version": row.get("model_version"), "count": int(row.get("count") or 0)}
            for row in by_version
        ],
    }
