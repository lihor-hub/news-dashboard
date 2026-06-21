from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db import connect, init_db, row_to_dict

BEHAVIORAL_MODEL_VERSION = "behavioral-affinity-v1"
SEMANTIC_MODEL_VERSION = "semantic-hybrid-v1"

# Weight each workflow action contributes toward feature affinity.
# Starred is handled separately as a flag bonus (see STAR_WEIGHT) because an
# article can be starred while in any state.  Later is deliberately neutral:
# it signals deferred interest, not rejection.
STATE_SIGNAL_WEIGHTS: dict[str, float] = {
    "done": 1.0,
    "skipped": -1.0,
    "archived": -1.0,
    "later": 0.0,
    "today": 0.0,
}

# Starred is the strongest positive signal; it stacks on top of the state weight.
STAR_WEIGHT = 2.0

# Laplace-style smoothing: shrinks affinity toward neutral when only a handful of
# interactions exist for a feature, so a single click can't dominate scoring.
AFFINITY_SMOOTHING = 2.0

# Relative importance of each feature family when blending into one adjustment.
SOURCE_AFFINITY_WEIGHT = 1.0
CATEGORY_AFFINITY_WEIGHT = 1.0
TOPIC_AFFINITY_WEIGHT = 1.0

# Maximum number of points behavioral affinity can shift a score in either
# direction.  Kept well below the base-score range so a high-quality article from
# a noisy/disliked source can still rise — affinity nudges, it does not gate.
AFFINITY_SCORE_SPAN = 25.0

# Maximum points semantic similarity to the user's valued history can add to a
# score.  Like affinity, it is a bounded lift that blends with — never replaces —
# the behavioral and cold-start factors, so semantic scoring degrading to a
# no-op simply leaves the other factors in charge.
SEMANTIC_SCORE_SPAN = 25.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_tags(tags: str | None) -> tuple[str, ...]:
    """Split a stored comma-separated tag string into a normalized tuple."""
    if not tags:
        return ()
    return tuple(t.strip().lower() for t in tags.split(",") if t.strip())


@dataclass(frozen=True)
class ArticleSignal:
    """One past user/article interaction used to learn affinity."""

    state: str
    starred: bool
    source_slug: str
    category: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def weight(self) -> float:
        """Signed strength of this interaction as an implicit-feedback signal."""
        base = STATE_SIGNAL_WEIGHTS.get(self.state, 0.0)
        if self.starred:
            base += STAR_WEIGHT
        return base


@dataclass
class AffinityProfile:
    """Per-user, per-feature affinities learned from workflow actions.

    Each affinity is normalized to roughly [-1, 1]: positive means the user
    tends to engage with that feature, negative means they dismiss it.
    """

    sources: dict[str, float] = field(default_factory=dict)
    categories: dict[str, float] = field(default_factory=dict)
    topics: dict[str, float] = field(default_factory=dict)

    def adjustment(self, source_slug: str, category: str | None, tags: tuple[str, ...]) -> float:
        """Return the score delta (in points) for an article with these features."""
        contributions: list[tuple[float, float]] = []
        if source_slug in self.sources:
            contributions.append((SOURCE_AFFINITY_WEIGHT, self.sources[source_slug]))
        if category and category in self.categories:
            contributions.append((CATEGORY_AFFINITY_WEIGHT, self.categories[category]))
        topic_affinities = [self.topics[tag] for tag in tags if tag in self.topics]
        if topic_affinities:
            contributions.append(
                (TOPIC_AFFINITY_WEIGHT, sum(topic_affinities) / len(topic_affinities))
            )
        if not contributions:
            return 0.0
        total_weight = sum(weight for weight, _ in contributions)
        blended = sum(weight * affinity for weight, affinity in contributions) / total_weight
        return _clamp(blended, -1.0, 1.0) * AFFINITY_SCORE_SPAN


