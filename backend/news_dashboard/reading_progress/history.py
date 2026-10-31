"""Explicit historical-v1 tooling, never called by startup, GET or scheduler.

All mutations use the caller connection/transaction and shared account lock.
Retention protection is an externally authorized operational precondition, not
something a cursor, CLI flag or database row can establish.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, cast
from uuid import uuid4

from psycopg.types.json import Jsonb

from news_dashboard.db import connect
from news_dashboard.reading_progress.credits import credit_article
from news_dashboard.reading_progress.daily import lock_account, utc_now

POLICY = "historical-v1"
BATCH_SIZE = 200
SOURCE_KEY = "historical:v1"


def snapshot(conn: Any, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM user_historical_credit_state WHERE user_id=%s", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in dict(row).items()
        if key not in {"user_id", "protection_ref"}
    }


def prepare(conn: Any, user_id: int, *, protection_ref: str) -> dict[str, Any]:
    """Capture a server-owned horizon AFTER externally approved pause/drain.

    Never extend an existing horizon on retry. New old-ID imports must use the
    synchronous import credit hook, not rely on a future scan.
    """
    if not isinstance(protection_ref, str) or not 1 <= len(protection_ref.strip()) <= 200:
        msg = "A bounded external retention-protection reference is required"
        raise ValueError(msg)
    lock_account(conn, user_id)
    conn.execute(
        """INSERT INTO user_historical_credit_state
           (user_id,policy_version,cutoff_at,protection_ref,upper_article_id,preserved_rewards)
           SELECT %s,%s,%s,%s,
             COALESCE((SELECT MAX(article_id) FROM user_article_state WHERE user_id=%s),0),
             (SELECT COUNT(*) FROM user_achievements WHERE user_id=%s)
           ON CONFLICT(user_id) DO NOTHING""",
        (user_id, POLICY, utc_now(), protection_ref.strip(), user_id, user_id),
    )
    return cast("dict[str, Any]", snapshot(conn, user_id))


def batch(conn: Any, user_id: int) -> dict[str, Any]:
    """At most 200 source rows; lock account before stable article/UAS rows.

    No SKIP LOCKED: skipping a locked row would create a permanent cursor hole.
    Commit is exclusively the caller's responsibility; exceptions roll back all
    credits, attribution, awards, cursor and completion/introduction together.
    """
    lock_account(conn, user_id)
    state = conn.execute(
        "SELECT * FROM user_historical_credit_state WHERE user_id=%s", (user_id,)
    ).fetchone()
    if state is None:
        msg = "Prepare a protected horizon before applying batches"
        raise ValueError(msg)
    if state["policy_version"] != POLICY:
        msg = "Unsupported historical policy"
        raise ValueError(msg)
    if state["status"] == "complete":
        return cast("dict[str, Any]", snapshot(conn, user_id))
    articles = conn.execute(
        """SELECT a.* FROM articles a JOIN user_article_state u ON u.article_id=a.id
           WHERE u.user_id=%s AND a.id>%s AND a.id<=%s
           ORDER BY a.id LIMIT %s FOR NO KEY UPDATE OF a""",
        (user_id, state["cursor_article_id"], state["upper_article_id"], BATCH_SIZE),
    ).fetchall()
    eligible = credited = 0
    for article in articles:
        evidence = conn.execute(
            """SELECT state,done_at FROM user_article_state
               WHERE user_id=%s AND article_id=%s FOR UPDATE""",
            (user_id, article["id"]),
        ).fetchone()
        if evidence and (evidence["done_at"] is not None or evidence["state"] == "done"):
            eligible += 1
            credited += int(
                credit_article(
                    conn, user_id, dict(article), method="historical", origin="historical"
                )["credit_inserted"]
            )
    complete = len(articles) < BATCH_SIZE
    cursor = state["upper_article_id"] if complete else articles[-1]["id"]
    now = utc_now()
    conn.execute(
        """UPDATE user_historical_credit_state SET cursor_article_id=%s,
           scanned=scanned+%s,eligible=eligible+%s,credited_reads=credited_reads+%s,
           status=%s,completed_at=%s WHERE user_id=%s""",
        (
            cursor,
            len(articles),
            eligible,
            credited,
            "complete" if complete else "running",
            now if complete else None,
            user_id,
        ),
    )
    result = cast("dict[str, Any]", snapshot(conn, user_id))
    if complete and (result["credited_reads"] or result["preserved_rewards"]):
        conn.execute(
            """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at,summary)
               VALUES (%s,%s,%s,'historical_intro',%s,%s)
               ON CONFLICT(user_id,source_key) DO NOTHING""",
            (
                uuid4(),
                user_id,
                SOURCE_KEY,
                now,
                Jsonb(
                    {"credited_reads": result["credited_reads"], "exact_earned_dates_known": False}
                ),
            ),
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "dry-run", "prepare", "batch"))
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--policy", choices=(POLICY,), required=True)
    parser.add_argument("--protection-ref")
    args = parser.parse_args()
    # No init_db: schema rollout and operational authorization are separate steps.
    with connect() as conn:
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET LOCAL statement_timeout='30s'")
        if args.action in {"status", "dry-run"}:
            conn.execute("SET TRANSACTION READ ONLY")
            result = snapshot(conn, args.user_id)
            if args.action == "dry-run":
                result = {
                    "state": result,
                    "retained_eligible_rows": conn.execute(
                        """SELECT COUNT(*) AS n FROM user_article_state WHERE user_id=%s
                       AND (done_at IS NOT NULL OR state='done')""",
                        (args.user_id,),
                    ).fetchone()["n"],
                    "notice": "Source rows, not deduplicated credits; not approval to apply.",
                }
        elif args.action == "prepare":
            result = prepare(conn, args.user_id, protection_ref=args.protection_ref)
        else:
            result = batch(conn, args.user_id)
    print(json.dumps(result))  # noqa: T201 - explicit operator output


if __name__ == "__main__":
    main()
