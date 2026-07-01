"""Demo mode: seed data + read-only guest account.

When ``DEMO_MODE`` is set, calling :func:`seed_demo` creates a ``guest`` user
with ``is_guest=True`` and populates the database with deterministic sample
articles across multiple categories and workflow states.  No network or LLM
calls are made — all data is bundled locally.

The guest account is read-only: the ``reject_guest_writes`` middleware in
``main.py`` blocks all unsafe-method requests from guest sessions.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from news_dashboard.auth import create_user, get_user_by_username
from news_dashboard.db import connect

logger = logging.getLogger(__name__)

_DEMO_GUEST_USERNAME = "guest"
_DEMO_GUEST_PASSWORD = "demo"  # noqa: S105 — intentional hardcoded password for demo

# ---------------------------------------------------------------------------
# Sample article data — fully offline, no external fetches needed.
# ---------------------------------------------------------------------------

_DEMO_SOURCES: list[dict[str, Any]] = [
    {
        "slug": "demo-python",
        "name": "Python Insider (Demo)",
        "url": "https://blog.python.org/demo",
        "category": "python",
        "kind": "rss_feed",
    },
    {
        "slug": "demo-ai",
        "name": "AI Weekly (Demo)",
        "url": "https://aiweekly.com/demo",
        "category": "ai-llm",
        "kind": "rss_feed",
    },
    {
        "slug": "demo-rust",
        "name": "Rust Blog (Demo)",
        "url": "https://blog.rust-lang.org/demo",
        "category": "rust",
        "kind": "rss_feed",
    },
    {
        "slug": "demo-k8s",
        "name": "Kubernetes Blog (Demo)",
        "url": "https://kubernetes.io/demo",
        "category": "cloud-infra",
        "kind": "rss_feed",
    },
    {
        "slug": "demo-eng",
        "name": "The Pragmatic Engineer (Demo)",
        "url": "https://pragmaticengineer.com/demo",
        "category": "engineering",
        "kind": "rss_feed",
    },
]

_DEMO_ARTICLES: list[dict[str, Any]] = [
    # -- python --
    {
        "url": "https://example.com/demo/python-313",
        "title": "Python 3.13 Released: Free-Threaded CPython and Improved Error Messages",
        "summary": (
            "Python 3.13 introduces experimental free-threaded CPython, removing the GIL "
            "for true parallelism, plus much-improved error messages and interactive debugger."
        ),
        "source_slug": "demo-python",
        "category": "python",
        "importance_score": 90,
        "tags": "python,release,performance",
    },
    {
        "url": "https://example.com/demo/uv-0.5",
        "title": "uv 0.5: 10x Faster pip install",
        "summary": (
            "Astral's uv package manager reaches 0.5 with 10x faster installs, "
            "workspace support, and improved lockfile compatibility."
        ),
        "source_slug": "demo-python",
        "category": "python",
        "importance_score": 85,
        "tags": "python,uv,tools",
    },
    {
        "url": "https://example.com/demo/ruff-0.8",
        "title": "Ruff 0.8: New Formatter and 30% Faster Linting",
        "summary": (
            "The Ruff Python linter/formatter gains a new Markdown formatter, 30% faster "
            "linting, and dozens of new rules from popular plugins."
        ),
        "source_slug": "demo-python",
        "category": "python",
        "importance_score": 80,
        "tags": "python,ruff,linter",
    },
    # -- ai-llm --
    {
        "url": "https://example.com/demo/claude-4",
        "title": "Claude 4: Agentic Coding and Multi-Step Reasoning",
        "summary": (
            "Anthropic announces Claude 4 with state-of-the-art coding benchmarks, native "
            "tool use, and a new extended-thinking mode for complex multi-step reasoning tasks."
        ),
        "source_slug": "demo-ai",
        "category": "ai-llm",
        "importance_score": 95,
        "tags": "ai,agents,llm",
    },
    {
        "url": "https://example.com/demo/gpt-5",
        "title": "GPT-5: OpenAI's Next Frontier Model",
        "summary": (
            "OpenAI unveils GPT-5 with dramatic reasoning improvements, native multimodal "
            "capabilities, and a new API for structured outputs."
        ),
        "source_slug": "demo-ai",
        "category": "ai-llm",
        "importance_score": 90,
        "tags": "ai,llm,openai",
    },
    {
        "url": "https://example.com/demo/llama-4",
        "title": "Llama 4: Meta's Open-Source Multi-Modal Model",
        "summary": (
            "Meta releases Llama 4, an open-weight multi-modal model that matches "
            "proprietary alternatives on vision and language benchmarks."
        ),
        "source_slug": "demo-ai",
        "category": "ai-llm",
        "importance_score": 85,
        "tags": "ai,open-source,llama",
    },
    {
        "url": "https://example.com/demo/mcp-explained",
        "title": "Model Context Protocol: A Deep Dive",
        "summary": (
            "A comprehensive guide to MCP, the new standard for connecting AI assistants "
            "to external data sources and tools."
        ),
        "source_slug": "demo-ai",
        "category": "ai-llm",
        "importance_score": 75,
        "tags": "ai,mcp,agents",
    },
    # -- rust --
    {
        "url": "https://example.com/demo/rust-2025",
        "title": "Rust 2025 Edition: Async Closures and Stabilized Features",
        "summary": (
            "The Rust 2025 edition brings async closures, stabilized async traits, "
            "and improved error handling patterns."
        ),
        "source_slug": "demo-rust",
        "category": "rust",
        "importance_score": 85,
        "tags": "rust,release,systems",
    },
    # -- cloud-infra --
    {
        "url": "https://example.com/demo/k8s-1.32",
        "title": "Kubernetes 1.32: Structured Logging and New Auth APIs",
        "summary": (
            "Kubernetes 1.32 introduces structured logging, a new authentication API, "
            "and improved multi-cluster management."
        ),
        "source_slug": "demo-k8s",
        "category": "cloud-infra",
        "importance_score": 70,
        "tags": "kubernetes,cloud,infra",
    },
    {
        "url": "https://example.com/demo/docker-buildkit",
        "title": "BuildKit 0.15: Up to 50% Faster Builds",
        "summary": (
            "Docker's BuildKit 0.15 brings up to 50% faster cold builds through "
            "parallel stage execution and enhanced caching."
        ),
        "source_slug": "demo-k8s",
        "category": "cloud-infra",
        "importance_score": 70,
        "tags": "docker,containers,infra",
    },
    # -- engineering --
    {
        "url": "https://example.com/demo/staff-engineer",
        "title": "The Staff Engineer's Playbook",
        "summary": (
            "Practical advice for senior engineers navigating tech lead, architect, "
            "and manager-without-authority roles."
        ),
        "source_slug": "demo-eng",
        "category": "engineering",
        "importance_score": 65,
        "tags": "engineering,career,leadership",
    },
    {
        "url": "https://example.com/demo/postmortem",
        "title": "How We Reduced P99 Latency by 80%",
        "summary": (
            "A detailed postmortem on diagnosing and fixing a latency bottleneck "
            "caused by database connection pool exhaustion."
        ),
        "source_slug": "demo-eng",
        "category": "engineering",
        "importance_score": 75,
        "tags": "engineering,performance,database",
    },
]

# Assign workflow states to articles for the demo user.
# Order maps to _DEMO_ARTICLES by index.
_DEMO_ARTICLE_STATES: list[str] = [
    "done",  # Python 3.13 — read
    "today",  # uv 0.5 — in inbox
    "today",  # Ruff 0.8 — in inbox
    "done",  # Claude 4 — read
    "today",  # GPT-5 — in inbox
    "done",  # Llama 4 — read
    "today",  # MCP — in inbox
    "done",  # Rust 2025 — read
    "today",  # K8s 1.32 — in inbox
    "today",  # BuildKit — in inbox
    "done",  # Staff Engineer — read
    "today",  # Postmortem — in inbox
]


def seed_demo() -> dict[str, Any]:
    """Seed demo data: guest user, sample sources, articles, and article states.

    Only runs when ``DEMO_MODE`` env var is truthy.  Returns a dict indicating
    what happened (``{created: True}`` or ``{skipped: True, reason: ...}``).
    """
    if os.getenv("DEMO_MODE", "").strip().lower() not in ("1", "true", "yes", "on"):
        return {"skipped": True, "reason": "DEMO_MODE not set"}

    # Idempotency: if the guest user already exists, skip.
    existing = get_user_by_username(_DEMO_GUEST_USERNAME)
    if existing:
        return {"skipped": True, "reason": "guest user already exists"}

    # Ensure sources table has the demo entries before inserting articles.
    _seed_demo_sources()
    source_ids = _get_demo_source_slugs()
    if not source_ids:
        msg = "demo sources must exist before seeding articles"
        raise RuntimeError(msg)

    # Create the guest user.
    guest = create_user(
        _DEMO_GUEST_USERNAME,
        _DEMO_GUEST_PASSWORD,
        is_admin=False,
        is_guest=True,
    )
    guest_id = int(guest["id"])
    logger.info("Demo guest user created: id=%s", guest_id)

    # Subscribe guest to demo sources.
    _subscribe_guest_to_sources(guest_id)

    # Insert demo articles.
    article_ids = _seed_demo_articles()

    # Create per-user article states.
    _seed_demo_article_states(guest_id, article_ids)

    logger.info(
        "Demo data seeded: %d sources, %d articles, %d states for guest user %s",
        len(_DEMO_SOURCES),
        len(article_ids),
        len(article_ids),
        guest_id,
    )

    return {"created": True, "guest_id": guest_id, "articles": len(article_ids)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seed_demo_sources() -> None:
    """Insert demo source rows (idempotent via ON CONFLICT)."""
    with connect() as conn:
        for src in _DEMO_SOURCES:
            conn.execute(
                """
                INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
                VALUES (%s, %s, %s, %s, %s, 50, TRUE)
                ON CONFLICT (slug) DO NOTHING
                """,
                (src["slug"], src["name"], src["url"], src["category"], src["kind"]),
            )


def _get_demo_source_slugs() -> list[str]:
    from news_dashboard.db import placeholders

    slugs = [s["slug"] for s in _DEMO_SOURCES]
    with connect() as conn:
        rows = conn.execute(
            f"SELECT slug FROM sources WHERE slug IN ({placeholders(slugs)}) ORDER BY slug",
            slugs,
        ).fetchall()
    return [r["slug"] for r in rows]


def _subscribe_guest_to_sources(user_id: int) -> None:
    """Subscribe the guest user to all demo sources."""
    with connect() as conn:
        for src in _DEMO_SOURCES:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (user_id, source_slug) DO NOTHING
                """,
                (user_id, src["slug"]),
            )


