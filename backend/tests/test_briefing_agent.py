"""Pure-function unit tests for the briefing agent pipeline stages.

No DB or network access — covers theme clustering and citation verification
in isolation from ``news_dashboard.briefings.service``.
"""

from __future__ import annotations

from typing import Any

import pytest

from news_dashboard.briefing_agent import (
    STAGE_ASSEMBLY,
    STAGE_CANDIDATE_SELECTION,
    STAGE_CITATION_VERIFICATION,
    STAGE_DRAFTING,
    STAGE_THEME_CLUSTERING,
    Theme,
    cluster_themes,
    flatten_themes,
    verify_citations,
)

# ── cluster_themes / flatten_themes ───────────────────────────────────────────


def test_cluster_themes_groups_by_category() -> None:
    candidates = [
        {"id": 1, "category": "tech"},
        {"id": 2, "category": "sports"},
        {"id": 3, "category": "tech"},
    ]
    themes = cluster_themes(candidates)
    by_label = {t.label: [c["id"] for c in t.candidates] for t in themes}
    assert by_label == {"tech": [1, 3], "sports": [2]}


def test_cluster_themes_preserves_first_seen_order() -> None:
    candidates = [
        {"id": 1, "category": "b"},
        {"id": 2, "category": "a"},
        {"id": 3, "category": "b"},
    ]
    themes = cluster_themes(candidates)
    assert [t.label for t in themes] == ["b", "a"]


def test_cluster_themes_defaults_missing_category_to_general() -> None:
    candidates: list[dict[str, Any]] = [{"id": 1, "category": None}, {"id": 2}]
    themes = cluster_themes(candidates)
    assert len(themes) == 1
    assert themes[0].label == "General"


def test_flatten_themes_restores_full_candidate_list() -> None:
    candidates = [
        {"id": 1, "category": "tech"},
        {"id": 2, "category": "sports"},
        {"id": 3, "category": "tech"},
    ]
    themes = cluster_themes(candidates)
    assert flatten_themes(themes) == [
        {"id": 1, "category": "tech"},
        {"id": 3, "category": "tech"},
        {"id": 2, "category": "sports"},
    ]


def test_flatten_themes_empty_list() -> None:
    assert flatten_themes([]) == []


def test_theme_is_a_plain_dataclass() -> None:
    theme = Theme(label="tech", candidates=[{"id": 1}])
    assert theme.label == "tech"
    assert theme.candidates == [{"id": 1}]


# ── verify_citations ──────────────────────────────────────────────────────────


def test_verify_citations_strips_unknown_ids() -> None:
    raw = {
        "title": "T",
        "summary": "S",
        "sections": [{"title": "A", "body": "B", "citations": [1, 2, 999]}],
        "worth_opening": [1, 999],
    }
    content, unsupported = verify_citations(raw, candidate_ids={1, 2})
    assert content["sections"][0]["citations"] == [1, 2]
    assert content["worth_opening"] == [1]
    assert unsupported == []


def test_verify_citations_flags_section_with_only_unsupported_citations() -> None:
    raw = {
        "title": "T",
        "summary": "S",
        "sections": [
            {"title": "Grounded", "body": "B1", "citations": [1]},
            {"title": "Hallucinated", "body": "B2", "citations": [999]},
        ],
    }
    content, unsupported = verify_citations(raw, candidate_ids={1})
    assert content["sections"][0]["citations"] == [1]
    assert content["sections"][1]["citations"] == []
    assert unsupported == ["Hallucinated"]


def test_verify_citations_section_with_no_citations_is_not_flagged_unsupported() -> None:
    raw = {"title": "T", "summary": "S", "sections": [{"title": "A", "body": "B"}]}
    content, unsupported = verify_citations(raw, candidate_ids={1})
    assert content["sections"][0]["citations"] == []
    assert unsupported == []


def test_verify_citations_raises_value_error_on_missing_keys() -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        verify_citations({"title": "T"}, candidate_ids=set())


def test_verify_citations_raises_type_error_when_sections_not_a_list() -> None:
    raw = {"title": "T", "summary": "S", "sections": "nope"}
    with pytest.raises(TypeError, match="must be a list"):
        verify_citations(raw, candidate_ids=set())


def test_verify_citations_handles_missing_worth_opening() -> None:
    raw = {"title": "T", "summary": "S", "sections": []}
    content, _unsupported = verify_citations(raw, candidate_ids={1})
    assert content["worth_opening"] == []


def test_stage_constants_cover_the_full_pipeline() -> None:
    from news_dashboard.briefing_agent import STAGE_ORDER

    assert STAGE_ORDER == (
        STAGE_CANDIDATE_SELECTION,
        STAGE_THEME_CLUSTERING,
        STAGE_DRAFTING,
        STAGE_CITATION_VERIFICATION,
        STAGE_ASSEMBLY,
    )
