from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any

import typer

from news_dashboard.auth import hash_password
from news_dashboard.db import connect, init_db, row_to_dict

app = typer.Typer(help="Migration helpers for news-dashboard")

SOURCE_COLUMNS = [
    "slug",
    "name",
    "url",
    "category",
    "kind",
    "priority",
    "enabled",
    "last_checked_at",
    "last_success_at",
    "last_error",
    "last_fetched_count",
    "last_inserted_count",
]
ARTICLE_COLUMNS = [
    "url",
    "canonical_url",
    "title",
    "source_slug",
    "source_name",
    "category",
    "kind",
    "published_at",
    "summary",
    "reason",
    "importance_score",
    "tags",
    "status",
    "discovered_at",
    "read_at",
    "saved_at",
    "skipped_at",
    "archived_at",
    "updated_at",
]


def _coerce_source_value(column: str, row: sqlite3.Row) -> Any:
    """Map a SQLite source column to a PostgreSQL-compatible value.

    Older dumps lack the newer health columns; the NOT NULL count columns must
    fall back to 0, and SQLite stores ``enabled`` as an integer 0/1 which
    PostgreSQL's boolean column rejects.
    """
    not_null_counts = {"last_fetched_count", "last_inserted_count"}
    present = column in row.keys()  # noqa: SIM118 - sqlite3.Row is not a Mapping
    value = row[column] if present else None
    if column == "enabled":
        return None if value is None else bool(value)
    if column in not_null_counts and value is None:
        return 0
    return value


def sqlite_rows(path: Path, table: str) -> list[sqlite3.Row]:
    sqlite = sqlite3.connect(path)
    sqlite.row_factory = sqlite3.Row
    try:
        return list(sqlite.execute(f"SELECT * FROM {table}"))
    finally:
        sqlite.close()


@app.command("sqlite-to-postgres")
def sqlite_to_postgres(
    sqlite_path: Annotated[Path, typer.Argument(help="Existing SQLite database path")],
) -> None:
    if not os.getenv("POSTGRES_HOST") and not os.getenv("DATABASE_URL"):
        message = "Set POSTGRES_* env vars or DATABASE_URL before migrating"
        raise typer.BadParameter(message)
    if not sqlite_path.exists():
        message = f"SQLite DB not found: {sqlite_path}"
        raise typer.BadParameter(message)

    init_db()
    sources = sqlite_rows(sqlite_path, "sources")
    articles = sqlite_rows(sqlite_path, "articles")
    with connect() as conn:
        for row in sources:
            # Gracefully handle older SQLite dumps that lack new health columns
            source_values = tuple(_coerce_source_value(c, row) for c in SOURCE_COLUMNS)
            conn.execute(
                """
                INSERT INTO sources(
                  slug, name, url, category, kind, priority, enabled, last_checked_at,
                  last_success_at, last_error, last_fetched_count, last_inserted_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(slug) DO UPDATE SET
                  name=excluded.name,
                  url=excluded.url,
                  category=excluded.category,
                  kind=excluded.kind,
                  priority=excluded.priority,
                  enabled=excluded.enabled,
                  last_checked_at=excluded.last_checked_at,
                  last_success_at=excluded.last_success_at,
                  last_error=excluded.last_error,
                  last_fetched_count=excluded.last_fetched_count,
                  last_inserted_count=excluded.last_inserted_count
                """,
                source_values,
            )
        for row in articles:
            article_values: tuple[Any, ...] = tuple(row[column] for column in ARTICLE_COLUMNS)
            conn.execute(
                """
                INSERT INTO articles(
                  url, canonical_url, title, source_slug, source_name, category, kind, published_at,
                  summary, reason, importance_score, tags, status, discovered_at, read_at, saved_at,
                  skipped_at, archived_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (url) DO UPDATE SET
                  title=excluded.title,
                  source_slug=excluded.source_slug,
                  source_name=excluded.source_name,
                  category=excluded.category,
                  kind=excluded.kind,
                  published_at=excluded.published_at,
                  summary=excluded.summary,
                  reason=excluded.reason,
                  importance_score=excluded.importance_score,
                  tags=excluded.tags,
                  status=excluded.status,
                  read_at=excluded.read_at,
                  saved_at=excluded.saved_at,
                  skipped_at=excluded.skipped_at,
                  archived_at=excluded.archived_at,
                  updated_at=excluded.updated_at
                """,
                article_values,
            )
    typer.echo(
        f"Migrated {len(sources)} source(s) and {len(articles)} article(s) from {sqlite_path}"
    )


def _row_count(row: Any) -> int:
    """Extract an integer from a PostgreSQL COUNT(*) row."""
    if row is None:
        return 0
    try:
        d = row_to_dict(row)
        return int(d.get("count") or 0)
    except Exception:
        try:
            return int(row[0])
        except Exception:
            return 0


def _check_prerequisites(conn: Any) -> list[str]:
    """Return a list of missing prerequisite schema items."""
    missing: list[str] = []
    required_tables = ["users", "user_article_state", "user_sources"]
    for tbl in required_tables:
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables"
            " WHERE table_name = %s AND table_schema = current_schema()",
            (tbl,),
        ).fetchone()
        if row is None:
            missing.append(f"table '{tbl}'")

    try:
        conn.execute("SELECT user_id FROM briefings LIMIT 0")
    except Exception:
        missing.append("column 'briefings.user_id'")

    return missing


