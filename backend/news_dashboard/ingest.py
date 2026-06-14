from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser

from .db import connect, init_db, insert_article_sql, is_postgres, row_to_dict
from .ingest_events import ingest_events
from .sources import DEFAULT_SOURCES, SourceDefinition

try:
    from rapidfuzz.distance import Levenshtein

    def _title_similarity(a: str, b: str) -> float:
        a, b = a.lower().strip(), b.lower().strip()
        if not a or not b:
            return 0.0
        max_len = max(len(a), len(b))
        dist = Levenshtein.distance(a, b)
        return 1.0 - dist / max_len
except ImportError:

    def _title_similarity(a: str, b: str) -> float:
        # Fallback: simple token-overlap Jaccard similarity
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)


logger = logging.getLogger(__name__)

DEDUP_TITLE_THRESHOLD = 0.85
VALID_STATUSES = frozenset({"new", "read", "saved", "skipped", "archived"})
VALID_STATES = frozenset({"today", "later", "done", "skipped", "archived"})

# (from_state, to_state) pairs that are permitted
_ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("today", "done"),
        ("today", "later"),
        ("today", "skipped"),
        ("today", "archived"),
        ("later", "today"),
        ("later", "done"),
        ("later", "archived"),
        ("done", "archived"),
        ("skipped", "today"),
        ("skipped", "archived"),
        ("archived", "today"),
        ("archived", "done"),
    }
)
_INGEST_RUN_LOCK = threading.Lock()


class FeedFetchError(RuntimeError):
    """Raised when a feed could not be fetched or parsed."""


@dataclass(frozen=True)
class SourceIngestOutcome:
    source_name: str
    articles_found: int
    articles_new: int
    duration_seconds: float
    error_message: str | None = None


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "fbclid",
    "gclid",
    "yclid",
}

KEYWORD_TAGS = {
    "python": [
        "python",
        "typing",
        "mypy",
        "pyright",
        "ruff",
        "uv",
        "pypi",
        "scipy",
        "sklearn",
        "pytorch",
        "tensorflow",
        "pip",
    ],
    "agents": [
        "agent",
        "agents",
        "agentic",
        "langgraph",
        "langchain",
        "tool use",
        "workflow",
        "mcp",
        "multi-agent",
    ],
    "llm": [
        "llm",
        "language model",
        "openai",
        "anthropic",
        "claude",
        "gemini",
        "rag",
        "retrieval",
        "embeddings",
        "transformer",
    ],
    "infra": [
        "kubernetes",
        "k8s",
        "docker",
        "podman",
        "aws",
        "gcp",
        "azure",
        "container",
        "helm",
        "terraform",
    ],
    "data": ["data", "analytics", "observability", "evaluation", "benchmark", "metrics", "dataset"],
    "release": [
        "release",
        "v0.",
        "v1.",
        "v2.",
        "v3.",
        "v4.",
        "v5.",
        "changelog",
        "update",
        "new version",
    ],
    "security": ["security", "vulnerability", "cve", "exploit", "patch", "advisory"],
    "tutorial": ["tutorial", "how to", "guide", "getting started", "introduction", "deep dive"],
}

