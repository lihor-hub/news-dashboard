"""AI Q&A feature: embedding generation and retrieval-augmented answering.

Embedding model : text-embedding-3-small (OpenAI)
Answer model    : claude-haiku-4-5 (Anthropic)
Storage         : articles.embedding BYTEA (serialized float32 numpy array)
Retrieval       : pure-Python cosine similarity
"""
from __future__ import annotations

import struct
from typing import Any

MIN_ARTICLES = 5   # refuse to answer if fewer than this many articles are embedded
TOP_K = 8          # articles to include as context


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

    client = OpenAI()  # reads OPENAI_API_KEY from env
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


# ── Cosine similarity ──────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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


def embed_all_eligible(db_path: Any = None) -> int:
    """Embed all saved/read articles that don't have an embedding yet.

    Called lazily on the first /api/ask request to backfill existing articles.
    Returns the number of articles newly embedded.
    """
    from .db import connect, init_db

    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, summary FROM articles "
            "WHERE status IN ('saved', 'read') AND embedding IS NULL",
        ).fetchall()

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

def ask(query: str, db_path: Any = None) -> dict:
    """Answer *query* using RAG over saved/read articles.

    Returns:
        {
          "answer": str,
          "sources": [{"id": int, "title": str, "url": str}, ...]
        }

    Raises:
        ValueError if fewer than MIN_ARTICLES are embedded.
    """
    from .db import connect, init_db

    # 1. Backfill embeddings for any eligible articles not yet embedded
    embed_all_eligible(db_path)

    # 2. Load embedded articles
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, url, summary, embedding FROM articles "
            "WHERE status IN ('saved', 'read') AND embedding IS NOT NULL",
        ).fetchall()

    if len(rows) < MIN_ARTICLES:
        return {
            "answer": (
                f"Not enough articles yet — I need at least {MIN_ARTICLES} saved or read articles "
                f"to answer questions. You currently have {len(rows)}."
            ),
            "sources": [],
        }

    # 3. Embed the query
    query_vec = _embed(query)

    # 4. Rank by cosine similarity and pick top-k
    scored = [
        (row, _cosine(query_vec, _unpack(bytes(row["embedding"]))))
        for row in rows
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:TOP_K]

    # 5. Build context for the prompt
    context_blocks = []
    for i, (row, score) in enumerate(top, 1):
        context_blocks.append(
            f"[{i}] Title: {row['title']}\nURL: {row['url']}\nSummary: {row['summary']}"
        )
    context_text = "\n\n".join(context_blocks)

    system_prompt = (
        "You are a helpful assistant that answers questions based on the user's curated news articles. "
        "Use only the provided article excerpts to answer. "
        "Cite articles by their bracketed number, e.g. [1], [2]. "
        "If the articles do not contain enough information, say so clearly. "
        "Be concise (2-4 sentences unless a longer answer is clearly needed)."
    )
    user_prompt = (
        f"Articles:\n\n{context_text}\n\n"
        f"Question: {query}"
    )

    # 6. Call claude-haiku-4-5 for the answer
    import anthropic  # lazy import

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    answer_text = message.content[0].text if message.content else ""

    # 7. Return answer + deduplicated source list (top-k order)
    sources = [
        {"id": row["id"], "title": row["title"], "url": row["url"]}
        for row, _ in top
    ]
    return {"answer": answer_text, "sources": sources}
