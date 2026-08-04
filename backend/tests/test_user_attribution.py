"""Assert that user_id is threaded to Langfuse traces in all AI features.

Each test checks that the relevant LangChain/Langfuse or native embedding seam
is called with the expected user attribution — either a real user
id or the "system" label for background / ingest-time calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

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


def _chat_model(content: str) -> RunnableLambda[Any, AIMessage]:
    return RunnableLambda(lambda _value: AIMessage(content=content))


# ── insights ──────────────────────────────────────────────────────────────────


def test_generate_insights_threads_user_id_to_langfuse() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.insights import generate_insights

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("prompt", None)),
        patch("news_dashboard.ai_client.get_chat_model", return_value=_chat_model("• Bullet")),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        generate_insights(_ARTICLE, user_id=42)

    assert attributes.call_args.kwargs["user_id"] == "42"


def test_generate_insights_passes_none_user_id_when_no_user() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.insights import generate_insights

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("prompt", None)),
        patch("news_dashboard.ai_client.get_chat_model", return_value=_chat_model("• Bullet")),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        generate_insights(_ARTICLE)

    assert attributes.call_args.kwargs["user_id"] is None


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


def test_embed_uses_free_llm_gateway_base_url_when_configured() -> None:
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
                "FREE_LLM_BASE_URL": "http://127.0.0.1:9130/v1",
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


def test_answer_treats_managed_system_prompt_braces_as_literal_text() -> None:
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from news_dashboard.embeddings import _answer

    captured: list[Any] = []

    def answer(messages: Any) -> AIMessage:
        captured.extend(messages.to_messages())
        return AIMessage(content="The answer.")

    model = RunnableLambda(answer)
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model) as factory,
    ):
        result = _answer('system prompt with JSON {"answer": true}', "user prompt")

    assert result == "The answer."
    assert [message.content for message in captured] == [
        'system prompt with JSON {"answer": true}',
        "user prompt",
    ]
    factory.assert_called_once_with(api_key="sk-test", base_url=None, model="gpt-4o-mini")


def test_ask_uses_native_langfuse_user_and_session_attributes() -> None:
    from contextlib import contextmanager

    from news_dashboard import embeddings

    span = MagicMock()
    client = MagicMock()
    client.get_current_trace_id.return_value = "root-trace"

    @contextmanager
    def observation(**kwargs: Any) -> Any:
        assert kwargs == {
            "name": "ask-ai",
            "as_type": "chain",
            "input": {"query": "question", "include_all": False},
        }
        yield span

    @contextmanager
    def attributes(**kwargs: Any) -> Any:
        assert kwargs == {
            "user_id": "7",
            "session_id": "conversation-42",
            "tags": ["ask-ai"],
            "prompt": None,
        }
        yield

    client.start_as_current_observation.side_effect = observation
    with (
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("news_dashboard.ai_client._client", return_value=client),
        patch("langfuse.propagate_attributes", side_effect=attributes),
        patch.object(embeddings, "embed_all_eligible", return_value=0),
        patch.object(embeddings, "_embed", return_value=[]),
        patch("news_dashboard.db.init_db"),
        patch("news_dashboard.db.connect") as connect,
    ):
        rows = [
            {
                "id": i,
                "title": f"Title {i}",
                "url": f"https://x/{i}",
                "summary": "S",
                "eligible_count": 5,
            }
            for i in range(1, 6)
        ]
        fetchall = connect.return_value.__enter__.return_value.execute.return_value.fetchall
        fetchall.return_value = rows
        with (
            patch.object(embeddings, "graph_context_for_articles", return_value=None),
            patch("news_dashboard.ai_client.get_prompt") as get_prompt,
            patch("news_dashboard.ai_memory.service.format_memories_for_prompt", return_value=""),
            patch.object(embeddings, "_answer", return_value="answer"),
        ):
            get_prompt.return_value.text = "system"
            get_prompt.return_value.langfuse_prompt = None
            result = embeddings.ask("question", user_id=7, session_id="conversation-42")

    assert result["trace_id"] == "root-trace"
    span.update.assert_called_once_with(output="answer")


def test_mcp_ask_trace_contains_only_safe_operational_metadata() -> None:
    from contextlib import contextmanager

    from news_dashboard import embeddings
    from news_dashboard.assistant.service import AskExecutionPolicy

    question = "PRIVATE QUESTION"
    article_text = "PRIVATE ARTICLE"
    answer = "PRIVATE ANSWER"
    article_url = "https://private.example/secret"
    captured: dict[str, Any] = {}
    observations: list[tuple[dict[str, Any], MagicMock]] = []
    client = MagicMock()
    client.get_current_trace_id.return_value = "0123456789abcdef0123456789abcdef"

    @contextmanager
    def attributes(**kwargs: Any) -> Any:
        captured["attributes"] = kwargs
        yield

    @contextmanager
    def observation(**kwargs: Any) -> Any:
        span = MagicMock()
        observations.append((kwargs, span))
        yield span

    client.start_as_current_observation.side_effect = observation
    rows = [
        {
            "id": i,
            "title": f"Title {i}",
            "url": article_url,
            "summary": article_text,
            "eligible_count": 5,
        }
        for i in range(1, 6)
    ]
    with (
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("news_dashboard.ai_client._client", return_value=client),
        patch("langfuse.propagate_attributes", side_effect=attributes),
        patch.object(embeddings, "embed_all_eligible", return_value=0),
        patch.object(embeddings, "_embed", return_value=[]),
        patch("news_dashboard.db.init_db"),
        patch("news_dashboard.db.connect") as connect,
        patch.object(embeddings, "graph_context_for_articles", return_value=None),
        patch("news_dashboard.ai_client.get_prompt") as get_prompt,
        patch("news_dashboard.ai_memory.service.format_memories_for_prompt", return_value=""),
        patch.object(embeddings, "_answer", return_value=answer),
    ):
        fetchall = connect.return_value.__enter__.return_value.execute.return_value.fetchall
        fetchall.return_value = rows
        get_prompt.return_value.text = "PRIVATE PROMPT"
        get_prompt.return_value.langfuse_prompt = object()
        result = embeddings.ask(
            question,
            user_id=7,
            execution_policy=AskExecutionPolicy.mcp(),
        )

    assert result["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert captured["attributes"] | observations[0][0] == {
        "user_id": "7",
        "tags": ["ask-ai", "mcp"],
        "metadata": {"surface": "mcp", "corpus": "saved_and_read"},
        "trace_name": "ask-news",
        "name": "ask-ai",
        "as_type": "chain",
        "input": {
            "question_chars": len(question),
            "corpus": "saved_and_read",
            "retrieval_limit": 8,
        },
    }
    assert observations[1][0] == {
        "name": "answer-pipeline",
        "as_type": "chain",
        "input": {
            "question_chars": len(question),
            "corpus": "saved_and_read",
            "retrieval_limit": 8,
        },
        "prompt": get_prompt.return_value.langfuse_prompt,
    }
    observations[0][1].update.assert_called_once_with(
        output={"answer_chars": len(answer), "source_count": 5, "status": "ok"}
    )
    observations[1][1].update.assert_called_once_with(
        output={"answer_chars": len(answer), "status": "ok"}
    )
    rendered = repr((captured, observations))
    for secret in (question, article_text, article_url, answer, "PRIVATE PROMPT"):
        assert secret not in rendered


# ── body_fetch: AI body extraction threads user_id ────────────────────────────


def test_ai_extract_body_threads_user_id_to_langfuse() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=_chat_model("Article body text."),
        ),
        patch("langfuse.propagate_attributes") as attributes,
        patch(
            "news_dashboard.body_fetch._fetch_capped_html",
            return_value="<html><body><p>article content here</p></body></html>",
        ),
    ):
        _ai_extract_body("https://example.com/article", user_id=55)

    assert attributes.call_args.kwargs["user_id"] == "55"


def test_ai_extract_body_passes_none_user_id_by_default() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=_chat_model("Article body text."),
        ),
        patch("langfuse.propagate_attributes") as attributes,
        patch(
            "news_dashboard.body_fetch._fetch_capped_html",
            return_value="<html><body><p>article content here</p></body></html>",
        ),
    ):
        _ai_extract_body("https://example.com/article")

    assert attributes.call_args.kwargs["user_id"] is None


def test_ai_extract_body_uses_free_llm_gateway_config() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    with (
        patch.dict(
            "os.environ",
            {
                "FREE_LLM_API_KEY": "sk-gateway",
                "FREE_LLM_BASE_URL": "http://gateway:9130/v1",
                "OPENAI_BRIEFING_MODEL": "gateway-chat-model",
            },
        ),
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=_chat_model("Article body text."),
        ) as factory,
        patch(
            "news_dashboard.body_fetch._fetch_capped_html",
            return_value="<html><body><p>article content here</p></body></html>",
        ),
    ):
        _ai_extract_body("https://example.com/article")

    factory.assert_called_once_with(
        api_key="sk-gateway",
        base_url="http://gateway:9130/v1",
        model="gateway-chat-model",
        max_tokens=2048,
    )


def test_ai_extract_body_falls_back_to_openai_when_gateway_unset() -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-openai"}, clear=True),
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=_chat_model("Article body text."),
        ) as factory,
        patch(
            "news_dashboard.body_fetch._fetch_capped_html",
            return_value="<html><body><p>article content here</p></body></html>",
        ),
    ):
        _ai_extract_body("https://example.com/article")

    factory.assert_called_once_with(
        api_key="sk-openai", base_url=None, model="gpt-4o-mini", max_tokens=2048
    )


# ── briefings: generation threads user_id ─────────────────────────────────────


def test_call_openai_threads_user_id_to_langfuse() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.briefings.service import _call_openai

    json_text = '{"title":"T","summary":"S","sections":[],"worth_opening":[]}'
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("system", None)),
        patch("news_dashboard.ai_client.get_chat_model", return_value=_chat_model(json_text)),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        _call_openai(_CANDIDATES, "gpt-4o-mini", user_id=33)

    assert attributes.call_args.kwargs["user_id"] == "33"


def test_call_openai_passes_none_user_id_for_system_briefings() -> None:
    from news_dashboard.ai_client import ManagedPrompt
    from news_dashboard.briefings.service import _call_openai

    json_text = '{"title":"T","summary":"S","sections":[],"worth_opening":[]}'
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_prompt", return_value=ManagedPrompt("system", None)),
        patch("news_dashboard.ai_client.get_chat_model", return_value=_chat_model(json_text)),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        _call_openai(_CANDIDATES, "gpt-4o-mini")

    assert attributes.call_args.kwargs["user_id"] is None
