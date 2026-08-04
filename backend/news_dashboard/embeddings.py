"""AI Q&A feature: embedding generation and retrieval-augmented answering.

Embedding model : text-embedding-3-small (OpenAI)
Answer model    : gpt-4o-mini (OpenAI)
Storage         : articles.embedding_vec (pgvector, cosine ops, HNSW index)
Retrieval       : SQL top-k via the `<=>` cosine-distance operator
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletion

    from news_dashboard.assistant.service import AskExecutionPolicy

logger = logging.getLogger(__name__)

MIN_ARTICLES = 5  # refuse to answer if fewer than this many articles are embedded
TOP_K = 8  # articles to include as context
DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

# Retry budget for transient (e.g. 429 rate-limit) embedding failures.
EMBED_MAX_ATTEMPTS = 4
EMBED_BACKOFF_SECONDS = 1.0

# Local fallback for the Ask AI system prompt. The live prompt is managed in
# Langfuse (name "ask-system", label "production"); this string is used verbatim
# when Langfuse is disabled or unreachable, so behaviour never depends on it.
ASK_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based on the user's "
    "curated news articles. "
    "Use only the provided article excerpts to answer. "
    "Cite articles by their bracketed number, e.g. [1], [2]. "
    "If the articles do not contain enough information, say so clearly. "
    "Be concise (2-4 sentences unless a longer answer is clearly needed)."
)


class MissingAICredentialsError(RuntimeError):
    """Raised when Ask AI is used without the required provider credentials."""


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding provider stays unavailable after retries (e.g. persistent 429s)."""


