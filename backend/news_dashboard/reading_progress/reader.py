"""Connected article-body evidence; deliberately independent of app activity."""

from __future__ import annotations

import math
import re
from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from news_dashboard.analytics import analytics_globally_enabled
from news_dashboard.article_visibility import get_visible_article_row
from news_dashboard.db import connect, init_db
from news_dashboard.reading_progress.credits import credit_article
from news_dashboard.reading_progress.daily import lock_account, utc_now


class ReaderEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    token: UUID | None = None
    sequence: int = Field(default=0, ge=0, le=100000)
    attentive_ms: int = Field(default=0, ge=0, le=15000, strict=True)
    end_ms: int = Field(default=0, ge=0, le=15000, strict=True)
    progress: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_interval(self) -> ReaderEvidence:
        if self.end_ms > self.attentive_ms:
            msg = "End visibility cannot exceed attentive time"
            raise ValueError(msg)
        if self.token is None and (
            self.sequence or self.attentive_ms or self.end_ms or self.progress
        ):
            msg = "Start carries no evidence"
            raise ValueError(msg)
        return self


def required_seconds(body: str) -> int:
    # Whitespace tokenization is not meaningful for unsegmented scripts.
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", body):
        return 120
    return max(30, min(120, math.ceil(len(body.split()) / 8)))


def body_version(body: str) -> str:
    return sha256(body.encode("utf-8")).hexdigest()


def accept_evidence(  # noqa: PLR0912 - one account-locked evidence transaction
    user_id: int, article_id: int, payload: ReaderEvidence, *, database_url: str | None = None
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        lock_account(conn, user_id)
        consent = conn.execute(
            "SELECT analytics_enabled FROM users WHERE id=%s", (user_id,)
        ).fetchone()
        if not analytics_globally_enabled() or not consent["analytics_enabled"]:
            conn.execute("DELETE FROM user_reader_evidence WHERE user_id=%s", (user_id,))
            # Commit invalidation before returning a disabled result, not an exception rollback.
            return {"available": False, "reason": "automatic_reading_disabled", "credited": False}
        now = utc_now()
        conn.execute(
            "DELETE FROM user_reader_evidence WHERE user_id=%s AND expires_at<=%s", (user_id, now)
        )
        article = get_visible_article_row(conn, article_id, user_id, for_update=True)
        if article is None:
            raise HTTPException(404, "Article not found")
        article = dict(article)
        body = article.get("body") or ""
        if article.get("body_status") != "ok" or not body.strip():
            raise HTTPException(409, "article_body_unavailable")
        version = body_version(body)
        original = article.get("original_body") or ""
        if payload.body_version != version:
            if original.strip() and payload.body_version == body_version(original):
                body = original
                version = payload.body_version
            else:
                raise HTTPException(409, "article_body_changed")
        required = required_seconds(body) * 1000
        row = conn.execute(
            "SELECT * FROM user_reader_evidence WHERE user_id=%s", (user_id,)
        ).fetchone()
        if payload.token is None:
            if row and row["lease_until"] > now:
                raise HTTPException(409, "reader_lease_busy")
            same_body = (
                row
                and row["article_id"] == article_id
                and row["body_version"] == version
                and not (row["last_result"] or {}).get("credited", False)
            )
            token = uuid4()
            conn.execute(
                """INSERT INTO user_reader_evidence(user_id,article_id,body_version,token,
                   lease_until,updated_at,expires_at,attentive_ms,end_ms)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(user_id) DO UPDATE SET article_id=EXCLUDED.article_id,
                     body_version=EXCLUDED.body_version,token=EXCLUDED.token,
                     lease_until=EXCLUDED.lease_until,updated_at=EXCLUDED.updated_at,
                     expires_at=EXCLUDED.expires_at,attentive_ms=EXCLUDED.attentive_ms,
                     end_ms=EXCLUDED.end_ms,sequence=0,last_payload=NULL,last_result=NULL""",
                (
                    user_id,
                    article_id,
                    version,
                    token,
                    now + timedelta(seconds=20),
                    now,
                    now + timedelta(hours=24),
                    row["attentive_ms"] if same_body else 0,
                    row["end_ms"] if same_body else 0,
                ),
            )
            return {
                "available": True,
                "token": str(token),
                "sequence": 0,
                "required_ms": required,
                "credited": False,
            }
        if (
            not row
            or row["token"] != payload.token
            or row["article_id"] != article_id
            or row["body_version"] != version
        ):
            raise HTTPException(409, "reader_lease_invalid")
        data = payload.model_dump(mode="json")
        if payload.sequence == row["sequence"] and row["last_payload"] == data:
            return dict(row["last_result"])
        if row["lease_until"] <= now or payload.sequence != row["sequence"] + 1:
            raise HTTPException(409, "reader_sequence_or_lease_expired")
        elapsed = max(0, min(15000, int((now - row["updated_at"]).total_seconds() * 1000)))
        accepted = min(payload.attentive_ms, elapsed)
        attentive = min(120000, row["attentive_ms"] + accepted)
        end = (
            min(2000, row["end_ms"] + min(payload.end_ms, accepted))
            if payload.progress >= 0.9
            else 0
        )
        qualified = attentive >= required and payload.progress >= 0.9 and end >= 2000
        result = {
            "available": True,
            "token": str(payload.token),
            "sequence": payload.sequence,
            "required_ms": required,
            "attentive_ms": attentive,
            "credited": qualified,
        }
        if qualified:
            result.update(credit_article(conn, user_id, article, method="automatic"))
            # Do not override an explicit archived/skipped state or navigate the reader.
            from news_dashboard.ingest.service import transition_article_state_on_connection

            state = conn.execute(
                "SELECT state FROM user_article_state WHERE user_id=%s AND article_id=%s",
                (user_id, article_id),
            ).fetchone()
            if not state or state["state"] in ("today", "later"):
                transition_article_state_on_connection(
                    conn, article_id, "done", user_id=user_id, method="automatic"
                )
        conn.execute(
            """UPDATE user_reader_evidence SET attentive_ms=%s,end_ms=%s,updated_at=%s,
               lease_until=%s,sequence=%s,last_payload=%s,last_result=%s WHERE user_id=%s""",
            (
                attentive,
                end,
                now,
                now + timedelta(seconds=20),
                payload.sequence,
                Jsonb(data),
                Jsonb(result),
                user_id,
            ),
        )
        return result
