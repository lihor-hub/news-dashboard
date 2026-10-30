"""Real PostgreSQL/password-cookie/Chromium vertical read-to-badge acceptance."""

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
from news_dashboard.digest import _make_token
from news_dashboard.main import SPAStaticFiles, app

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1",
        reason="Opt-in built-SPA real-backed browser acceptance",
    ),
]


def test_read_to_badge_browser(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-read-test", "test-password-not-production")
    with connect() as conn:
        conn.execute("UPDATE users SET daily_welcome_enabled=FALSE WHERE id=%s", (user["id"],))
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('live-read','Live read','https://example.test/feed','tech','rss_feed')"
        )
        ids = [
            conn.execute(
                """INSERT INTO articles(url,canonical_url,title,source_slug,source_name,
                       category,kind,body,body_status)
                   VALUES (%s,%s,%s,'live-read','Live read','tech','rss_feed',
                       'Short real loaded body for attentive reading.','ok') RETURNING id""",
                (
                    f"https://example.test/read-{n}",
                    f"https://example.test/read-{n}",
                    f"Live read article {n}",
                ),
            ).fetchone()["id"]
            for n in (1, 2, 3)
        ]
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
            [node, "e2e/read-progress-live.mjs"],
            cwd=root,
            env={
                **os.environ,
                "LIVE_PROGRESS_URL": f"http://127.0.0.1:{port}",
                "LIVE_READ_MANUAL_ID": str(ids[0]),
                "LIVE_READ_AUTO_ID": str(ids[1]),
                "LIVE_READ_EMAIL_ID": str(ids[2]),
                "LIVE_READ_EMAIL_TOKEN": _make_token(user["id"], ids[2]),
            },
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if storage := os.getenv("BB_THREAD_STORAGE"):
            (Path(storage) / "read-browser-node.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "READ_PROGRESS_LIVE_OK" in result.stdout
        with connect() as conn:
            rows = conn.execute(
                "SELECT method FROM user_read_credits WHERE user_id=%s ORDER BY id", (user["id"],)
            ).fetchall()
            assert [row["method"] for row in rows] == ["manual", "automatic", "email"]
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM user_achievements WHERE user_id=%s "
                    "AND achievement_key='articles_read_1'",
                    (user["id"],),
                ).fetchone()["n"]
                == 1
            )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
