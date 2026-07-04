"""Regression test: DEFAULT_SOURCES must not contain duplicate slugs (issue #842)."""

from __future__ import annotations

from collections import Counter

from news_dashboard.sources import DEFAULT_SOURCES


def test_default_sources_have_unique_slugs() -> None:
    """Every DEFAULT_SOURCES slug appears exactly once.

    A duplicate slug lets ingest_all() fetch the same built-in source twice
    in one run and lets onboarding recommendations offer duplicate candidates,
    even though PostgreSQL upserts converge on a single sources row.
    """
    slugs = [source.slug for source in DEFAULT_SOURCES]
    counts = Counter(slugs)
    duplicates = {slug: count for slug, count in counts.items() if count > 1}
    assert not duplicates, f"duplicate DEFAULT_SOURCES slugs: {duplicates}"
