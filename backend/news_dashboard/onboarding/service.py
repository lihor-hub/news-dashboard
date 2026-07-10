"""Business logic for new-user onboarding: interests and source recommendations."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from news_dashboard.db import connect

INTEREST_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "ai",
        "label": "AI",
        "options": (
            {"id": "agents", "label": "Agents"},
            {"id": "model-releases", "label": "Model releases"},
            {"id": "evals", "label": "Evals"},
            {"id": "product-news", "label": "Product news"},
        ),
    },
    {
        "id": "engineering",
        "label": "Engineering",
        "options": (
            {"id": "python", "label": "Python"},
            {"id": "infra", "label": "Infrastructure"},
            {"id": "cloud", "label": "Cloud"},
            {"id": "security", "label": "Security"},
        ),
    },
)


def interest_options() -> set[str]:
    return {str(option["id"]) for group in INTEREST_GROUPS for option in group["options"]}


def source_recommendations(user_id: int, interests: list[str]) -> list[dict[str, Any]]:
    from news_dashboard.ingest import sync_sources
    from news_dashboard.sources import DEFAULT_SOURCES

    selected = set(interests)
    sync_sources()
    with connect() as conn:
        rows = conn.execute(
            "SELECT source_slug, enabled FROM user_sources WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    subscriptions = {str(row["source_slug"]): bool(row["enabled"]) for row in rows}

    recommendations: list[dict[str, Any]] = []
    for source in DEFAULT_SOURCES:
        tags = set(source.interest_tags)
        matched = sorted(selected & (tags | {source.category}))
        score = float((len(selected & tags) * 100) + (25 if source.category in selected else 0))
        score += source.priority / 100
        recommended = bool(matched)
        if not selected:
            score = source.priority / 100
            recommended = False
        reason = (
            f"Matches {', '.join(matched)}" if matched else f"Baseline {source.category} source"
        )
        recommendations.append(
            {
                "source_slug": source.slug,
                "source_name": source.name,
                "kind": source.kind,
                "url": source.url,
                "category": source.category,
                "matched_interests": matched,
                "reason": reason,
                "recommended": recommended,
                "subscribed": subscriptions.get(source.slug, False),
                "priority": source.priority,
                "_score": score,
                "_priority": source.priority,
            }
        )

    recommendations.sort(
        key=lambda item: (
            float(item["_score"]),
            bool(item["subscribed"]),
            int(item["_priority"]),
            str(item["source_name"]),
        ),
        reverse=True,
    )
    for item in recommendations:
        item.pop("_score")
        item.pop("_priority")
    return recommendations


def frontend_recommendations(user_id: int, interests: list[str]) -> list[dict[str, Any]]:
    """Return source recommendations using the frontend field-name contract (slug, name)."""
    raw = source_recommendations(user_id, interests)
    return [
        {
            "slug": item["source_slug"],
            "name": item["source_name"],
            "category": item["category"],
            "kind": item["kind"],
            "url": item["url"],
            "matched_interests": item["matched_interests"],
            "reason": item["reason"],
            "recommended": item["recommended"],
            "enabled": 1 if item["subscribed"] else 0,
            "priority": item["priority"],
        }
        for item in raw
    ]


def get_status(user_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT completed_at FROM user_interest_profiles WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return row is not None and row["completed_at"] is not None


def get_interests(user_id: int) -> list[str]:
    with connect() as conn:
        row = conn.execute(
            "SELECT interests FROM user_interest_profiles WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return [str(interest) for interest in row["interests"]] if row else []


def save_profile(user_id: int, interest_ids: list[str], enabled_slugs: list[str]) -> None:
    from news_dashboard.ingest import sync_sources

    sync_sources()
    with connect() as conn:
        if enabled_slugs:
            rows = conn.execute(
                "SELECT slug FROM sources WHERE owner_user_id IS NULL AND slug = ANY(%s)",
                (enabled_slugs,),
            ).fetchall()
            allowed = {str(row["slug"]) for row in rows}
            missing = [slug for slug in enabled_slugs if slug not in allowed]
            if missing:
                raise UnknownGlobalSourcesError(missing)

        conn.execute(
            """
            INSERT INTO user_interest_profiles(user_id, interests, completed_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT(user_id) DO UPDATE SET
              interests = excluded.interests,
              completed_at = NOW(),
              updated_at = NOW()
            """,
            (user_id, Jsonb(interest_ids)),
        )
        for slug in enabled_slugs:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, TRUE)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = TRUE
                """,
                (user_id, slug),
            )


def save_interests(
    user_id: int,
    interests: list[str],
    enabled_source_slugs: list[str],
    disabled_source_slugs: list[str],
    completed: bool,
) -> None:
    from news_dashboard.ingest import sync_sources

    requested = list(dict.fromkeys(enabled_source_slugs + disabled_source_slugs))
    sync_sources()
    with connect() as conn:
        if requested:
            rows = conn.execute(
                "SELECT slug FROM sources WHERE owner_user_id IS NULL AND slug = ANY(%s)",
                (requested,),
            ).fetchall()
            allowed = {str(row["slug"]) for row in rows}
            missing = [slug for slug in requested if slug not in allowed]
            if missing:
                raise UnknownGlobalSourcesError(missing)

        conn.execute(
            """
            INSERT INTO user_interest_profiles(user_id, interests, completed_at, updated_at)
            VALUES (%s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW())
            ON CONFLICT(user_id) DO UPDATE SET
              interests = excluded.interests,
              completed_at = excluded.completed_at,
              updated_at = NOW()
            """,
            (user_id, Jsonb(interests), completed),
        )
        for slug in enabled_source_slugs:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, TRUE)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = TRUE
                """,
                (user_id, slug),
            )
        for slug in disabled_source_slugs:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, FALSE)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = FALSE
                """,
                (user_id, slug),
            )


class UnknownGlobalSourcesError(ValueError):
    """Raised when a request references source slugs that don't exist as global sources."""

    def __init__(self, missing_slugs: list[str]) -> None:
        self.missing_slugs = missing_slugs
        super().__init__(f"unknown global sources: {', '.join(missing_slugs)}")
