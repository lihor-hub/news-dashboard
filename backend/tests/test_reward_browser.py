"""Grouped feedback through the existing real-cookie/PostgreSQL/built-SPA harness."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import uvicorn

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.main import SPAStaticFiles, app
from news_dashboard.reading_progress import credits, daily  # noqa: A004

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1", reason="Opt-in real grouped reward browser"
    ),
]


def test_grouped_reward_browser(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-reward-test", "test-password-not-production")
    now = datetime.now(timezone.utc)
    with connect() as conn:
        daily.lock_account(conn, user["id"])
        conn.execute(
            "UPDATE users SET progress_timezone='UTC', reward_animations_enabled=FALSE WHERE id=%s",
            (user["id"],),
        )
        conn.execute(
            """INSERT INTO user_daily_visit_state(user_id,last_credited_date,
            current_streak_days,best_streak_days,next_credit_at) VALUES (%s,%s,2,2,%s)""",
            (user["id"], now.date() - timedelta(days=1), now - timedelta(hours=1)),
        )
        for title, count in (("Python", 9), ("Ruby", 3), ("CSS", 2), ("General news", 35)):
            for index in range(count):
                credits.credit_read(
                    conn,
                    user["id"],
                    url=f"https://fixture.test/{title}/{index}",
                    title=title,
                    method="import",
                    origin="import",
                )
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('reward-live','Reward live','https://example.test/feed','tech','rss_feed')"
        )
        titles = ("Python CSS reward article", "Cybersecurity reward article")
        for index, title in enumerate(titles):
            conn.execute(
                """INSERT INTO articles(url,canonical_url,title,source_slug,source_name,
                category,kind,body,body_status) VALUES (%s,%s,%s,'reward-live','Reward live',
                'tech','rss_feed',
                'A real loaded article body for grouped reward acceptance.','ok')""",
                (
                    f"https://example.test/reward/{index}",
                    f"https://example.test/reward/{index}",
                    title,
                ),
            )
    root = Path(__file__).resolve().parents[2]
    dist = root / "frontend" / "dist"
    assert (dist / "index.html").exists(), "Build SPA first"
    if not any(getattr(route, "name", None) == "static" for route in app.routes):
        app.mount("/", SPAStaticFiles(directory=dist, html=True), name="static")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            lifespan="off",
            log_level="warning",
            loop="asyncio",
            http="h11",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert thread.is_alive()
        assert time.monotonic() < deadline
        time.sleep(0.05)
    try:
        node = shutil.which("node")
        assert node
        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [node, "e2e/reward-progress-live.mjs"],
            cwd=root,
            env={**os.environ, "LIVE_PROGRESS_URL": f"http://127.0.0.1:{port}"},
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
        if storage := os.getenv("BB_THREAD_STORAGE"):
            (Path(storage) / "reward-browser-node.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "REWARD_PROGRESS_LIVE_OK" in result.stdout
        with connect() as conn:
            rows = conn.execute(
                """SELECT achievement_key,reward_group_id FROM user_achievements
                   WHERE user_id=%s AND achievement_key IN
                   ('articles_read_50','topic_python_10','breadth_3')""",
                (user["id"],),
            ).fetchall()
            assert len(rows) == 3
            assert len({row["reward_group_id"] for row in rows}) == 1
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM user_reward_groups "
                    "WHERE user_id=%s AND claimed_at IS NULL",
                    (user["id"],),
                ).fetchone()["n"]
                == 0
            )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
