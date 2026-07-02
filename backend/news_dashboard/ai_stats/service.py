"""AI-derived statistics over the user's visible news corpus.

Pure aggregation over data the pipeline already produced (titles, summaries,
stored embeddings) — no LLM calls happen here, so the endpoints are fast,
free, and always available.
"""

from __future__ import annotations

import math
import re
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.embeddings import decode_embedding
from news_dashboard.insights import (
    greedy_cluster,
    load_recent_embedded_articles,
    normalize_vector,
    pca_2d,
)

_MAX_ARTICLES = 300
_CLUSTER_THRESHOLD = 0.72
_LABEL_TERMS = 2

# Common English stopwords plus newsfeed noise that would otherwise dominate
# every word cloud without carrying any signal.
_STOPWORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "across",
        "after",
        "again",
        "against",
        "all",
        "along",
        "already",
        "also",
        "am",
        "amid",
        "among",
        "an",
        "and",
        "another",
        "any",
        "are",
        "aren't",
        "around",
        "as",
        "at",
        "back",
        "based",
        "be",
        "because",
        "become",
        "becomes",
        "been",
        "before",
        "behind",
        "being",
        "below",
        "best",
        "better",
        "between",
        "big",
        "biggest",
        "both",
        "but",
        "by",
        "can",
        "can't",
        "cannot",
        "com",
        "could",
        "couldn't",
        "day",
        "days",
        "despite",
        "did",
        "didn't",
        "do",
        "does",
        "doesn't",
        "doing",
        "don't",
        "down",
        "during",
        "each",
        "early",
        "even",
        "ever",
        "every",
        "few",
        "first",
        "for",
        "from",
        "further",
        "get",
        "gets",
        "getting",
        "given",
        "goes",
        "going",
        "good",
        "got",
        "great",
        "had",
        "hadn't",
        "has",
        "hasn't",
        "have",
        "haven't",
        "having",
        "he",
        "he'd",
        "he'll",
        "he's",
        "her",
        "here",
        "here's",
        "hers",
        "herself",
        "high",
        "him",
        "himself",
        "his",
        "how",
        "how's",
        "however",
        "http",
        "https",
        "i",
        "i'd",
        "i'll",
        "i'm",
        "i've",
        "if",
        "in",
        "inside",
        "instead",
        "into",
        "is",
        "isn't",
        "it",
        "it's",
        "its",
        "itself",
        "just",
        "know",
        "known",
        "large",
        "last",
        "late",
        "later",
        "latest",
        "least",
        "less",
        "let's",
        "like",
        "likely",
        "little",
        "long",
        "look",
        "looking",
        "made",
        "make",
        "makes",
        "making",
        "many",
        "may",
        "maybe",
        "me",
        "might",
        "million",
        "minute",
        "minutes",
        "month",
        "months",
        "more",
        "most",
        "much",
        "must",
        "mustn't",
        "my",
        "myself",
        "near",
        "need",
        "needs",
        "never",
        "new",
        "news",
        "next",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "often",
        "old",
        "on",
        "once",
        "one",
        "only",
        "onto",
        "or",
        "other",
        "others",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "part",
        "per",
        "plan",
        "plans",
        "post",
        "read",
        "really",
        "recent",
        "report",
        "reports",
        "right",
        "said",
        "same",
        "say",
        "says",
        "see",
        "seen",
        "set",
        "several",
        "shan't",
        "she",
        "she'd",
        "she'll",
        "she's",
        "should",
        "shouldn't",
        "show",
        "shows",
        "since",
        "site",
        "small",
        "so",
        "some",
        "state",
        "still",
        "such",
        "take",
        "takes",
        "taking",
        "tell",
        "tells",
        "than",
        "that",
        "that's",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "there's",
        "these",
        "they",
        "they'd",
        "they'll",
        "they're",
        "they've",
        "third",
        "this",
        "those",
        "three",
        "through",
        "time",
        "times",
        "to",
        "today",
        "told",
        "too",
        "top",
        "toward",
        "two",
        "under",
        "until",
        "up",
        "use",
        "used",
        "user",
        "users",
        "uses",
        "using",
        "very",
        "via",
        "want",
        "wants",
        "was",
        "wasn't",
        "way",
        "ways",
        "we",
        "we'd",
        "we'll",
        "we're",
        "we've",
        "week",
        "weeks",
        "well",
        "went",
        "were",
        "weren't",
        "what",
        "what's",
        "when",
        "when's",
        "where",
        "where's",
        "which",
        "while",
        "who",
        "who's",
        "whom",
        "why",
        "why's",
        "will",
        "with",
        "within",
        "without",
        "won't",
        "work",
        "working",
        "works",
        "would",
        "wouldn't",
        "year",
        "years",
        "yet",
        "you",
        "you'd",
        "you'll",
        "you're",
        "you've",
        "your",
        "yours",
        "yourself",
        "yourselves",
    ]
)

_TOKEN_RE = re.compile(r"[a-z][a-z0-9'\-]{2,}")