def _require_env(name: str, purpose: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    message = f"Ask AI requires {name} to {purpose}. Set {name} in the app environment."
    raise MissingAICredentialsError(message)


# ── pgvector (de)serialisation ──────────────────────────────────────────────


def vector_literal(vector: list[float]) -> str:
    """Format a Python float vector as a pgvector input literal, e.g. "[0.1,0.2]"."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def parse_vector(value: Any) -> list[float]:
    """Parse a pgvector column value (returned as text) into a float vector."""
    text = value.strip("[]") if isinstance(value, str) else str(value).strip("[]")
    if not text:
        return []
    return [float(x) for x in text.split(",")]


# ── Embedding source text ──────────────────────────────────────────────────


def embedding_text(
    title: str | None,
    summary: str | None,
    reason: str | None = None,
    tags: str | None = None,
) -> str:
    """Build the text fed to the embedding model from an article's fields.

    Uses title, summary, reason, and tags — no full-body extraction required.
    Empty fields are dropped so missing data never adds noise.
    """
    parts = [part.strip() for part in (title, summary, reason, tags) if part and part.strip()]
    return " ".join(parts)


# ── OpenAI-compatible embedding ────────────────────────────────────────────


def _embeddings_ai_config() -> tuple[str, str | None, str]:
    """Resolve the (api_key, base_url, model) for embedding generation via the free LLM gateway."""
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = (
            "Ask AI requires FREE_LLM_API_KEY (or OPENAI_API_KEY) to "
            "generate article embeddings. Set it in the app environment."
        )
        raise MissingAICredentialsError(msg)
    model = os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    return api_key, base_url, model


def _is_retryable_embedding_error(exc: Exception) -> bool:
    """True for transient upstream errors (429 rate limits) worth retrying."""
    from openai import APIStatusError, RateLimitError

    if isinstance(exc, RateLimitError):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code == 429


def _embed(
    text: str,
    *,
    timeout_seconds: float | None = None,
    trace_content: bool = True,
    operation: str = "query-embedding",
) -> list[float]:
    """Embed *text* via the configured OpenAI-compatible endpoint.

    Retries transient rate-limit (429) errors with exponential backoff. Once
    the retry budget is exhausted, raises EmbeddingUnavailableError instead of
    the raw provider exception so callers can distinguish "provider is
    rate-limiting us" from other failures (e.g. bad credentials).
    """
    from news_dashboard.ai_client import SafeAIObservation, get_chat_client, trace_params

    api_key, base_url, model = _embeddings_ai_config()
    client_kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    if timeout_seconds is not None:
        client_kwargs["timeout_seconds"] = timeout_seconds
    if not trace_content:
        client_kwargs["enable_tracing"] = False
        client_kwargs["safe_observation"] = SafeAIObservation(
            operation=operation,
            as_type="embedding",
            model=model,
        )
    client = get_chat_client(**client_kwargs)

    attempt = 0
    while True:
        try:
            response = client.embeddings.create(
                model=model,
                input=text,
                **(
                    trace_params("article-embedding", tags=["embedding"], user_id="system")
                    if trace_content
                    else {}
                ),
            )
            return list(response.data[0].embedding)
        except Exception as exc:
            if not _is_retryable_embedding_error(exc):
                raise
            attempt += 1
            if attempt >= EMBED_MAX_ATTEMPTS:
                message = f"embedding provider rate-limited after {attempt} attempts: {exc}"
                raise EmbeddingUnavailableError(message) from exc
            wait = EMBED_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "embedding request rate-limited (attempt %d/%d); retrying in %.1fs",
                attempt,
                EMBED_MAX_ATTEMPTS,
                wait,
            )
            time.sleep(wait)


def _answer(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    timeout_seconds: float | None = None,
    trace_content: bool = True,
) -> str:
    """Generate an answer with a vanilla LangChain prompt/model/parser pipeline."""
    from langchain_core.messages import SystemMessage
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    from news_dashboard.ai_client import (
        SafeAIObservation,
        free_llm_config,
        get_chat_client,
        get_chat_model,
    )

    api_key, base_url = free_llm_config()
    if not api_key:
        _require_env("FREE_LLM_API_KEY", "use Ask AI")
    model_name = os.getenv("OPENAI_ANSWER_MODEL", DEFAULT_ANSWER_MODEL)
    if not trace_content:
        client = get_chat_client(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            enable_tracing=False,
            safe_observation=SafeAIObservation(
                operation="answer-generation",
                as_type="generation",
                model=model_name,
                model_parameters={"max_tokens": max_tokens} if max_tokens is not None else {},
            ),
        )
        request: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        response = cast("ChatCompletion", client.chat.completions.create(**request))
        content = response.choices[0].message.content
        if not isinstance(content, str):
            message = "AI response must contain string content"
            raise TypeError(message)
        return content
    model_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model_name,
    }
    if max_tokens is not None:
        model_kwargs["max_tokens"] = max_tokens
    if timeout_seconds is not None:
        model_kwargs["timeout_seconds"] = timeout_seconds
    model = get_chat_model(
        **model_kwargs,
    )
    chain = (
        ChatPromptTemplate.from_messages(
            [SystemMessage(content=system_prompt), ("human", "{user_prompt}")]
        )
        | model
        | StrOutputParser()
    )
    return chain.invoke({"user_prompt": user_prompt})


def graph_context_for_articles(article_ids: list[int]) -> dict[str, Any] | None:
    """Fetch optional Neo4j context for article IDs already authorized by Ask retrieval."""
    from news_dashboard.graph_store import GraphUnavailableError, graph_store_from_env

    try:
        graph_store = graph_store_from_env()
    except GraphUnavailableError:
        logger.exception("Neo4j graph store is configured but unavailable")
        return None
    if graph_store is None:
        return None
    try:
        return graph_store.ask_context(article_ids=article_ids)
    except Exception:
        logger.exception("Failed to load Ask AI graph context")
        return None
    finally:
        close = getattr(graph_store, "close", None)
        if callable(close):
            close()


def _format_graph_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    entities = context.get("entities")
    relationships = context.get("relationships")
    if not isinstance(entities, list) or not isinstance(relationships, list):
        return ""

    entity_names = {
        str(entity.get("id")): str(entity.get("name"))
        for entity in entities
        if isinstance(entity, dict) and entity.get("id") and entity.get("name")
    }
    lines: list[str] = []
    for relationship in relationships[:8]:
        if not isinstance(relationship, dict):
            continue
        source_id = str(relationship.get("source") or "")
        target_id = str(relationship.get("target") or "")
        if not source_id or not target_id:
            continue
        label = str(
            relationship.get("label")
            or str(relationship.get("relationship_type") or "").replace("_", " ")
        ).strip()
        article_ids = relationship.get("article_ids")
        if not isinstance(article_ids, list):
            article_ids = []
        refs = ", ".join(str(int(article_id)) for article_id in article_ids if article_id)
        source = str(relationship.get("source_name") or entity_names.get(source_id, source_id))
        target = str(relationship.get("target_name") or entity_names.get(target_id, target_id))
        suffix = f" (articles [{refs}])" if refs else ""
        lines.append(f"- {source} {label} {target}{suffix}")
    if not lines:
        return ""
    return "Knowledge graph:\n" + "\n".join(lines)


def _answer_with_policy(
    system_prompt: str,
    user_prompt: str,
    execution_policy: AskExecutionPolicy | None,
) -> str:
    if execution_policy is None:
        return _answer(system_prompt, user_prompt)
    return _answer(
        system_prompt,
        user_prompt,
        max_tokens=execution_policy.answer_max_tokens,
        timeout_seconds=execution_policy.provider_timeout_seconds,
        trace_content=execution_policy.trace_content,
    )


def _generate_answer(
    *,
    query: str,
    include_all: bool,
    user_id: int | None,
    session_id: str | None,
    prompt: Any,
    user_prompt: str,
    execution_policy: AskExecutionPolicy | None,
) -> tuple[str, str | None]:
    from news_dashboard.ai_client import _client, langfuse_enabled

    if not langfuse_enabled():
        return _answer_with_policy(prompt.text, user_prompt, execution_policy), None

    from langfuse import propagate_attributes

    trace_content = execution_policy is None or execution_policy.trace_content
    retrieval_limit = execution_policy.retrieval_limit if execution_policy is not None else TOP_K
    corpus = "all_visible" if include_all else "saved_and_read"
    trace_input = (
        {"query": query, "include_all": include_all}
        if trace_content
        else {"question_chars": len(query), "corpus": corpus, "retrieval_limit": retrieval_limit}
    )
    client = _client()
    if not trace_content:
        failure: BaseException | None = None
        failure_traceback = None
        answer: str | None = None
        trace_id: str | None = None
        with client.start_as_current_observation(
            name="answer-pipeline",
            as_type="chain",
            input=trace_input,
            prompt=prompt.langfuse_prompt,
        ) as root:
            try:
                answer = _answer_with_policy(prompt.text, user_prompt, execution_policy)
            except BaseException as exc:
                failure = exc
                failure_traceback = exc.__traceback__
                root.update(
                    output={"status": "error"},
                    level="ERROR",
                    status_message="answer generation failed",
                )
            else:
                root.update(output={"answer_chars": len(answer), "status": "ok"})
                trace_id = client.get_current_trace_id()
        if failure is not None:
            raise failure.with_traceback(failure_traceback)
        if answer is None:
            message = "Answer generation returned no result"
            raise RuntimeError(message)
        return answer, trace_id

    attribute_kwargs: dict[str, Any] = {
        "user_id": str(user_id) if user_id is not None else None,
        "session_id": session_id,
        "tags": ["ask-ai"],
        "prompt": prompt.langfuse_prompt,
    }
    with (
        propagate_attributes(**attribute_kwargs),
        client.start_as_current_observation(
            name="ask-ai", as_type="chain", input=trace_input
        ) as root,
    ):
        answer = _answer_with_policy(prompt.text, user_prompt, execution_policy)
        root.update(
            output=answer if trace_content else {"answer_chars": len(answer), "status": "ok"}
        )
        return answer, client.get_current_trace_id()


# ── Cosine similarity ──────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Public helper: cosine similarity between two embedding vectors."""
    return _cosine(a, b)


# ── Lazy embedding of saved/read articles ─────────────────────────────────


def ensure_article_embedded(article_id: int, db_path: Any = None) -> None:
    """Generate and persist an embedding for *article_id* if not already set."""
    from news_dashboard.db import connect, init_db

    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, title, summary, reason, tags, embedding_vec FROM articles WHERE id=%s",
            (article_id,),
        ).fetchone()
        if row is None or row["embedding_vec"] is not None:
            return  # already embedded or gone
        text = embedding_text(row["title"], row["summary"], row["reason"], row["tags"])
        if not text:
            return
        vector = _embed(text)
        conn.execute(
            "UPDATE articles SET embedding_vec=%s::vector WHERE id=%s",
            (vector_literal(vector), article_id),
        )


