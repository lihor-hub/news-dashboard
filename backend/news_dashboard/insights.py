"""AI-generated 'Why it matters' bullet points and topic clustering for articles.

Calls an OpenAI-compatible chat model with the article text and caches the result in
articles.insights (JSON) so the AI is invoked at most once per article.

cluster_recent_articles() groups articles from the last 7 days by embedding similarity
and generates AI headlines and trend summaries for each cluster.
"""

from __future__ import annotations

import json
import logging
import math
import os
import struct
from typing import Any

from news_dashboard.body_fetch import get_article
from news_dashboard.db import connect, init_db

logger = logging.getLogger(__name__)

DEFAULT_INSIGHTS_MODEL = "gpt-4o-mini"
_MAX_CHARS = 8_000
_PROMPT = (
    "You are analyzing a news article. Based ONLY on the information explicitly stated in the "
    "article text below, generate 3-5 concise bullet points explaining why this story matters "
    "and what its potential impact is. "
    "Ground every bullet strictly in what the article actually says — do not add context, "
    "speculation, or general knowledge about the topic that is not stated in the article. "
    "If the article text does not clearly support a takeaway, return fewer bullets rather than "
    "inventing one. "
    "Return only the bullet points, one per line, starting with '•'."
)


class InsightsNotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is not set."""


def _build_text(article: dict[str, Any]) -> str:
    title = str(article.get("title") or "")
    body = str(article.get("body") or "")
    summary = str(article.get("summary") or "")
    content = body if len(body) > len(summary) else summary
    text = f"Title: {title}\n\n{content}" if title else content
    return text[:_MAX_CHARS]


def _parse_bullets(response_text: str) -> list[str]:
    bullets: list[str] = []
    for line in response_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("•"):
            bullet = stripped[1:].strip()
            if bullet:
                bullets.append(bullet)
    return bullets


def _insights_ai_config() -> tuple[str, str | None, str]:
    """Resolve the (api_key, base_url, model) for article insight generation.

    Insights can target any OpenAI-compatible endpoint via
    ``OPENAI_INSIGHTS_BASE_URL`` / ``OPENAI_INSIGHTS_API_KEY``, falling back to
    the shared ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``. The base URL is
    optional; when unset the official OpenAI endpoint is used.
    """
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise InsightsNotConfiguredError(msg)
    model = os.getenv("OPENAI_INSIGHTS_MODEL", DEFAULT_INSIGHTS_MODEL)
    return api_key, base_url, model


def generate_insights(article: dict[str, Any], *, user_id: int | None = None) -> list[str]:
    """Call OpenAI and return a list of bullet-point strings.

    Raises InsightsNotConfiguredError when OPENAI_API_KEY is absent.
    Raises RuntimeError on API failure.
    """
    api_key, base_url, model = _insights_ai_config()

    text = _build_text(article)
    if not text.strip():
        return []

    from news_dashboard.ai_client import chat_create, get_chat_client, get_prompt

    client = get_chat_client(api_key=api_key, base_url=base_url)
    prompt = get_prompt("article-insights", fallback=_PROMPT)
    logger.info("Generating insights for article %s", article.get("id"))
    result = chat_create(
        client,
        name="article-insights",
        tags=["insights"],
        user_id=user_id,
        prompt=prompt,
        model=model,
        messages=[{"role": "user", "content": f"{prompt.text}\n\n{text}"}],
        max_tokens=512,
    )
    response_text = (result.choices[0].message.content or "").strip()
    bullets = _parse_bullets(response_text)
    logger.info("Insights generated for article %s: %d bullets", article.get("id"), len(bullets))
    return bullets


def get_or_generate_insights(
    article_id: int,
    user_id: int | None = None,
    database_url: str | None = None,
) -> list[str]:
    """Return cached insights or generate + cache them.

    When user_id is provided the article must be visible to that user
    (global source not disabled, or private source owned by the user).
    Returns [] for invisible or non-existent articles.

    Raises InsightsNotConfiguredError when OPENAI_API_KEY is absent and
    no cached insights exist.
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT a.insights
                FROM articles a
                JOIN sources src ON src.slug = a.source_slug
                LEFT JOIN user_sources us_src
                  ON us_src.source_slug = a.source_slug AND us_src.user_id = %s
                WHERE a.id = %s AND (
                  (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
                  OR src.owner_user_id = %s
                )
                """,
                (user_id, article_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT insights FROM articles WHERE id = %s", (article_id,)
            ).fetchone()

    if row is None:
        return []

    cached = row["insights"] if isinstance(row, dict) else row[0]
    if cached is not None:
        return list(json.loads(cached))

    article = get_article(article_id, user_id=user_id)
    if article is None:
        return []

    # Require a fetched article body — do not generate from headline/summary alone
    if not str(article.get("body") or "").strip():
        return []

    bullets = generate_insights(article, user_id=user_id)

    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE articles SET insights = %s WHERE id = %s",
            (json.dumps(bullets), article_id),
        )

    return bullets


# ── Topic Map / Story Clustering ──────────────────────────────────────────────

_CLUSTER_THRESHOLD = 0.72  # cosine similarity threshold for same-cluster assignment
_MIN_CLUSTER_SIZE = 3  # minimum articles per cluster to surface
_MAX_ARTICLES = 300  # cap to keep computation bounded
_CLUSTER_LABEL_PROMPT = (
    "You are analyzing a group of related news articles that cover the same story or topic arc. "
    "Based ONLY on the article titles and summaries provided below, generate:\n"
    "1. A concise Story Headline (max 8 words) capturing the central theme.\n"
    "2. A one-sentence Trend Summary explaining the story arc or why these "
    "articles are connected.\n\n"
    "Respond in this exact format:\n"
    "HEADLINE: <headline here>\n"
    "SUMMARY: <one-sentence summary here>"
)

DEFAULT_CLUSTER_MODEL = "gpt-4o-mini"


def _cluster_ai_config() -> tuple[str, str | None, str]:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise InsightsNotConfiguredError(msg)
    model = os.getenv("OPENAI_INSIGHTS_MODEL", DEFAULT_CLUSTER_MODEL)
    return api_key, base_url, model


def _unpack_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return list(vec)
    return [x / norm for x in vec]


def _vec_mean(vecs: list[list[float]]) -> list[float]:
    if not vecs:
        return []
    dim = len(vecs[0])
    result = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            result[i] += x
    n = len(vecs)
    return [x / n for x in result]


def _pca_2d(vecs: list[list[float]]) -> list[tuple[float, float]]:
    """Project vectors into 2D using the first two principal components via power iteration."""
    if len(vecs) == 1:
        return [(0.0, 0.0)]
    if len(vecs) == 2:
        return [(-0.5, 0.0), (0.5, 0.0)]

    dim = len(vecs[0])
    n = len(vecs)
    mean = _vec_mean(vecs)
    centered = [[vecs[i][j] - mean[j] for j in range(dim)] for i in range(n)]

    def _power_iter(
        matrix: list[list[float]], deflation_vec: list[float] | None = None
    ) -> list[float]:
        import random

        rng = random.Random(42)  # noqa: S311
        pc = _normalize([rng.gauss(0, 1) for _ in range(dim)])
        for _ in range(50):
            scores = [sum(row[j] * pc[j] for j in range(dim)) for row in matrix]
            new_pc = [sum(scores[i] * matrix[i][j] for i in range(n)) for j in range(dim)]
            if deflation_vec is not None:
                dot = sum(new_pc[j] * deflation_vec[j] for j in range(dim))
                new_pc = [new_pc[j] - dot * deflation_vec[j] for j in range(dim)]
            pc = _normalize(new_pc)
        return pc

    pc1 = _power_iter(centered)
    pc2 = _power_iter(centered, deflation_vec=pc1)

    coords = [
        (
            sum(centered[i][j] * pc1[j] for j in range(dim)),
            sum(centered[i][j] * pc2[j] for j in range(dim)),
        )
        for i in range(n)
    ]
    max_abs = max((max(abs(x), abs(y)) for x, y in coords), default=1.0)
    if max_abs > 0:
        coords = [(x / max_abs, y / max_abs) for x, y in coords]
    return coords


def _greedy_cluster(normalized_vecs: list[list[float]], threshold: float) -> list[int]:
    """Assign each vector to the nearest cluster centroid if similarity >= threshold."""
    assignments: list[int] = []
    centroids: list[list[float]] = []
    centroid_counts: list[int] = []

    for vec in normalized_vecs:
        best_cluster = -1
        best_sim = threshold

        for ci, centroid in enumerate(centroids):
            sim = _cosine_sim(vec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_cluster = ci

        if best_cluster >= 0:
            count = centroid_counts[best_cluster]
            old = centroids[best_cluster]
            new_centroid = [(old[j] * count + vec[j]) / (count + 1) for j in range(len(vec))]
            centroids[best_cluster] = _normalize(new_centroid)
            centroid_counts[best_cluster] += 1
            assignments.append(best_cluster)
        else:
            assignments.append(len(centroids))
            centroids.append(list(vec))
            centroid_counts.append(1)

    return assignments


def _generate_cluster_label(
    articles: list[dict[str, Any]],
    user_id: int | None = None,
) -> tuple[str, str]:
    """Call the LLM to generate a headline and trend summary for a cluster."""
    api_key, base_url, model = _cluster_ai_config()

    articles_text = "\n".join(
        f"- Title: {a.get('title', '')}\n  Summary: {a.get('summary', '')}" for a in articles[:10]
    )

    from news_dashboard.ai_client import chat_create, get_chat_client

    client = get_chat_client(api_key=api_key, base_url=base_url)
    result = chat_create(
        client,
        name="topic-cluster-label",
        tags=["clustering"],
        user_id=user_id,
        prompt=None,
        model=model,
        messages=[
            {
                "role": "user",
                "content": f"{_CLUSTER_LABEL_PROMPT}\n\nArticles:\n{articles_text}",
            },
        ],
        max_tokens=200,
    )
    text = (result.choices[0].message.content or "").strip()

    headline = ""
    trend_summary = ""
    for line in text.splitlines():
        if line.startswith("HEADLINE:"):
            headline = line[len("HEADLINE:") :].strip()
        elif line.startswith("SUMMARY:"):
            trend_summary = line[len("SUMMARY:") :].strip()

    if not headline:
        headline = articles[0].get("title", "Untitled Story")
    if not trend_summary:
        trend_summary = f"A cluster of {len(articles)} related articles."

    return headline, trend_summary


def cluster_recent_articles(
    user_id: int | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Cluster articles from the last 7 days by embedding similarity.

    Returns a list of story cluster dicts:
      - id: int
      - headline: str
      - trend_summary: str
      - x, y: float (2D coordinates in [-1, 1])
      - article_ids: list[int]
      - articles: list[{id, title, url, summary}]
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        if user_id is None:
            rows = conn.execute(
                """
                SELECT id, title, url, summary, category, embedding
                FROM articles
                WHERE discovered_at::timestamptz >= NOW() - INTERVAL '7 days'
                  AND embedding IS NOT NULL
                ORDER BY discovered_at DESC
                LIMIT %s
                """,
                (_MAX_ARTICLES,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT a.id, a.title, a.url, a.summary, a.category, a.embedding
                FROM articles a
                JOIN sources src ON src.slug = a.source_slug
                LEFT JOIN user_sources us
                  ON us.source_slug = src.slug AND us.user_id = %s
                LEFT JOIN user_article_state uas
                  ON uas.article_id = a.id AND uas.user_id = %s
                WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '7 days'
                  AND a.embedding IS NOT NULL
                  AND COALESCE(uas.state, 'today') != 'archived'
                  AND (
                    (
                      src.owner_user_id IS NULL
                      AND COALESCE(us.enabled, TRUE) IS TRUE
                    )
                    OR (
                      src.owner_user_id = %s
                      AND src.enabled IS TRUE
                    )
                  )
                ORDER BY a.discovered_at DESC
                LIMIT %s
                """,
                (user_id, user_id, user_id, _MAX_ARTICLES),
            ).fetchall()

    if not rows:
        return []

    article_data: list[dict[str, Any]] = []
    norm_vecs: list[list[float]] = []
    for row in rows:
        vec = _unpack_embedding(bytes(row["embedding"]))
        norm_vec = _normalize(vec)
        article_data.append(
            {
                "id": row["id"],
                "title": row["title"],
                "url": row["url"],
                "summary": row["summary"],
                "category": row["category"],
            }
        )
        norm_vecs.append(norm_vec)

    assignments = _greedy_cluster(norm_vecs, _CLUSTER_THRESHOLD)

    cluster_map: dict[int, list[int]] = {}
    for idx, cid in enumerate(assignments):
        cluster_map.setdefault(cid, []).append(idx)

    valid_clusters = [
        (cid, indices) for cid, indices in cluster_map.items() if len(indices) >= _MIN_CLUSTER_SIZE
    ]

    if not valid_clusters:
        return []

    centroids = [
        _normalize(_vec_mean([norm_vecs[i] for i in indices])) for _, indices in valid_clusters
    ]
    coords_2d = _pca_2d(centroids)

    result: list[dict[str, Any]] = []
    for cluster_seq, ((cid, indices), (cx, cy)) in enumerate(
        zip(valid_clusters, coords_2d, strict=False)
    ):
        cluster_articles = [article_data[i] for i in indices]
        try:
            headline, trend_summary = _generate_cluster_label(cluster_articles, user_id=user_id)
        except Exception:
            logger.exception("Failed to generate label for cluster %d", cid)
            headline = cluster_articles[0]["title"]
            trend_summary = f"A cluster of {len(cluster_articles)} related articles."

        result.append(
            {
                "id": cluster_seq,
                "headline": headline,
                "trend_summary": trend_summary,
                "x": cx,
                "y": cy,
                "article_ids": [a["id"] for a in cluster_articles],
                "articles": [
                    {
                        "id": a["id"],
                        "title": a["title"],
                        "url": a["url"],
                        "summary": a["summary"],
                    }
                    for a in cluster_articles
                ],
            }
        )

    return result
