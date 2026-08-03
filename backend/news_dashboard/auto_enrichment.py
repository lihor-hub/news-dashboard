"""Bounded, consent-based article AI enrichment after ingestion."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Any

from news_dashboard.db import connect

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentSummary:
    eligible: int = 0
    attempted: int = 0
    cached: int = 0
    generated: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def auto_enrich_limit() -> int:
    try:
        configured = int(os.getenv("AI_AUTO_ENRICH_LIMIT", "5"))
    except ValueError:
        configured = 5
    return min(20, max(0, configured))


def ai_available() -> bool:
    return bool(os.getenv("FREE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _candidates(limit: int, database_url: str | None) -> tuple[int, list[dict[str, Any]]]:
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            WITH visible_candidates AS (
            SELECT a.id AS article_id, u.id AS user_id,
              a.insights IS NOT NULL AS insights_cached,
              a.perspective_analysis IS NOT NULL AS perspectives_cached,
              COALESCE(r.recommendation_score, 0) AS recommendation_score,
              a.discovered_at,
              ROW_NUMBER() OVER (
                PARTITION BY a.id
                ORDER BY r.recommendation_score DESC NULLS LAST, u.id
              ) AS user_rank
            FROM articles a
            JOIN sources src ON src.slug = a.source_slug
            JOIN users u ON u.auto_ai_enrichment_enabled = TRUE
            LEFT JOIN user_sources us
              ON us.user_id = u.id AND us.source_slug = a.source_slug
            LEFT JOIN user_article_recommendations r
              ON r.user_id = u.id AND r.article_id = a.id
            WHERE a.body_status = 'ok'
              AND a.discovered_at >= NOW() - INTERVAL '7 days'
              AND (a.insights IS NULL OR a.perspective_analysis IS NULL)
              AND ((src.owner_user_id IS NULL AND COALESCE(us.enabled, TRUE))
                   OR src.owner_user_id = u.id)
            )
            SELECT article_id, user_id, insights_cached, perspectives_cached,
                   COUNT(*) OVER () AS total_eligible
            FROM visible_candidates
            WHERE user_rank = 1
            ORDER BY recommendation_score DESC, discovered_at DESC, article_id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    candidates = [dict(row) for row in rows]
    eligible = int(candidates[0]["total_eligible"]) if candidates else 0
    return eligible, candidates


def run_auto_enrichment(database_url: str | None = None) -> EnrichmentSummary:
    summary = EnrichmentSummary()
    limit = auto_enrich_limit()
    if limit == 0 or not ai_available():
        return summary
    summary.eligible, candidates = _candidates(limit, database_url)
    from news_dashboard.insights import get_or_generate_insights
    from news_dashboard.perspectives import get_or_generate_perspectives

    for item in candidates:
        summary.attempted += 1
        article_id, user_id = int(item["article_id"]), int(item["user_id"])
        for cache_key, generator in (
            ("insights_cached", get_or_generate_insights),
            ("perspectives_cached", get_or_generate_perspectives),
        ):
            if item[cache_key]:
                summary.cached += 1
                continue
            try:
                result = generator(article_id, user_id=user_id, database_url=database_url)
                if result:
                    summary.generated += 1
                else:
                    summary.skipped += 1
            except Exception as exc:
                summary.failed += 1
                logger.warning(
                    "Automatic AI enrichment failed: article_id=%d type=%s error=%s",
                    article_id,
                    cache_key,
                    type(exc).__name__,
                )
    logger.info("Automatic AI enrichment: %s", summary.as_dict())
    return summary


def prefetch_then_auto_enrich() -> EnrichmentSummary:
    from news_dashboard.body_fetch import prefetch_article_bodies

    prefetch_article_bodies()
    return run_auto_enrichment()
