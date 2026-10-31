"""Real existing-account history introduction, never operational user data."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.main import SPAStaticFiles, app
from news_dashboard.reading_progress import history

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1", reason="Opt-in real historical browser"
    ),
]


@pytest.mark.parametrize("popup", [True, False])
def test_history_browser(pg_clean: str, monkeypatch: pytest.MonkeyPatch, popup: bool) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-history-test", "test-password-not-production")
    with connect() as conn:
        conn.execute(
            "UPDATE users SET progress_timezone='UTC',daily_welcome_enabled=%s WHERE id=%s",
            (popup, user["id"]),
        )
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('history-live','History','https://fixture.test/feed','tech','rss_feed')"
        )
        aid = conn.execute("""INSERT INTO articles(url,canonical_url,title,
            source_slug,source_name,category,kind)
            VALUES ('https://fixture.test/history','https://fixture.test/history','Python history',
            'history-live','History','tech','rss_feed') RETURNING id""").fetchone()["id"]
        conn.execute(
            """INSERT INTO user_article_state(user_id,article_id,state,done_at)
               VALUES (%s,%s,'archived','2001-01-01')""",
            (user["id"], aid),
        )
        conn.execute(
            """INSERT INTO user_achievements(user_id,achievement_key,unlocked_at)
               VALUES (%s,'unknown_legacy_history','2000-01-01')""",
            (user["id"],),
        )
        history.prepare(conn, user["id"], protection_ref="fresh isolated browser test fixture")
        assert history.batch(conn, user["id"])["status"] == "complete"
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
            [node, "e2e/history-progress-live.mjs"],
            cwd=root,
            env={
                **os.environ,
                "LIVE_PROGRESS_URL": f"http://127.0.0.1:{port}",
                "HISTORY_POPUP": str(popup),
            },
            capture_output=True,
            text=True,
            timeout=150,
            check=False,
        )
        if storage := os.getenv("BB_THREAD_STORAGE"):
            (Path(storage) / f"history-browser-{popup}-node.log").write_text(
                result.stdout + result.stderr
            )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "HISTORY_PROGRESS_LIVE_OK" in result.stdout
        with connect() as conn:
            group = conn.execute(
                "SELECT * FROM user_reward_groups WHERE user_id=%s", (user["id"],)
            ).fetchone()
            assert group["kind"] == "historical_intro"
            assert group["claimed_at"] is not None
            assert group["acknowledged_at"] is not None
            assert (
                conn.execute(
                    "SELECT COUNT(*) AS n FROM user_read_credits WHERE user_id=%s", (user["id"],)
                ).fetchone()["n"]
                == 1
            )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
