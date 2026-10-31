"""Real authenticated built-SPA time acceptance; test-owned clocks, no runtime bypass."""

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
from news_dashboard.reading_progress import activity

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1", reason="Opt-in real activity browser"
    ),
]


def test_real_active_time_browser(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-activity-test", "test-password-not-production")
    with connect() as conn:
        conn.execute("UPDATE users SET daily_welcome_enabled=FALSE WHERE id=%s", (user["id"],))
        activity.ensure_total(conn, user["id"])
        conn.execute(
            "UPDATE user_activity_totals SET total_ms=899000 WHERE user_id=%s", (user["id"],)
        )
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(activity, "utc_now", lambda: clock[0])
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
        with subprocess.Popen(  # noqa: S603 - fixed repository test script
            [node, "e2e/activity-progress-live.mjs"],
            cwd=root,
            env={**os.environ, "LIVE_PROGRESS_URL": f"http://127.0.0.1:{port}"},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            assert proc.stdout
            assert proc.stdin
            output = []
            watchdog = threading.Timer(120, proc.kill)
            watchdog.daemon = True
            watchdog.start()
            try:
                for line in proc.stdout:
                    output.append(line)
                    if line.startswith("ADVANCE_MS "):
                        clock[0] += timedelta(milliseconds=int(line.split()[1]))
                        proc.stdin.write("ADVANCED\n")
                        proc.stdin.flush()
                result = proc.wait(timeout=10)
            finally:
                watchdog.cancel()
        if storage := os.getenv("BB_THREAD_STORAGE"):
            (Path(storage) / "activity-browser-node.log").write_text("".join(output))
        assert result == 0, "".join(output)
        assert "ACTIVITY_PROGRESS_LIVE_OK" in "".join(output)
        with connect() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM user_achievements "
                    "WHERE user_id=%s AND achievement_key='active_time_900'",
                    (user["id"],),
                ).fetchone()["n"]
                == 1
            )
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM user_read_credits WHERE user_id=%s", (user["id"],)
                ).fetchone()["n"]
                == 0
            )
            total = conn.execute(
                "SELECT total_ms FROM user_activity_totals WHERE user_id=%s", (user["id"],)
            ).fetchone()["total_ms"]
            assert 900000 <= total < 1400000
    finally:
        server.should_exit = True
        thread.join(timeout=10)
