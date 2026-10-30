"""Immutable qualifying reads. Call on the workflow connection after the account lock."""

from __future__ import annotations

from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from news_dashboard.reading_progress import topics
from news_dashboard.reading_progress.daily import utc_now
from news_dashboard.reading_progress.rewards import READ_TARGETS, award_rewards, read_key

# Frozen v1 identity; ingest normalization changes must not change earned identity.
_TRACKING_V1 = frozenset(
    {
        "ref",
        "fbclid",
        "gclid",
        "yclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "spm",
        "ck_subscriber_id",
    }
)


def identity_digest(url: str) -> str:
    parsed = urlparse(url.strip())
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_V1 and not k.lower().startswith("utm_")
    )
    path = parsed.path.rstrip("/") if len(parsed.path) > 1 else parsed.path
    normalized = urlunparse(
        parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=path,
            fragment="",
            query=urlencode(query, doseq=True),
        )
    )
    return sha256(normalized.encode("utf-8")).hexdigest()


def credit_read(  # noqa: PLR0913 - caller-owned source/provenance, no hidden connection
    conn: Any,
    user_id: int,
    *,
    url: str,
    article_id: int | None = None,
    title: str = "",
    summary: str = "",
    method: str = "manual",
    origin: str = "live",
) -> dict[str, Any]:
    """First insert freezes provenance and subject, including an empty subject.

    No commit, connection, initialization, or mutable duplicate-root lookup here.
    """
    now = utc_now()
    effective = now if origin == "live" else None
    row = conn.execute(
        """INSERT INTO user_read_credits(user_id,identity_digest,article_id,origin,method,
             recorded_at,effective_at) VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(user_id,identity_version,identity_digest) DO NOTHING RETURNING id""",
        (user_id, identity_digest(url), article_id, origin, method, now, effective),
    ).fetchone()
    result = {
        "credit_inserted": False,
        "progress_changed": False,
        "newly_unlocked": [],
        "reward_group_id": None,
    }
    if row is None:
        return result
    topics.finalize_topics(conn, row["id"], title or "", summary or "")
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM user_read_credits WHERE user_id=%s",
        (user_id,),
    ).fetchone()["n"]
    rewards = award_rewards(
        conn,
        user_id,
        cause_key=f"read:{row['id']}",
        origin=origin,
        earned_at=effective,
        candidates=[
            {"key": read_key(n), "criteria_version": 1, "progress": total, "target": n}
            for n in READ_TARGETS
            if total >= n
        ]
        + topics.candidates(conn, user_id),
    )
    return {**result, **rewards, "credit_inserted": True, "progress_changed": True}


def credit_article(
    conn: Any, user_id: int, article: Any, *, method: str = "manual", origin: str = "live"
) -> dict[str, Any]:
    return credit_read(
        conn,
        user_id,
        url=article.get("canonical_url") or article["url"],
        article_id=article["id"],
        title=article.get("title") or "",
        summary=article.get("summary") or "",
        method=method,
        origin=origin,
    )
