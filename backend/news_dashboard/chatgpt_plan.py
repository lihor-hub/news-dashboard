"""Stateless Responses adapter for an explicitly authorized ChatGPT plan."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from news_dashboard.chatgpt_auth import access_token

if TYPE_CHECKING:
    from langchain_core.language_models import LanguageModelInput
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import Runnable
    from openai.types.chat import ChatCompletion


class PlanInferenceError(RuntimeError):
    """A subscription inference request failed or never completed."""


class PlanChatClient:
    """Expose the app's non-streaming chat surface over subscription SSE requests.

    Credentials are loaded immediately before inference so token rotation is
    respected by long-lived models. This client never constructs an API fallback.
    """

    def __init__(self, *, timeout_seconds: float | None = None) -> None:
        self.chat = self
        self.completions = self
        self._timeout_seconds = timeout_seconds

    def create(self, **kwargs: Any) -> ChatCompletion:
        from openai import OpenAI
        from openai.types.chat import ChatCompletion

        from news_dashboard.ai_client import chat_model_parameters, request_timeout_seconds

        messages = [
            {
                "role": "developer" if item["role"] == "system" else item["role"],
                "content": item["content"],
            }
            for item in kwargs["messages"]
        ]
        request: dict[str, Any] = {
            "model": kwargs["model"],
            "input": messages,
            "store": False,
            "stream": True,
        }
        reasoning = chat_model_parameters(kwargs["model"]).get("reasoning")
        if reasoning:
            request["reasoning"] = reasoning
        response_format = kwargs.get("response_format")
        if response_format:
            request["text"] = {"format": response_format}
        chunks: list[str] = []
        completed: Any = None
        # Use the supported public endpoint, not ChatGPT's private backend.
        with (
            OpenAI(
                api_key=access_token(),
                base_url="https://api.openai.com/v1",
                max_retries=0,
                timeout=self._timeout_seconds or max(request_timeout_seconds(), 120),
            ) as client,
            client.responses.create(**request) as stream,
        ):
            for event in stream:
                if event.type == "response.output_text.delta":
                    chunks.append(event.delta)
                elif event.type == "response.completed":
                    completed = event.response
                elif event.type in {"response.failed", "response.incomplete", "error"}:
                    error = getattr(getattr(event, "response", None), "error", None)
                    code = getattr(error, "code", None) or event.type
                    message = f"ChatGPT plan request did not complete ({code})"
                    raise PlanInferenceError(message)
        if completed is None:
            message = "ChatGPT plan stream ended without response.completed"
            raise PlanInferenceError(message)
        usage = getattr(completed, "usage", None)
        return ChatCompletion.model_validate(
            {
                "id": completed.id,
                "created": 0,
                "model": kwargs["model"],
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "".join(chunks),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": usage.input_tokens,
                    "completion_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
                if usage
                else None,
            }
        )


def get_plan_chat_model(
    *,
    model: str,
    response_format: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> Runnable[LanguageModelInput, AIMessage]:
    """Adapt LangChain prompts/history without sending tracing metadata upstream."""
    from langchain_core.messages import AIMessage, convert_to_messages
    from langchain_core.prompt_values import PromptValue
    from langchain_core.runnables import RunnableLambda

    def invoke(value: LanguageModelInput) -> AIMessage:
        if isinstance(value, str):
            messages = [{"role": "user", "content": value}]
        else:
            items = (
                value.to_messages()
                if isinstance(value, PromptValue)
                else convert_to_messages(value)
            )
            messages = []
            for item in items:
                if not isinstance(item.content, str):
                    message = "ChatGPT plan adapter requires text messages"
                    raise TypeError(message)
                role = {"human": "user", "ai": "assistant", "system": "developer"}.get(item.type)
                if role is None:
                    message = "ChatGPT plan adapter does not support tool messages"
                    raise TypeError(message)
                messages.append({"role": role, "content": item.content})
        result = PlanChatClient(timeout_seconds=timeout_seconds).create(
            model=model,
            messages=messages,
            response_format=response_format,
        )
        return AIMessage(content=result.choices[0].message.content or "")

    return RunnableLambda(invoke)