def _normalize_affinity(weighted_sum: float, count: int) -> float:
    """Smoothed, normalized affinity in [-1, 1] for one feature value."""
    smoothed = weighted_sum / (count + AFFINITY_SMOOTHING)
    # Normalize against STAR_WEIGHT so a fully-starred history maps near +1.
    return _clamp(smoothed / STAR_WEIGHT, -1.0, 1.0)


def build_affinity_profile(signals: list[ArticleSignal]) -> AffinityProfile:
    """Aggregate interaction signals into a normalized per-feature affinity profile."""
    source_sum: dict[str, float] = defaultdict(float)
    source_count: dict[str, int] = defaultdict(int)
    category_sum: dict[str, float] = defaultdict(float)
    category_count: dict[str, int] = defaultdict(int)
    topic_sum: dict[str, float] = defaultdict(float)
    topic_count: dict[str, int] = defaultdict(int)

    for signal in signals:
        weight = signal.weight
        source_sum[signal.source_slug] += weight
        source_count[signal.source_slug] += 1
        if signal.category:
            category_sum[signal.category] += weight
            category_count[signal.category] += 1
        for tag in signal.tags:
            topic_sum[tag] += weight
            topic_count[tag] += 1

    return AffinityProfile(
        sources={
            slug: _normalize_affinity(total, source_count[slug])
            for slug, total in source_sum.items()
        },
        categories={
            cat: _normalize_affinity(total, category_count[cat])
            for cat, total in category_sum.items()
        },
        topics={
            tag: _normalize_affinity(total, topic_count[tag]) for tag, total in topic_sum.items()
        },
    )


def score_article(
    base_score: float,
    *,
    source_slug: str,
    category: str | None,
    tags: tuple[str, ...],
    profile: AffinityProfile,
) -> float:
    """Combine a cold-start base score with learned affinity, clamped to [0, 100]."""
    adjusted = base_score + profile.adjustment(source_slug, category, tags)
    return _clamp(adjusted, 0.0, 100.0)


def build_semantic_profile(vectors: list[list[float]]) -> list[float] | None:
    """Mean-pool valued-history embeddings into one taste vector.

    Returns ``None`` when there are no usable vectors (no embedded history),
    which callers treat as "semantic scoring unavailable" and fall back to the
    non-semantic path.
    """
    centroid: list[float] | None = None
    used = 0
    for vector in vectors:
        if not vector:
            continue
        if centroid is None:
            centroid = list(vector)
        elif len(vector) == len(centroid):
            for i, value in enumerate(vector):
                centroid[i] += value
        else:
            continue  # skip mismatched dimensions defensively
        used += 1
    if centroid is None or used == 0:
        return None
    return [value / used for value in centroid]


def semantic_adjustment(
    candidate_vector: list[float] | None,
    profile_vector: list[float] | None,
) -> float:
    """Score delta (in points) from semantic similarity to the user's taste.

    Degrades to ``0.0`` when either the candidate or the profile vector is
    missing, so missing embeddings never disturb the rest of the score.
    """
    if not candidate_vector or not profile_vector:
        return 0.0
    if len(candidate_vector) != len(profile_vector):
        return 0.0
    from .embeddings import cosine_similarity

    similarity = cosine_similarity(candidate_vector, profile_vector)
    return _clamp(similarity, -1.0, 1.0) * SEMANTIC_SCORE_SPAN


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


# States that constitute an explicit interaction worth learning from.
_INTERACTION_STATES = ("done", "skipped", "archived", "later")


def _load_user_signals(conn: Any, user_id: int) -> list[ArticleSignal]:
    """Read the user's live workflow state + starred metadata into signals."""
    rows = conn.execute(
        """
        SELECT uas.state, uas.starred, a.source_slug, a.category, a.tags
        FROM user_article_state uas
        JOIN articles a ON a.id = uas.article_id
        WHERE uas.user_id = %s
          AND (uas.starred IS TRUE OR uas.state IN ('done', 'skipped', 'archived', 'later'))
        """,
        (user_id,),
    ).fetchall()
    signals: list[ArticleSignal] = []
    for row in rows:
        d = row_to_dict(row)
        signals.append(
            ArticleSignal(
                state=str(d.get("state") or "today"),
                starred=bool(d.get("starred", False)),
                source_slug=str(d["source_slug"]),
                category=d.get("category"),
                tags=parse_tags(d.get("tags")),
            )
        )
    return signals