def _seed_demo_articles() -> list[int]:
    """Insert demo articles and return their IDs."""
    now = datetime.now(timezone.utc)
    article_ids: list[int] = []
    with connect() as conn:
        for idx, art in enumerate(_DEMO_ARTICLES):
            published = now - timedelta(days=1, hours=idx)
            row = conn.execute(
                """
                INSERT INTO articles(
                    url, canonical_url, title, source_slug, source_name,
                    category, kind, published_at, summary, importance_score, tags, state
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'today')
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                (
                    art["url"],
                    art["url"],
                    art["title"],
                    art["source_slug"],
                    art["source_slug"],  # source_name = slug for demo
                    art["category"],
                    "rss_feed",
                    published.isoformat(),
                    art.get("summary", ""),
                    art.get("importance_score", 50),
                    art.get("tags", ""),
                ),
            ).fetchone()
            if row:
                article_ids.append(int(row["id"]))
            else:
                # Already exists — fetch the existing id.
                existing_row = conn.execute(
                    "SELECT id FROM articles WHERE url = %s",
                    (art["url"],),
                ).fetchone()
                if existing_row:
                    article_ids.append(int(existing_row["id"]))
    return article_ids


def _seed_demo_article_states(user_id: int, article_ids: list[int]) -> None:
    """Create user_article_state entries for the guest, spanning multiple states."""
    now = datetime.now(timezone.utc)
    with connect() as conn:
        for idx, article_id in enumerate(article_ids):
            state = _DEMO_ARTICLE_STATES[idx] if idx < len(_DEMO_ARTICLE_STATES) else "today"
            done_at = now if state == "done" else None
            conn.execute(
                """
                INSERT INTO user_article_state(user_id, article_id, state, starred, done_at)
                VALUES (%s, %s, %s, FALSE, %s)
                ON CONFLICT (user_id, article_id) DO NOTHING
                """,
                (user_id, article_id, state, done_at.isoformat() if done_at else None),
            )
