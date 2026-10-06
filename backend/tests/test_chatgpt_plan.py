from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard import ai_client


def _event(kind: str, **kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(type=kind, **kwargs)


def test_plan_stream_must_complete_and_omits_unsupported_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.chatgpt_plan import PlanChatClient

    monkeypatch.setenv("AI_MODEL_PRESET", "luna-high")
    client = MagicMock()
    client.__enter__.return_value = client
    stream = client.responses.create.return_value.__enter__.return_value
    stream.__iter__.return_value = iter(
        [
            _event("response.output_text.delta", delta="answer"),
            _event("response.completed", response=SimpleNamespace(id="resp-test", usage=None)),
        ]
    )
    with (
        patch("news_dashboard.chatgpt_plan.access_token", return_value="test-token"),
        patch("openai.OpenAI", return_value=client),
    ):
        completion = PlanChatClient().create(
            model="gpt-6-luna",
            messages=[
                {"role": "system", "content": "instructions"},
                {"role": "user", "content": "question"},
            ],
            max_tokens=100,
            temperature=0,
            metadata={"private": "value"},
            name="trace",
            response_format={"type": "json_object"},
        )
    assert completion.choices[0].message.content == "answer"
    request = client.responses.create.call_args.kwargs
    assert request == {
        "model": "gpt-6-luna",
        "input": [
            {"role": "developer", "content": "instructions"},
            {"role": "user", "content": "question"},
        ],
        "store": False,
        "stream": True,
        "reasoning": {"effort": "high"},
        "text": {"format": {"type": "json_object"}},
    }


@pytest.mark.parametrize("terminal", ["response.incomplete", "response.failed", "error", None])
def test_plan_rejects_failed_and_interrupted_streams(terminal: str | None) -> None:
    from news_dashboard.chatgpt_plan import PlanChatClient, PlanInferenceError

    client = MagicMock()
    client.__enter__.return_value = client
    events = [_event("response.output_text.delta", delta="partial")]
    if terminal:
        events.append(_event(terminal, response=SimpleNamespace(error=None)))
    client.responses.create.return_value.__enter__.return_value.__iter__.return_value = iter(events)
    with (
        patch("news_dashboard.chatgpt_plan.access_token", return_value="test-token"),
        patch("openai.OpenAI", return_value=client),
        pytest.raises(PlanInferenceError),
    ):
        PlanChatClient().create(model="gpt-6-luna", messages=[])


def test_subscription_client_cannot_fall_back_to_paid_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.chatgpt_plan import PlanChatClient

    monkeypatch.setenv("OPENAI_API_KEY", "paid-key")
    with patch("news_dashboard.ai_client.get_openai_client") as paid_client:
        client = ai_client.get_chat_client(api_key="chatgpt-plan")
    assert type(client).__name__ == PlanChatClient.__name__
    paid_client.assert_not_called()
