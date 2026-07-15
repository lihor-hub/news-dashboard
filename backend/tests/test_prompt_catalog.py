from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from news_dashboard.prompt_catalog import PROMPT_CATALOG, PromptCatalogEntry

EXPECTED_NAMES = {
    "ai-body-fetch",
    "briefing-chat",
    "briefing-push-hook",
    "lesson-chat",
    "lesson-infographic",
    "lesson-relevance",
    "lesson-slide-deck",
    "podcast-script-generation",
    "reading-list-summary",
    "recap-push-hook",
    "recommendation-explanation",
    "share-context",
    "summarize-media-article",
    "topic-cluster-label",
    "translate-article",
    "translate-body",
    "weekly-lesson-recap-narrative",
    "weekly-quiz",
    "weekly-recap-narrative",
}


def _load_sync_module(monkeypatch: pytest.MonkeyPatch, client: Any) -> ModuleType:
    class FakeLangfuseModule(ModuleType):
        Langfuse: Any

    fake_langfuse = FakeLangfuseModule("langfuse")
    fake_langfuse.Langfuse = lambda **_kwargs: client
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    path = Path(__file__).parents[2] / "scripts" / "sync_langfuse_prompts.py"
    spec = importlib.util.spec_from_file_location("sync_langfuse_prompts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_contains_exactly_the_managed_prompts() -> None:
    assert len(PROMPT_CATALOG) == 19
    assert {entry.name for entry in PROMPT_CATALOG} == EXPECTED_NAMES
    assert all(isinstance(entry, PromptCatalogEntry) for entry in PROMPT_CATALOG)


def test_catalog_prompt_shapes_are_valid_and_templates_are_safe() -> None:
    for entry in PROMPT_CATALOG:
        if entry.type == "text":
            assert isinstance(entry.prompt, str)
            assert entry.prompt.strip()
            contents = [entry.prompt]
        else:
            assert entry.type == "chat"
            assert isinstance(entry.prompt, tuple)
            assert entry.prompt
            assert all(message.role in {"system", "user", "assistant"} for message in entry.prompt)
            assert all(message.content.strip() for message in entry.prompt)
            contents = [message.content for message in entry.prompt]

        rendered = "\n".join(contents)
        assert "{{" in rendered
        assert "}}" in rendered
        assert "LANGFUSE_SECRET_KEY" not in rendered
        assert "sk-" not in rendered


def test_sync_creates_each_missing_prompt_with_production_label(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def get_prompt(self, *_args: Any, **_kwargs: Any) -> Any:
            message = "not found"
            raise RuntimeError(message)

        def create_prompt(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(version=len(calls))

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public-from-environment")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret-from-environment")
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example")
    module = _load_sync_module(monkeypatch, FakeClient())

    assert module.main() == 0
    assert len(calls) == len(PROMPT_CATALOG)
    assert {call["name"] for call in calls} == EXPECTED_NAMES
    assert all(call["labels"] == ["production"] for call in calls)
    output = capsys.readouterr().out
    assert "secret-from-environment" not in output
    assert "public-from-environment" not in output


def test_sync_is_idempotent_when_production_content_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_name = {entry.name: entry for entry in PROMPT_CATALOG}
    create_calls: list[dict[str, Any]] = []

    class FakeClient:
        def get_prompt(self, name: str, **_kwargs: Any) -> Any:
            entry = by_name[name]
            prompt = (
                entry.prompt
                if isinstance(entry.prompt, str)
                else [{"role": item.role, "content": item.content} for item in entry.prompt]
            )
            return SimpleNamespace(prompt=prompt, type=entry.type, version=7)

        def create_prompt(self, **kwargs: Any) -> Any:
            create_calls.append(kwargs)
            return SimpleNamespace(version=8)

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret")
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example")
    module = _load_sync_module(monkeypatch, FakeClient())

    assert module.main() == 0
    assert create_calls == []


@pytest.mark.parametrize("missing", ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"])
def test_sync_requires_all_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.setenv(name, "configured")
    monkeypatch.delenv(missing)
    module = _load_sync_module(monkeypatch, object())

    assert module.main() != 0