def embed_all_eligible(
    db_path: Any = None,
    *,
    include_all: bool = False,
    user_id: int | None = None,
    max_articles: int | None = None,
    provider_timeout_seconds: float | None = None,
    trace_content: bool = True,
) -> int:
    """Embed eligible articles that don't have an embedding yet.

    Called lazily on the first /api/ask request to backfill existing articles.
    When user_id is provided, only backfills articles visible to that user.
    A single article's embedding failure (e.g. exhausted rate-limit retries)
    is logged and skipped rather than aborting the rest of the backfill.
    Returns the number of articles newly embedded.
    """
    from news_dashboard.db import connect, init_db

    init_db(db_path)
    with connect(db_path) as conn:
        if user_id is not None:
            if include_all:
                query = """
                    SELECT a.id, a.title, a.summary, a.reason, a.tags
                    FROM articles a
                    LEFT JOIN sources src ON src.slug = a.source_slug
                    LEFT JOIN user_sources us_src
                        ON us_src.user_id = %s AND us_src.source_slug = a.source_slug
                    LEFT JOIN user_article_state uas
                        ON uas.article_id = a.id AND uas.user_id = %s
                    WHERE COALESCE(uas.state, 'today') != 'archived'
                      AND a.embedding_vec IS NULL
                      AND (
                        (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
                        OR src.owner_user_id = %s
                      )
                """
            else:
                query = """
                    SELECT a.id, a.title, a.summary, a.reason, a.tags
                    FROM articles a
                    LEFT JOIN sources src ON src.slug = a.source_slug
                    LEFT JOIN user_sources us_src
                        ON us_src.user_id = %s AND us_src.source_slug = a.source_slug
                    JOIN user_article_state uas
                        ON uas.article_id = a.id AND uas.user_id = %s
                    WHERE (uas.state = 'done' OR uas.starred = TRUE)
                      AND a.embedding_vec IS NULL
                      AND (
                        (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
                        OR src.owner_user_id = %s
                      )
                """
            query += " ORDER BY a.id"
            params: tuple[Any, ...] = (user_id, user_id, user_id)
            if max_articles is not None:
                query += " LIMIT %s"
                params += (max_articles,)
            rows = conn.execute(query, params).fetchall()
        else:
            status_filter = "status != 'archived'" if include_all else "status IN ('saved', 'read')"
            query = (
                "SELECT id, title, summary, reason, tags FROM articles "
                f"WHERE {status_filter} AND embedding_vec IS NULL ORDER BY id"
            )
            params = ()
            if max_articles is not None:
                query += " LIMIT %s"
                params = (max_articles,)
            rows = conn.execute(query, params).fetchall()

    count = 0
    for row in rows:
        text = embedding_text(row["title"], row["summary"], row["reason"], row["tags"])
        if not text:
            continue
        try:
            vector = (
                _embed(
                    text,
                    timeout_seconds=provider_timeout_seconds,
                    trace_content=trace_content,
                    operation="article-backfill",
                )
                if provider_timeout_seconds is not None
                else (
                    _embed(text)
                    if trace_content
                    else _embed(text, trace_content=False, operation="article-backfill")
                )
            )
            from news_dashboard.db import connect as _connect

            with _connect(db_path) as conn:
                conn.execute(
                    "UPDATE articles SET embedding_vec=%s::vector WHERE id=%s",
                    (vector_literal(vector), row["id"]),
                )
            count += 1
        except Exception:
            if trace_content:
                logger.warning(
                    "failed to embed article %s during backfill; skipping",
                    row["id"],
                    exc_info=True,
                )
            else:
                logger.warning("failed to embed article during private backfill; skipping")
    return count


