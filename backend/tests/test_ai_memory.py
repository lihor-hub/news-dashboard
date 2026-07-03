from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_user(database_url: str, username: str) -> int:
    from news_dashboard.db import connect

    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO users(username, password_hash)
            VALUES (%s, 'hash')
            RETURNING id
            """,
            (username,),
        ).fetchone()
    return int(row["id"])


def test_memory_crud_is_scoped_to_user(pg_clean: str) -> None:
    from news_dashboard.ai_memory.service import create_memory, list_memories, update_memory

    alice = _make_user(pg_clean, "alice-memory")
    bob = _make_user(pg_clean, "bob-memory")

    memory = create_memory(
        alice,
        "prioritize agent infrastructure",
        database_url=pg_clean,
    )
    assert list_memories(alice, database_url=pg_clean)[0]["content"] == (
        "prioritize agent infrastructure"
    )
    assert list_memories(bob, database_url=pg_clean) == []

    assert update_memory(bob, memory["id"], active=False, database_url=pg_clean) is None
    inactive = update_memory(alice, memory["id"], active=False, database_url=pg_clean)
    assert inactive is not None
    assert inactive["active"] is False
    assert list_memories(alice, database_url=pg_clean) == []


def test_prompt_formatter_uses_only_active_user_memories(pg_clean: str) -> None:
    from news_dashboard.ai_memory.service import create_memory, format_memories_for_prompt

    alice = _make_user(pg_clean, "alice-prompt")
    bob = _make_user(pg_clean, "bob-prompt")
    create_memory(alice, "prefer postgres operations", database_url=pg_clean)
    inactive = create_memory(alice, "ignore inactive memories", database_url=pg_clean)
    create_memory(bob, "bob private memory", database_url=pg_clean)

    from news_dashboard.ai_memory.service import update_memory

    update_memory(alice, inactive["id"], active=False, database_url=pg_clean)

    prompt = format_memories_for_prompt(alice, database_url=pg_clean)

    assert "prefer postgres operations" in prompt
    assert "ignore inactive memories" not in prompt
    assert "bob private memory" not in prompt


def test_briefing_prompt_includes_memory_for_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.briefings import _call_openai

    response = MagicMock()
    response.choices = [
        MagicMock(message=MagicMock(content='{"title":"T","summary":"S","sections":[]}'))
    ]
    chat_create = MagicMock(return_value=response)

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("system", None)),
        patch("news_dashboard.ai_client.chat_create", new=chat_create),
    ):
        monkeypatch.setattr(
            "news_dashboard.ai_memory.service.format_memories_for_prompt",
            lambda user_id: "User memory:\n- prefer infra" if user_id == 42 else "",
        )
        _call_openai(
            [{"id": 1, "title": "A", "summary": "S", "source_name": "Source", "category": "ai"}],
            "gpt-4o-mini",
            user_id=42,
        )

    system_message = chat_create.call_args.kwargs["messages"][0]["content"]
    assert "prefer infra" in system_message


def test_user_export_includes_memories_and_events(pg_clean: str) -> None:
    from news_dashboard.ai_memory.service import create_memory, record_memory_event
    from news_dashboard.export import assemble_user_export

    user_id = _make_user(pg_clean, "export-memory")
    memory = create_memory(user_id, "remember export", database_url=pg_clean)
    record_memory_event(
        user_id,
        event_type="feedback",
        source="ask_feedback",
        content="useful",
        memory_id=memory["id"],
        metadata={"trace_id": "t"},
        database_url=pg_clean,
    )

    exported = assemble_user_export(user_id, database_url=pg_clean)

    assert exported["ai_memories"][0]["content"] == "remember export"
    assert exported["ai_memory_events"][-1]["metadata"]["trace_id"] == "t"
