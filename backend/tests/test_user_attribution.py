"""Assert that user_id is threaded to Langfuse traces in all AI features.

Each test checks that the relevant ai_client wrapper function (chat_create or
trace_params) is called with the expected user attribution — either a real user
id or the "system" label for background / ingest-time calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

_ARTICLE: dict[str, Any] = {
    "id": 1,
    "title": "Test Article",
    "body": "Article body text with enough content to process.",
    "summary": "Article summary.",
}

_CANDIDATES: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "Some Article",
        "source_name": "Test Source",
        "category": "tech",
        "summary": "Some summary",
    }
]


def _mock_completion(content: str = "• Bullet") -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = content
    return completion


def _mock_json_completion(json_text: str) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = json_text
    return completion


# ── insights ──────────────────────────────────────────────────────────────────


def test_generate_insights_threads_user_id_to_chat_create() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.insights import generate_insights

    mock_cc = MagicMock(return_value=_mock_completion())
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("prompt", None)),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
    ):
        generate_insights(_ARTICLE, user_id=42)

    assert mock_cc.call_args.kwargs["user_id"] == 42


def test_generate_insights_passes_none_user_id_when_no_user() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.insights import generate_insights

    mock_cc = MagicMock(return_value=_mock_completion())
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("prompt", None)),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
    ):
        generate_insights(_ARTICLE)

    assert mock_cc.call_args.kwargs["user_id"] is None


# ── embeddings: article embedding tags "system" ────────────────────────────────


def test_embed_passes_system_user_id_to_trace_params() -> None:
    from news_dashboard.embeddings import _embed

    mock_tp = MagicMock(return_value={})
    mock_response = MagicMock()
    mock_response.data[0].embedding = [0.1, 0.2, 0.3]
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_response

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client", return_value=mock_client),
        patch("news_dashboard.ai_client.trace_params", new=mock_tp),
    ):
        _embed("some text")

    mock_tp.assert_called_once_with("article-embedding", tags=["embedding"], user_id="system")


def test_embed_uses_briefing_gateway_base_url_when_configured() -> None:
    from news_dashboard.embeddings import _embed

    mock_response = MagicMock()
    mock_response.data[0].embedding = [0.1, 0.2, 0.3]
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_response

    with (
        patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_BRIEFING_BASE_URL": "http://127.0.0.1:9130/v1",
            },
            clear=True,
        ),
        patch(
            "news_dashboard.ai_client.get_openai_client",
            return_value=mock_client,
        ) as mock_client_factory,
    ):
        _embed("some text")

    mock_client_factory.assert_called_once_with(
        api_key="sk-test",
        base_url="http://127.0.0.1:9130/v1",
    )


def test_embed_uses_shared_openai_base_url_when_briefing_gateway_missing() -> None:
    from news_dashboard.embeddings import _embed

    mock_response = MagicMock()
    mock_response.data[0].embedding = [0.1, 0.2, 0.3]
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_response

    with (
        patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_BASE_URL": "http://shared-gateway:9130/v1",
            },
            clear=True,
        ),
        patch(
            "news_dashboard.ai_client.get_openai_client",
            return_value=mock_client,
        ) as mock_client_factory,
    ):
        _embed("some text")

    mock_client_factory.assert_called_once_with(
        api_key="sk-test",
        base_url="http://shared-gateway:9130/v1",
    )


def test_embed_falls_back_to_openai_when_no_gateway_configured() -> None:
    from news_dashboard.embeddings import _embed

    mock_response = MagicMock()
    mock_response.data[0].embedding = [0.1, 0.2, 0.3]
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_response

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True),
        patch(
            "news_dashboard.ai_client.get_openai_client",
            return_value=mock_client,
        ) as mock_client_factory,
    ):
        _embed("some text")

    mock_client_factory.assert_called_once_with(api_key="sk-test", base_url=None)


# ── embeddings: ask-ai answer threads real user_id ────────────────────────────


def test_answer_threads_user_id_to_chat_create() -> None:
    from news_dashboard.embeddings import _answer

    mock_cc = MagicMock(return_value=_mock_completion("The answer."))
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
    ):
        _answer("system prompt", "user prompt", user_id=7)

    assert mock_cc.call_args.kwargs["user_id"] == 7


def test_answer_passes_none_user_id_when_absent() -> None:
    from news_dashboard.embeddings import _answer

    mock_cc = MagicMock(return_value=_mock_completion("The answer."))
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
    ):
        _answer("system prompt", "user prompt")

    assert mock_cc.call_args.kwargs["user_id"] is None


# ── body_fetch: AI body extraction threads user_id ────────────────────────────


def test_ai_extract_body_threads_user_id_to_chat_create() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    mock_cc = MagicMock(return_value=_mock_completion("Article body text."))
    mock_http_response = MagicMock()
    mock_http_response.text = "<html><body><p>article content here</p></body></html>"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
        patch("httpx.get", return_value=mock_http_response),
    ):
        _ai_extract_body("https://example.com/article", user_id=55)

    assert mock_cc.call_args.kwargs["user_id"] == 55


def test_ai_extract_body_passes_none_user_id_by_default() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    mock_cc = MagicMock(return_value=_mock_completion("Article body text."))
    mock_http_response = MagicMock()
    mock_http_response.text = "<html><body><p>article content here</p></body></html>"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
        patch("httpx.get", return_value=mock_http_response),
    ):
        _ai_extract_body("https://example.com/article")

    assert mock_cc.call_args.kwargs["user_id"] is None


def test_ai_extract_body_uses_briefing_gateway_config() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    mock_cc = MagicMock(return_value=_mock_completion("Article body text."))
    mock_http_response = MagicMock()
    mock_http_response.text = "<html><body><p>article content here</p></body></html>"

    with (
        patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-openai",
                "OPENAI_BRIEFING_API_KEY": "sk-gateway",
                "OPENAI_BRIEFING_BASE_URL": "http://gateway:9130/v1",
                "OPENAI_BRIEFING_MODEL": "gateway-chat-model",
            },
        ),
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
        patch("httpx.get", return_value=mock_http_response),
    ):
        _ai_extract_body("https://example.com/article")

    mock_client_factory.assert_called_once_with(
        api_key="sk-gateway", base_url="http://gateway:9130/v1"
    )
    assert mock_cc.call_args.kwargs["model"] == "gateway-chat-model"


def test_ai_extract_body_falls_back_to_openai_when_gateway_unset() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    mock_cc = MagicMock(return_value=_mock_completion("Article body text."))
    mock_http_response = MagicMock()
    mock_http_response.text = "<html><body><p>article content here</p></body></html>"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-openai"}, clear=True),
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
        patch("httpx.get", return_value=mock_http_response),
    ):
        _ai_extract_body("https://example.com/article")

    mock_client_factory.assert_called_once_with(api_key="sk-openai", base_url=None)
    assert mock_cc.call_args.kwargs["model"] == "gpt-4o-mini"


# ── briefings: generation threads user_id ─────────────────────────────────────


def test_call_openai_threads_user_id_to_chat_create() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.briefings import _call_openai

    json_text = '{"title":"T","summary":"S","sections":[],"worth_opening":[]}'
    mock_cc = MagicMock(return_value=_mock_json_completion(json_text))

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("system", None)),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
    ):
        _call_openai(_CANDIDATES, "gpt-4o-mini", user_id=33)

    assert mock_cc.call_args.kwargs["user_id"] == 33


def test_call_openai_passes_none_user_id_for_system_briefings() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.briefings import _call_openai

    json_text = '{"title":"T","summary":"S","sections":[],"worth_opening":[]}'
    mock_cc = MagicMock(return_value=_mock_json_completion(json_text))

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_openai_client"),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("system", None)),
        patch("news_dashboard.ai_client.chat_create", new=mock_cc),
    ):
        _call_openai(_CANDIDATES, "gpt-4o-mini")

    assert mock_cc.call_args.kwargs["user_id"] is None