# ── Main Q&A entry-point ───────────────────────────────────────────────────


def _ask_impl(
    query: str,
    db_path: Any = None,
    *,
    include_all: bool = False,
    user_id: int | None = None,
    session_id: str | None = None,
    execution_policy: AskExecutionPolicy | None = None,
) -> dict[str, Any]:
    """Answer *query* using RAG over saved/read articles.

    Args:
        include_all: When True, includes all non-archived articles instead of
            only Starred (saved) + Done (read) articles.
        user_id: Authenticated user; scopes retrieval to articles visible to this
            user via user_article_state and user_sources. Also attached to Langfuse trace.

    Returns:
        {
          "answer": str,
          "sources": [{"id": int, "title": str, "url": str}, ...]
        }
    """
    from news_dashboard.db import connect, init_db

    # 1. Backfill embeddings for any eligible articles not yet embedded
    backfill_limit = execution_policy.backfill_limit if execution_policy is not None else None
    provider_timeout = (
        execution_policy.provider_timeout_seconds if execution_policy is not None else None
    )
    retrieval_limit = execution_policy.retrieval_limit if execution_policy is not None else TOP_K
    if execution_policy is None:
        embed_all_eligible(db_path, include_all=include_all, user_id=user_id)
    else:
        embed_all_eligible(
            db_path,
            include_all=include_all,
            user_id=user_id,
            max_articles=backfill_limit,
            provider_timeout_seconds=provider_timeout,
            trace_content=execution_policy.trace_content,
        )

    # 2. Embed the user's question, then let Postgres rank + return the top-k
    #    nearest articles in one query via the pgvector `<=>` cosine-distance
    #    operator (using the embedding_vec HNSW index), with a COUNT(*) in the
    #    same round trip for the MIN_ARTICLES eligibility check.
    query_embedding = (
        _embed(query)
        if execution_policy is None
        else _embed(
            query,
            timeout_seconds=provider_timeout,
            trace_content=execution_policy.trace_content,
        )
    )
    query_vec = vector_literal(query_embedding)
    init_db(db_path)
    with connect(db_path) as conn:
        if user_id is not None:
            if include_all:
                sql = """
                    SELECT a.id, a.title, a.url, a.summary,
                      COUNT(*) OVER () AS eligible_count
                    FROM articles a
                    LEFT JOIN sources src ON src.slug = a.source_slug
                    LEFT JOIN user_sources us_src
                        ON us_src.user_id = %(user_id)s AND us_src.source_slug = a.source_slug
                    LEFT JOIN user_article_state uas
                        ON uas.article_id = a.id AND uas.user_id = %(user_id)s
                    WHERE COALESCE(uas.state, 'today') != 'archived'
                      AND a.embedding_vec IS NOT NULL
                      AND (
                        (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
                        OR src.owner_user_id = %(user_id)s
                      )
                    ORDER BY a.embedding_vec <=> %(query_vec)s::vector
                    LIMIT %(top_k)s
                """
            else:
                sql = """
                    SELECT a.id, a.title, a.url, a.summary,
                      COUNT(*) OVER () AS eligible_count
                    FROM articles a
                    LEFT JOIN sources src ON src.slug = a.source_slug
                    LEFT JOIN user_sources us_src
                        ON us_src.user_id = %(user_id)s AND us_src.source_slug = a.source_slug
                    JOIN user_article_state uas
                        ON uas.article_id = a.id AND uas.user_id = %(user_id)s
                    WHERE (uas.state = 'done' OR uas.starred = TRUE)
                      AND a.embedding_vec IS NOT NULL
                      AND (
                        (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
                        OR src.owner_user_id = %(user_id)s
                      )
                    ORDER BY a.embedding_vec <=> %(query_vec)s::vector
                    LIMIT %(top_k)s
                """
            rows = conn.execute(
                sql, {"user_id": user_id, "query_vec": query_vec, "top_k": retrieval_limit}
            ).fetchall()
        else:
            status_filter = "status != 'archived'" if include_all else "status IN ('saved', 'read')"
            rows = conn.execute(
                "SELECT id, title, url, summary, COUNT(*) OVER () AS eligible_count "
                f"FROM articles WHERE {status_filter} AND embedding_vec IS NOT NULL "
                "ORDER BY embedding_vec <=> %(query_vec)s::vector LIMIT %(top_k)s",
                {"query_vec": query_vec, "top_k": retrieval_limit},
            ).fetchall()

    eligible_count = rows[0]["eligible_count"] if rows else 0
    if eligible_count < MIN_ARTICLES:
        return {
            "answer": (
                f"Not enough articles yet — I need at least {MIN_ARTICLES} saved or read "
                f"articles to answer questions. You currently have {eligible_count}."
            ),
            "sources": [],
            "trace_id": None,
        }

    # 3. Build context for the prompt (rows already top-k, nearest first)
    context_blocks = []
    for i, row in enumerate(rows, 1):
        context_blocks.append(
            f"[{i}] Title: {row['title']}\nURL: {row['url']}\nSummary: {row['summary']}"
        )
    context_text = "\n\n".join(context_blocks)
    graph_context = graph_context_for_articles([int(row["id"]) for row in rows])
    graph_context_text = _format_graph_context(graph_context)

    from news_dashboard.ai_client import get_prompt
    from news_dashboard.ai_memory.service import format_memories_for_prompt

    prompt = get_prompt("ask-system", fallback=ASK_SYSTEM_PROMPT)
    memory_text = format_memories_for_prompt(user_id)
    memory_block = f"{memory_text}\n\n" if memory_text else ""
    graph_block = f"\n\n{graph_context_text}" if graph_context_text else ""
    user_prompt = f"{memory_block}Articles:\n\n{context_text}{graph_block}\n\nQuestion: {query}"

    answer_text, trace_id = _generate_answer(
        query=query,
        include_all=include_all,
        user_id=user_id,
        session_id=session_id,
        prompt=prompt,
        user_prompt=user_prompt,
        execution_policy=execution_policy,
    )

    # 7. Return answer + source list (top-k order)
    sources = [{"id": row["id"], "title": row["title"], "url": row["url"]} for row in rows]
    result: dict[str, Any] = {
        "answer": answer_text,
        "sources": sources,
        "trace_id": trace_id,
    }
    if graph_context is not None:
        result["graph_context"] = graph_context
    return result