# Per-source noise-filter rules: (max_items_per_run, keyword_include_list)
# keyword_include_list: keep entry only if title/summary contains at least one keyword
# None keyword_include = no filter
NOISE_FILTERS: dict[str, dict[str, Any]] = {
    "hacker-news-best": {"max_items": 20, "keywords": None},
    "hacker-news-ai": {"max_items": 15, "keywords": None},
    "github-trending-all": {"max_items": 15, "keywords": None},
    "github-trending-python": {"max_items": 10, "keywords": None},
    "github-trending-typescript": {"max_items": 10, "keywords": None},
    "infoq-ai-ml": {"max_items": 10, "keywords": None},
    "import-ai": {"max_items": 5, "keywords": None},
    "latent-space": {"max_items": 5, "keywords": None},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    parsed = parsed._replace(fragment="", query=urlencode(query, doseq=True))
    return urlunparse(parsed)


def parse_date(entry: Any) -> str | None:
    for key in ("published", "updated", "created"):
        value = getattr(entry, key, None) or entry.get(key)
        if value:
            try:
                return (
                    parsedate_to_datetime(value)
                    .astimezone(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                )
            except Exception:
                return str(value)
    return None


def infer_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []
    for tag, keywords in KEYWORD_TAGS.items():
        if any(kw in lowered for kw in keywords):
            tags.append(tag)
    return tags


def make_reason(  # noqa: PLR0911 - a flat "first match wins" rule chain is clearest here
    title: str, source: SourceDefinition, tags: list[str]
) -> str:
    """Generate a meaningful 'why this matters' blurb from content signals."""
    # Release feeds: mention version if detectable
    if source.kind in ("github_release_feed",) or "release" in tags:
        # Try to extract a version number like v1.2.3
        m = re.search(r"\bv?(\d+\.\d+[\d.a-z-]*)\b", title, re.I)
        version = m.group(0) if m else None
        if version:
            return f"New release {version} from {source.name}."
        return f"New release from {source.name}."

    if "security" in tags:
        return f"Security update from {source.name} — review recommended."

    if "tutorial" in tags:
        cat_label = source.category.replace("-", "/")
        return f"How-to or deep-dive on {cat_label} from {source.name}."

    if source.kind == "trending_feed":
        if "hacker-news" in source.slug:
            return "Trending on Hacker News."
        if "github" in source.slug:
            lang = source.slug.split("-")[-1].title()
            return f"Trending {lang} repository on GitHub today."
        return f"Trending item from {source.name}."

    if "agents" in tags or "llm" in tags:
        return f"AI/agent development news from {source.name}."

    if "python" in tags:
        return f"Python ecosystem update from {source.name}."

    if "infra" in tags:
        return f"Cloud/infrastructure update from {source.name}."

    # Fallback: slightly more informative than before
    cat_label = source.category.replace("-", " ")
    return f"{cat_label.title()} — {source.name}."


def make_summary(
    title: str, description: str, source: SourceDefinition
) -> tuple[str, str, int, str]:
    text = clean_html(description)
    summary = text[:280] + ("…" if len(text) > 280 else "")
    tags = infer_tags(f"{title} {text} {source.category}")
    reason = make_reason(title, source, tags)
    score = min(100, source.priority + (10 if tags else 0))
    return summary, reason, score, ",".join(tags)


def _should_include(title: str, description: str, source_slug: str) -> bool:
    """Apply optional keyword include-filter for noisy sources."""
    rule = NOISE_FILTERS.get(source_slug)
    if not rule or rule.get("keywords") is None:
        return True
    haystack = (title + " " + description).lower()
    return any(kw in haystack for kw in rule["keywords"])


def _find_canonical(conn: Any, canonical_url: str, title: str) -> int | None:
    """Return the id of an existing canonical article matching by URL or fuzzy title, or None."""
    # Exact URL match (canonical_url already stripped of tracking params)
    row = conn.execute(
        """
        SELECT id FROM articles
        WHERE canonical_url=? AND (canonical_id IS NULL OR canonical_id=id)
        LIMIT 1
        """,
        (canonical_url,),
    ).fetchone()
    if row:
        return int(row["id"] if isinstance(row, dict) else row[0])

    # Fuzzy title match against recent articles (last 7 days) that are canonical
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = conn.execute(
        """SELECT id, title FROM articles
           WHERE canonical_id IS NULL
             AND discovered_at >= ?
           ORDER BY discovered_at DESC
           LIMIT 200""",
        (cutoff,),
    ).fetchall()
    for r in rows:
        existing_title = str(r["title"] if isinstance(r, dict) else r[1])
        existing_id = int(r["id"] if isinstance(r, dict) else r[0])
        if _title_similarity(title, existing_title) >= DEDUP_TITLE_THRESHOLD:
            return existing_id
    return None


def sync_sources(db_path: Path | None = None) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        for source in DEFAULT_SOURCES:
            conn.execute(
                """
                INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(slug) DO UPDATE SET
                  name=excluded.name,
                  url=excluded.url,
                  category=excluded.category,
                  kind=excluded.kind,
                  priority=excluded.priority
                """,
                (
                    source.slug,
                    source.name,
                    source.url,
                    source.category,
                    source.kind,
                    source.priority,
                ),
            )


def _fetch_feed_entries(source: SourceDefinition) -> list[dict[str, Any]]:
    """Fetch and normalize feed entries, surfacing fetch failures as FeedFetchError."""
    parsed = feedparser.parse(source.url, agent="news-dashboard/0.1 (personal; contact@lihor.ro)")
    # feedparser swallows network errors via bozo; surface them so health tracking works
    if parsed.bozo and not parsed.entries:
        exc = getattr(parsed, "bozo_exception", None)
        message = f"Feed fetch failed: {exc or 'no entries, bozo=True'}"
        raise FeedFetchError(message)
    return [
        {
            "url": e.get("link") or e.get("id") or "",
            "title": e.get("title") or "Untitled",
            "description": e.get("summary") or e.get("description") or "",
            "date": parse_date(e),
        }
        for e in parsed.entries
    ]


def _ingest_source(source: SourceDefinition, db_path: Path | None = None) -> SourceIngestOutcome:
    """Fetch and insert articles for a single source. Returns count inserted."""
    from .scraper import scrape_source

    checked_at = now_iso()
    inserted = 0
    fetched = 0
    started = time.perf_counter()

    try:
        entries = (
            scrape_source(source) if source.kind == "scraped_page" else _fetch_feed_entries(source)
        )

        # Apply per-source item limit
        noise_rule = NOISE_FILTERS.get(source.slug, {})
        max_items = noise_rule.get("max_items", 50)
        entries = entries[:max_items]
        fetched = len(entries)

        with connect(db_path) as conn:
            for entry in entries:
                raw_url = entry.get("url", "")
                if not raw_url:
                    continue
                url = canonicalize_url(raw_url)
                title = clean_html(entry.get("title") or "Untitled")
                description = entry.get("description", "")

                if not _should_include(title, description, source.slug):
                    continue

                summary, reason, score, tags = make_summary(title, description, source)

                # Deduplication: check if this article is a duplicate of an existing canonical
                canonical_id = _find_canonical(conn, url, title)
                if canonical_id is not None:
                    # Insert as archived duplicate pointing to canonical
                    conn.execute(
                        """INSERT INTO articles(
                             url, canonical_url, title, source_slug, source_name, category, kind,
                             published_at, summary, reason, importance_score, tags,
                             status, canonical_id
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'archived', ?)
                           ON CONFLICT (url) DO NOTHING""",
                        (
                            url,
                            url,
                            title,
                            source.slug,
                            source.name,
                            source.category,
                            source.kind,
                            entry.get("date"),
                            summary,
                            reason,
                            score,
                            tags,
                            canonical_id,
                        ),
                    )
                    # Tag canonical article's source list (stored in reason prefix)
                    conn.execute(
                        """UPDATE articles SET updated_at=? WHERE id=? AND canonical_id IS NULL""",
                        (now_iso(), canonical_id),
                    )
                else:
                    sql = insert_article_sql()
                    if not is_postgres():
                        sql = sql.replace("%s", "?")
                    cursor = conn.execute(
                        sql,
                        (
                            url,
                            url,
                            title,
                            source.slug,
                            source.name,
                            source.category,
                            source.kind,
                            entry.get("date"),
                            summary,
                            reason,
                            score,
                            tags,
                        ),
                    )
                    inserted += cursor.rowcount

            conn.execute(
                """UPDATE sources SET
                     last_checked_at=?, last_success_at=?, last_error=NULL,
                     last_fetched_count=?, last_inserted_count=?
                   WHERE slug=?""",
                (checked_at, checked_at, fetched, inserted, source.slug),
            )

    except Exception as exc:
        error_msg = str(exc)[:500]
        with connect(db_path) as conn:
            conn.execute(
                """UPDATE sources SET
                     last_checked_at=?, last_error=?,
                     last_fetched_count=0, last_inserted_count=0
                   WHERE slug=?""",
                (checked_at, error_msg, source.slug),
            )
        return SourceIngestOutcome(
            source_name=source.name,
            articles_found=fetched,
            articles_new=0,
            duration_seconds=time.perf_counter() - started,
            error_message=error_msg,
        )

    return SourceIngestOutcome(
        source_name=source.name,
        articles_found=fetched,
        articles_new=inserted,
        duration_seconds=time.perf_counter() - started,
    )


def ingest_source(source: SourceDefinition, db_path: Path | None = None) -> int:
    """Fetch and insert articles for a single source. Returns count inserted."""
    outcome = _ingest_source(source, db_path)
    if outcome.error_message is not None:
        raise RuntimeError(outcome.error_message)
    return outcome.articles_new


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    try:
        return row[key]
    except Exception:
        return row[index]


def _create_ingest_run(db_path: Path | None, started_at: str) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO ingest_runs(started_at) VALUES (?) RETURNING id",
            (started_at,),
        ).fetchone()
    return int(_row_value(row, "id", 0))


def _record_ingest_source(run_id: int, outcome: SourceIngestOutcome, db_path: Path | None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                outcome.source_name,
                outcome.articles_found,
                outcome.articles_new,
                outcome.error_message,
            ),
        )


