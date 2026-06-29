from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

COLD_START_MODEL_VERSION = "cold-start-v1"
BEHAVIORAL_MODEL_VERSION = "behavioral-affinity-v1"
SEMANTIC_MODEL_VERSION = "semantic-hybrid-v1"
NOVELTY_MODEL_VERSION = "novelty-freshness-v1"

# Model versions :func:`recompute_user_recommendations` writes today.  Any stored
# recommendation whose ``model_version`` is outside this set was produced by an
# older scoring formula or embedding scheme and is eligible for a background
# repair recompute (see :mod:`news_dashboard.recommendation_jobs`).
CURRENT_MODEL_VERSIONS: frozenset[str] = frozenset(
    {BEHAVIORAL_MODEL_VERSION, NOVELTY_MODEL_VERSION}
)

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

# Maximum points a fresh, high-quality article can gain from the freshness
# contribution.  Freshness gives recent quality items a controlled path upward
# so they are not buried by historical preference alone; it is a smaller lift
# than behavioral/semantic so relevance still leads.
FRESHNESS_SCORE_SPAN = 15.0

# Articles older than this are considered to have no freshness left.  The lift
# decays linearly from full at age zero to nothing at the horizon.
FRESHNESS_HORIZON_HOURS = 168.0  # 7 days

# Maximum points the novelty contribution can add.  Novelty rewards plausible
# but *surprising* articles — ones dissimilar to the user's taste — so the feed
# is not purely more of the same.  It is deliberately a fraction of the semantic
# span so relevance still dominates while novelty keeps a controlled path up.
NOVELTY_SCORE_SPAN = 10.0


def _quality_factor(importance: float | None) -> float:
    """Map an importance score (0-100, default 50) onto a [0, 1] quality factor."""
    if importance is None:
        importance = 50.0
    return _clamp(importance / 100.0, 0.0, 1.0)


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


@dataclass(frozen=True)
class RecommendationPreferences:
    """Manual user controls layered on top of learned recommendation signals."""

    category_weights: dict[str, float] = field(default_factory=dict)
    novelty_weight: float = 1.0


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
    from news_dashboard.embeddings import cosine_similarity

    similarity = cosine_similarity(candidate_vector, profile_vector)
    return _clamp(similarity, -1.0, 1.0) * SEMANTIC_SCORE_SPAN


def freshness_adjustment(age_hours: float | None, importance: float | None) -> float:
    """Score delta (in points) rewarding recent, high-quality articles.

    The lift decays linearly with age over :data:`FRESHNESS_HORIZON_HOURS` and
    is scaled by article quality, so a brand-new important item gets a real
    boost while a stale or low-quality one gets little or none.  Returns ``0.0``
    when the age is unknown, so missing timestamps never disturb the score.
    """
    if age_hours is None:
        return 0.0
    recency = _clamp(1.0 - max(age_hours, 0.0) / FRESHNESS_HORIZON_HOURS, 0.0, 1.0)
    return recency * _quality_factor(importance) * FRESHNESS_SCORE_SPAN


def novelty_adjustment(
    candidate_vector: list[float] | None,
    profile_vector: list[float] | None,
    importance: float | None,
) -> float:
    """Score delta (in points) rewarding plausible-but-surprising articles.

    Novelty is the controlled inverse of semantic similarity: articles that are
    *dissimilar* to the user's taste get a lift, but only in proportion to their
    quality (``importance``) so the path up is reserved for surprising yet
    plausible items rather than random low-signal noise.  Degrades to ``0.0``
    when novelty cannot be assessed (missing vectors), leaving the rest of the
    score — including the relevance-seeking semantic lift — in charge.
    """
    if not candidate_vector or not profile_vector:
        return 0.0
    if len(candidate_vector) != len(profile_vector):
        return 0.0
    from news_dashboard.embeddings import cosine_similarity

    similarity = cosine_similarity(candidate_vector, profile_vector)
    # Map similarity [-1, 1] onto a dissimilarity factor [0, 1]: the further the
    # candidate is from the user's taste, the more novel it is.
    dissimilarity = _clamp((1.0 - similarity) / 2.0, 0.0, 1.0)
    return dissimilarity * _quality_factor(importance) * NOVELTY_SCORE_SPAN