def ask(
    query: str,
    db_path: Any = None,
    *,
    include_all: bool = False,
    user_id: int | None = None,
    session_id: str | None = None,
    execution_policy: AskExecutionPolicy | None = None,
) -> dict[str, Any]:
    """Answer a question over the caller's authorized article corpus."""
    from news_dashboard.ai_client import langfuse_enabled

    if execution_policy is None or execution_policy.trace_content or not langfuse_enabled():
        return _ask_impl(
            query,
            db_path,
            include_all=include_all,
            user_id=user_id,
            session_id=session_id,
            execution_policy=execution_policy,
        )

    from langfuse import propagate_attributes

    from news_dashboard.ai_client import _client

    corpus = "all_visible" if include_all else "saved_and_read"
    failure: BaseException | None = None
    failure_traceback = None
    result: dict[str, Any] | None = None
    with (
        propagate_attributes(
            user_id=str(user_id) if user_id is not None else None,
            tags=["ask-ai", "mcp"],
            metadata={"surface": execution_policy.trace_surface, "corpus": corpus},
            trace_name="ask-news",
        ),
        _client().start_as_current_observation(
            name="ask-ai",
            as_type="chain",
            input={
                "question_chars": len(query),
                "corpus": corpus,
                "retrieval_limit": execution_policy.retrieval_limit,
            },
        ) as root,
    ):
        try:
            result = _ask_impl(
                query,
                db_path,
                include_all=include_all,
                user_id=user_id,
                session_id=session_id,
                execution_policy=execution_policy,
            )
        except BaseException as exc:
            failure = exc
            failure_traceback = exc.__traceback__
            root.update(
                output={"status": "error"},
                level="ERROR",
                status_message="ask failed",
            )
        else:
            if result.get("trace_id") is None:
                result["trace_id"] = _client().get_current_trace_id()
            root.update(
                output={
                    "answer_chars": len(str(result.get("answer", ""))),
                    "source_count": len(result.get("sources", [])),
                    "status": "ok",
                }
            )
    if failure is not None:
        raise failure.with_traceback(failure_traceback)
    if result is None:
        message = "Ask returned no result"
        raise RuntimeError(message)
    return result