def _finish_ingest_run(
    run_id: int,
    db_path: Path | None,
    finished_at: str,
    duration_ms: int,
    total_new: int,
    total_errors: int,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE ingest_runs
               SET finished_at=?, duration_ms=?, total_new=?, total_errors=?
             WHERE id=?
            """,
            (finished_at, duration_ms, total_new, total_errors, run_id),
        )


def _format_source_log(outcome: SourceIngestOutcome) -> str:
    if outcome.error_message:
        return f"✗ {outcome.source_name} — {outcome.error_message}"
    article_word = "article" if outcome.articles_new == 1 else "articles"
    return (
        f"✓ {outcome.source_name} — {outcome.articles_new} new {article_word} "
        f"({outcome.duration_seconds:.1f}s)"
    )


def ingest_all(db_path: Path | None = None) -> dict[str, int]:
    with _INGEST_RUN_LOCK:
        sync_sources(db_path)
        run_started_at = now_iso()
        run_started = time.perf_counter()
        run_id = _create_ingest_run(db_path, run_started_at)
        ingest_events.start_run(run_id, f"Ingest run #{run_id} started at {run_started_at}")

        # Collect sources to ingest: DEFAULT_SOURCES + enabled user-owned private sources
        sources_to_ingest: list[SourceDefinition] = [s for s in DEFAULT_SOURCES if s.enabled]
        with connect(db_path) as conn:
            private_rows = conn.execute(
                "SELECT slug, name, url, category, kind, priority"
                " FROM sources WHERE owner_user_id IS NOT NULL AND enabled = 1"
            ).fetchall()
        for row in private_rows:
            r = row_to_dict(row)
            sources_to_ingest.append(
                SourceDefinition(
                    slug=r["slug"],
                    name=r["name"],
                    url=r["url"],
                    category=r["category"],
                    kind=r["kind"],
                    priority=int(r["priority"] or 0),
                )
            )

        results: dict[str, int] = {}
        total_new = 0
        total_errors = 0
        try:
            for source in sources_to_ingest:
                outcome = _ingest_source(source, db_path)
                _record_ingest_source(run_id, outcome, db_path)
                ingest_events.append_line(_format_source_log(outcome))
                if outcome.error_message is not None:
                    results[source.slug] = -1
                    total_errors += 1
                else:
                    results[source.slug] = outcome.articles_new
                    total_new += outcome.articles_new
        finally:
            duration_seconds = time.perf_counter() - run_started
            duration_ms = int(duration_seconds * 1000)
            _finish_ingest_run(run_id, db_path, now_iso(), duration_ms, total_new, total_errors)
            article_word = "article" if total_new == 1 else "articles"
            error_text = (
                f", {total_errors} error{'s' if total_errors != 1 else ''}" if total_errors else ""
            )
            ingest_events.complete_run(
                f"Summary — {total_new} new {article_word}{error_text} ({duration_seconds:.1f}s)"
            )
    return results


_INTERNAL_ARTICLE_COLUMNS = frozenset({"embedding", "fts_vector"})

# UAS columns that override article-level state when a user_id is provided
_UAS_STATE_COLUMNS = frozenset(
    {
        "state",
        "starred",
        "done_at",
        "starred_at",
        "skipped_at",
        "archived_at",
        "later_until",
        "restored_at",
    }
)


def _article_dict(row: Any) -> dict[str, Any]:
    """Convert a DB row to a dict, stripping internal-only columns.

    'embedding' (BLOB/BYTEA) contains binary float data that is not
    UTF-8-safe and must never be sent to the frontend.  'fts_vector'
    (Postgres GENERATED ALWAYS tsvector) is similarly internal.
    """
    d = row_to_dict(row)
    for col in _INTERNAL_ARTICLE_COLUMNS:
        d.pop(col, None)
    return d


def _merge_uas(article: dict[str, Any], uas: dict[str, Any] | None) -> dict[str, Any]:
    """Overlay per-user state from a user_article_state row onto an article dict.

    When uas is None the article is implicitly in the 'today' state for the user
    (the row doesn't exist yet because the user hasn't acted on it).
    """
    if uas is None:
        article["state"] = "today"
        article["starred"] = False
        for col in (
            "done_at",
            "starred_at",
            "skipped_at",
            "archived_at",
            "later_until",
            "restored_at",
        ):
            article[col] = None
    else:
        article["state"] = uas.get("state") or "today"
        article["starred"] = bool(uas.get("starred", False))
        article["done_at"] = uas.get("done_at")
        article["starred_at"] = uas.get("starred_at")
        article["skipped_at"] = uas.get("skipped_at")
        article["archived_at"] = uas.get("archived_at")
        article["later_until"] = uas.get("later_until")
        article["restored_at"] = uas.get("restored_at")
    return article


def _fetch_uas_map(conn: Any, article_ids: list[int], user_id: int) -> dict[int, dict[str, Any]]:
    """Return a map of article_id → UAS row dict for the given user and article IDs."""
    if not article_ids:
        return {}
    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"SELECT * FROM user_article_state WHERE user_id = ? AND article_id IN ({placeholders})",
        [user_id, *article_ids],
    ).fetchall()
    return {row_to_dict(r)["article_id"]: row_to_dict(r) for r in rows}


def _get_uas_row(conn: Any, article_id: int, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM user_article_state WHERE user_id = ? AND article_id = ?",
        (user_id, article_id),
    ).fetchone()
    return row_to_dict(row) if row else None


def _upsert_uas(  # noqa: PLR0913
    conn: Any,
    user_id: int,
    article_id: int,
    *,
    state: str,
    starred: bool,
    done_at: str | None = None,
    starred_at: str | None = None,
    skipped_at: str | None = None,
    archived_at: str | None = None,
    later_until: str | None = None,
    restored_at: str | None = None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO user_article_state(
          user_id, article_id, state, starred,
          done_at, starred_at, skipped_at, archived_at, later_until, restored_at, updated_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, article_id) DO UPDATE SET
          state = excluded.state,
          starred = excluded.starred,
          done_at = COALESCE(excluded.done_at, user_article_state.done_at),
          starred_at = COALESCE(excluded.starred_at, user_article_state.starred_at),
          skipped_at = COALESCE(excluded.skipped_at, user_article_state.skipped_at),
          archived_at = COALESCE(excluded.archived_at, user_article_state.archived_at),
          later_until = excluded.later_until,
          restored_at = COALESCE(excluded.restored_at, user_article_state.restored_at),
          updated_at = excluded.updated_at
        """,
        (
            user_id,
            article_id,
            state,
            1 if starred else 0,
            done_at,
            starred_at,
            skipped_at,
            archived_at,
            later_until,
            restored_at,
            updated_at,
        ),
    )


