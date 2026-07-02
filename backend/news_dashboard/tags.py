"""User-defined tags for organizing articles into free-form collections.

Tags are per-user and orthogonal to Workflow State (see CONTEXT.md): an
article can be ``done`` and tagged ``rust`` at the same time. A tag applies
to an article via the ``article_tags`` join table; deleting a tag removes
its associations without touching the article itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db


def create_tag(
    user_id: int,
    name: str,
    color: str | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_tags (user_id, name, color)
            VALUES (%s, %s, %s)
            RETURNING id, user_id, name, color, created_at
            """,
            (user_id, name.strip(), color),
        ).fetchone()
    return dict(row)


def list_tags(
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.user_id, t.name, t.color, t.created_at,
              COUNT(at.article_id) AS article_count
            FROM user_tags t
            LEFT JOIN article_tags at ON at.tag_id = t.id AND at.user_id = t.user_id
            WHERE t.user_id = %s
            GROUP BY t.id
            ORDER BY t.name ASC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def rename_tag(
    tag_id: int,
    user_id: int,
    name: str,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE user_tags SET name = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, name, color, created_at
            """,
            (name.strip(), tag_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def delete_tag(
    tag_id: int,
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> bool:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        result = conn.execute(
            "DELETE FROM user_tags WHERE id = %s AND user_id = %s",
            (tag_id, user_id),
        )
        return bool(result.rowcount > 0)


def add_tag_to_article(
    user_id: int,
    article_id: int,
    tag_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> bool:
    """Attach a tag to an article. Returns False if the tag isn't owned by user_id."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        owned = conn.execute(
            "SELECT 1 FROM user_tags WHERE id = %s AND user_id = %s",
            (tag_id, user_id),
        ).fetchone()
        if not owned:
            return False
        conn.execute(
            """
            INSERT INTO article_tags (user_id, article_id, tag_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, article_id, tag_id) DO NOTHING
            """,
            (user_id, article_id, tag_id),
        )
        return True


def remove_tag_from_article(
    user_id: int,
    article_id: int,
    tag_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> bool:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        result = conn.execute(
            "DELETE FROM article_tags WHERE user_id = %s AND article_id = %s AND tag_id = %s",
            (user_id, article_id, tag_id),
        )
        return bool(result.rowcount > 0)


def list_tags_for_article(
    user_id: int,
    article_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.user_id, t.name, t.color, t.created_at
            FROM article_tags at
            JOIN user_tags t ON t.id = at.tag_id
            WHERE at.user_id = %s AND at.article_id = %s
            ORDER BY t.name ASC
            """,
            (user_id, article_id),
        ).fetchall()
    return [dict(r) for r in rows]