def get_recommendation_preferences(
    user_id: int,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> RecommendationPreferences:
    """Return persisted manual recommendation preferences for ``user_id``."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT category_weights, novelty_weight
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return RecommendationPreferences()
    data = row_to_dict(row)
    raw_weights = data.get("category_weights") or {}
    category_weights = {
        str(category): _clamp(float(weight), 0.0, 3.0)
        for category, weight in dict(raw_weights).items()
    }
    return RecommendationPreferences(
        category_weights=category_weights,
        novelty_weight=_clamp(float(data.get("novelty_weight") or 1.0), 0.0, 3.0),
    )


def save_recommendation_preferences(
    user_id: int,
    *,
    category_weights: dict[str, float] | None = None,
    novelty_weight: float | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> RecommendationPreferences:
    """Persist manual recommendation preferences and mark current scores stale."""
    current = get_recommendation_preferences(user_id, db_path=db_path, database_url=database_url)
    next_weights = current.category_weights if category_weights is None else category_weights
    cleaned_weights = {
        str(category).strip().lower(): _clamp(float(weight), 0.0, 3.0)
        for category, weight in next_weights.items()
        if str(category).strip()
    }
    next_novelty = current.novelty_weight if novelty_weight is None else novelty_weight
    cleaned_novelty = _clamp(float(next_novelty), 0.0, 3.0)
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO user_settings(user_id, category_weights, novelty_weight)
            VALUES (%s, %s::jsonb, %s)
            ON CONFLICT(user_id) DO UPDATE SET
              category_weights = excluded.category_weights,
              novelty_weight = excluded.novelty_weight,
              updated_at = NOW()
            """,
            (user_id, json.dumps(cleaned_weights), cleaned_novelty),
        )
        conn.execute(
            "UPDATE user_article_recommendations SET stale = TRUE WHERE user_id = %s",
            (user_id,),
        )
    return RecommendationPreferences(
        category_weights=cleaned_weights,
        novelty_weight=cleaned_novelty,
    )


