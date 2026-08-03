from __future__ import annotations

import pytest

from news_dashboard.auto_enrichment import auto_enrich_limit


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 5), ("-2", 0), ("0", 0), ("8", 8), ("99", 20)]
)
def test_auto_enrich_limit_is_defaulted_and_clamped(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: int
) -> None:
    if raw is None:
        monkeypatch.delenv("AI_AUTO_ENRICH_LIMIT", raising=False)
    else:
        monkeypatch.setenv("AI_AUTO_ENRICH_LIMIT", raw)

    assert auto_enrich_limit() == expected


def test_auto_enrich_limit_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AUTO_ENRICH_LIMIT", "many")

    assert auto_enrich_limit() == 5