def _tokenize(text: str) -> list[str]:
    """Lowercase, split into word-ish tokens of 3+ chars, drop stopwords."""
    return [
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS and not token.endswith("-")
    ]


def _load_recent_articles(
    user_id: int | None,
    days: int,
    limit: int,
    database_url: str | None,
) -> list[dict[str, Any]]:
    """Recent visible articles regardless of embedding status.

    Same visibility scoping as ``insights.load_recent_embedded_articles`` but
    without the ``embedding IS NOT NULL`` filter, so callers can also report
    how much of the corpus is embedded.
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        if user_id is None:
            rows = conn.execute(
                """
                SELECT id, title, summary, category, (embedding IS NOT NULL) AS embedded
                FROM articles
                WHERE discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
                ORDER BY discovered_at DESC
                LIMIT %s
                """,
                (days, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT a.id, a.title, a.summary, a.category,
                       (a.embedding IS NOT NULL) AS embedded
                FROM articles a
                JOIN sources src ON src.slug = a.source_slug
                LEFT JOIN user_sources us
                  ON us.source_slug = src.slug AND us.user_id = %s
                LEFT JOIN user_article_state uas
                  ON uas.article_id = a.id AND uas.user_id = %s
                WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
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
                (user_id, user_id, days, user_id, limit),
            ).fetchall()

    return [dict(row) for row in rows]


def _tfidf_scores(docs: list[list[str]]) -> dict[str, tuple[int, float]]:
    """Map term -> (total count, TF-IDF score) across the given token lists."""
    tf: dict[str, int] = {}
    df: dict[str, int] = {}
    for tokens in docs:
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1

    n_docs = len(docs)
    return {term: (count, count * math.log(1 + n_docs / df[term])) for term, count in tf.items()}


def word_cloud(
    user_id: int | None = None,
    days: int = 7,
    max_terms: int = 60,
    database_url: str | None = None,
) -> dict[str, Any]:
    """TF-IDF-weighted terms from recent visible articles' titles and summaries.

    Returns ``{"terms": [{"term", "count", "weight"}], "article_count", "days"}``
    with weights normalized to (0, 1] and terms sorted by weight descending.
    """
    articles = _load_recent_articles(user_id, days, _MAX_ARTICLES, database_url)

    docs = [
        _tokenize(f"{article['title'] or ''} {article['summary'] or ''}") for article in articles
    ]
    scored = _tfidf_scores([doc for doc in docs if doc])

    ranked = sorted(scored.items(), key=lambda item: (-item[1][1], item[0]))[:max_terms]
    max_score = ranked[0][1][1] if ranked else 1.0

    return {
        "terms": [
            {"term": term, "count": count, "weight": score / max_score}
            for term, (count, score) in ranked
        ],
        "article_count": len(articles),
        "days": days,
    }


def _cluster_label(titles: list[str]) -> str:
    """Deterministic cluster label: the top TF-IDF terms of member titles."""
    docs = [_tokenize(title) for title in titles]
    scored = _tfidf_scores([doc for doc in docs if doc])
    top = sorted(scored.items(), key=lambda item: (-item[1][1], item[0]))[:_LABEL_TERMS]
    return " · ".join(term for term, _ in top)


def embedding_map(
    user_id: int | None = None,
    days: int = 7,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Per-article 2D PCA projection of stored embeddings with greedy clusters.

    Returns ``{"points", "clusters", "embedded_count", "total_count", "days"}``;
    ``total_count`` includes visible articles that have no embedding yet so the
    UI can explain sparse maps.
    """
    all_articles = _load_recent_articles(user_id, days, _MAX_ARTICLES, database_url)
    embedded = load_recent_embedded_articles(user_id=user_id, days=days, database_url=database_url)

    if not embedded:
        return {
            "points": [],
            "clusters": [],
            "embedded_count": 0,
            "total_count": len(all_articles),
            "days": days,
        }

    norm_vecs = [
        normalize_vector(decode_embedding(bytes(article["embedding"]))) for article in embedded
    ]
    coords = pca_2d(norm_vecs)
    assignments = greedy_cluster(norm_vecs, _CLUSTER_THRESHOLD)

    members: dict[int, list[int]] = {}
    for idx, cid in enumerate(assignments):
        members.setdefault(cid, []).append(idx)

    clusters = [
        {
            "id": cid,
            "label": _cluster_label([embedded[i]["title"] or "" for i in indices]),
            "size": len(indices),
        }
        for cid, indices in sorted(members.items(), key=lambda item: -len(item[1]))
    ]

    points = [
        {
            "id": article["id"],
            "title": article["title"],
            "category": article["category"],
            "x": x,
            "y": y,
            "cluster": cid,
        }
        for article, (x, y), cid in zip(embedded, coords, assignments, strict=True)
    ]

    return {
        "points": points,
        "clusters": clusters,
        "embedded_count": len(embedded),
        "total_count": len(all_articles),
        "days": days,
    }
