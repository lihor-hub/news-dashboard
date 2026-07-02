"""Tests for the ai_stats feature module's service layer.

Covers the word-cloud TF-IDF aggregation and the per-article embedding map,
including per-user visibility scoping (global vs private vs disabled sources).
"""

from __future__ import annotations

import struct

from news_dashboard.ai_stats.service import _tokenize, embedding_map, word_cloud
from news_dashboard.db import connect

# ── helpers ───────────────────────────────────────────────────────────────────


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _seed_source(
    pg_url: str,
    slug: str,
    *,
    owner_user_id: int | None = None,
) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id)
            VALUES (%s, %s, %s, 'tech', 'rss_feed', %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, f"https://{slug}.example", owner_user_id),
        )


def _seed_article(
    pg_url: str,
    *,
    slug: str = "ai-stats-src",
    url_slug: str,
    title: str,
    summary: str = "",
    category: str = "tech",
    embedding: list[float] | None = None,
) -> int:
    _seed_source(pg_url, slug)
    blob = _pack_vec(embedding) if embedding is not None else None
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, summary, embedding, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', %s, %s, NOW())
            RETURNING id
            """,
            (
                f"https://{slug}.example/{url_slug}",
                f"https://{slug}.example/{url_slug}",
                title,
                slug,
                slug,
                category,
                summary,
                blob,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_user(pg_url: str, username: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


# ── _tokenize ─────────────────────────────────────────────────────────────────


def test_tokenize_filters_stopwords_and_short_tokens() -> None:
    tokens = _tokenize("The new AI model and its uses in an open, modern world")
    assert "the" not in tokens
    assert "and" not in tokens
    assert "its" not in tokens
    assert "in" not in tokens
    assert "an" not in tokens
    assert "ai" not in tokens  # shorter than 3 chars
    assert "model" in tokens
    assert "modern" in tokens
    assert "world" in tokens


def test_tokenize_lowercases_and_keeps_hyphenated_terms() -> None:
    tokens = _tokenize("Kubernetes-Native tooling beats VM-based flows")
    assert "kubernetes-native" in tokens
    assert "vm-based" in tokens
    assert "tooling" in tokens


# ── word_cloud ────────────────────────────────────────────────────────────────


def test_word_cloud_empty_corpus_returns_no_terms(pg_clean: str) -> None:
    result = word_cloud(database_url=pg_clean)
    assert result["terms"] == []
    assert result["article_count"] == 0
    assert result["days"] == 7


def test_word_cloud_ranks_distinctive_terms_above_ubiquitous(pg_clean: str) -> None:
    # "kubernetes" appears once in every article (ubiquitous), while
    # "quantum" appears three times but only in a single article.
    for idx in range(4):
        _seed_article(
            pg_clean,
            url_slug=f"ubiquitous-{idx}",
            title=f"Kubernetes release note {idx}",
            summary="Improvements landed.",
        )
    _seed_article(
        pg_clean,
        url_slug="distinctive",
        title="Quantum breakthrough: quantum chips go mainstream",
        summary="A quantum leap for kubernetes workloads.",
    )

    result = word_cloud(database_url=pg_clean)
    terms = {t["term"]: t for t in result["terms"]}
    assert "quantum" in terms
    assert "kubernetes" in terms
    ranked = [t["term"] for t in result["terms"]]
    assert ranked.index("quantum") < ranked.index("kubernetes")
    assert result["article_count"] == 5


def test_word_cloud_weights_normalized_and_counts_reported(pg_clean: str) -> None:
    _seed_article(
        pg_clean,
        url_slug="weights",
        title="Rust rewrites accelerate compilers",
        summary="Rust rust rust everywhere.",
    )
    result = word_cloud(database_url=pg_clean)
    assert result["terms"], "expected at least one term"
    weights = [t["weight"] for t in result["terms"]]
    assert max(weights) == 1.0
    assert all(0.0 < w <= 1.0 for w in weights)
    top = result["terms"][0]
    assert top["term"] == "rust"
    assert top["count"] == 4


def test_word_cloud_caps_terms(pg_clean: str) -> None:
    _seed_article(
        pg_clean,
        url_slug="caps",
        title="alpha bravo charlie delta echo foxtrot golf hotel india juliet",
        summary="kilo lima mike november oscar papa quebec romeo sierra tango",
    )
    result = word_cloud(database_url=pg_clean, max_terms=5)
    assert len(result["terms"]) == 5


def test_word_cloud_scopes_to_user_visible_articles(pg_clean: str) -> None:
    user_id = _seed_user(pg_clean, "wc-user")
    other_id = _seed_user(pg_clean, "wc-other")

    _seed_source(pg_clean, "wc-visible-global")
    _seed_source(pg_clean, "wc-disabled-global")
    _seed_source(pg_clean, "wc-own-private", owner_user_id=user_id)
    _seed_source(pg_clean, "wc-other-private", owner_user_id=other_id)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled)"
            " VALUES (%s, 'wc-disabled-global', FALSE)",
            (user_id,),
        )

    _seed_article(pg_clean, slug="wc-visible-global", url_slug="v", title="Visibleterm everywhere")
    _seed_article(pg_clean, slug="wc-own-private", url_slug="o", title="Ownprivateterm article")
    _seed_article(pg_clean, slug="wc-disabled-global", url_slug="d", title="Disabledterm article")
    _seed_article(pg_clean, slug="wc-other-private", url_slug="x", title="Foreignterm article")

    result = word_cloud(user_id=user_id, database_url=pg_clean)
    terms = {t["term"] for t in result["terms"]}
    assert "visibleterm" in terms
    assert "ownprivateterm" in terms
    assert "disabledterm" not in terms
    assert "foreignterm" not in terms
    assert result["article_count"] == 2


# ── embedding_map ─────────────────────────────────────────────────────────────


def test_embedding_map_empty_corpus(pg_clean: str) -> None:
    result = embedding_map(database_url=pg_clean)
    assert result["points"] == []
    assert result["clusters"] == []
    assert result["embedded_count"] == 0
    assert result["total_count"] == 0


def test_embedding_map_returns_per_article_points_within_unit_range(pg_clean: str) -> None:
    dim = 8
    for idx in range(4):
        vec = [0.0] * dim
        vec[idx] = 1.0
        _seed_article(
            pg_clean,
            url_slug=f"pt-{idx}",
            title=f"Point article {idx}",
            embedding=vec,
        )

    result = embedding_map(database_url=pg_clean)
    assert len(result["points"]) == 4
    for point in result["points"]:
        assert set(point) >= {"id", "title", "category", "x", "y", "cluster"}
        assert -1.01 <= point["x"] <= 1.01
        assert -1.01 <= point["y"] <= 1.01
        assert point["category"] == "tech"


def test_embedding_map_groups_similar_vectors_into_same_cluster(pg_clean: str) -> None:
    dim = 8
    group_a = [[1.0, 0.01 * i] + [0.0] * (dim - 2) for i in range(3)]
    group_b = [[0.0] * (dim - 2) + [0.01 * i, 1.0] for i in range(3)]
    ids_a = [
        _seed_article(pg_clean, url_slug=f"a-{i}", title=f"Alpha topic {i}", embedding=v)
        for i, v in enumerate(group_a)
    ]
    ids_b = [
        _seed_article(pg_clean, url_slug=f"b-{i}", title=f"Beta subject {i}", embedding=v)
        for i, v in enumerate(group_b)
    ]

    result = embedding_map(database_url=pg_clean)
    cluster_of = {p["id"]: p["cluster"] for p in result["points"]}
    assert len({cluster_of[i] for i in ids_a}) == 1
    assert len({cluster_of[i] for i in ids_b}) == 1
    assert cluster_of[ids_a[0]] != cluster_of[ids_b[0]]

    clusters = {c["id"]: c for c in result["clusters"]}
    assert clusters[cluster_of[ids_a[0]]]["size"] == 3
    assert clusters[cluster_of[ids_a[0]]]["label"]
    assert "alpha" in clusters[cluster_of[ids_a[0]]]["label"].lower()


def test_embedding_map_excludes_unembedded_but_counts_them(pg_clean: str) -> None:
    for idx in range(3):
        _seed_article(
            pg_clean,
            url_slug=f"emb-{idx}",
            title=f"Embedded {idx}",
            embedding=[1.0, 0.01 * idx, 0.0, 0.0],
        )
    for idx in range(2):
        _seed_article(pg_clean, url_slug=f"raw-{idx}", title=f"Unembedded {idx}")

    result = embedding_map(database_url=pg_clean)
    assert len(result["points"]) == 3
    assert result["embedded_count"] == 3
    assert result["total_count"] == 5


def test_embedding_map_scopes_to_user_visible_articles(pg_clean: str) -> None:
    user_id = _seed_user(pg_clean, "em-user")
    other_id = _seed_user(pg_clean, "em-other")
    _seed_source(pg_clean, "em-global")
    _seed_source(pg_clean, "em-other-private", owner_user_id=other_id)

    vec = [1.0, 0.0, 0.0, 0.0]
    visible_id = _seed_article(
        pg_clean, slug="em-global", url_slug="v", title="Visible", embedding=vec
    )
    hidden_id = _seed_article(
        pg_clean, slug="em-other-private", url_slug="h", title="Hidden", embedding=vec
    )

    result = embedding_map(user_id=user_id, database_url=pg_clean)
    ids = {p["id"] for p in result["points"]}
    assert visible_id in ids
    assert hidden_id not in ids
    assert result["total_count"] == 1