@app.command("migrate-multi-user")
def migrate_multi_user(  # noqa: PLR0912, PLR0915
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print planned actions only")] = False,
) -> None:
    """Promote existing single-tenant data to the first user account."""
    with connect() as conn:
        # ── 1. Check prerequisites ─────────────────────────────────────────────
        missing = _check_prerequisites(conn)
        if missing:
            typer.echo("ERROR: prerequisite schema missing:")
            for item in missing:
                typer.echo(f"  - {item}")
            typer.echo("Run 'news-dashboard init' to apply schema migrations first.")
            raise typer.Exit(code=1)

        # ── 2. Seed user ───────────────────────────────────────────────────────
        user_count = _row_count(conn.execute("SELECT COUNT(*) FROM users").fetchone())

        if user_count > 0:
            typer.echo(f"Users already exist ({user_count}); skipping seed user creation.")
            seed_row = conn.execute("SELECT id, username FROM users ORDER BY id LIMIT 1").fetchone()
            seed_uid = int(row_to_dict(seed_row)["id"])
            seed_username = str(row_to_dict(seed_row)["username"])
            typer.echo(f"Using existing first user: {seed_username!r} (id={seed_uid})")
        else:
            seed_username = os.getenv("SEED_USER") or typer.prompt("Seed username")
            seed_password = os.getenv("SEED_PASSWORD") or typer.prompt(
                "Seed password", hide_input=True, confirmation_prompt=True
            )
            if dry_run:
                typer.echo(f"[dry-run] Would create user {seed_username!r}")
                seed_uid = -1
            else:
                pw_hash = hash_password(seed_password)
                row = conn.execute(
                    "INSERT INTO users(username, password_hash, is_admin)"
                    " VALUES(%s, %s, TRUE) RETURNING id",
                    (seed_username, pw_hash),
                ).fetchone()
                if row is None:
                    message = "User insert returned no row"
                    raise RuntimeError(message)
                seed_uid = int(row_to_dict(row)["id"])
                typer.echo(f"Created seed user {seed_username!r} (id={seed_uid}, is_admin=1)")

        if dry_run and seed_uid == -1:
            typer.echo("[dry-run] Skipping data migration steps (no real user id)")
            raise typer.Exit(0)

        # ── 3. Migrate article state ───────────────────────────────────────────
        articles = conn.execute(
            """
            SELECT id, state, starred, done_at, starred_at, later_until, restored_at, skipped_at
            FROM articles
            WHERE (
              state != 'today'
              OR starred IS TRUE
              OR done_at IS NOT NULL
              OR starred_at IS NOT NULL
            )
            """
        ).fetchall()

        uas_inserted = 0
        for art in articles:
            d = row_to_dict(art)
            if dry_run:
                uas_inserted += 1
                continue
            conn.execute(
                """
                INSERT INTO user_article_state(
                  user_id, article_id, state, starred,
                  done_at, starred_at, skipped_at, later_until, restored_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(user_id, article_id) DO NOTHING
                """,
                (
                    seed_uid,
                    d["id"],
                    d.get("state", "today"),
                    bool(d.get("starred")),
                    d.get("done_at"),
                    d.get("starred_at"),
                    d.get("skipped_at"),
                    d.get("later_until"),
                    d.get("restored_at"),
                ),
            )
            uas_inserted += 1

        action = "[dry-run] Would migrate" if dry_run else "Migrated"
        typer.echo(f"{action} {uas_inserted} article state row(s) → user_article_state")

        # ── 4. Migrate briefings ───────────────────────────────────────────────
        briefing_count = _row_count(
            conn.execute("SELECT COUNT(*) FROM briefings WHERE user_id IS NULL").fetchone()
        )

        if dry_run:
            typer.echo(f"[dry-run] Would migrate {briefing_count} briefing(s) → user_id={seed_uid}")
        else:
            conn.execute(
                "UPDATE briefings SET user_id = %s WHERE user_id IS NULL",
                (seed_uid,),
            )
            typer.echo(f"Migrated {briefing_count} briefing(s) → user_id={seed_uid}")

        # ── 5. Seed source subscriptions ──────────────────────────────────────
        enabled_sources = conn.execute(
            "SELECT slug FROM sources"
            " WHERE enabled IS TRUE"
            " AND (owner_user_id IS NULL OR owner_user_id = %s)",
            (seed_uid,),
        ).fetchall()

        us_inserted = 0
        for src in enabled_sources:
            slug = src[0] if isinstance(src, tuple) else row_to_dict(src)["slug"]
            if dry_run:
                us_inserted += 1
                continue
            conn.execute(
                "INSERT INTO user_sources(user_id, source_slug, enabled)"
                " VALUES(%s, %s, TRUE) ON CONFLICT(user_id, source_slug) DO NOTHING",
                (seed_uid, slug),
            )
            us_inserted += 1

        action = "[dry-run] Would insert" if dry_run else "Inserted"
        typer.echo(f"{action} {us_inserted} source subscription(s) → user_sources")

    typer.echo("Done.")


if __name__ == "__main__":
    app()
