from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect, init_db


def upsert_recommendation_score(
    user_id: int,
    article_id: int,
    recommendation_score: float,
    *,
    db_path: Path | None = None,
    cold_start_score: float | None = None,
    signals: dict[str, Any] | None = None,
    model_version: str = "cold-start-v1",
) -> None:
    """Persist recommendation metadata for one user/article pair."""
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_article_recommendations(
              user_id, article_id, recommendation_score, cold_start_score, signals, model_version
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT(user_id, article_id) DO UPDATE SET
              recommendation_score = excluded.recommendation_score,
              cold_start_score = excluded.cold_start_score,
              signals = excluded.signals,
              model_version = excluded.model_version,
              updated_at = NOW()
            """,
            (
                user_id,
                article_id,
                float(recommendation_score),
                cold_start_score,
                json.dumps(signals or {}),
                model_version,
            ),
        )