def generate_recommendation_explanation(
    user_id: int,
    article_id: int,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> str | None:
    """Generate a natural language explanation of why an article was recommended.

    Queries the user's recent positive interactions (starred/done) and the
    article's metadata, then asks the LLM for a single concise sentence
    (under 20 words).  Returns ``None`` when the AI client is not configured or
    the call fails, so callers treat it as an optional enrichment.
    """
    import os

    from news_dashboard.ai_client import chat_create, free_llm_config, get_chat_client

    api_key, base_url = free_llm_config()
    if not api_key:
        return None

    model = os.getenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        article_row = conn.execute(
            "SELECT title, category, tags, source_name FROM articles WHERE id = %s",
            (article_id,),
        ).fetchone()
        if article_row is None:
            return None
        article = row_to_dict(article_row)

        history_rows = conn.execute(
            """
            SELECT a.title, a.category, a.source_name, a.tags, uas.starred
            FROM user_article_state uas
            JOIN articles a ON a.id = uas.article_id
            WHERE uas.user_id = %s
              AND (uas.starred IS TRUE OR uas.state = 'done')
            ORDER BY uas.done_at DESC NULLS LAST, uas.starred_at DESC NULLS LAST
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()

    history = [row_to_dict(r) for r in history_rows]

    if not history:
        history_text = "No reading history yet."
    else:
        lines = []
        for h in history:
            label = "starred" if h.get("starred") else "read"
            lines.append(
                f'- {label}: "{h.get("title", "")}" '
                f"({h.get('source_name', '')} / {h.get('category', '')})"
            )
        history_text = "\n".join(lines)

    tags = article.get("tags") or ""
    prompt = (
        f"You are a personalized news assistant. Explain in one short sentence (under 20 words) "
        f"why this article matches the user's reading interests.\n\n"
        f'Article: "{article.get("title", "")}"\n'
        f"Source: {article.get('source_name', '')}\n"
        f"Category: {article.get('category', '')}\n"
        f"Tags: {tags}\n\n"
        f"User's recent reading history:\n{history_text}\n\n"
        f"Reply with just the explanation sentence, no preamble."
    )

    try:
        client = get_chat_client(api_key=api_key, base_url=base_url)
        response = chat_create(
            client,
            name="recommendation-explanation",
            tags=["recommendation", "explanation"],
            user_id=user_id,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.3,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return None


def upsert_recommendation_score(  # noqa: PLR0913
    user_id: int,
    article_id: int,
    recommendation_score: float,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
    cold_start_score: float | None = None,
    signals: dict[str, Any] | None = None,
    model_version: str = COLD_START_MODEL_VERSION,
    explanation: str | None = None,
) -> None:
    """Persist recommendation metadata for one user/article pair."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO user_article_recommendations(
              user_id, article_id, recommendation_score, cold_start_score,
              signals, model_version, stale, explanation
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, FALSE, %s)
            ON CONFLICT(user_id, article_id) DO UPDATE SET
              recommendation_score = excluded.recommendation_score,
              cold_start_score = excluded.cold_start_score,
              signals = excluded.signals,
              model_version = excluded.model_version,
              stale = FALSE,
              explanation = COALESCE(
                excluded.explanation, user_article_recommendations.explanation
              ),
              updated_at = NOW()
            """,
            (
                user_id,
                article_id,
                float(recommendation_score),
                cold_start_score,
                json.dumps(signals or {}),
                model_version,
                explanation,
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
    from news_dashboard.embeddings import decode_embedding

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
    """Read today/later-eligible articles with their cold-start base score.

    Scoped to the user's visible corpus: global sources the user has not
    disabled, and private sources owned by this user.
    """
    from news_dashboard.ingest import _COLD_START_RECOMMENDATION_SCORE_SQL

    rows = conn.execute(
        f"""
        SELECT a.id, a.title, a.source_slug, a.category, a.tags, a.embedding,
          a.importance_score,
          EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - a.discovered_at::timestamptz))
            / 3600.0 AS age_hours,
          {_COLD_START_RECOMMENDATION_SCORE_SQL} AS base_score
        FROM articles a
        LEFT JOIN sources src ON src.slug = a.source_slug
        LEFT JOIN user_sources us_src
          ON us_src.user_id = %s AND us_src.source_slug = a.source_slug
        LEFT JOIN user_article_state uas
          ON uas.article_id = a.id AND uas.user_id = %s
        WHERE (a.canonical_id IS NULL OR COALESCE(uas.state, 'today') != 'archived')
          AND COALESCE(uas.state, 'today') IN ('today', 'later')
          AND (
            (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
            OR src.owner_user_id = %s
          )
        ORDER BY a.discovered_at DESC, a.id DESC
        LIMIT %s
        """,
        (user_id, user_id, user_id, limit),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def recompute_user_recommendations(
    user_id: int,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
    limit: int = 1000,
) -> int:
    """Recompute and persist behavioral-affinity scores for a user's live feed.

    Learns affinity from the user's workflow actions (starred/done/skipped/
    archived/later) and blends it with each candidate article's cold-start base
    score.  Returns the number of articles scored.  Pure scoring logic lives in
    :func:`build_affinity_profile` / :func:`score_article` and is unit-testable
    without touching the database.
    """
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        profile = build_affinity_profile(_load_user_signals(conn, user_id))
        semantic_profile = build_semantic_profile(_load_user_history_vectors(conn, user_id))
        preferences = get_recommendation_preferences(
            user_id,
            db_path=db_path,
            database_url=database_url,
        )
        candidates = _load_candidates(conn, user_id, limit)
        goal_rows = conn.execute(
            "SELECT description, keywords FROM user_goals WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        goals = [dict(r) for r in goal_rows]

    from news_dashboard.quiz import goal_alignment_adjustment

    # Novelty needs an embedded taste vector to measure surprise against; without
    # one it degrades to a no-op, so the version only advertises novelty when the
    # semantic profile is present.
    model_version = NOVELTY_MODEL_VERSION if semantic_profile else BEHAVIORAL_MODEL_VERSION
    scored = 0
    scored_items: list[tuple[int, float]] = []
    for candidate in candidates:
        base = float(candidate["base_score"])
        source_slug = str(candidate["source_slug"])
        category = candidate.get("category")
        tags = parse_tags(candidate.get("tags"))
        importance = _opt_float(candidate.get("importance_score"))
        age_hours = _opt_float(candidate.get("age_hours"))
        adjustment = profile.adjustment(source_slug, category, tags)
        category_factor = preferences.category_weights.get(str(category).lower(), 1.0)
        manual_category = (category_factor - 1.0) * CATEGORY_AFFINITY_WEIGHT * AFFINITY_SCORE_SPAN
        candidate_vector = _decode_candidate_embedding(candidate.get("embedding"))
        semantic = semantic_adjustment(candidate_vector, semantic_profile)
        freshness = freshness_adjustment(age_hours, importance)
        novelty = (
            novelty_adjustment(candidate_vector, semantic_profile, importance)
            * preferences.novelty_weight
        )
        goal_boost = goal_alignment_adjustment(
            candidate.get("title"),
            str(category) if category else None,
            candidate.get("tags"),
            goals,
        )
        final_score = _clamp(
            base + adjustment + manual_category + semantic + freshness + novelty + goal_boost,
            0.0,
            100.0,
        )
        upsert_recommendation_score(
            user_id,
            int(candidate["id"]),
            final_score,
            db_path=db_path,
            database_url=database_url,
            cold_start_score=base,
            signals={
                "base_score": round(base, 4),
                "affinity_adjustment": round(adjustment, 4),
                "manual_category_adjustment": round(manual_category, 4),
                "semantic_adjustment": round(semantic, 4),
                "freshness_adjustment": round(freshness, 4),
                "novelty_adjustment": round(novelty, 4),
                "novelty_weight": round(preferences.novelty_weight, 4),
                "goal_alignment_adjustment": round(goal_boost, 4),
                "source_slug": source_slug,
                "category": category,
            },
            model_version=model_version,
        )
        scored_items.append((int(candidate["id"]), final_score))
        scored += 1

    # Generate explanations for the top 20 articles only; the rest are low-signal
    # enough that a generic label suffices and the AI quota stays manageable.
    top_articles = sorted(scored_items, key=lambda x: x[1], reverse=True)[:20]
    for article_id, _ in top_articles:
        explanation = generate_recommendation_explanation(
            user_id,
            article_id,
            db_path=db_path,
            database_url=database_url,
        )
        if explanation:
            with connect(db_path, database_url=database_url) as conn:
                conn.execute(
                    "UPDATE user_article_recommendations SET explanation = %s"
                    " WHERE user_id = %s AND article_id = %s AND explanation IS NULL",
                    (explanation, user_id, article_id),
                )

    return scored


def _opt_float(value: Any) -> float | None:
    """Coerce an optional numeric DB column to ``float``, preserving ``None``."""
    if value is None:
        return None
    return float(value)


def _decode_candidate_embedding(blob: Any) -> list[float] | None:
    """Best-effort decode of a candidate's stored embedding, ``None`` if absent."""
    if blob is None:
        return None
    from news_dashboard.embeddings import decode_embedding

    return decode_embedding(bytes(blob))
