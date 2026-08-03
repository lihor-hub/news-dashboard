"""AgentExecutor bridging A2A SendMessage requests to the assistant."""

from __future__ import annotations

import asyncio

from a2a.helpers import new_data_part, new_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.errors import A2AError, InvalidParamsError, UnsupportedOperationError

from news_dashboard.a2a import service


class AssistantAgentExecutor(AgentExecutor):
    """Answers each incoming message with a single agent message (no long-running tasks)."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        state = context.call_context.state if context.call_context else {}
        user_id = state.get("user_id")
        if not isinstance(user_id, int):
            message = "request is not associated with an authenticated token owner"
            raise InvalidParamsError(message)
        query = context.get_user_input()
        from news_dashboard.embeddings import EmbeddingUnavailableError

        try:
            result = await asyncio.to_thread(service.answer_question, query, user_id=user_id)
        except ValueError as exc:
            raise InvalidParamsError(str(exc)) from exc
        except EmbeddingUnavailableError as exc:
            message = "the embedding service is unavailable; retry later"
            raise A2AError(message) from exc
        parts = [new_text_part(str(result.get("answer") or ""))]
        sources = result.get("sources") or []
        if sources:
            parts.append(new_data_part({"sources": sources}))
        await event_queue.enqueue_event(new_message(parts=parts, context_id=context.context_id))

    async def cancel(
        self,
        context: RequestContext,  # noqa: ARG002 -- fixed by the AgentExecutor interface
        event_queue: EventQueue,  # noqa: ARG002 -- fixed by the AgentExecutor interface
    ) -> None:
        message = "this agent answers synchronously; tasks cannot be cancelled"
        raise UnsupportedOperationError(message)
