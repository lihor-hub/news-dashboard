"""Assemble a portable JSON archive of a user's personal reading data."""

from __future__ import annotations

from typing import Any

from news_dashboard.db import connect, row_to_dict


def assemble_user_export(
    user_id: int,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic JSON-serialisable dict of the user's reading archive.

    Includes:
    - articles the user has explicitly interacted with (user_article_state rows),
      joined with article metadata (title, URL, category, summary, tags, body).
    - user-owned briefings with their cited article IDs.

    Data is ordered by stable keys (id / created_at) so the output is
    deterministic enough for snapshot-style tests.
    """
    with connect(database_url=database_url) as conn:
        article_rows = conn.execute(
            """
            SELECT
                a.id,
                a.canonical_url,
                a.title,
                a.source_slug,
                a.source_name,
                a.category,
                a.kind,
                a.published_at,
                a.discovered_at,
                a.summary,
                a.reason,
                a.tags,
                a.body,
                uas.state,
                uas.starred,
                uas.done_at,
                uas.starred_at,
                uas.skipped_at,
                uas.archived_at,
                uas.later_until,
                uas.restored_at,
                uas.updated_at
            FROM user_article_state uas
            JOIN articles a ON a.id = uas.article_id
            WHERE uas.user_id = %s
            ORDER BY a.id ASC
            """,
            (user_id,),
        ).fetchall()

        articles: list[dict[str, Any]] = []
        for row in article_rows:
            d = row_to_dict(row)
            # Normalise timestamps to ISO strings for portability.
            for ts_col in (
                "done_at",
                "starred_at",
                "skipped_at",
                "archived_at",
                "later_until",
                "restored_at",
                "updated_at",
            ):
                val = d.get(ts_col)
                if val is not None and not isinstance(val, str):
                    d[ts_col] = val.isoformat()
            articles.append(d)

        briefing_rows = conn.execute(
            """
            SELECT
                b.id,
                b.created_at,
                b.scope,
                b.since_at,
                b.until_at,
                b.status,
                b.title,
                b.summary,
                b.focus_prompt,
                b.model
            FROM briefings b
            WHERE b.user_id = %s
            ORDER BY b.id ASC
            """,
            (user_id,),
        ).fetchall()

        briefings: list[dict[str, Any]] = []
        for brow in briefing_rows:
            bd = row_to_dict(brow)
            for ts_col in ("created_at", "since_at", "until_at"):
                val = bd.get(ts_col)
                if val is not None and not isinstance(val, str):
                    bd[ts_col] = val.isoformat()

            cited_rows = conn.execute(
                """
                SELECT ba.article_id, a.canonical_url
                FROM briefing_articles ba
                JOIN articles a ON a.id = ba.article_id
                WHERE ba.briefing_id = %s
                ORDER BY ba.article_id ASC
                """,
                (bd["id"],),
            ).fetchall()
            bd["cited_articles"] = [
                {"article_id": r["article_id"], "canonical_url": r["canonical_url"]}
                for r in cited_rows
            ]
            briefings.append(bd)

    return {
        "schema_version": 1,
        "articles": articles,
        "briefings": briefings,
    }