def list_articles(  # noqa: PLR0913
    status: str | None = None,
    state: str | None = None,
    category: str | None = None,
    starred: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    db_path: Path | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    now = now_iso()

    if user_id is not None:
        return _list_articles_for_user(
            user_id=user_id,
            status=status,
            state=state,
            category=category,
            starred=starred,
            limit=limit,
            offset=offset,
            db_path=db_path,
            now=now,
        )

    # ── Legacy path (no user context) ─────────────────────────────────────────
    # Exclude canonical-archived duplicates from results
    clauses: list[str] = ["(canonical_id IS NULL OR state != 'archived')"]
    params: list[object] = []
    if status:
        # Legacy compat: map old status filter to state
        legacy_map = {
            "new": "today",
            "read": "done",
            "saved": "today",
            "skipped": "skipped",
            "archived": "archived",
        }
        mapped = legacy_map.get(status, status)
        clauses.append("state = ?")
        params.append(mapped)
        if status == "saved":
            clauses.append("starred = 1")
    if state:
        if state == "today":
            clauses.append(
                "(state = 'today'"
                " OR (state = 'later' AND later_until IS NOT NULL AND later_until <= ?))"
            )
            params.append(now)
        else:
            clauses.append("state = ?")
            params.append(state)
    if starred is not None:
        clauses.append("starred = ?")
        params.append(1 if starred else 0)
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = f"WHERE {' AND '.join(clauses)}"
    params.extend([limit, offset])
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM articles {where} ORDER BY discovered_at DESC, id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        articles = [_article_dict(row) for row in rows]
        _attach_also_from(conn, articles)
        return articles


def _list_articles_for_user(  # noqa: PLR0913
    user_id: int,
    *,
    status: str | None,
    state: str | None,
    category: str | None,
    starred: bool | None,
    limit: int,
    offset: int,
    db_path: Path | None,
    now: str,
) -> list[dict[str, Any]]:
    """Article listing scoped to a specific user via user_article_state."""
    # Map legacy status → state
    if status:
        legacy_map = {
            "new": "today",
            "read": "done",
            "saved": "today",
            "skipped": "skipped",
            "archived": "archived",
        }
        state = legacy_map.get(status, status)
        if status == "saved":
            starred = True

    # Build WHERE on articles
    not_archived = "(a.canonical_id IS NULL OR COALESCE(uas.state, 'today') != 'archived')"
    art_clauses: list[str] = [not_archived]
    where_params: list[object] = []  # params only for WHERE predicates

    # State filter on UAS
    if state:
        if state == "today":
            art_clauses.append(
                "(uas.state IS NULL OR uas.state = 'today'"
                " OR (uas.state = 'later' AND uas.later_until IS NOT NULL"
                " AND uas.later_until <= ?))"
            )
            where_params.append(now)
        else:
            art_clauses.append("COALESCE(uas.state, 'today') = ?")
            where_params.append(state)
    if starred is not None:
        art_clauses.append("COALESCE(uas.starred, false) = ?")
        where_params.append(bool(starred))
    if category:
        art_clauses.append("a.category = ?")
        where_params.append(category)

    where = f"WHERE {' AND '.join(art_clauses)}"

    # Final param order matches SQL left-to-right:
    # 1. us_src JOIN: user_id
    # 2. uas JOIN:    user_id
    # 3. WHERE:       where_params
    # 4. owner check: user_id
    # 5. LIMIT/OFFSET
    all_params: list[object] = [user_id, user_id, *where_params, user_id, limit, offset]

    sql = f"""
        SELECT a.*,
          COALESCE(uas.state, 'today') AS _uas_state,
          COALESCE(uas.starred, false)  AS _uas_starred,
          uas.done_at     AS _uas_done_at,
          uas.starred_at  AS _uas_starred_at,
          uas.skipped_at  AS _uas_skipped_at,
          uas.archived_at AS _uas_archived_at,
          uas.later_until AS _uas_later_until,
          uas.restored_at AS _uas_restored_at
        FROM articles a
        LEFT JOIN sources src ON src.slug = a.source_slug
        LEFT JOIN user_sources us_src ON us_src.user_id = ? AND us_src.source_slug = a.source_slug
        LEFT JOIN user_article_state uas ON uas.article_id = a.id AND uas.user_id = ?
        {where}
          AND (
            (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, true))
            OR src.owner_user_id = ?
          )
        ORDER BY a.discovered_at DESC, a.id DESC
        LIMIT ? OFFSET ?
    """
    with connect(db_path) as conn:
        rows = conn.execute(sql, all_params).fetchall()
        articles = []
        for row in rows:
            d = _article_dict(row)
            # Apply UAS overrides from the prefixed columns
            d["state"] = d.pop("_uas_state", "today")
            d["starred"] = bool(d.pop("_uas_starred", 0))
            d["done_at"] = d.pop("_uas_done_at", None)
            d["starred_at"] = d.pop("_uas_starred_at", None)
            d["skipped_at"] = d.pop("_uas_skipped_at", None)
            d["archived_at"] = d.pop("_uas_archived_at", None)
            d["later_until"] = d.pop("_uas_later_until", None)
            d["restored_at"] = d.pop("_uas_restored_at", None)
            articles.append(d)
        _attach_also_from(conn, articles)
        return articles


def _attach_also_from(conn: Any, articles: list[dict[str, Any]]) -> None:
    """Attach duplicate source names to canonical articles (in-place)."""
    article_ids = [a["id"] for a in articles]
    if not article_ids:
        return
    placeholders = ",".join("?" * len(article_ids))
    dup_rows = conn.execute(
        f"""
        SELECT canonical_id, source_name FROM articles
        WHERE canonical_id IN ({placeholders}) AND state='archived'
        """,
        article_ids,
    ).fetchall()
    dupes_by_canonical: dict[int, list[str]] = defaultdict(list)
    for dr in dup_rows:
        d = row_to_dict(dr)
        dupes_by_canonical[d["canonical_id"]].append(d["source_name"])
    for article in articles:
        article["also_from"] = dupes_by_canonical.get(article["id"], [])


def search_articles(  # noqa: PLR0913
    q: str = "",
    limit: int = 50,
    db_path: Path | None = None,
    states: list[str] | None = None,
    categories: list[str] | None = None,
    sources: list[str] | None = None,
    starred_only: bool = False,
    include_archived: bool = False,
    date_range: str = "all",
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    terms = [t for t in q.split() if len(t) >= 2]
    now_ts = now_iso()

    if user_id is not None:
        return _search_articles_for_user(
            user_id=user_id,
            q=q,
            limit=limit,
            db_path=db_path,
            states=states,
            categories=categories,
            sources=sources,
            starred_only=starred_only,
            include_archived=include_archived,
            date_range=date_range,
            now_ts=now_ts,
        )

    clauses: list[str] = []
    params: list[Any] = []

    # Full-text search across title, summary, reason, tags, source_name, body
    for term in terms:
        like = f"%{term}%"
        clauses.append(
            "(title LIKE ? OR summary LIKE ? OR reason LIKE ? OR tags LIKE ?"
            " OR source_name LIKE ? OR (body IS NOT NULL AND body LIKE ?))"
        )
        params.extend([like, like, like, like, like, like])

    # Archived exclusion — must come before state filter to avoid conflict
    if not include_archived:
        clauses.append("state != 'archived'")

    # State filter (multi-select; overrides archived exclusion for explicit archived selection)
    if states:
        placeholders = ",".join("?" * len(states))
        clauses.append(f"state IN ({placeholders})")
        params.extend(states)
        if include_archived is False and "archived" in states:
            # User explicitly wants archived — remove the exclusion clause we just added
            clauses.remove("state != 'archived'")

    # Category filter
    if categories:
        placeholders = ",".join("?" * len(categories))
        clauses.append(f"category IN ({placeholders})")
        params.extend(categories)

    # Source filter
    if sources:
        placeholders = ",".join("?" * len(sources))
        clauses.append(f"source_slug IN ({placeholders})")
        params.extend(sources)

    # Starred filter
    if starred_only:
        clauses.append("starred = 1")

    # Date range filter
    if date_range == "today":
        clauses.append("discovered_at >= datetime(?, '-1 day')")
        params.append(now_ts)
    elif date_range == "week":
        clauses.append("discovered_at >= datetime(?, '-7 days')")
        params.append(now_ts)
    elif date_range == "month":
        clauses.append("discovered_at >= datetime(?, '-30 days')")
        params.append(now_ts)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    sql = (
        f"SELECT * FROM articles {where} ORDER BY importance_score DESC, discovered_at DESC LIMIT ?"
    )

    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_article_dict(row) for row in rows]


def _search_articles_for_user(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    user_id: int,
    q: str,
    limit: int,
    db_path: Path | None,
    states: list[str] | None,
    categories: list[str] | None,
    sources: list[str] | None,
    starred_only: bool,
    include_archived: bool,
    date_range: str,
    now_ts: str,
) -> list[dict[str, Any]]:
    terms = [t for t in q.split() if len(t) >= 2]
    clauses: list[str] = []
    where_params: list[Any] = []  # params only for WHERE predicates

    for term in terms:
        like = f"%{term}%"
        clauses.append(
            "(a.title LIKE ? OR a.summary LIKE ? OR a.reason LIKE ? OR a.tags LIKE ?"
            " OR a.source_name LIKE ? OR (a.body IS NOT NULL AND a.body LIKE ?))"
        )
        where_params.extend([like, like, like, like, like, like])

    if not include_archived:
        clauses.append("COALESCE(uas.state, 'today') != 'archived'")

    if states:
        placeholders = ",".join("?" * len(states))
        clauses.append(f"COALESCE(uas.state, 'today') IN ({placeholders})")
        where_params.extend(states)
        if include_archived is False and "archived" in states:
            clauses.remove("COALESCE(uas.state, 'today') != 'archived'")

    if categories:
        placeholders = ",".join("?" * len(categories))
        clauses.append(f"a.category IN ({placeholders})")
        where_params.extend(categories)

    if sources:
        placeholders = ",".join("?" * len(sources))
        clauses.append(f"a.source_slug IN ({placeholders})")
        where_params.extend(sources)

    if starred_only:
        clauses.append("COALESCE(uas.starred, false) = true")

    if date_range == "today":
        clauses.append("a.discovered_at >= datetime(?, '-1 day')")
        where_params.append(now_ts)
    elif date_range == "week":
        clauses.append("a.discovered_at >= datetime(?, '-7 days')")
        where_params.append(now_ts)
    elif date_range == "month":
        clauses.append("a.discovered_at >= datetime(?, '-30 days')")
        where_params.append(now_ts)

    # Source subscription filter appended to WHERE
    src_filter = (
        "(src.owner_user_id IS NULL AND COALESCE(us_src.enabled, true)) OR src.owner_user_id = ?"
    )
    if clauses:
        clauses.append(f"({src_filter})")
    else:
        clauses = [f"({src_filter})"]

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    # Param order: us_src JOIN, uas JOIN, WHERE params, owner check, limit
    all_params: list[Any] = [user_id, user_id, *where_params, user_id, limit]

    sql = f"""
        SELECT a.*,
          COALESCE(uas.state, 'today') AS _uas_state,
          COALESCE(uas.starred, false)  AS _uas_starred,
          uas.done_at     AS _uas_done_at,
          uas.starred_at  AS _uas_starred_at,
          uas.skipped_at  AS _uas_skipped_at,
          uas.archived_at AS _uas_archived_at,
          uas.later_until AS _uas_later_until,
          uas.restored_at AS _uas_restored_at
        FROM articles a
        LEFT JOIN sources src ON src.slug = a.source_slug
        LEFT JOIN user_sources us_src ON us_src.user_id = ? AND us_src.source_slug = a.source_slug
        LEFT JOIN user_article_state uas ON uas.article_id = a.id AND uas.user_id = ?
        {where}
        ORDER BY a.importance_score DESC, a.discovered_at DESC LIMIT ?
    """
    with connect(db_path) as conn:
        rows = conn.execute(sql, all_params).fetchall()
        result = []
        for row in rows:
            d = _article_dict(row)
            d["state"] = d.pop("_uas_state", "today")
            d["starred"] = bool(d.pop("_uas_starred", 0))
            d["done_at"] = d.pop("_uas_done_at", None)
            d["starred_at"] = d.pop("_uas_starred_at", None)
            d["skipped_at"] = d.pop("_uas_skipped_at", None)
            d["archived_at"] = d.pop("_uas_archived_at", None)
            d["later_until"] = d.pop("_uas_later_until", None)
            d["restored_at"] = d.pop("_uas_restored_at", None)
            result.append(d)
        return result


def set_article_status(
    article_id: int, status: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    if status not in VALID_STATUSES:
        message = f"invalid status: {status!r} (expected one of {sorted(VALID_STATUSES)})"
        raise ValueError(message)
    timestamp_column = {
        "read": "read_at",
        "saved": "saved_at",
        "skipped": "skipped_at",
        "archived": "archived_at",
    }.get(status)
    init_db(db_path)
    with connect(db_path) as conn:
        if timestamp_column:
            conn.execute(
                f"UPDATE articles SET status=?, {timestamp_column}=?, updated_at=? WHERE id=?",
                (status, now_iso(), now_iso(), article_id),
            )
        else:
            conn.execute(
                "UPDATE articles SET status=?, updated_at=? WHERE id=?",
                (status, now_iso(), article_id),
            )
        row = conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        result = _article_dict(row) if row else None

    # Lazily embed articles when they become saved/read (fire-and-forget; ignore errors)
    if result and status in {"saved", "read"}:
        try:
            from .embeddings import ensure_article_embedded

            ensure_article_embedded(article_id, db_path)
        except Exception:  # embedding is optional — don't break the status update
            logger.debug("Skipping embedding for article %d", article_id, exc_info=True)

    return result


def _get_article_row(conn: Any, article_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    return _article_dict(row) if row else None


def transition_article_state(  # noqa: PLR0912, PLR0915
    article_id: int,
    new_state: str,
    db_path: Path | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Apply a state transition, enforcing allowed-transition rules.

    Raises ValueError for invalid states, disallowed transitions, or
    the starred-cannot-skip rule.
    """
    if new_state not in VALID_STATES:
        message = f"invalid state: {new_state!r} (expected one of {sorted(VALID_STATES)})"
        raise ValueError(message)

    init_db(db_path)
    with connect(db_path) as conn:
        base = _get_article_row(conn, article_id)
        if base is None:
            return None

        if user_id is not None:
            uas = _get_uas_row(conn, article_id, user_id)
            current_state = str((uas or {}).get("state") or "today")
            current_starred = bool((uas or {}).get("starred", False))
        else:
            current_state = str(base.get("state") or "today")
            current_starred = bool(base.get("starred", False))

        if current_state == new_state:
            if user_id is not None:
                return _merge_uas(base, uas if "uas" in dir() else None)
            return base

        if (current_state, new_state) not in _ALLOWED_TRANSITIONS:
            message = f"transition {current_state!r} → {new_state!r} is not allowed"
            raise ValueError(message)

        if new_state == "skipped" and current_starred:
            message = "starred articles cannot be skipped"
            raise ValueError(message)

        ts = now_iso()

        if user_id is not None:
            existing = _get_uas_row(conn, article_id, user_id)
            _upsert_uas(
                conn,
                user_id,
                article_id,
                state=new_state,
                starred=current_starred,
                done_at=ts if new_state == "done" else None,
                skipped_at=ts if new_state == "skipped" else None,
                archived_at=ts if new_state == "archived" else None,
                restored_at=ts if new_state == "today" else None,
                later_until=None if new_state == "today" else (existing or {}).get("later_until"),
                updated_at=ts,
            )
            result: dict[str, Any] | None = _merge_uas(
                _get_article_row(conn, article_id) or {},
                _get_uas_row(conn, article_id, user_id),
            )
        else:
            timestamp_sets: list[str] = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new_state, ts]

            if new_state == "done":
                timestamp_sets.append("done_at = ?")
                params.append(ts)
            elif new_state == "skipped":
                timestamp_sets.append("skipped_at = ?")
                params.append(ts)
            elif new_state == "archived":
                timestamp_sets.append("archived_at = ?")
                params.append(ts)
            elif new_state == "today":
                timestamp_sets.append("restored_at = ?")
                timestamp_sets.append("later_until = NULL")
                params.append(ts)

            set_clause = ", ".join(timestamp_sets)
            params.append(article_id)
            conn.execute(f"UPDATE articles SET {set_clause} WHERE id = ?", params)
            result = _get_article_row(conn, article_id)

    # Embed done articles lazily
    if result and new_state == "done":
        try:
            from .embeddings import ensure_article_embedded

            ensure_article_embedded(article_id, db_path)
        except Exception:
            logger.debug("Skipping embedding for article %d", article_id, exc_info=True)

    return result


def set_article_starred(
    article_id: int,
    starred: bool,
    db_path: Path | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Set the starred flag on an article. Raises ValueError if starring a skipped article."""
    init_db(db_path)
    with connect(db_path) as conn:
        base = _get_article_row(conn, article_id)
        if base is None:
            return None

        ts = now_iso()

        if user_id is not None:
            existing = _get_uas_row(conn, article_id, user_id)
            current_state = str((existing or {}).get("state") or "today")
            _upsert_uas(
                conn,
                user_id,
                article_id,
                state=current_state,
                starred=starred,
                starred_at=ts if starred else (existing or {}).get("starred_at"),
                updated_at=ts,
            )
            base2 = _get_article_row(conn, article_id) or {}
            return _merge_uas(base2, _get_uas_row(conn, article_id, user_id))

        if starred:
            conn.execute(
                "UPDATE articles SET starred = 1, starred_at = ?, updated_at = ? WHERE id = ?",
                (ts, ts, article_id),
            )
        else:
            conn.execute(
                "UPDATE articles SET starred = 0, updated_at = ? WHERE id = ?",
                (ts, article_id),
            )

        return _get_article_row(conn, article_id)


def send_article_later(
    article_id: int,
    days: int = 1,
    db_path: Path | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Snooze an article to Later with an expiry of `days` days from now.

    Only articles in the today or later state can be snoozed.
    """
    if days < 1:
        message = "days must be >= 1"
        raise ValueError(message)

    init_db(db_path)
    with connect(db_path) as conn:
        base = _get_article_row(conn, article_id)
        if base is None:
            return None

        if user_id is not None:
            uas = _get_uas_row(conn, article_id, user_id)
            current_state = str((uas or {}).get("state") or "today")
        else:
            current_state = str(base.get("state") or "today")

        if current_state not in {"today", "later"}:
            message = f"cannot snooze article in state {current_state!r}"
            raise ValueError(message)

        later_until = (
            (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()
        )
        ts = now_iso()

        if user_id is not None:
            existing = _get_uas_row(conn, article_id, user_id)
            _upsert_uas(
                conn,
                user_id,
                article_id,
                state="later",
                starred=bool((existing or {}).get("starred", False)),
                later_until=later_until,
                updated_at=ts,
            )
            base3 = _get_article_row(conn, article_id) or {}
            return _merge_uas(base3, _get_uas_row(conn, article_id, user_id))

        conn.execute(
            "UPDATE articles SET state = 'later', later_until = ?, updated_at = ? WHERE id = ?",
            (later_until, ts, article_id),
        )

        return _get_article_row(conn, article_id)