def _load_user_history_vectors(conn: Any, user_id: int) -> list[list[float]]:
    """Decode embeddings of the user's valued history (starred or done).

    Articles without an embedding are skipped, so an empty list means "no
    embedded history" and semantic scoring stays disabled for this user.
    """
    from .embeddings import decode_embedding

    rows = conn.execute(
        """
        SELECT a.embedding
        FROM user_article_state uas
        JOIN articles a ON a.id = uas.article_id
        WHERE uas.user_id = %s
          AND a.embedding IS NOT NULL
          AND (uas.starred IS TRUE OR uas.state = 'done')
        """,
        (user_id,),
    ).fetchall()
    vectors: list[list[float]] = []
    for row in rows:
        blob = row_to_dict(row).get("embedding")
        if blob is not None:
            vectors.append(decode_embedding(bytes(blob)))
    return vectors


def _load_candidates(conn: Any, user_id: int, limit: int) -> list[dict[str, Any]]:
    """Read today/later-eligible articles with their cold-start base score."""
    from .ingest import _COLD_START_RECOMMENDATION_SCORE_SQL

    rows = conn.execute(
        f"""
        SELECT a.id, a.source_slug, a.category, a.tags, a.embedding,
          {_COLD_START_RECOMMENDATION_SCORE_SQL} AS base_score
        FROM articles a
        LEFT JOIN sources src ON src.slug = a.source_slug
        LEFT JOIN user_article_state uas
          ON uas.article_id = a.id AND uas.user_id = %s
        WHERE (a.canonical_id IS NULL OR COALESCE(uas.state, 'today') != 'archived')
          AND COALESCE(uas.state, 'today') IN ('today', 'later')
        ORDER BY a.discovered_at DESC, a.id DESC
        LIMIT %s
        """,
        (user_id, limit),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def recompute_user_recommendations(
    user_id: int,
    *,
    db_path: Path | None = None,
    limit: int = 1000,
) -> int:
    """Recompute and persist behavioral-affinity scores for a user's live feed.

    Learns affinity from the user's workflow actions (starred/done/skipped/
    archived/later) and blends it with each candidate article's cold-start base
    score.  Returns the number of articles scored.  Pure scoring logic lives in
    :func:`build_affinity_profile` / :func:`score_article` and is unit-testable
    without touching the database.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        profile = build_affinity_profile(_load_user_signals(conn, user_id))
        semantic_profile = build_semantic_profile(_load_user_history_vectors(conn, user_id))
        candidates = _load_candidates(conn, user_id, limit)

    model_version = SEMANTIC_MODEL_VERSION if semantic_profile else BEHAVIORAL_MODEL_VERSION
    scored = 0
    for candidate in candidates:
        base = float(candidate["base_score"])
        source_slug = str(candidate["source_slug"])
        category = candidate.get("category")
        tags = parse_tags(candidate.get("tags"))
        adjustment = profile.adjustment(source_slug, category, tags)
        candidate_vector = _decode_candidate_embedding(candidate.get("embedding"))
        semantic = semantic_adjustment(candidate_vector, semantic_profile)
        final_score = _clamp(base + adjustment + semantic, 0.0, 100.0)
        upsert_recommendation_score(
            user_id,
            int(candidate["id"]),
            final_score,
            db_path=db_path,
            cold_start_score=base,
            signals={
                "base_score": round(base, 4),
                "affinity_adjustment": round(adjustment, 4),
                "semantic_adjustment": round(semantic, 4),
                "source_slug": source_slug,
                "category": category,
            },
            model_version=model_version,
        )
        scored += 1
    return scored


def _decode_candidate_embedding(blob: Any) -> list[float] | None:
    """Best-effort decode of a candidate's stored embedding, ``None`` if absent."""
    if blob is None:
        return None
    from .embeddings import decode_embedding

    return decode_embedding(bytes(blob))
