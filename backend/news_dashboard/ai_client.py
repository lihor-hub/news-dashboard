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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from openai import OpenAI
    from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)

ScoreDataType = Literal["NUMERIC", "CATEGORICAL", "BOOLEAN"]
_DEFAULT_AI_REQUEST_TIMEOUT_SECONDS = 30.0
_DEFAULT_AI_TTS_TIMEOUT_SECONDS = 120.0


def _timeout_seconds_from_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %.1fs", name, value, default)
        return default
    if parsed <= 0:
        logger.warning("Ignoring non-positive %s=%r; using %.1fs", name, value, default)
        return default
    return parsed


def request_timeout_seconds() -> float:
    """Return the configured timeout for chat and embedding OpenAI-compatible calls."""
    return _timeout_seconds_from_env(
        "AI_REQUEST_TIMEOUT_SECONDS", _DEFAULT_AI_REQUEST_TIMEOUT_SECONDS
    )


def tts_timeout_seconds() -> float:
    """Return the configured timeout for OpenAI TTS/audio calls."""
    return _timeout_seconds_from_env("AI_TTS_TIMEOUT_SECONDS", _DEFAULT_AI_TTS_TIMEOUT_SECONDS)


def langfuse_enabled() -> bool:
    """Return True when Langfuse tracing credentials are configured."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _client() -> Any:
    """Return the configured Langfuse client (host normalised).

    Callers must guard with :func:`langfuse_enabled` first; this resolves the
    SDK dynamically so the module type-checks whether or not langfuse is
    installed.
    """
    _normalise_host_env()
    langfuse = importlib.import_module("langfuse")
    return langfuse.get_client()


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
    prompt: ManagedPrompt | None = None,
    **kwargs: Any,
) -> ChatCompletion:
    """Create a (non-streaming) chat completion, traced when Langfuse is on.

    Centralises the Langfuse trace name/tags/user/session so call sites stay
    clean and the overloaded ``create`` keeps resolving to a non-streaming
    ``ChatCompletion`` (unpacking ``**kwargs`` otherwise widens the return type
    to include ``Stream``).

    When *prompt* is a Langfuse-managed prompt, the generation is linked to its
    version (via the ``langfuse_prompt`` kwarg the wrapped client understands),
    so the Langfuse UI shows which prompt version produced each answer. The link
    is gated on tracing being enabled and on the prompt not being a local
    fallback, so the plain OpenAI client never receives Langfuse-only kwargs.
    """
    trace = trace_params(name, tags=tags, user_id=user_id, session_id=session_id)
    if langfuse_enabled() and prompt is not None and prompt.langfuse_prompt is not None:
        trace["langfuse_prompt"] = prompt.langfuse_prompt
    completion = client.chat.completions.create(**kwargs, **trace)
    return cast("ChatCompletion", completion)


def openai_config() -> tuple[str, str | None]:
    """Return (api_key, base_url) for real-OpenAI-only features (TTS audio, body extraction).

    Uses ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL``. The key may be an empty
    string when unconfigured — callers that require it must check and raise.
    """
    return os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_BASE_URL") or None


def free_llm_config() -> tuple[str, str | None]:
    """Return (api_key, base_url) for the free LLM gateway (chat, embeddings, etc.).

    Uses ``FREE_LLM_API_KEY`` / ``FREE_LLM_BASE_URL`` first, falling back to
    ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` so a single-key setup still works.
    The key may be an empty string when unconfigured — callers that require it
    must check and raise.
    """
    api_key = os.getenv("FREE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    base_url = os.getenv("FREE_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    return api_key, base_url


def get_openai_client(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
) -> OpenAI:
    """Return an OpenAI client, Langfuse-wrapped when tracing is configured.

    The returned object is API-compatible with ``openai.OpenAI`` in both cases,
    so call sites are identical whether or not tracing is active.
    """
    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": request_timeout_seconds() if timeout_seconds is None else timeout_seconds,
    }
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


# ── Runtime free-LLM → OpenAI fallback ─────────────────────────────────────


def _invoke[T](
    primary: OpenAI,
    fallback: tuple[str, str | None] | None,
    call: Callable[[OpenAI], T],
) -> T:
    """Run *call* against *primary*; on OpenAIError retry once on the OpenAI fallback.

    The same request is replayed verbatim (same model and kwargs) against a
    lazily-built OpenAI client, so the fallback is only constructed when the free
    LLM gateway actually fails. When no distinct fallback is configured, the call
    runs directly against *primary* and any error propagates unchanged.
    """
    if fallback is None:
        return call(primary)

    from openai import OpenAIError  # lazy import — optional dep at import time

    try:
        return call(primary)
    except OpenAIError as exc:
        api_key, base_url = fallback
        logger.warning("free LLM request failed (%s); retrying on OpenAI fallback", exc)
        return call(get_openai_client(api_key=api_key, base_url=base_url))


class _FallbackCompletions:
    """``chat.completions`` shim that routes ``create`` through :func:`_invoke`."""

    def __init__(self, primary: OpenAI, fallback: tuple[str, str | None] | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def create(self, **kwargs: Any) -> Any:
        return _invoke(self._primary, self._fallback, lambda c: c.chat.completions.create(**kwargs))


class _FallbackChat:
    """``chat`` namespace exposing a fallback-aware ``completions``."""

    def __init__(self, primary: OpenAI, fallback: tuple[str, str | None] | None) -> None:
        self.completions = _FallbackCompletions(primary, fallback)


class _FallbackEmbeddings:
    """``embeddings`` shim that routes ``create`` through :func:`_invoke`."""

    def __init__(self, primary: OpenAI, fallback: tuple[str, str | None] | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def create(self, **kwargs: Any) -> Any:
        return _invoke(self._primary, self._fallback, lambda c: c.embeddings.create(**kwargs))


class _FallbackClient:
    """Chat/embedding client that prefers the free LLM gateway, then OpenAI.

    Exposes only the ``chat.completions.create`` and ``embeddings.create``
    surfaces the backend uses through it; each request prefers the primary (free
    LLM) client and falls back to OpenAI on failure (see :func:`get_chat_client`).
    """

    def __init__(self, primary: OpenAI, fallback: tuple[str, str | None] | None) -> None:
        self.chat = _FallbackChat(primary, fallback)
        self.embeddings = _FallbackEmbeddings(primary, fallback)


def get_chat_client(*, api_key: str, base_url: str | None = None) -> OpenAI:
    """Return a chat/embedding client that prefers the free LLM gateway.

    *api_key* / *base_url* are the primary (free LLM) credentials, as resolved by
    :func:`free_llm_config`. When a distinct, configured OpenAI endpoint exists —
    a non-empty ``OPENAI_API_KEY`` whose ``(key, base_url)`` differs from the
    primary — any chat or embedding request that raises ``openai.OpenAIError`` is
    retried once against OpenAI with the same model and arguments. For single-key
    setups, where the free config already *is* the OpenAI endpoint, no fallback
    is attempted and errors propagate unchanged.

    The returned object is API-compatible with ``openai.OpenAI`` for the
    ``chat.completions.create`` and ``embeddings.create`` calls made through it.
    The OpenAI fallback client is built lazily, only on the first failure.
    """
    primary = get_openai_client(api_key=api_key, base_url=base_url)
    openai_key, openai_base = openai_config()
    fallback: tuple[str, str | None] | None = None
    if openai_key and (openai_key, openai_base) != (api_key, base_url):
        fallback = (openai_key, openai_base)
    return cast("OpenAI", _FallbackClient(primary, fallback))


# ── Trace context ────────────────────────────────────────────────────────


@dataclass
class TraceHandle:
    """Handle to the current Langfuse trace, returned by :func:`observe`.

    ``trace_id`` is ``None`` when tracing is disabled, so callers can pass it
    through to API responses unconditionally (clients simply omit feedback when
    it is absent).
    """

    trace_id: str | None = None
    _span: Any = field(default=None, repr=False)

    def update_output(self, output: Any) -> None:
        """Attach the final pipeline output to the trace, if tracing is on."""
        if self._span is not None:
            try:
                self._span.update(output=output)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("langfuse span update failed: %s", exc)


@contextmanager
def observe(
    name: str,
    *,
    input: Any = None,  # noqa: A002 - mirrors the Langfuse SDK kwarg name
) -> Iterator[TraceHandle]:
    """Group nested AI calls under a single Langfuse trace.

    Any wrapped-client calls made inside the ``with`` block (embeddings, chat
    completions) attach as child observations of one trace, instead of each
    creating its own. The yielded :class:`TraceHandle` exposes ``trace_id`` so
    the caller can return it to the frontend and later attach user feedback as a
    score. A no-op (``trace_id=None``) when tracing is disabled.
    """
    if not langfuse_enabled():
        yield TraceHandle()
        return
    try:
        client = _client()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("langfuse client unavailable, tracing skipped: %s", exc)
        yield TraceHandle()
        return
    with client.start_as_current_observation(name=name, as_type="span", input=input) as span:
        yield TraceHandle(trace_id=client.get_current_trace_id(), _span=span)


def create_score(
    trace_id: str,
    *,
    name: str,
    value: float | str,
    data_type: ScoreDataType = "NUMERIC",
    comment: str | None = None,
) -> bool:
    """Attach a score (e.g. user feedback) to a trace. Returns success.

    No-op returning ``False`` when tracing is disabled or the SDK is
    unavailable, so feedback endpoints degrade gracefully. Flushes immediately
    because the API request that triggers feedback is short-lived.
    """
    if not langfuse_enabled() or not trace_id:
        return False
    try:
        client = _client()
        client.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            data_type=data_type,
            comment=comment,
        )
        client.flush()
    except Exception as exc:
        logger.warning("langfuse score creation failed: %s", exc)
        return False
    return True


def get_trace_url(trace_id: str) -> str | None:
    """Return the Langfuse UI URL for *trace_id*, or ``None`` if unavailable."""
    if not langfuse_enabled() or not trace_id:
        return None
    try:
        url = _client().get_trace_url(trace_id=trace_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("langfuse trace url lookup failed: %s", exc)
        return None
    return cast("str | None", url)


# ── Prompt management ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ManagedPrompt:
    """A prompt resolved from Langfuse, or a local fallback.

    ``text`` is the compiled prompt string ready to use. ``langfuse_prompt`` is
    the underlying Langfuse prompt object when the prompt was fetched from
    Langfuse (used to link generations to the prompt version), or ``None`` for
    the local fallback.
    """

    text: str
    langfuse_prompt: Any | None = None


def get_prompt(
    name: str,
    *,
    fallback: str,
    label: str = "production",
    variables: dict[str, Any] | None = None,
) -> ManagedPrompt:
    """Fetch a managed text prompt from Langfuse, falling back to *fallback*.

    Prompts live in Langfuse (type ``text``) so they can be edited and
    versioned without redeploying. When tracing is disabled, the prompt is
    missing, or the fetch fails, the hardcoded *fallback* is used so behaviour
    is never blocked on Langfuse availability. ``{{variable}}`` placeholders are
    substituted from *variables* (Langfuse's ``compile`` for fetched prompts; a
    simple local substitution for the fallback).
    """
    variables = variables or {}
    if not langfuse_enabled():
        return ManagedPrompt(_compile_fallback(fallback, variables))
    try:
        client = _client()
        prompt = client.get_prompt(name, label=label, type="text", fallback=fallback)
        compiled = prompt.compile(**variables) if variables else prompt.prompt
        # A fallback-resolved prompt has no real version to link against.
        is_fallback = getattr(prompt, "is_fallback", False)
        return ManagedPrompt(str(compiled), None if is_fallback else prompt)
    except Exception as exc:
        logger.warning("langfuse get_prompt(%s) failed, using fallback: %s", name, exc)
        return ManagedPrompt(_compile_fallback(fallback, variables))


def _compile_fallback(template: str, variables: dict[str, Any]) -> str:
    """Substitute ``{{var}}`` placeholders locally (Langfuse-compatible syntax)."""
    text = template
    for key, val in variables.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


# ── Metrics ────────────────────────────────────────────────────────────────


def _metrics_query(query: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one Langfuse Metrics API query, returning its ``data`` rows."""
    import json

    response = _client().api.metrics.metrics(query=json.dumps(query))
    return [dict(row) for row in (response.data or [])]


def fetch_metrics(*, days: int = 30) -> dict[str, Any]:
    """Return aggregate AI usage metrics from Langfuse for the last *days*.

    Surfaces cost, latency and feedback aggregates in-app (e.g. an admin
    dashboard) so they are visible without opening the Langfuse UI. Degrades
    gracefully: returns ``{"enabled": False}`` when tracing is off, and
    per-section ``None`` when a query fails, so the endpoint never errors.
    """
    from datetime import datetime, timedelta, timezone

    if not langfuse_enabled():
        return {"enabled": False}

    to_ts = datetime.now(timezone.utc)
    from_ts = to_ts - timedelta(days=days)
    window = {
        "fromTimestamp": from_ts.isoformat(),
        "toTimestamp": to_ts.isoformat(),
        "filters": [],
        "dimensions": [{"field": "name"}],
    }
    result: dict[str, Any] = {"enabled": True, "window_days": days}

    try:
        result["usage"] = _metrics_query(
            {
                "view": "observations",
                "metrics": [
                    {"measure": "count", "aggregation": "count"},
                    {"measure": "totalCost", "aggregation": "sum"},
                    {"measure": "latency", "aggregation": "avg"},
                ],
                **window,
            }
        )
    except Exception as exc:
        logger.warning("langfuse usage metrics query failed: %s", exc)
        result["usage"] = None

    try:
        result["scores"] = _metrics_query(
            {
                "view": "scores-numeric",
                "metrics": [
                    {"measure": "value", "aggregation": "avg"},
                    {"measure": "count", "aggregation": "count"},
                ],
                **window,
            }
        )
    except Exception as exc:
        logger.warning("langfuse score metrics query failed: %s", exc)
        result["scores"] = None

    return result


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
