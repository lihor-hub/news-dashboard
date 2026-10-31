"""Opt-in real-cookie browser acceptance; build the frontend before running.

RUN_LIVE_PROGRESS_BROWSER=1 pytest -n 0 backend/tests/test_daily_visits_browser.py
No production clock endpoint: the test process owns its clock and loopback HTTP server.
"""

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
from news_dashboard.reading_progress import daily

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1",
        reason="Opt-in built-SPA real-backed browser acceptance",
    ),
]


def test_authenticated_return_visit_browser(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-progress-test", "test-password-not-production")
    with connect() as conn:
        conn.execute(
            """INSERT INTO sources(slug,name,url,category,kind)
               VALUES ('live-visit','Live test','https://example.test/feed','tech','rss_feed')"""
        )
        article_id = conn.execute(
            """INSERT INTO articles(
                url,canonical_url,title,source_slug,source_name,category,kind,state)
            VALUES ('https://example.test/visit','https://example.test/visit',
                    'Live daily visit article','live-visit','Live test','tech','rss_feed','today')
            RETURNING id"""
        ).fetchone()["id"]
        conn.execute(
            """UPDATE articles SET body='A locally stored browser test article.', body_status='ok'
               WHERE id=%s""",
            (article_id,),
        )
        sender = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('live-sender','x') RETURNING id"
        ).fetchone()["id"]
        share_id = conn.execute(
            """INSERT INTO article_shares(article_id,from_user_id,to_user_id)
               VALUES (%s,%s,%s) RETURNING id""",
            (article_id, sender, user["id"]),
        ).fetchone()["id"]
    clock = [datetime(2026, 1, 1, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(daily, "utc_now", lambda: clock[0])
    root = Path(__file__).resolve().parents[2]
    dist = root / "frontend" / "dist"
    assert (dist / "index.html").exists(), "Run npx vite build first"
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
        env = {
            **os.environ,
            "LIVE_PROGRESS_URL": f"http://127.0.0.1:{port}",
            "LIVE_PROGRESS_ARTICLE_ID": str(article_id),
            "LIVE_PROGRESS_SHARE_ID": str(share_id),
        }
        node = shutil.which("node")
        assert node is not None, "Node is required for the browser acceptance test"
        with subprocess.Popen(  # noqa: S603 - fixed repository test script, no user input
            [node, "e2e/daily-progress-live.mjs"],
            cwd=root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            assert proc.stdout is not None
            assert proc.stdin is not None
            output = []
            watchdog = threading.Timer(90, proc.kill)
            watchdog.daemon = True
            watchdog.start()
            try:
                for line in proc.stdout:
                    output.append(line)
                    if line.strip() == "ADVANCE_DAY":
                        clock[0] += timedelta(days=1)
                        proc.stdin.write("ADVANCED\n")
                        proc.stdin.flush()
                    elif line.strip() == "TRAVEL_START":
                        clock[0] = datetime(2026, 1, 6, 1, tzinfo=timezone.utc)
                        proc.stdin.write("ADVANCED\n")
                        proc.stdin.flush()
                    elif line.strip() == "TRAVEL_MIDNIGHT":
                        clock[0] = datetime(2026, 1, 6, 5, tzinfo=timezone.utc)
                        proc.stdin.write("ADVANCED\n")
                        proc.stdin.flush()
                result = proc.wait(timeout=10)
            finally:
                watchdog.cancel()
        assert result == 0, "".join(output)
        assert "LIVE_ACCEPTANCE_OK" in "".join(output)
        state = daily.get_daily_streak(user["id"])
        assert state["current_streak_days"] == 6
        assert state["best_streak_days"] == 6
    finally:
        server.should_exit = True
        thread.join(timeout=10)
