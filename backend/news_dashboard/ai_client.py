"""Central factory for OpenAI clients with optional Langfuse tracing.

Every AI interaction in the backend is created through :func:`get_openai_client`
so that, when Langfuse is configured, all chat/embedding/audio calls are traced
in one place. When Langfuse credentials are absent (local dev, CI), the factory
returns a plain ``openai.OpenAI`` client with zero tracing and no warnings — so
behaviour is unchanged wherever Langfuse is not wired up.

Tracing is enabled when both ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY``
are present in the environment. ``LANGFUSE_HOST`` selects the self-hosted
instance; ``LANGFUSE_BASE_URL`` is accepted as an alias (the Langfuse SDK only
reads ``LANGFUSE_HOST``, so we normalise it). The drop-in wrapper reads those
variables itself.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from openai import OpenAI
    from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)


def langfuse_enabled() -> bool:
    """Return True when Langfuse tracing credentials are configured."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _normalise_host_env() -> None:
    """Map ``LANGFUSE_BASE_URL`` to ``LANGFUSE_HOST`` when only the former is set.

    The Langfuse SDK reads ``LANGFUSE_HOST`` exclusively; without this, an env
    that only defines ``LANGFUSE_BASE_URL`` would silently target the public
    cloud instead of the configured (self-hosted) endpoint.
    """
    if not os.getenv("LANGFUSE_HOST"):
        base_url = os.getenv("LANGFUSE_BASE_URL")
        if base_url:
            os.environ["LANGFUSE_HOST"] = base_url


def trace_params(
    name: str,
    *,
    tags: list[str] | None = None,
    user_id: int | str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Return per-call Langfuse trace kwargs for an OpenAI ``create`` call.

    Returns ``{}`` when tracing is disabled, so the plain OpenAI client (which
    rejects unknown kwargs) is never handed Langfuse-only arguments. When
    enabled, sets a descriptive observation ``name`` plus optional ``tags``,
    ``user_id`` and ``session_id`` so traces are filterable by feature, user
    and conversation in the Langfuse UI.
    """
    if not langfuse_enabled():
        return {}
    metadata: dict[str, Any] = {}
    if tags:
        metadata["langfuse_tags"] = tags
    if user_id is not None:
        metadata["langfuse_user_id"] = str(user_id)
    if session_id is not None:
        metadata["langfuse_session_id"] = session_id
    params: dict[str, Any] = {"name": name}
    if metadata:
        params["metadata"] = metadata
    return params


def chat_create(
    client: OpenAI,
    *,
    name: str,
    tags: list[str] | None = None,
    user_id: int | str | None = None,
    session_id: str | None = None,
    **kwargs: Any,
) -> ChatCompletion:
    """Create a (non-streaming) chat completion, traced when Langfuse is on.

    Centralises the Langfuse trace name/tags/user/session so call sites stay
    clean and the overloaded ``create`` keeps resolving to a non-streaming
    ``ChatCompletion`` (unpacking ``**kwargs`` otherwise widens the return type
    to include ``Stream``).
    """
    trace = trace_params(name, tags=tags, user_id=user_id, session_id=session_id)
    completion = client.chat.completions.create(**kwargs, **trace)
    return cast("ChatCompletion", completion)


def get_openai_client(*, api_key: str, base_url: str | None = None) -> OpenAI:
    """Return an OpenAI client, Langfuse-wrapped when tracing is configured.

    The returned object is API-compatible with ``openai.OpenAI`` in both cases,
    so call sites are identical whether or not tracing is active.
    """
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url is not None:
        kwargs["base_url"] = base_url

    if langfuse_enabled():
        _normalise_host_env()
        # Langfuse's drop-in client subclasses openai.OpenAI and traces every
        # request. Resolve it dynamically so this module type-checks whether or
        # not langfuse is installed (it re-exports OpenAI without an __all__).
        langfuse_openai = importlib.import_module("langfuse.openai")
        client: OpenAI = langfuse_openai.OpenAI(**kwargs)
        return client

    from openai import OpenAI as PlainOpenAI

    return PlainOpenAI(**kwargs)


def flush() -> None:
    """Flush buffered Langfuse traces.

    Langfuse sends spans asynchronously; short-lived processes (e.g. the ingest
    cron) must flush before exit or trailing traces are lost. No-op when tracing
    is disabled or the SDK is unavailable.
    """
    if not langfuse_enabled():
        return
    try:
        _normalise_host_env()
        langfuse = importlib.import_module("langfuse")
        langfuse.get_client().flush()
    except Exception as exc:
        logger.warning("langfuse flush failed: %s", exc)
