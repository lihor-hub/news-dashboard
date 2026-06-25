from __future__ import annotations

import pytest

from news_dashboard.prompt_optimizer import (
    NegativeExample,
    PromptOptimizerError,
    _extract_question,
    _score_is_negative,
    build_optimizer_prompt,
    collect_negative_examples,
)


@pytest.fixture
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, True), (0.0, True), ("0", True), (1, False), ("1", False), (None, False), ("x", False)],
)
def test_score_is_negative(value: object, expected: bool) -> None:
    assert _score_is_negative(value) is expected


def test_extract_question_from_dict_and_string() -> None:
    assert _extract_question({"query": " hello ", "include_all": False}) == "hello"
    assert _extract_question("raw question") == "raw question"
    assert _extract_question(None) == ""
    assert _extract_question({"other": "x"}) == ""


def test_build_optimizer_prompt_includes_current_and_examples() -> None:
    examples = [
        NegativeExample(question="Q1", answer="A1", comment="too vague"),
        NegativeExample(question="Q2", answer="A2"),
    ]
    out = build_optimizer_prompt("CURRENT PROMPT TEXT", examples)

    assert "CURRENT PROMPT TEXT" in out
    assert "Q1" in out
    assert "A1" in out
    assert "too vague" in out
    assert "Q2" in out
    assert "A2" in out
    # The example without a comment must not emit a stray "User comment:" line.
    assert out.count("User comment:") == 1


@pytest.mark.usefixtures("_no_langfuse")
def test_collect_negative_examples_requires_langfuse() -> None:
    with pytest.raises(PromptOptimizerError, match="not configured"):
        collect_negative_examples()
