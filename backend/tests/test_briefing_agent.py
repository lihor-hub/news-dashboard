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
    STAGE_ORDER,
    STAGE_THEME_CLUSTERING,
    Theme,
    cluster_themes,
    flatten_themes,
    verify_citations,
)
from news_dashboard.briefings.service import (
    BriefingNode,
    BriefingState,
    _compile_briefing_graph,
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


def test_verify_citations_removes_duplicates() -> None:
    raw = {
        "title": "T",
        "summary": "Summary",
        "sections": [{"title": "A", "body": "B", "citations": [1, 1, 2, 1]}],
    }
    content, _unsupported = verify_citations(raw, candidate_ids={1, 2})
    assert content["sections"][0]["citations"] == [1, 2]


def test_verify_citations_rejects_empty_summary_with_stories() -> None:
    raw = {
        "title": "T",
        "summary": "  ",
        "sections": [{"title": "A", "body": "B", "citations": [1]}],
    }
    with pytest.raises(ValueError, match="summary"):
        verify_citations(raw, candidate_ids={1})


@pytest.mark.parametrize(
    ("body_word_count", "raises"),
    [(1_797, False), (1_798, True)],
    ids=["exactly-1800-accepted", "1801-rejected"],
)
def test_verify_citations_enforces_total_1800_word_budget(
    body_word_count: int, raises: bool
) -> None:
    raw = {
        "title": "T",
        "summary": "Summary",
        "sections": [
            {"title": "A", "body": " ".join(["word"] * body_word_count), "citations": [1]}
        ],
    }
    if raises:
        with pytest.raises(ValueError, match="1800-word"):
            verify_citations(raw, candidate_ids={1})
    else:
        content, _unsupported = verify_citations(raw, candidate_ids={1})
        assert content["summary"] == "Summary"


def test_stage_constants_cover_the_full_pipeline() -> None:
    assert STAGE_ORDER == (
        STAGE_CANDIDATE_SELECTION,
        STAGE_THEME_CLUSTERING,
        STAGE_DRAFTING,
        STAGE_CITATION_VERIFICATION,
        STAGE_ASSEMBLY,
    )


def test_briefing_graph_has_exact_pipeline_nodes_and_edges() -> None:
    def _node(state: BriefingState) -> BriefingState:
        return state

    compiled = _compile_briefing_graph(dict.fromkeys(STAGE_ORDER, _node))
    drawable = compiled.get_graph()

    assert set(drawable.nodes) == {"__start__", *STAGE_ORDER, "__end__"}
    assert {(edge.source, edge.target, edge.conditional) for edge in drawable.edges} == {
        ("__start__", STAGE_CANDIDATE_SELECTION, False),
        (STAGE_CANDIDATE_SELECTION, "__end__", True),
        (STAGE_CANDIDATE_SELECTION, STAGE_THEME_CLUSTERING, True),
        (STAGE_THEME_CLUSTERING, STAGE_DRAFTING, False),
        (STAGE_DRAFTING, STAGE_CITATION_VERIFICATION, False),
        (STAGE_CITATION_VERIFICATION, STAGE_ASSEMBLY, False),
        (STAGE_ASSEMBLY, "__end__", False),
    }


def test_briefing_graph_no_candidates_routes_to_end_and_skips_downstream() -> None:
    calls: list[str] = []

    def _candidate_selection(_state: BriefingState) -> BriefingState:
        calls.append(STAGE_CANDIDATE_SELECTION)
        return {"candidates": []}

    def _downstream(_state: BriefingState) -> BriefingState:
        calls.append("downstream")
        return {}

    nodes: dict[str, BriefingNode] = dict.fromkeys(STAGE_ORDER, _downstream)
    nodes[STAGE_CANDIDATE_SELECTION] = _candidate_selection

    result = _compile_briefing_graph(nodes).invoke(BriefingState())

    assert result == {"candidates": []}
    assert calls == [STAGE_CANDIDATE_SELECTION]


def test_briefing_graph_node_failure_skips_every_later_node() -> None:
    calls: list[str] = []

    def _candidate_selection(_state: BriefingState) -> BriefingState:
        calls.append(STAGE_CANDIDATE_SELECTION)
        return {"candidates": [{"id": 1}]}

    def _theme_failure(_state: BriefingState) -> BriefingState:
        calls.append(STAGE_THEME_CLUSTERING)
        msg = "theme node failed"
        raise RuntimeError(msg)

    def _downstream(_state: BriefingState) -> BriefingState:
        calls.append("downstream")
        return {}

    nodes: dict[str, BriefingNode] = dict.fromkeys(STAGE_ORDER, _downstream)
    nodes[STAGE_CANDIDATE_SELECTION] = _candidate_selection
    nodes[STAGE_THEME_CLUSTERING] = _theme_failure

    with pytest.raises(RuntimeError, match="theme node failed"):
        _compile_briefing_graph(nodes).invoke(BriefingState())

    assert calls == [STAGE_CANDIDATE_SELECTION, STAGE_THEME_CLUSTERING]
