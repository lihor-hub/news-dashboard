"""AI Q&A feature: embedding generation and retrieval-augmented answering.

Embedding model : text-embedding-3-small (OpenAI)
Answer model    : gpt-4o-mini (OpenAI)
Storage         : articles.embedding BLOB (serialized float32 numpy array)
Retrieval       : pure-Python cosine similarity over stored vectors
"""

from __future__ import annotations

import os
import struct
from typing import Any

MIN_ARTICLES = 5  # refuse to answer if fewer than this many articles are embedded
TOP_K = 8  # articles to include as context
DEFAULT_ANSWER_MODEL = "gpt-4o-mini"


class MissingAICredentialsError(RuntimeError):
    """Raised when Ask AI is used without the required provider credentials."""


def _require_env(name: str, purpose: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    message = f"Ask AI requires {name} to {purpose}. Set {name} in the app environment."
    raise MissingAICredentialsError(message)


# ── Embedding serialisation ────────────────────────────────────────────────


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


# ── OpenAI embedding ───────────────────────────────────────────────────────


def _embed(text: str) -> list[float]:
    """Embed *text* with text-embedding-3-small via the OpenAI SDK."""
    from openai import OpenAI  # lazy import — optional dep at import time

    client = OpenAI(api_key=_require_env("OPENAI_API_KEY", "generate article embeddings"))
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return list(response.data[0].embedding)


def _answer(system_prompt: str, user_prompt: str) -> str:
    """Generate an answer with OpenAI using the same key as embeddings."""
    from openai import OpenAI  # lazy import — optional dep at import time

    client = OpenAI(api_key=_require_env("OPENAI_API_KEY", "use Ask AI"))
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_ANSWER_MODEL", DEFAULT_ANSWER_MODEL),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


# ── Cosine similarity ──────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


# ── Lazy embedding of saved/read articles ─────────────────────────────────


def ensure_article_embedded(article_id: int, db_path: Any = None) -> None:
    """Generate and persist an embedding for *article_id* if not already set."""
    from .db import connect, init_db

    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, title, summary, embedding FROM articles WHERE id=%s",
            (article_id,),
        ).fetchone()
        if row is None or row["embedding"] is not None:
            return  # already embedded or gone
        text = f"{row['title']} {row['summary']}".strip()
        if not text:
            return
        vector = _embed(text)
        blob = _pack(vector)
        conn.execute(
            "UPDATE articles SET embedding=%s WHERE id=%s",
            (blob, article_id),
        )


def embed_all_eligible(db_path: Any = None, *, include_all: bool = False) -> int:
    """Embed eligible articles that don't have an embedding yet.

    Called lazily on the first /api/ask request to backfill existing articles.
    Returns the number of articles newly embedded.
    """
    from .db import connect, init_db

    status_filter = "status != 'archived'" if include_all else "status IN ('saved', 'read')"
    init_db(db_path)
    with connect(db_path) as conn:
        query = (
            f"SELECT id, title, summary FROM articles WHERE {status_filter} AND embedding IS NULL"
        )
        rows = conn.execute(query).fetchall()

    count = 0
    for row in rows:
        text = f"{row['title']} {row['summary']}".strip()
        if not text:
            continue
        vector = _embed(text)
        blob = _pack(vector)
        from .db import connect as _connect

        with _connect(db_path) as conn:
            conn.execute(
                "UPDATE articles SET embedding=%s WHERE id=%s",
                (blob, row["id"]),
            )
        count += 1
    return count


# ── Main Q&A entry-point ───────────────────────────────────────────────────


def ask(query: str, db_path: Any = None, *, include_all: bool = False) -> dict[str, Any]:
    """Answer *query* using RAG over saved/read articles.

    Args:
        include_all: When True, includes all non-archived articles instead of
            only Starred (saved) + Done (read) articles.

    Returns:
        {
          "answer": str,
          "sources": [{"id": int, "title": str, "url": str}, ...]
        }
    """
    from .db import connect, init_db

    # 1. Backfill embeddings for any eligible articles not yet embedded
    embed_all_eligible(db_path, include_all=include_all)

    status_filter = "status != 'archived'" if include_all else "status IN ('saved', 'read')"

    # 2. Load embedded articles
    init_db(db_path)
    with connect(db_path) as conn:
        query = (
            "SELECT id, title, url, summary, embedding FROM articles "
            f"WHERE {status_filter} AND embedding IS NOT NULL"
        )
        rows = conn.execute(query).fetchall()

    if len(rows) < MIN_ARTICLES:
        return {
            "answer": (
                f"Not enough articles yet — I need at least {MIN_ARTICLES} saved or read "
                f"articles to answer questions. You currently have {len(rows)}."
            ),
            "sources": [],
        }

    # 3. Embed the query
    query_vec = _embed(query)

    # 4. Rank by cosine similarity and pick top-k
    scored = [(row, _cosine(query_vec, _unpack(bytes(row["embedding"])))) for row in rows]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:TOP_K]

    # 5. Build context for the prompt
    context_blocks = []
    for i, (row, _score) in enumerate(top, 1):
        context_blocks.append(
            f"[{i}] Title: {row['title']}\nURL: {row['url']}\nSummary: {row['summary']}"
        )
    context_text = "\n\n".join(context_blocks)

    system_prompt = (
        "You are a helpful assistant that answers questions based on the user's "
        "curated news articles. "
        "Use only the provided article excerpts to answer. "
        "Cite articles by their bracketed number, e.g. [1], [2]. "
        "If the articles do not contain enough information, say so clearly. "
        "Be concise (2-4 sentences unless a longer answer is clearly needed)."
    )
    user_prompt = f"Articles:\n\n{context_text}\n\nQuestion: {query}"

    # 6. Call OpenAI for the answer
    answer_text = _answer(system_prompt, user_prompt)

    # 7. Return answer + deduplicated source list (top-k order)
    sources = [{"id": row["id"], "title": row["title"], "url": row["url"]} for row, _ in top]
    return {"answer": answer_text, "sources": sources}
